#!/usr/bin/env python3
"""Review record present (#2290): the PR must carry its review evidence at its head.

Advisory. Stdlib only. Reads the PR, its file list, its issue comments and its
submitted reviews through the GitHub REST API and publishes a commit status on
the PR head. PR code is never checked out or executed, and PR-controlled text
(comment bodies, paths) is only pattern-matched; every printed line goes through
``_log_safe`` so it can never be read as a workflow command.

What counts as a record (parsed line by line, so prose like "cannot ACCEPT until"
or "Codex review still pending" never counts):

- A *verdict line* carries an uppercase ``ACCEPT``/``ACCEPTED``/``APPROVE``/
  ``APPROVED`` token and no negation (``NOT``, ``cannot``, ``until``, ``pending``,
  ``please``, ``REJECT``, ``REPAIR_REQUIRED``, ``REQUEST_CHANGES`` ...).
- The verdict is *bound to the head* when that line names the head sha (full, or a
  hex prefix of at least ``MIN_PREFIX`` characters), or when the comment has a
  ``Head`` line naming it (``Head reviewed: <sha>``, ``head <sha>``).
- The *reviewer family* is read from the verdict line itself, else from the lines
  of its section (the lines since the previous verdict line): ``claude``/``opus``/
  ``sonnet``, or cross-model ``codex``/``gemini``/``gpt``. A verdict with no family
  is not a record (Issue #2290 asks for the reviewer identity).
- A *rebuttal at the cap* is a cross-model section (the lines since the previous
  verdict line) that says ``rebutted`` (past tense; "will rebut" does not count)
  and ``cap`` or a round number of three or more, in a comment that names the head.
- A submitted ``APPROVED`` review whose ``commit_id`` is the head also counts as an
  independent record.

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
_POSITIVE = re.compile(r"\b(?:ACCEPT|ACCEPTED|APPROVE|APPROVED)\b")
_NEGATION = re.compile(
    r"\bNOT\b|\bcannot\b|\bcan't\b|\buntil\b|\bpending\b|\bplease\b|\bbefore\b|\bno longer\b"
    r"|\bREJECT(?:ED)?\b|\bREPAIR_REQUIRED\b|\bREQUEST_CHANGES\b|\bCHANGES[ _]REQUESTED\b"
    r"|\bNO_VERDICT\b|\bnot run\b|\bwas not\b|\bwere not\b",
    re.IGNORECASE,
)
_REBUTTED = re.compile(r"\brebutted\b|\brebuttals? (?:accepted|stands)\b", re.IGNORECASE)
_CAP = re.compile(r"\bcap\b|\bround\s*(?:[3-9]|[1-9]\d)\b|\br(?:[3-9]|[1-9]\d)\b", re.IGNORECASE)
_CLAUDE = re.compile(r"\b(?:claude|opus|sonnet)\b", re.IGNORECASE)
_CROSS = re.compile(r"\b(?:codex|gemini|gpt)\b", re.IGNORECASE)
_HEAD_LINE = re.compile(r"\bhead\b", re.IGNORECASE)


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
    if _CROSS.search(text):
        return "cross_model"
    if _CLAUDE.search(text):
        return "claude"
    return None


_CLAUSE_SPLIT = re.compile(r"[;,]\s+|\.\s+|!\s+|\s[\u2014\u2013]\s|\s-\s|\)\s+")


def _clauses(line: str) -> list[str]:
    return [clause for clause in _CLAUSE_SPLIT.split(line) if clause]


def verdict_clauses(line: str) -> list[str]:
    """Clauses of the line that carry an uppercase accepting token and no negation.

    A clause is a comma/semicolon/sentence-separated part of the line, so a round
    list such as ``r1 REJECT (fixed), r2 REJECT (fixed), r3 ACCEPT@<sha>`` keeps its
    final ACCEPT while ``cannot ACCEPT until ...`` or ``Please APPROVE`` never count.
    """
    return [
        clause
        for clause in _clauses(line)
        if _POSITIVE.search(clause) and not _NEGATION.search(clause)
    ]


def is_verdict_line(line: str) -> bool:
    return bool(verdict_clauses(line))


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


def classify_record(body: str, head: str) -> dict[str, Any] | None:
    """Classify one comment body; None when it does not name the head anywhere.

    Returns the verdicts bound to the head (each with its reviewer family) and
    whether a cross-model section rebuts at the cap.
    """
    if not isinstance(body, str) or not names_head(body, head):
        return None
    lines = body.splitlines()
    comment_head = any(_HEAD_LINE.search(line) and names_head(line, head) for line in lines)
    verdicts: list[dict[str, Any]] = []
    rebuttal_at_cap = False
    section: list[str] = []
    for line in lines:
        section.append(line)
        clauses = verdict_clauses(line)
        if clauses:
            for clause in clauses:
                family = _family(clause) or _family("\n".join(section))
                if family and _binding(clause, line, head, comment_head):
                    verdicts.append({"family": family, "line": clause.strip()})
            section = []
            continue
        # A rebuttal at the cap is read per section (the lines since the previous
        # verdict line): "Rebutted" and "cap reached (3 rounds)" are often on
        # different lines of the same cross-model section (#2280's record).
        text = "\n".join(section)
        if _family(text) == "cross_model" and _REBUTTED.search(text) and _CAP.search(text):
            rebuttal_at_cap = True
    return {
        "verdict": bool(verdicts),
        "claude": any(v["family"] == "claude" for v in verdicts),
        "cross_model": any(v["family"] == "cross_model" for v in verdicts),
        "rebuttal_at_cap": rebuttal_at_cap,
        "verdict_lines": [v["line"] for v in verdicts],
    }


def _is_high_risk(name: Any) -> bool:
    return isinstance(name, str) and (
        name in HIGH_RISK_FILES or name.startswith(HIGH_RISK_PREFIXES)
    )


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
