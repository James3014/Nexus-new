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
  ``final head <sha>``). A clause bound to another sha cannot be rebound. When the
  comment's Head labels name different commits, only the nearest label above the
  verdict binds it (#2992).
- The *reviewer family* comes from the words before the token in its clause, else
  from the header of its section (a heading, bold label or ``Reviewer:`` line):
  ``claude``/``opus``/``sonnet``, or cross-model ``codex``/``gemini``/``gpt``. When
  both appear, the family is Claude. A verdict with no family is not a record.
- A later *REJECT* (or ``REPAIR_REQUIRED`` / ``REQUEST_CHANGES``) in verdict position at
  the head withdraws the earlier ACCEPTs of its reviewer family (the model named closest
  before it), in the same comment or a later one, unless it says it was resolved
  (``fixed``, ``rebutted``) or an ACCEPT is from a later round; a later ACCEPT stands
  again (#2992).
- A *rebuttal at the cap* is a cross-model section with a REJECT line at round
  three or later followed by a past-tense ``rebutted`` line. It does not count for
  the repos in ``NO_REBUTTAL_AT_CAP_REPOS`` (cairnwork/cairnwork since cairnwork#344:
  a finding still open at round three goes back to design, not past a rebuttal).
- A submitted ``APPROVED`` review whose ``commit_id`` is the head also counts as an
  independent record, unless the same reviewer later requested changes.

Verdict:
- ``OK``: an independent record at head and, for a high-risk PR, a cross-model
  record at head (an accepting verdict, or a rebuttal at the cap where it counts).
  A PR file list at the API cap (3000 files) may hide a path, so it is high-risk.
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
# Repos whose review rules take no rebuttal at the cap as a cross-model record (#2954).
# Matched against --repo, which the callers set from github.repository (not PR text).
NO_REBUTTAL_AT_CAP_REPOS = frozenset({"cairnwork/cairnwork"})
MIN_PREFIX = 9
MAX_DESCRIPTION = 140
# The PR files API lists at most 3000 files and then stops without an error (#2992).
MAX_PR_FILES = 3000
TRUNCATED_FILES = f"(file list of {MAX_PR_FILES}+ entries may be truncated)"

# Paths whose change makes the PR high-risk (nexus-codex-review skill list, 2026-10-15).
HIGH_RISK_PREFIXES = (
    ".github/workflows/",
    ".nexus-core/",
    "scripts/ops/",
    "scripts/ci/",
    "nexus/orchestrator/governed_integration.py",
    "nexus/orchestrator/self_hosted_task_service.py",
    # Big-file split surfaces (#2473): the original module and its _parts package only;
    # near-miss siblings such as unified_mcp_gateway_helpers.py stay low-risk.
    "nexus/orchestrator/self_hosted_task_service_parts/",
    "nexus/orchestrator/unified_mcp_gateway.py",
    "nexus/orchestrator/unified_mcp_gateway_parts/",
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
_REJECT_TOKEN = r"(?:REJECT(?:ED)?|REPAIR_?REQUIRED|REQUEST_?CHANGES|CHANGES[ _]?REQUESTED)"
_REJECT = re.compile(rf"\b{_REJECT_TOKEN}\b")
# A rejecting verdict in the same positions as an accepting one (#2992); uppercase only.
_REJECT_POS = re.compile(
    rf"(?:\b(?i:verdict)\s*:\s*|@\s*|:\s*|\s[\-–—]\s*|\b(?i:r)\d+\s+|\b(?i:round)\s*\d+\s*:?\s*|^\s*)"
    rf"({_REJECT_TOKEN})\b"
    rf"|(?<![\w-])({_REJECT_TOKEN})(?=\s*(?:@|\bat\s)\s*[0-9a-f]{{{MIN_PREFIX},}})",
)
_REJECT_PRE_DENY = re.compile(
    r"\b(?:no|not|never|none|nothing|if|unless|whether|would|could|might|may|should|cannot"
    r"|can't|didn't|doesn't|won't|wouldn't|without|avoid|prevent|instead of)\b",
    re.IGNORECASE,
)
_RESOLVED = re.compile(
    r"\b(?:fixed|rebutted|addressed|resolved|superseded|withdrawn|retracted|overturned"
    r"|dismissed|overridden|cleared)\b",
    re.IGNORECASE,
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
# A Head label proper ("Head reviewed: <sha>", "final head <sha>", "head is now <sha>",
# "Reviewed commit <sha>"), not prose that merely has a sha within reach of the word
# ("this head and main <sha>").
_HEAD_LABEL = re.compile(
    r"\b(?:head|reviewed)\b(?:\s+(?:reviewed|sha|commit))?(?:\s+(?:is|was))?(?:\s+now)?(?:\s+at)?"
    rf"\s*[:=@]?\s*(?<![0-9a-f])([0-9a-f]{{{MIN_PREFIX},40}})(?![0-9a-f])"
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
    r"\b(?:pending|unavailable|timed out|out of credits|not run|tbd|skipped|n/a|no run|none"
    r"|awaiting|in progress|queued|running)\b",
    re.IGNORECASE,
)
# A parenthetical that STARTS with a not-run word is the header's own status ("Codex
# review (pending)"); one that merely mentions it later is an aside ("(agy Gemini ...;
# Codex: out of credits)").
_ASIDE_NOT_RUN = re.compile(
    r"\(\s*(?:pending|unavailable|timed out|out of credits|not run|tbd|skipped|n/a|no run|none"
    r"|awaiting|in progress|queued|running)\b",
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


def reject_clauses(line: str) -> list[str]:
    """Clauses of the line that carry an open rejecting verdict (#2992).

    The token (``REJECT``, ``REPAIR_REQUIRED``, ``REQUEST_CHANGES``, ``CHANGES_REQUESTED``)
    sits in the same verdict positions as an accepting one; it is not negated, conditional
    or quoted, and nothing from it to the next verdict on the line says it was resolved
    (``r1 REJECT (fixed)``, ``REJECT, rebutted``). Lines skipped for accepting verdicts
    (tables, quotes, unticked checklist items, pasted commands) are skipped here too.
    """
    if _SKIP_LINE.match(line):
        return []
    out: list[str] = []
    plain_line = _plain(line, keep_parens=True)
    consumed = 0
    for clause in _clauses(plain_line):
        start = plain_line.find(clause, consumed)
        consumed = start + len(clause) if start >= 0 else consumed
        match = _REJECT_POS.search(clause)
        if not match:
            continue
        token_start = match.start(1) if match.group(1) else match.start(2)
        if _REJECT_PRE_DENY.search(_plain(clause[:token_start])) or _QUOTE.search(
            clause[:token_start]
        ):
            continue
        rest = plain_line[start + token_start :] if start >= 0 else clause[token_start:]
        following = _VERDICT_POS.search(rest, 1)
        following_reject = _REJECT_POS.search(rest, 1)
        cut = min([m.start() for m in (following, following_reject) if m is not None] + [len(rest)])
        if _RESOLVED.search(rest[:cut]):
            continue
        out.append(clause)
    return out


def _head_labels(lines: list[str]) -> list[tuple[list[str], str | None]]:
    """Per line: every sha a loose ``head ... <sha>`` mention names, and the sha its first
    Head label proper names (``Head reviewed: <sha>``, ``final head <sha>``) or None.
    A parenthetical is neither."""
    out: list[tuple[list[str], str | None]] = []
    for line in lines:
        text = _plain(line).lower()
        strict = _HEAD_LABEL.search(text)
        out.append((_HEAD_BIND.findall(text), strict.group(1) if strict else None))
    return out


def _label_binds(labels: list[tuple[list[str], str | None]], index: int, head: str) -> bool:
    """Whether a verdict on line ``index`` whose line names no sha binds to the head.

    By default any line of the comment that names the head after the word ``head`` binds
    it, above or below the verdict. When a Head label proper names another commit
    ("Head reviewed: <old>" with "head is now <new>" elsewhere), only the nearest Head
    label above the verdict binds it (#2992): the record is then that older head's, and
    a merge-only delta to the new head is left to the API verification (#2308).
    """
    head = head.lower()
    strict = [label for _loose, label in labels]
    if all(label is None or head.startswith(label) for label in strict):
        return any(head.startswith(found) for loose, _label in labels for found in loose)
    for label in reversed(strict[: index + 1]):
        if label is not None:
            return head.startswith(label)
    return False


def _binding(clause: str, line: str, head: str, comment_head: bool) -> bool:
    """A verdict binds to the head by its own clause's sha, else the line, else a Head label.

    A clause that names a different sha is bound to that sha: a later ``Head`` line
    or another sha on the same line cannot rebind it.
    """
    if _hex_tokens(clause):
        return names_head(clause, head)
    if _hex_tokens(line):
        return names_head(line, head)
    return comment_head


_MODEL_WORDS = re.compile(r"\b(?:codex|gemini|gpt|claude|opus|sonnet)\b", re.IGNORECASE)
_NEAREST_MODEL = re.compile(
    r"\b(?:codex|gemini|gpt|claude|opus|sonnet|cross-model)\b", re.IGNORECASE
)


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


def _not_run_label(line: str) -> bool:
    """The text carries a not-run word as its own status ("Codex: unavailable",
    "Codex review (queued)", "**Codex review awaiting**")."""
    plain = _plain(line, keep_parens=True).strip()
    return bool(_NOT_A_HEADER.search(_plain(line)) or _ASIDE_NOT_RUN.search(plain)) or _own_status(
        line
    )


def _split_label(prefix: str) -> tuple[str, str]:
    """Split at the first colon outside parentheses: (label, text after it). A parenthetical
    aside such as "(Gemini via agy, Codex out of credits)" stays inside the label (#2299)."""
    depth = 0
    for index, char in enumerate(prefix):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == ":" and depth == 0:
            return prefix[:index], prefix[index + 1 :]
    return prefix, ""


def _disabled_verdict_label(label_part: str) -> bool:
    """A label part that names a model and is disabled by a not-run word ("Codex (not run):")
    contributes no family to a verdict clause that follows it (#2308)."""
    return bool(_MODEL_WORDS.search(label_part)) and _not_run_label(label_part)


def _label_family(line: str) -> str | None:
    """Family named by a heading, bold label, ``Reviewer:`` line or ``<label>:`` prefix."""
    plain = _plain(line, keep_parens=True).strip()
    if _not_run_label(line):
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


def _stated_reject(text: str) -> bool:
    """A REJECT word whose clause does not negate, condition or quote it (#2992):
    "Round 17 (REJECT) is rebutted" states one, "r3 Codex did not REJECT" does not."""
    for match in _REJECT.finditer(text):
        splits = [m.end() for m in _CLAUSE_SPLIT.finditer(text, 0, match.start())]
        before = text[(splits[-1] if splits else 0) : match.start()]
        if not (_REJECT_PRE_DENY.search(_plain(before)) or _QUOTE.search(before)):
            return True
    return False


def _rebuttal_point(section: list[str], head: str) -> tuple[int, int] | None:
    """Where a cross-model REJECT at round >= 3 is followed (or joined) by a past-tense
    rebuttal: (offset of the rebuttal line in the section, the REJECT's round), else None.

    A later REJECT line that names the current head withdraws it: a rebuttal of an
    earlier round does not cover a fresh rejection of this head.
    """
    reject_round = 0
    point: tuple[int, int] | None = None
    for offset, line in enumerate(section):
        plain = _plain(line, keep_parens=True)
        rounds = [int(n) for n in _ROUND.findall(plain) if int(n) >= 3]
        if _stated_reject(plain) and rounds:
            if point is not None and names_head(plain, head):
                return None
            reject_round = max(reject_round, *rounds)
        if (
            reject_round
            and point is None
            and not _REBUTTAL_BUT_NOT.search(plain)
            and any(
                _REBUTTED.search(clause) and not _REBUTTAL_DENY.search(clause)
                for clause in _clauses(plain)
            )
        ):
            point = (offset, reject_round)
    return point


def _reject_match(clause: str) -> tuple[int, int] | None:
    match = _REJECT_POS.search(clause)
    if not match:
        return None
    group = 1 if match.group(1) else 2
    return match.start(group), match.end(group)


def _clause_family(
    clause: str,
    span: tuple[int, int] | None,
    plain_line: str,
    start: int,
    header_family: str | None,
    nearest: bool = False,
) -> str | None:
    """Reviewer family of a verdict clause: named before the token in the clause, else on
    the line before it ("Claude: r1 ..., r2 ACCEPT"), else the section header's. None when
    the label naming the model is disabled ("**Codex (not run)**: ACCEPT @ sha").

    ``nearest`` (a REJECT) takes the model named closest before the token instead, so
    "Claude ACCEPT at <sha>; Cross-model review (Gemini) REJECT at <sha>" rejects for
    the cross-model family only.
    """
    before = clause[: span[0]] if span else ""
    line_before = plain_line[: start + span[0]] if (span and start >= 0) else before
    label_part, status_part = _split_label(line_before)
    if _disabled_verdict_label(label_part) or (
        label_part != line_before
        and bool(_MODEL_WORDS.search(label_part))
        and len(status_part.split()) <= 4
        and bool(_NOT_A_HEADER.search(_plain(status_part)))
    ):
        return None
    if nearest:
        named = _NEAREST_MODEL.findall(line_before)
        if not named:
            return header_family
        return "cross_model" if named[-1].lower() == "cross-model" else _family(named[-1])
    return _family(before) or _family(line_before) or header_family


def standing_families(events: list[dict[str, Any]]) -> set[str]:
    """Reviewer families whose ACCEPT at the head still stands after later REJECTs (#2992).

    Events are in posting order (comments oldest first, lines top to bottom). A REJECT
    withdraws every earlier ACCEPT of its family except one from a later round
    (``r3 ACCEPT`` survives an ``r2 REJECT`` listed after it) and, inside one comment, an
    unnumbered ACCEPT ahead of a numbered round history ("Verdict: ACCEPT" then
    "r1: REJECT"). A later ACCEPT stands again.
    """
    accepts: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        family = event["family"]
        if event["kind"] == "accept":
            accepts.setdefault(family, []).append(event)
            continue
        reject_round = event["round"]

        def survives(accept: dict[str, Any], reject: dict[str, Any] = event) -> bool:
            if reject_round is None:
                return False
            if accept["round"] is None:
                return accept["comment"] == reject["comment"]
            return accept["round"] > reject_round

        accepts[family] = [a for a in accepts.get(family, []) if survives(a)]
    return {family for family, kept in accepts.items() if kept}


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
    labels = _head_labels(lines)
    verdicts: list[dict[str, Any]] = []
    events: list[tuple[tuple[int, int], dict[str, Any]]] = []
    rebuttals: list[tuple[tuple[int, int], dict[str, Any]]] = []
    section: list[str] = []
    section_start = 0
    header_family: str | None = None
    header_level = 0  # heading level that opened the section; 99 for a non-heading label

    def close_section() -> None:
        # A rebuttal at the cap is a cross-model event at its rebuttal line, so a later
        # REJECT of a later round withdraws it like an ACCEPT (#2992).
        point = _rebuttal_point(section, head) if header_family == "cross_model" else None
        if point is not None:
            event = {
                "family": "cross_model",
                "kind": "accept",
                "rebuttal": True,
                "round": point[1],
                "comment": 0,
                "line": section[point[0]].strip(),
            }
            rebuttals.append(((section_start + point[0], 1 << 30), event))

    for index, line in enumerate(lines):
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
            close_section()
            section, header_family = [], label  # "## Notes" opens a section with no family
        if not section:
            section_start = index
        section.append(line)
        comment_head = _label_binds(labels, index, head)
        plain_line = _plain(line, keep_parens=True)
        accept_clauses = verdict_clauses(line)
        line_events: list[tuple[int, dict[str, Any]]] = []
        for kind, clauses in (("accept", accept_clauses), ("reject", reject_clauses(line))):
            consumed = 0
            for clause in clauses:
                span = _verdict_match(clause) if kind == "accept" else _reject_match(clause)
                start = plain_line.find(clause, consumed)
                consumed = start + len(clause) if start >= 0 else consumed
                family = _clause_family(
                    clause, span, plain_line, start, header_family, nearest=kind == "reject"
                )
                if family and _binding(clause, line, head, comment_head):
                    rounds = _ROUND.findall(clause[: span[0]]) if span else []
                    event = {
                        "family": family,
                        "kind": kind,
                        "round": int(rounds[-1]) if rounds else None,
                        "comment": 0,
                        "line": clause.strip(),
                    }
                    line_events.append((start + (span[0] if span else 0), event))
        events.extend(((index, at), event) for at, event in line_events)
        verdicts.extend(e for _, e in line_events if e["kind"] == "accept")
        if not accept_clauses:
            continue
        close_section()
        section = []  # the header family persists: a reviewer block lists its rounds
    close_section()
    ordered = [event for _, event in sorted(events + rebuttals, key=lambda item: item[0])]
    standing = standing_families([e for e in ordered if not e.get("rebuttal")])
    return {
        "verdict": bool(verdicts),
        "claude": "claude" in standing,
        "cross_model": "cross_model" in standing,
        "rebuttal_at_cap": bool(rebuttals),
        "verdict_lines": [v["line"] for v in verdicts],
        "events": ordered,
    }


def _is_high_risk(name: str) -> bool:
    return name in HIGH_RISK_FILES or name.startswith(HIGH_RISK_PREFIXES)


def high_risk_paths(files: list[Any]) -> list[str]:
    """High-risk paths touched by the PR; a rename counts by its old name too.

    A list at the API's file cap may hide a high-risk path, so it counts as high-risk.
    """
    paths: set[str] = {TRUNCATED_FILES} if len(files) >= MAX_PR_FILES else set()
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


def rebuttal_counts(repo: str) -> bool:
    """Whether a rebuttal at the cap counts as a cross-model record for ``repo``."""
    return repo.strip().lower() not in NO_REBUTTAL_AT_CAP_REPOS


def _evidence_at(
    head: str, comments: list[Any], reviews: list[Any], allow_rebuttal: bool = True
) -> tuple[list[dict[str, Any]], bool, bool, int, set[str]]:
    """Records, stale flag, unbound flag, approved-review count and the reviewer families
    whose ACCEPT still stands at one head (comments in API order: oldest first)."""
    records: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    stale = False
    unbound = False
    for number, comment in enumerate(comments):
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
        if not allow_rebuttal:
            kept = [event for event in record["events"] if not event.get("rebuttal")]
            record = dict(record, rebuttal_at_cap=False, events=kept)
        events.extend(dict(event, comment=number) for event in record["events"])
        if record["verdict"] or record["rebuttal_at_cap"]:
            records.append(record)
        else:
            unbound = True
    standing = standing_families(events)
    return records, stale, unbound, approved_reviews_at_head(reviews, head), standing


def _contributes(
    head: str, comments: list[Any], reviews: list[Any], allow_rebuttal: bool = True
) -> tuple[bool, bool]:
    """(independent, cross_model) evidence a record at ``head`` provides."""
    records, _stale, _unbound, approved, standing = _evidence_at(
        head, comments, reviews, allow_rebuttal
    )
    return (
        approved > 0 or "claude" in standing,
        "cross_model" in standing,
    )


def evaluate(
    head: str,
    files: list[Any],
    comments: list[Any],
    reviews: list[Any],
    delta_verified: tuple[str, ...] = (),
    allow_rebuttal: bool = True,
) -> dict[str, Any]:
    """Pure classification of the PR's review evidence at ``head``.

    ``delta_verified`` lists older reviewed heads whose delta to ``head`` the caller has
    verified as merge-only (#2308); a record at one of those counts as a record at the head.
    The caller is the only place that may verify a delta; this function trusts nothing else.
    ``allow_rebuttal`` False (``rebuttal_counts(repo)``) drops rebuttals at the cap.
    """
    risky = high_risk_paths(files)
    records, stale, unbound, approved_reviews, standing = _evidence_at(
        head, comments, reviews, allow_rebuttal
    )
    # The independent record is the Claude-family review (or a submitted approval); a
    # cross-model record alone satisfies only the cross-model requirement. A family's
    # ACCEPT counts only while no later REJECT of that family at the head withdraws it.
    independent_head = approved_reviews > 0 or "claude" in standing
    cross_head = "cross_model" in standing  # a rebuttal at the cap is a cross-model event
    withdrawn = {
        event["family"]
        for record in records
        for event in record["events"]
        if event["kind"] == "accept"
    } - standing
    independent, cross_model = independent_head, cross_head
    delta_heads: list[str] = []
    for old in delta_verified:
        if old.lower() == head.lower():
            continue
        old_ind, old_cross = _contributes(old, comments, reviews, allow_rebuttal)
        used = (old_ind and not independent_head) or (old_cross and not cross_head and bool(risky))
        independent = independent or old_ind
        cross_model = cross_model or old_cross
        if used:
            delta_heads.append(old)
    short = head[:12]
    if not independent:
        status = "MISSING_RECORD"
        if "claude" in withdrawn:
            reason = f"a later Claude/Opus REJECT at head {short} withdraws its ACCEPT"
        elif stale:
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
        if "cross_model" in withdrawn:
            reason = f"a later Codex/Gemini REJECT at head {short} withdraws its ACCEPT"
        elif allow_rebuttal:
            reason = (
                f"high-risk paths changed but no Codex/Gemini verdict or rebuttal at head {short}"
            )
        else:
            reason = (
                f"high-risk paths changed but no Codex/Gemini ACCEPT verdict at head {short} "
                "(a rebuttal at the cap does not count for this repo)"
            )
    elif delta_heads:
        status = "OK"
        reason = (
            f"record at {', '.join(h[:MIN_PREFIX] for h in delta_heads)}, "
            f"merge-only delta verified (head {short})"
        )
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
        "delta_verified_heads": delta_heads,
        "status": status,
        "reason": reason,
    }


# -- merge-only delta (#2308) -----------------------------------------------------------

MAX_DELTA_COMMITS = 100  # compare returns at most 250 commits / 300 files; stay well inside
MAX_DELTA_FILES = 300
MAX_DELTA_CANDIDATES = 6
_FULL_SHA = re.compile(r"[0-9a-f]{40}")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,200}")


def _compare(
    fetch: Callable[[str, str], Any], base: str, token: str, left: str, right: str, page: int = 1
) -> dict[str, Any]:
    data = fetch(f"{base}/compare/{left}...{right}?per_page={PER_PAGE}&page={page}", token)
    if not isinstance(data, dict):
        raise CheckError("unexpected compare response shape")
    return data


def _names(entries: list[Any]) -> set[str]:
    """Every path an entry list touches, a rename by both names. Raises on a bad entry."""
    out: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
            raise CheckError("unexpected file entry")
        out.add(entry["filename"])
        previous = entry.get("previous_filename")
        if isinstance(previous, str):
            out.add(previous)
    return out


def _compare_files(
    fetch: Callable[[str, str], Any], base: str, token: str, left: str, right: str
) -> set[str]:
    """All paths changed between two commits; raises when the list may be truncated.

    The compare API returns up to 300 files on page 1 whatever ``per_page`` says and no
    ``files`` key on later pages, so only page 1 is read and 300 files means truncated.
    """
    files = _compare(fetch, base, token, left, right).get("files")
    if not isinstance(files, list) or len(files) >= MAX_DELTA_FILES:
        raise CheckError("compare file list missing or may be truncated")
    return _names(files)


def merge_only_delta(
    fetch: Callable[[str, str], Any],
    base: str,
    token: str,
    reviewed: str,
    head: str,
    pr_paths: set[str],
    base_ref: str,
) -> bool:
    """True only when ``head`` differs from the reviewed ``reviewed`` by merges of the base branch.

    Fails closed on any doubt (API error, truncation, odd shape). Requires: the compare is
    "ahead" with nothing behind and a complete commit list; the first-parent chain from the
    head reaches the reviewed commit through merge commits only; every other parent of those
    merges is already on the base branch (so every other commit in the range is too); and no
    path of the PR (as of the head, and as of the reviewed commit) changed in the range.
    """
    try:
        if not (_FULL_SHA.fullmatch(reviewed) and _FULL_SHA.fullmatch(head)) or reviewed == head:
            return False
        if not _REF.fullmatch(base_ref) or ".." in base_ref:
            return False
        data = _compare(fetch, base, token, reviewed, head)
        total = data.get("total_commits")
        commits = data.get("commits")
        if (
            data.get("status") != "ahead"
            or data.get("behind_by") != 0
            or not isinstance(commits, list)
            or not isinstance(total, int)
            or data.get("ahead_by") != total
            or not 1 <= total <= MAX_DELTA_COMMITS
            or len(commits) != total
        ):
            return False
        parents: dict[str, list[str]] = {}
        for commit in commits:
            sha = commit.get("sha") if isinstance(commit, dict) else None
            plist = commit.get("parents") if isinstance(commit, dict) else None
            if not isinstance(sha, str) or not isinstance(plist, list) or sha in parents:
                return False
            shas = [p.get("sha") if isinstance(p, dict) else None for p in plist]
            if not shas or not all(isinstance(x, str) and _FULL_SHA.fullmatch(x) for x in shas):
                return False
            parents[sha] = [str(x) for x in shas]
        if head not in parents:
            return False
        # First-parent spine from the head down to the reviewed commit: merge commits only.
        side_parents: list[str] = []
        spine = 0
        cursor = head
        while cursor != reviewed:
            plist = parents.get(cursor)
            if plist is None or len(plist) < 2 or spine >= total:
                return False
            side_parents.extend(plist[1:])
            cursor = plist[0]
            spine += 1
        if spine == 0:
            return False
        # Every non-first parent is already on the base branch, so is everything under it.
        for side in dict.fromkeys(side_parents):
            if side == reviewed:
                return False
            relation = _compare(fetch, base, token, base_ref, side, 1)
            if (
                relation.get("status") not in ("identical", "behind")
                or relation.get("ahead_by") != 0
            ):
                return False
        # The PR's paths as of the reviewed commit; the head must not add any (an "evil merge"
        # that keeps the reviewed tree reverts what the base gained, and the reverted file
        # shows up as a new PR path).
        pr_at_reviewed = _compare_files(fetch, base, token, base_ref, reviewed)
        if not pr_paths <= pr_at_reviewed:
            return False
        covered = pr_paths | pr_at_reviewed
        # What the base branch gained since the reviewed commit forked from it must not
        # touch a PR path either (the squash would otherwise land a silent revert of it).
        for side in dict.fromkeys(side_parents):
            if _compare_files(fetch, base, token, reviewed, side) & covered:
                return False
        return not (_compare_files(fetch, base, token, reviewed, head) & covered)
    except Exception:  # noqa: BLE001 - any doubt means the delta is not verified
        return False


def _delta_candidates(
    fetch: Callable[[str, str], Any],
    base: str,
    token: str,
    head: str,
    comments: list[Any],
    reviews: list[Any],
) -> list[str]:
    """Full shas of older heads that records or approved reviews name (newest first, capped)."""
    found: list[str] = []
    tokens: list[str] = []
    for review in reversed(reviews):
        commit = str(review.get("commit_id", "")).lower() if isinstance(review, dict) else ""
        if _FULL_SHA.fullmatch(commit) and commit != head:
            found.append(commit)
    for comment in reversed(comments):
        body = comment.get("body") if isinstance(comment, dict) else None
        if not isinstance(body, str):
            continue
        # A record names its head on a "Head reviewed:" line, apart from the verdict line.
        if any(is_verdict_line(line) for line in body.splitlines()):
            tokens.extend(t for t in _hex_tokens(body) if not head.startswith(t))
    for token_hex in dict.fromkeys(tokens):
        if len(found) >= MAX_DELTA_CANDIDATES:
            break
        try:
            commit = fetch(f"{base}/commits/{token_hex}", token)
            full = str(commit.get("sha", "")).lower() if isinstance(commit, dict) else ""
        except Exception:  # noqa: BLE001 - an unresolvable token is just not a candidate
            continue
        if _FULL_SHA.fullmatch(full) and full.startswith(token_hex) and full != head:
            found.append(full)
    return list(dict.fromkeys(found))[:MAX_DELTA_CANDIDATES]


def _verify_deltas(
    fetch: Callable[[str, str], Any],
    base: str,
    token: str,
    head: str,
    pull: Any,
    files: list[Any],
    comments: list[Any],
    reviews: list[Any],
    allow_rebuttal: bool = True,
) -> tuple[str, ...]:
    """Older reviewed heads that carry a record and differ from the head by a merge only."""
    try:
        base_obj = pull.get("base") if isinstance(pull, dict) else None
        base_ref = str(base_obj.get("ref", "")) if isinstance(base_obj, dict) else ""
        pr_paths = _names(files)
        verified = []
        for old in _delta_candidates(fetch, base, token, head, comments, reviews):
            if any(_contributes(old, comments, reviews, allow_rebuttal)) and merge_only_delta(
                fetch, base, token, old, head, pr_paths, base_ref
            ):
                verified.append(old)
        return tuple(verified)
    except Exception:  # noqa: BLE001 - fail closed
        return ()


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
        allow = rebuttal_counts(repo)
        report = evaluate(head, files, comments, reviews, allow_rebuttal=allow)
        if report["status"] != "OK":
            deltas = _verify_deltas(fetch, base, token, head, pull, files, comments, reviews, allow)
            if deltas:
                report = evaluate(head, files, comments, reviews, deltas, allow_rebuttal=allow)
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
