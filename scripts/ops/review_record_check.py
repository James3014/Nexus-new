#!/usr/bin/env python3
"""Review record present (#2290): the PR must carry its review evidence at its head.

Advisory. Stdlib only. Reads the PR, its file list, its issue comments and its
submitted reviews through the GitHub REST API and publishes a commit status on
the PR head. PR code is never checked out or executed, and PR-controlled text
(comment bodies, paths) is only pattern-matched; every printed line goes through
``_log_safe`` so it can never be read as a workflow command.

What counts as a record (parsed line by line and clause by clause, so prose
like "cannot ACCEPT until", "awaiting Codex ACCEPT" or a disposition table that
quotes the words never counts):

- A *verdict* is an uppercase ``ACCEPT``/``ACCEPTED``/``APPROVE``/``APPROVED``
  token in verdict position: after ``Verdict:``, bound as ``ACCEPT@<sha>``, after a
  colon or dash, after a round marker (``r3 ACCEPT``) or alone on its line. Nothing
  before it in the clause may be a wish, condition or negation, and nothing right
  after it may withdraw it. Table rows, block quotes, unticked checklist items,
  fenced code and pasted ``coord ready`` lines are skipped.
- The verdict is *bound to the head* when its clause names the head sha (full, or
  a hex prefix of at least ``MIN_PREFIX`` characters), else when its line does,
  else when the comment has a ``Head`` label naming it (``Head reviewed: <sha>``,
  ``final head <sha>``). A clause bound to another sha cannot be rebound.
- The *reviewer family* comes from the words before the token in its clause, else
  from the header of its section (a heading, bold label or ``Reviewer:`` line):
  ``claude``/``opus``/``sonnet``, or cross-model ``codex``/``gemini``/``gpt``. When
  both appear, the family is Claude. A verdict with no family is not a record.
- A *rebuttal at the cap* is a cross-model section with a REJECT line at round
  three or later followed by a past-tense ``rebutted`` line.
- A submitted ``APPROVED`` review whose ``commit_id`` is the head also counts as an
  independent record, unless the same reviewer later requested changes.

Verdict:
- ``OK``: an independent record at head and, for a high-risk PR, a cross-model
  record at head (an accepting verdict, or a rebuttal at the cap).
- ``MISSING_RECORD`` / ``MISSING_CROSS_MODEL``: what is absent; the reason tells a
  stale-head record from a comment with no verdict.
- ``ERROR``: the API could not be read; fails closed and, when the head is known,
  publishes an ``error`` status.

This checks that the queue convention was followed. It is not proof that a review
happened: every agent posts as the same bot identity, and any in-repo workflow with
``statuses: write`` can post the same status context. It must not become a
required check without a source-bound mechanism; that is an Owner decision.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

API_ROOT = "https://api.github.com"
PER_PAGE = 100
STATUS_CONTEXT = "Review record present (advisory)"
MIN_PREFIX = 9
MAX_DESCRIPTION = 140

# Paths whose change makes the PR high-risk (nexus-codex-review skill list, 2026-10-15).
HIGH_RISK_PREFIXES = (
    ".github/workflows/",
    ".nexus-core/",
    "scripts/ops/",
    "scripts/ci/",
    "nexus/orchestrator/governed_integration.py",
    "nexus/orchestrator/self_hosted_task_service.py",
    "nexus/orchestrator/target_integration_lifecycle.py",
    "nexus/governance/",
)
HIGH_RISK_FILES = frozenset({
    "pyproject.toml",
    "uv.lock",
    "pytest.ini",
    "pyrightconfig.json",
    "ruff.toml",
    "AGENTS.md",
    "MUSE_PROTO.md",
})

_HEX_TOKEN = re.compile(rf"(?<![0-9a-f])([0-9a-f]{{{MIN_PREFIX},40}})(?![0-9a-f])")
_TOKEN = r"(?:ACCEPT|ACCEPTED|APPROVE|APPROVED)"
# Verdict position: after a "Verdict:" label, bound as "ACCEPT@<sha>", after a colon,
# dash or round marker ("r3 ACCEPT", "Round 2 @ sha: ACCEPT"), or alone on the line.
_VERDICT_POS = re.compile(
    rf"(?:\bverdict\s*:\s*|@\s*|[:\-–—]\s*|\br\d+\s+|\bround\s*\d+\s*:?\s*|^\s*)({_TOKEN})\b"
    rf"|({_TOKEN})(?=\s*(?:@|\bat\s)\s*[0-9a-f]{{{MIN_PREFIX},}})",
    re.IGNORECASE,
)
_REJECT = re.compile(r"\b(?:REJECT(?:ED)?|REPAIR_REQUIRED|REQUEST_CHANGES|CHANGES[ _]REQUESTED)\b")
# Words before the token in its clause that make it a wish, a condition or a negation.
_PRE_DENY = re.compile(
    r"\b(?:await(?:ing|s)?|need(?:s|ed|ing)?|request(?:s|ed|ing)?|should|would|will|could|may|might"
    r"|no|not|never|cannot|can't|don't|doesn't|didn't|won't|wouldn't|pending|withheld|blocked"
    r"|conditional|missing|without|lacking|unless|until|before|please|expect(?:s|ed|ing)?"
    r"|wait(?:s|ed|ing)?|still|yet|if|only|reject(?:ed|s)?|repair_required|request_changes"
    r"|no_verdict|said|say|says|give|gives|gave|get|gets|got|want(?:s|ed)?|hope(?:s|d)?)\b",
    re.IGNORECASE,
)
# Words right after the token (before a sha, punctuation or a parenthesis) that withdraw it.
_POST_DENY = re.compile(
    r"^\s*(?:pending|withheld|blocked|only|if|unless|once|when|later|is|was|would|will|should"
    r"|could|may|might|needed|required|expected|requested|awaited|\?)",
    re.IGNORECASE,
)
_POST_COND = re.compile(
    r"\b(?:only if|if|unless|provided|conditional on|once|when)\b|\?", re.IGNORECASE
)
_REBUTTED = re.compile(r"\brebutted\b|\brebuttals? (?:accepted|stands?)\b", re.IGNORECASE)
_ROUND = re.compile(r"\b(?:r|round\s*)(\d+)\b", re.IGNORECASE)
_CLAUDE = re.compile(r"\b(?:claude|opus|sonnet)\b", re.IGNORECASE)
_CROSS = re.compile(r"\b(?:codex|gemini|gpt)\b", re.IGNORECASE)
_HEAD_BIND = re.compile(
    rf"\bhead\b[^\n]{{0,24}}?(?<![0-9a-f])([0-9a-f]{{{MIN_PREFIX},40}})(?![0-9a-f])"
)
_SKIP_LINE = re.compile(r"^\s*(?:\||>|- \[ \]|\* \[ \]|\$ |coord ready\b|gh pr\b)")
_LABEL_LINE = re.compile(r"^\s*(?:#+\s|\*\*|- \*\*|\*\s\*\*|reviewer\b)", re.IGNORECASE)
_LABEL_WORDS = re.compile(
    r"\b(?:review|reviewer|cross-model|adversarial|independent|verdict)\b", re.IGNORECASE
)
_NOT_A_HEADER = re.compile(
    r"\b(?:pending|unavailable|timed out|out of credits|not run|tbd|skipped|n/a|no run|none)\b",
    re.IGNORECASE,
)
_CLAUSE_SPLIT = re.compile(r"[;,]\s+|\.\s+|!\s+|\s[—–]\s|\s-\s|\)\s+")
_STOP = re.compile(r"[.;,:(\n]")


class CheckError(Exception):
    """Raised for any condition that must fail closed."""


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "nexus-review-record-check",
    }


def _get_json(url: str, token: str) -> Any:
    request = urllib.request.Request(url, headers=_headers(token))
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, token: str, payload: dict[str, Any]) -> Any:
    data = json.dumps(payload).encode("utf-8")
    headers = _headers(token)
    headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _paginate(fetch: Callable[[str, str], Any], url: str, token: str) -> list[Any]:
    items: list[Any] = []
    page = 1
    while True:
        batch = fetch(f"{url}?per_page={PER_PAGE}&page={page}", token)
        if not isinstance(batch, list):
            raise CheckError("unexpected API response shape")
        items.extend(batch)
        if len(batch) < PER_PAGE:
            return items
        page += 1


def _log_safe(line: str) -> str:
    """One physical log line that can never be read as a GitHub workflow command."""
    text = str(line)
    indent = len(text) - len(text.lstrip(" "))
    body = " ".join("".join(ch if ch.isprintable() else " " for ch in text).split())
    while "##[" in body:
        body = body.replace("##[", "# #[")
    if body.startswith("::"):
        body = "> " + body
    return " " * indent + body


def _hex_tokens(text: str) -> list[str]:
    return _HEX_TOKEN.findall(text.lower())


def names_head(text: str, head: str) -> bool:
    """True when the text contains the head sha or a hex prefix of it (>= MIN_PREFIX)."""
    head = head.lower()
    return any(head.startswith(token) for token in _hex_tokens(text))


def names_other_sha(text: str, head: str) -> bool:
    """True when the text names a sha that is not (a prefix of) the head."""
    head = head.lower()
    return any(not head.startswith(token) for token in _hex_tokens(text))


def _family(text: str) -> str | None:
    """Reviewer family named in the text: Claude beats cross-model when both appear."""
    if _CLAUDE.search(text):
        return "claude"
    if _CROSS.search(text):
        return "cross_model"
    return None


def _plain(line: str, keep_parens: bool = False) -> str:
    """Markdown emphasis and code spans removed; parentheticals dropped unless kept."""
    text = re.sub(r"[*_`]+", "", line)
    return text if keep_parens else re.sub(r"\([^)]*\)", " ", text)


def _verdict_match(clause: str) -> tuple[int, int] | None:
    match = _VERDICT_POS.search(clause)
    if not match:
        return None
    group = 1 if match.group(1) else 2
    return match.start(group), match.end(group)


def _clauses(line: str) -> list[str]:
    return [clause for clause in _CLAUSE_SPLIT.split(line) if clause.strip()]


def verdict_clauses(line: str) -> list[str]:
    """Clauses of the line whose accepting token sits in verdict position.

    The token must follow ``Verdict:``, ``@``, a colon or dash, a round marker
    (``r3``, ``Round 2 @ sha:``) or start the line; nothing before it in the
    clause may be a wish, condition or negation (``awaiting``, ``should``, ``not``,
    ``cannot``, ``pending``, ``please``, ``if`` ...), and nothing right after it may
    withdraw it (``pending``, ``withheld``, ``only if``, ``?``). Table rows, block
    quotes, unticked checklist items and pasted commands never count.
    """
    if _SKIP_LINE.match(line):
        return []
    out: list[str] = []
    for clause in _clauses(_plain(line, keep_parens=True)):
        span = _verdict_match(clause)
        if span is None:
            continue
        before = _plain(clause[: span[0]])  # parentheticals carry model names, not verdicts
        after = clause[span[1] :]
        if _PRE_DENY.search(before) or _REJECT.search(before):
            continue
        head_of_after = _STOP.split(after, 1)[0]
        if _POST_DENY.match(head_of_after) or _POST_COND.search(head_of_after):
            continue
        out.append(clause)
    return out


def is_verdict_line(line: str) -> bool:
    return bool(verdict_clauses(line))


def _comment_head(lines: list[str], head: str) -> bool:
    """A line that labels the head: ``Head reviewed: <sha>``, ``final head <sha>``."""
    head = head.lower()
    for line in lines:
        for found in _HEAD_BIND.findall(_plain(line).lower()):
            if head.startswith(found):
                return True
    return False


def _binding(clause: str, line: str, head: str, comment_head: bool) -> bool:
    """A verdict binds to the head by its own clause's sha, else the line, else a Head line.

    A clause that names a different sha is bound to that sha: a later ``Head`` line
    or another sha on the same line cannot rebind it.
    """
    if _hex_tokens(clause):
        return names_head(clause, head)
    if _hex_tokens(line):
        return names_head(line, head)
    return comment_head


def _label_family(line: str) -> str | None:
    """Family named by a heading, bold label, ``Reviewer:`` line or ``<label>:`` prefix."""
    plain = _plain(line, keep_parens=True).strip()
    if _NOT_A_HEADER.search(plain):
        return None  # "Codex: unavailable", "Codex adversarial review: pending" open no section
    if _LABEL_LINE.match(line) or plain.lower().startswith("reviewer"):
        return _family(plain)
    if ":" in plain:
        prefix = plain.split(":", 1)[0]
        if _LABEL_WORDS.search(prefix):
            return _family(prefix)
    return None


def _rebuttal_at_cap(section: list[str]) -> bool:
    """A cross-model REJECT at round >= 3 followed (or joined) by a past-tense rebuttal."""
    reject_round_seen = False
    for line in section:
        plain = _plain(line, keep_parens=True)
        if _REJECT.search(plain) and any(int(n) >= 3 for n in _ROUND.findall(plain)):
            reject_round_seen = True
        if reject_round_seen and _REBUTTED.search(plain):
            return True
    return False


def classify_record(body: str, head: str) -> dict[str, Any] | None:
    """Classify one comment body; None when it does not name the head anywhere.

    Returns the verdicts bound to the head (each with its reviewer family) and
    whether a cross-model section rebuts at the cap. A section starts at a label
    line that names a family (heading, bold label, ``Reviewer:``) and ends at a
    verdict line; the family of a bare verdict is the section header's family.
    """
    if not isinstance(body, str) or not names_head(body, head):
        return None
    lines: list[str] = []
    fenced = False
    for raw in body.splitlines():
        if raw.strip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(raw)
    comment_head = _comment_head(lines, head)
    verdicts: list[dict[str, Any]] = []
    rebuttal_at_cap = False
    section: list[str] = []
    header_family: str | None = None
    for line in lines:
        label = _label_family(line)
        if label is not None and label != header_family:
            if section and header_family == "cross_model" and _rebuttal_at_cap(section):
                rebuttal_at_cap = True
            section, header_family = [], label
        section.append(line)
        clauses = verdict_clauses(line)
        if not clauses:
            continue
        for clause in clauses:
            span = _verdict_match(clause)
            before = clause[: span[0]] if span else ""
            family = _family(before) or header_family
            if family and _binding(clause, line, head, comment_head):
                verdicts.append({"family": family, "line": clause.strip()})
        if header_family == "cross_model" and _rebuttal_at_cap(section):
            rebuttal_at_cap = True
        section, header_family = [], None
    if section and header_family == "cross_model" and _rebuttal_at_cap(section):
        rebuttal_at_cap = True
    return {
        "verdict": bool(verdicts),
        "claude": any(v["family"] == "claude" for v in verdicts),
        "cross_model": any(v["family"] == "cross_model" for v in verdicts),
        "rebuttal_at_cap": rebuttal_at_cap,
        "verdict_lines": [v["line"] for v in verdicts],
    }


def _is_high_risk(name: str) -> bool:
    return name in HIGH_RISK_FILES or name.startswith(HIGH_RISK_PREFIXES)


def high_risk_paths(files: list[Any]) -> list[str]:
    """High-risk paths touched by the PR; a rename counts by its old name too."""
    paths: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            continue
        for key in ("filename", "previous_filename"):
            name = entry.get(key)
            if isinstance(name, str) and _is_high_risk(name):
                paths.add(name)
    return sorted(paths)


def approved_reviews_at_head(reviews: list[Any], head: str) -> int:
    """Reviewers whose LATEST submitted review at the head is APPROVED.

    A later CHANGES_REQUESTED (or a dismissal) by the same reviewer at the same
    commit supersedes an earlier approval; a COMMENTED review does not.
    """
    latest: dict[str, str] = {}
    for review in reviews:
        if not isinstance(review, dict):
            continue
        if str(review.get("commit_id", "")).lower() != head.lower():
            continue
        state = str(review.get("state", ""))
        if state == "COMMENTED":
            continue
        user = review.get("user") if isinstance(review.get("user"), dict) else {}
        who = str((user or {}).get("login") or review.get("id") or len(latest))
        latest[who] = state
    return sum(1 for state in latest.values() if state == "APPROVED")


def evaluate(
    head: str, files: list[Any], comments: list[Any], reviews: list[Any]
) -> dict[str, Any]:
    """Pure classification of the PR's review evidence at ``head``."""
    risky = high_risk_paths(files)
    records = []
    stale = False
    unbound = False
    for comment in comments:
        body = comment.get("body") if isinstance(comment, dict) else None
        if not isinstance(body, str):
            continue
        record = classify_record(body, head)
        if record is None:
            if names_other_sha(body, head) and any(
                is_verdict_line(line) for line in body.splitlines()
            ):
                stale = True
            continue
        if record["verdict"] or record["rebuttal_at_cap"]:
            records.append(record)
        else:
            unbound = True
    approved_reviews = approved_reviews_at_head(reviews, head)
    independent = approved_reviews > 0 or any(r["verdict"] for r in records)
    cross_model = any(r["cross_model"] or r["rebuttal_at_cap"] for r in records)
    short = head[:12]
    if not independent:
        status = "MISSING_RECORD"
        if stale:
            reason = f"review record found for an older head only; none names head {short}"
        elif unbound:
            reason = f"a comment names head {short} but carries no reviewer+ACCEPT/APPROVE verdict"
        else:
            reason = f"no review record names head {short} with an ACCEPT/APPROVE verdict"
    elif risky and not cross_model:
        status = "MISSING_CROSS_MODEL"
        reason = f"high-risk paths changed but no Codex/Gemini verdict or rebuttal at head {short}"
    else:
        status, reason = "OK", f"review record present at head {short}"
    return {
        "schema": "nexus.review_record_check.v1",
        "head": head,
        "high_risk": bool(risky),
        "high_risk_paths": risky,
        "records_at_head": len(records),
        "approved_reviews_at_head": approved_reviews,
        "independent": independent,
        "cross_model": cross_model,
        "status": status,
        "reason": reason,
    }


