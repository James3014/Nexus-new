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
# The token itself is case-sensitive (uppercase only); the label words are not.
_VERDICT_POS = re.compile(
    rf"(?:\b(?i:verdict)\s*:\s*|@\s*|:\s*|\s[\-–—]\s*|\b(?i:r)\d+\s+|\b(?i:round)\s*\d+\s*:?\s*|^\s*)"
    rf"({_TOKEN})\b"
    rf"|(?<![\w-])({_TOKEN})(?=\s*(?:@|\bat\s)\s*[0-9a-f]{{{MIN_PREFIX},}})",
)
# _plain strips underscores, so the joined forms must match too.
_REJECT = re.compile(
    r"\b(?:REJECT(?:ED)?|REPAIR_?REQUIRED|REQUEST_?CHANGES|CHANGES[ _]?REQUESTED)\b"
)
_VERDICT_NEGATIVE = re.compile(r"(?i:verdict)\s*:\s*(?:REJECT|REPAIR_?REQUIRED|REQUEST_?CHANGES)")
_QUOTE = re.compile("[\"\u201c\u2018]|(?<![A-Za-z])'")  # an apostrophe inside a word is possessive
# Words before the token in its clause that make it a wish, a condition or a negation.
_PRE_DENY = re.compile(
    r"\b(?:await(?:ing|s)?|need(?:s|ed|ing)?|request(?:s|ed|ing)?|should|would|will|could|may|might"
    r"|no|not|never|cannot|can't|don't|doesn't|didn't|won't|wouldn't|pending|withheld|blocked"
    r"|conditional|missing|without|lacking|unless|until|before|please|expect(?:s|ed|ing)?"
    r"|wait(?:s|ed|ing)?|still|yet|if|only"
    r"|author|self-check|self-review"
    r"|said|say|says|give|gives|gave|get|gets|got|want(?:s|ed)?|hope(?:s|d)?)\b",
    re.IGNORECASE,
)
# Words right after the token (before a sha, punctuation or a parenthesis) that withdraw it.
_POST_DENY = re.compile(
    r"^\s*(?:after|pending|withheld|blocked|only|if|unless|once|when|later|is|was|would|will|should"
    r"|could|may|might|needed|required|expected|requested|awaited|\?)",
    re.IGNORECASE,
)
_POST_COND = re.compile(
    r"\b(?:only if|if|unless|provided|conditional on|once|when)\b|\?", re.IGNORECASE
)
_REBUTTED = re.compile(r"\brebutted\b|\brebuttals? (?:accepted|stands?)\b", re.IGNORECASE)
_REBUTTAL_DENY = re.compile(
    r"\b(?:not|nothing|never|none|no|un-?rebutted|without)\b", re.IGNORECASE
)
_ROUND = re.compile(r"\b(?:r|round\s*)(\d+)\b", re.IGNORECASE)
_CLAUDE = re.compile(r"\b(?:claude|opus|sonnet)\b", re.IGNORECASE)
_CROSS = re.compile(r"\b(?:codex|gemini|gpt)\b", re.IGNORECASE)
_HEAD_BIND = re.compile(
    rf"\bhead\b[^\n]{{0,48}}?(?<![0-9a-f])([0-9a-f]{{{MIN_PREFIX},40}})(?![0-9a-f])"
)
_SKIP_LINE = re.compile(
    r"^\s*(?:\||>|(?:[-*+]|\d+\.)\s+\[ \]|\$ |coord ready\b|gh pr\b)"
    r"|^(?: {4}|\t)(?![-*+]\s|\d+\.\s)"  # indented code, but not a nested list item
)
_ROUND_MARKER = re.compile(r"\b(?i:r)\d+\b|\b(?i:round)\s*\d+\b")
_POST_LINE_DENY = re.compile(
    r"\b(?:pending|withheld|blocked|cannot|unless|only if)\b", re.IGNORECASE
)
_REBUTTAL_BUT_NOT = re.compile(
    r"\brebutted\b[^.;\n]*\b(?:but|though|however|yet)\b[^.;\n]*\b(?:not|nothing|never|wasn't|isn't)\b",
    re.IGNORECASE,
)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_LABEL_LINE = re.compile(r"^\s*(?:#+\s|\*\*|- \*\*|\*\s\*\*|reviewer\b)", re.IGNORECASE)
_LABEL_WORDS = re.compile(
    r"\b(?:review|reviewer|cross-model|adversarial|independent|verdict)\b", re.IGNORECASE
)
_NOT_A_HEADER = re.compile(
    r"\b(?:pending|unavailable|timed out|out of credits|not run|tbd|skipped|n/a|no run|none)\b",
    re.IGNORECASE,
)
# A parenthetical that STARTS with a not-run word is the header's own status ("Codex
# review (pending)"); one that merely mentions it later is an aside ("(agy Gemini ...;
# Codex: out of credits)").
_ASIDE_NOT_RUN = re.compile(
    r"\(\s*(?:pending|unavailable|timed out|out of credits|not run|tbd|skipped|n/a|no run|none)\b",
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


def _api_url(url: str) -> str:
    """Only the GitHub REST API over https is ever opened (B310: no file:/ or custom schemes)."""
    if not url.startswith(API_ROOT + "/"):
        raise CheckError("refusing to open a non-API URL")
    return url


def _get_json(url: str, token: str) -> Any:
    request = urllib.request.Request(_api_url(url), headers=_headers(token))
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - https API only
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, token: str, payload: dict[str, Any]) -> Any:
    data = json.dumps(payload).encode("utf-8")
    headers = _headers(token)
    headers["Content-Type"] = "application/json"
    request = urllib.request.Request(_api_url(url), data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - https API only
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
    plain_line = _plain(line, keep_parens=True)
    consumed = 0
    prev_token_end = 0
    for clause in _clauses(plain_line):
        start = plain_line.find(clause, consumed)
        consumed = start + len(clause) if start >= 0 else consumed
        span = _verdict_match(clause)
        if span is None:
            continue
        token_at = start + span[0]
        window_start = prev_token_end
        for marker in _ROUND_MARKER.finditer(plain_line, prev_token_end, token_at):
            window_start = marker.start()  # "r1 ... with one should-fix, r2 ACCEPT": new round
        prev_token_end = max(prev_token_end, start + span[1])
        if (
            start > 0
            and span[0] == 0
            and not re.search(r"[:\-\u2013\u2014@]\s*$", plain_line[:start].rstrip() + " ")
        ):
            # The "alone on its line" position applies to the line, not to a later clause.
            if not re.match(r"\s*$", plain_line[:start]):
                continue
        before = _plain(clause[: span[0]])  # parentheticals carry model names, not verdicts
        # Negations and modals anywhere earlier on the line also deny ("We cannot, under
        # any circumstances, ACCEPT"); REJECT words deny only inside the clause.
        # The window runs from the previous verdict token on the line (a round list
        # names several) to this one.
        line_before = _plain(plain_line[window_start : start + span[0]]) if start >= 0 else before
        after = clause[span[1] :]
        if _PRE_DENY.search(line_before) or _REJECT.search(before) or _QUOTE.search(line_before):
            continue  # a quoted or negated verdict is prose about a verdict, not one
        if _VERDICT_NEGATIVE.search(line_before) or _REJECT.search(_plain(clause[span[1] :])):
            continue  # "Verdict: REJECT — ACCEPT after the fixes" is a rejection
        head_of_after = _STOP.split(after, 1)[0]
        if _POST_DENY.match(head_of_after) or _POST_COND.search(head_of_after):
            continue
        if not _hex_tokens(clause):
            # A verdict not bound by its own clause borrows the sha from later on the
            # line, so a withdrawal later on the line ("ACCEPT, pending CI at <sha>",
            # "ACCEPT; cannot merge <sha>") belongs to it. A clause-bound
            # "ACCEPT@<sha>; Codex review still pending" is unaffected.
            rest_of_line = _plain(plain_line[start + span[1] :]) if start >= 0 else after
            next_token = _VERDICT_POS.search(rest_of_line)
            rest_of_line = rest_of_line[: next_token.start()] if next_token else rest_of_line
            if _hex_tokens(rest_of_line) and _POST_LINE_DENY.search(rest_of_line):
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


_MODEL_WORDS = re.compile(r"\b(?:codex|gemini|gpt|claude|opus|sonnet)\b", re.IGNORECASE)


def _own_status(line: str) -> bool:
    """A parenthetical part that holds a not-run word and names no model beyond the
    header's own is the header's status ("Codex review (still pending)"); a part that
    names another model is an aside ("Gemini review (Codex pending)")."""
    own = {m.lower() for m in _MODEL_WORDS.findall(_plain(line))}
    plain = _plain(line, keep_parens=True)
    return any(
        _NOT_A_HEADER.search(part) and {m.lower() for m in _MODEL_WORDS.findall(part)} <= own
        for paren in re.findall(r"\(([^)]*)\)", plain)
        for part in re.split(r"[;,]", paren)
    )


def _label_family(line: str) -> str | None:
    """Family named by a heading, bold label, ``Reviewer:`` line or ``<label>:`` prefix."""
    plain = _plain(line, keep_parens=True).strip()
    if _NOT_A_HEADER.search(_plain(line)) or _ASIDE_NOT_RUN.search(plain) or _own_status(line):
        # "Codex: unavailable", "Codex adversarial review: pending" open no section; a
        # not-run word inside a parenthetical aside ("Gemini ... (Codex: out of credits)")
        # does not disable the header (#2299, first live false negative on #2296).
        return None
    bold = re.match(r"^\s*(?:[-*]\s+)?\*\*(.+?)\*\*", line)
    if (
        bold
        and not re.match(r"^\s*#", line)
        and not verdict_clauses(line)
        and not _LABEL_WORDS.search(bold.group(1))
    ):
        # A finding bullet ("- **N1:** the Codex prompt is stale") labels by its bold
        # text only, so a model name in the finding text cannot switch the family.
        return _family(bold.group(1))
    if _LABEL_LINE.match(line) or plain.lower().startswith("reviewer"):
        return _family(plain)
    if ":" in plain:
        prefix = plain.split(":", 1)[0]
        if _LABEL_WORDS.search(prefix):
            return _family(prefix)
    return None


def _rebuttal_at_cap(section: list[str], head: str) -> bool:
    """A cross-model REJECT at round >= 3 followed (or joined) by a past-tense rebuttal.

    A later REJECT line that names the current head withdraws it: a rebuttal of an
    earlier round does not cover a fresh rejection of this head.
    """
    reject_round_seen = False
    rebutted = False
    for line in section:
        plain = _plain(line, keep_parens=True)
        if _REJECT.search(plain) and any(int(n) >= 3 for n in _ROUND.findall(plain)):
            reject_round_seen = True
            if rebutted and names_head(plain, head):
                return False
        if (
            reject_round_seen
            and not _REBUTTAL_BUT_NOT.search(plain)
            and any(
                _REBUTTED.search(clause) and not _REBUTTAL_DENY.search(clause)
                for clause in _clauses(plain)
            )
        ):
            rebutted = True
    return rebutted


def classify_record(body: str, head: str) -> dict[str, Any] | None:
    """Classify one comment body; None when it does not name the head anywhere.

    Returns the verdicts bound to the head (each with its reviewer family) and
    whether a cross-model section rebuts at the cap. A section starts at a label
    line that names a different family (heading, bold label, ``Reviewer:``); its
    line buffer restarts at each verdict line, while the header family persists
    until the next label, so a reviewer block that lists its rounds keeps its
    family. The family of a bare verdict is the section header's family.
    """
    if not isinstance(body, str) or not names_head(body, head):
        return None
    lines: list[str] = []
    fenced = False
    for raw in _HTML_COMMENT.sub(" ", body).splitlines():
        if raw.strip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(raw)
    comment_head = _comment_head(lines, head)
    verdicts: list[dict[str, Any]] = []
    rebuttal_at_cap = False
    section: list[str] = []
    header_family: str | None = None
    header_level = 0  # heading level that opened the section; 99 for a non-heading label
    for line in lines:
        label = _label_family(line)
        level = re.match(r"^\s*(#+)\s", line)
        if label is not None:
            header_level = len(level.group(1)) if level else 99
        # A plain heading closes the section only at the same or a higher level than
        # the heading that opened it ("### Findings" inside "## Review record" does not).
        neutral_heading = (
            label is None and level is not None and len(level.group(1)) <= header_level
        )
        if (label is not None and label != header_family) or neutral_heading:
            if section and header_family == "cross_model" and _rebuttal_at_cap(section, head):
                rebuttal_at_cap = True
            section, header_family = [], label  # "## Notes" opens a section with no family
        section.append(line)
        clauses = verdict_clauses(line)
        if not clauses:
            continue
        plain_line = _plain(line, keep_parens=True)
        consumed = 0
        for clause in clauses:
            span = _verdict_match(clause)
            before = clause[: span[0]] if span else ""
            start = plain_line.find(clause, consumed)
            consumed = start + len(clause) if start >= 0 else consumed
            # The family named on the line before the token ("Claude: r1 ..., r2 ACCEPT"),
            # else the section header's.
            line_before = plain_line[: start + span[0]] if (span and start >= 0) else before
            family = _family(before) or _family(line_before) or header_family
            if family and _binding(clause, line, head, comment_head):
                verdicts.append({"family": family, "line": clause.strip()})
        if header_family == "cross_model" and _rebuttal_at_cap(section, head):
            rebuttal_at_cap = True
        section = []  # the header family persists: a reviewer block lists its rounds
    if section and header_family == "cross_model" and _rebuttal_at_cap(section, head):
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
    # The independent record is the Claude-family review (or a submitted approval); a
    # cross-model record alone satisfies only the cross-model requirement.
    independent = approved_reviews > 0 or any(r["claude"] for r in records)
    cross_model = any(r["cross_model"] or r["rebuttal_at_cap"] for r in records)
    short = head[:12]
    if not independent:
        status = "MISSING_RECORD"
        if stale:
            reason = f"review record found for an older head only; none names head {short}"
        elif unbound:
            reason = (
                f"a comment names head {short} but carries no Claude/Opus ACCEPT/APPROVE verdict"
            )
        else:
            reason = (
                f"no Claude/Opus review record names head {short} with an ACCEPT/APPROVE verdict"
            )
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