def _description(report: dict[str, Any]) -> str:
    text = _log_safe(f"{report['status']}: {report['reason']}").strip()
    return text[:MAX_DESCRIPTION]


def run(
    repo: str,
    pr: int,
    token: str,
    fetch: Callable[[str, str], Any] = _get_json,
    post: Callable[[str, str, dict[str, Any]], Any] = _post_json,
    *,
    publish: bool = True,
    fail_on_missing: bool = True,
    target_url: str = "",
    output: str | None = None,
) -> int:
    base = f"{API_ROOT}/repos/{repo}"
    report: dict[str, Any]
    head = ""
    try:
        pull = fetch(f"{base}/pulls/{pr}", token)
        head_obj = pull.get("head") if isinstance(pull, dict) else None
        head = str(head_obj.get("sha", "")) if isinstance(head_obj, dict) else ""
        if not re.fullmatch(r"[0-9a-f]{40}", head):
            head = ""
            raise CheckError("PR head sha unavailable")
        files = _paginate(fetch, f"{base}/pulls/{pr}/files", token)
        comments = _paginate(fetch, f"{base}/issues/{pr}/comments", token)
        reviews = _paginate(fetch, f"{base}/pulls/{pr}/reviews", token)
        report = evaluate(head, files, comments, reviews)
    except Exception as exc:  # noqa: BLE001 - any read failure must fail closed
        report = {
            "schema": "nexus.review_record_check.v1",
            "head": head,
            "status": "ERROR",
            "reason": f"could not read the PR: {type(exc).__name__}: {exc}",
        }
    if output:
        with open(output, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
    for line in (
        f"review-record-check: {report['status']}",
        f"  {report['reason']}",
        f"  high-risk paths: {', '.join(report.get('high_risk_paths') or []) or '-'}",
    ):
        print(_log_safe(line))
    if report["status"] == "OK":
        state = "success"
    elif report["status"] == "ERROR":
        state = "error"
    else:
        state = "failure"
    if publish and head:
        payload = {
            "state": state,
            "context": STATUS_CONTEXT,
            "description": _description(report),
        }
        if target_url:
            payload["target_url"] = target_url
        try:
            post(f"{base}/statuses/{head}", token, payload)
        except Exception as exc:  # noqa: BLE001 - an unpublished status is a failed run
            print(_log_safe(f"review-record-check: could not publish the status: {exc}"))
            return 1
    if report["status"] == "ERROR":
        return 1
    return 1 if (fail_on_missing and state == "failure") else 0


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review record present (#2290): advisory check")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--output")
    parser.add_argument("--target-url", default="")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument(
        "--no-fail", action="store_true", help="exit 0 even when a record is missing"
    )
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        print("review-record-check: ERROR: GH_TOKEN is not set")
        return 1
    return run(
        args.repo,
        args.pr,
        token,
        publish=not args.no_publish,
        fail_on_missing=not args.no_fail,
        target_url=args.target_url,
        output=args.output,
    )


if __name__ == "__main__":
    sys.exit(_cli())
