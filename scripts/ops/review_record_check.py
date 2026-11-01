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
  fenced code, pasted ``coord ready`` lines and lines with more than
  ``MAX_VERDICTS_PER_LINE`` verdict tokens are skipped.
- The verdict is *bound to the head* by its own sha (``ACCEPT@<sha>``, ``ACCEPT at
  [head] <sha>``), else when every sha in its clause (7+ hex characters, all-digit
  ones too) is a prefix of the head, else every sha on its line, else when the comment
  names the head (at least ``MIN_PREFIX`` characters) and has a ``Head`` label naming it
  (``Head reviewed: <sha>``, ``final head <sha>``). A clause or line that also names
  another commit binds nothing. When the comment's Head labels name different commits,
  only the nearest label above the verdict binds it (#2992).
- The *reviewer family* comes from the words before the token in its clause, else
  from the header of its section (a heading, bold label or ``Reviewer:`` line):
  ``claude``/``opus``/``sonnet``, or cross-model ``codex``/``gemini``/``gpt``. When
  both appear, the family is Claude. A verdict with no family is not a record.
- A later *REJECT* (or ``REPAIR_REQUIRED`` / ``REQUEST_CHANGES``) in verdict position at
  the head withdraws the earlier ACCEPTs of its reviewer family (the model named closest
  before it, else its section's), in the same comment or a later one, unless it says it
  was resolved (``fixed``, ``rebutted``) or an ACCEPT is from a later round by the same
  model in the same numbering (a round 1 in a later comment starts a new one, #3041);
  a later ACCEPT stands again (#2992). REJECTs fail closed: one is about the head
  unless its own label binds it to another commit (``r1 @<old>: REJECT``), a hex-looking
  word in the finding never unbinds it, a 7-character head prefix binds it, and it is
  read in table rows, quotes, fenced and indented code too.
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
  A repo in ``REPO_HIGH_RISK_PREFIXES`` adds its own high-risk paths (cairnwork:
  ``src/``, ``scripts/``, ``REVIEW.md``).
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
import bisect
import itertools
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
# A line with more verdict tokens than this is not a record line; skipping it keeps
# parsing linear on a crafted comment (#2992).
MAX_VERDICTS_PER_LINE = 64
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
# Repo-specific high-risk paths on top of the lists above, keyed like
# NO_REBUTTAL_AT_CAP_REPOS (#2994). cairnwork: the HIGH tier of its AGENTS.md "Review
# speed and risk tiers" that a path can express (experimental/, docs/, tests/ are LOW).
REPO_HIGH_RISK_PREFIXES: dict[str, tuple[str, ...]] = {
    "cairnwork/cairnwork": ("src/", "scripts/"),
}
REPO_HIGH_RISK_FILES: dict[str, frozenset[str]] = {
    "cairnwork/cairnwork": frozenset({"REVIEW.md"}),
}

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
# Tried when _REJECT_POS finds nothing: after a dash, arrow or full-width colon that
# follows a closed label aside ("(Opus, separate agent) — REJECT", "(high)—REJECT"; the
# clause split at ") " leaves it at the clause start), an arrow after a space ("Codex r2
# → REJECT") or a full-width colon (#3041 r15). A hyphen at the start of a line is a
# list bullet, not a position (_reject_clause_starts).
_REJECT_POS_MORE = re.compile(
    rf"(?:^\s*(?:[\-–—]|→|->|=>|：)\s*|\)\s*(?:[\-–—]|→|->|=>|：)\s*|\s(?:→|->|=>)\s*|：\s*)"
    rf"({_REJECT_TOKEN})\b"
)
_REJECT_PRE_DENY = re.compile(
    r"\b(?:no|not|never|none|nothing|if|unless|whether|would|could|might|may|should|cannot"
    r"|can't|didn't|doesn't|won't|wouldn't|without|avoid|prevent|instead of)\b",
    re.IGNORECASE,
)
_RESOLUTION_WORD = (
    r"(?:fixed|rebutted|addressed|resolved|superseded|withdrawn|retracted|overturned"
    r"|dismissed|overridden|cleared|triaged|non-defects?|false[- ]positives?|disputed|declined"
    r"|deferred|waived|moot|answered|out of scope)"
)
# A resolution word right after one of these is still open ("not fixed yet", "will be
# addressed", "needs to be fixed").
_UNRESOLVED = re.compile(
    r"\b(?:not|no|never|yet|will|would|to be|needs?|pending|un)(?:\W+be(?:ing)?)?\W*$", re.I
)
_ANY_VERDICT_TOKEN = re.compile(rf"\b(?:{_TOKEN}|{_REJECT_TOKEN})\b")
# What may stand between the previous verdict on the line (or its start) and a REJECT
# for it to be a reviewer's verdict: reviewer labels, round markers and shas only. A
# finding that quotes a gate's verdict value ("a tampered receipt: REJECT") is not one.
_REJECT_LABEL_WORDS = frozenset({
    "independent",
    "cross-model",
    "adversarial",
    "review",
    "reviewer",
    "re-review",
    "verdict",
    "final",
    "latest",
    "round",
    "on",
    "at",
    "head",
    "sha",
    "commit",
    "delta",
    "full",
    "diff",
    "addendum",
    "pr",
    "the",
    "result",
    "status",
    "outcome",
})
# More label words before a REJECT: a status the label carries ("**Codex r2 fix in
# progress**: REJECT", #3004) and a model's tier ("Codex gpt-5.5 xhigh", "Gemini 3.1 Pro",
# "Gemini 3.8 Flash High via agy"; versions are in _REJECT_LABEL_WORD, r5 R5).
_REJECT_LABEL_EXTRA = frozenset({
    "fix",
    "fixes",
    "fixing",
    "in",
    "progress",
    "in-progress",
    "pending",
    "queued",
    "running",
    "now",
    "pro",
    "flash",
    "high",
    "xhigh",
    "low",
    "medium",
    "max",
    "mini",
    "nano",
    "ultra",
    "lite",
    "fast",
    "thinking",
    "preview",
    "via",
    "agy",
    "cli",
    "exec",
    "substitute",
})
_REJECT_LABEL_WORD = re.compile(
    r"(?:codex|gemini|gpt|claude|opus|sonnet)[a-z0-9.-]*|r?\d{1,3}[a-z]?|[0-9a-f]{7,40}"
    r"|[0-9a-f]{7,40}\.\.\.?[0-9a-f]{7,40}"
    r"|v?\d{1,3}(?:\.\d{1,3}){1,3}[a-z]{0,8}"
)
# What may NOT follow the token: a verb or noun that makes it a value in prose ("REJECT is
# returned", "REJECT items:", "CHANGES_REQUESTED reviews are ignored", "the r1 REJECT
# finding", "r1 REJECT then r2 ACCEPT", "REJECT / nit 1"). Anything else, a reason word
# included ("REJECT path traversal ..."), leaves it a verdict: an unread REJECT lets an
# ACCEPT stand, so the list holds only words honest records were seen to use and a new
# wording fails closed.
_REJECT_NOT_AFTER = re.compile(
    r"\s+(?:is|was|are|were|be|been|being|items?|reviews?|findings?|then)\b|\s*/",
    re.IGNORECASE,
)
# What main read after the token before #3038 (end, punctuation, a sha binding, a
# parenthesis). A REJECT read only because of the wider rule above, or placed on the head
# only by _reject_label_binds, is "weak": main never read it, so a later answer or a
# later "fixed in <sha>" on its line may close it without ever being looser than main.
_REJECT_AFTER_PUNCT = re.compile(r"\s*(?:$|[.:;,!)\]\-\u2013\u2014(@]|at\b|on\b)")
_LATER_FIX = re.compile(rf"\b{_RESOLUTION_WORD}\s+(?:in|by|at)\s+[0-9a-f]{{7,40}}\b", re.IGNORECASE)
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
_POST_NOT = re.compile(r"^\s*not\b", re.IGNORECASE)  # "ACCEPT not given yet" (#3041)
# A withdrawal right after the token, past its own sha and any punctuation, dash or
# opening parenthesis: "ACCEPT withdrawn", "ACCEPT at <sha> (retracted)", "ACCEPT — no
# longer stands" (#3041). Participles only: "ACCEPT; withdraws the r1 finding" is not one,
# and neither is one used as an adjective ("withdrawn findings: none", "denied-path tests").
_POST_WITHDRAWN = re.compile(
    r"\s*(?:(?:@|\bat\b|\bon\b)\s*[0-9a-f]{7,40}\b)?[\s.,;:!\-\u2013\u2014(\[]*"
    r"(?:withdrawn|revoked|retracted|rescinded|denied"
    r"|no\s+longer\s+(?:stands?|holds?|valid|applies|counts?))\b"
    r"(?=\s*(?:$|[^\w\s-]|(?:by|after|because|due|since|as|in|for|until|per|pending)\b))",
    re.IGNORECASE,
)
# Struck-through text (GitHub ``~~text~~`` or ``~text~``, ``<del>``, ``<s>``, ``<strike>``)
# is withdrawn: an ACCEPT inside it is not read. A REJECT inside it still is (fail closed).
_STRIKE_MARK = re.compile(r"(?<!~)~{1,2}(?!~)|<(/?)(del|s|strike)\b[^<>]{0,200}>", re.IGNORECASE)
_POST_COND = re.compile(
    r"\b(?:only if|if|unless|provided|conditional on|once|when)\b|\?", re.IGNORECASE
)
_REBUTTED = re.compile(r"\brebutted\b|\brebuttals? (?:accepted|stands?)\b", re.IGNORECASE)
_REBUTTAL_DENY = re.compile(
    r"\b(?:not|nothing|never|none|no|un-?rebutted|without)\b", re.IGNORECASE
)
_ROUND = re.compile(r"\b(?:r|round\s*)(\d+)\b", re.IGNORECASE)
_ROUND_ONE = re.compile(r"\b(?:r|round\s*)0*1\b", re.IGNORECASE)
_CLAUDE = re.compile(r"\b(?:claude|opus|sonnet)\b", re.IGNORECASE)
_CROSS = re.compile(r"\b(?:codex|gemini|gpt)\b", re.IGNORECASE)


def _head_bind(min_len: int) -> re.Pattern[str]:
    return re.compile(rf"\bhead\b[^\n]{{0,48}}?(?<![0-9a-f])([0-9a-f]{{{min_len},40}})(?![0-9a-f])")


_HEAD_BIND = _head_bind(MIN_PREFIX)
# A Head label proper, at the start of its line or in a heading ("Head reviewed: <sha>",
# "- final head <sha>", "Reviewed commit <sha>", "## Review record — head <sha>"), not
# prose that mentions a head ("re-review after fixes from head <sha>"). Whitespace runs
# are bounded so a long line cannot make the match quadratic.


def _head_label(min_len: int) -> re.Pattern[str]:
    return re.compile(
        r"^[ \t]{0,4}(?:#{1,6}[ \t][^\n]{0,200}?\bhead"
        r"|(?:[-*+][ \t]{1,4}|\d{1,3}\.[ \t]{1,4})?(?:(?:final|current|new)[ \t]{1,4})?"
        r"(?:head(?:[ \t]{1,4}(?:reviewed|sha|commit|is|was|now|at)){0,3}"
        r"|reviewed[ \t]{1,4}(?:head|commit)))"
        rf"[ \t]{{0,4}}[:=@]?[ \t]{{0,4}}(?<![0-9a-f])([0-9a-f]{{{min_len},40}})(?![0-9a-f])"
    )


_HEAD_LABEL = _head_label(MIN_PREFIX)
# A REJECT is bound by a Head label naming 7+ characters (the GitHub UI's short sha).
_HEAD_BIND_SHORT = _head_bind(7)
_HEAD_LABEL_SHORT = _head_label(7)
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
    tokens = set(_hex_tokens(text)) | set(_SHORT_SHA.findall(text.lower()))
    return any(not head.startswith(token) for token in tokens)


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


def _aside_closes(text: str) -> list[int | None]:
    """Per position, the index of the ``)`` closing the outermost parenthetical it lies in.

    One pass over the line; None where no parenthetical encloses the position or the
    outermost one never closes on the line. Nested asides are read as part of the
    outermost one, so each aside is checked once.
    """
    opens: list[int] = []
    enclosing: list[int | None] = []
    close_of: dict[int, int] = {}
    for index, char in enumerate(text):
        enclosing.append(opens[0] if opens else None)
        if char == "(":
            opens.append(index)
        elif char == ")" and opens:
            close_of[opens.pop()] = index
    return [None if at is None else close_of.get(at) for at in enclosing]


def _reject_aside_closes(text: str) -> list[int | None]:
    """``_aside_closes`` for reading a REJECT: a ``)`` with no ``(`` before it on the line
    also closes an aside that a manual line break carried over from the line above
    ("(Opus, separate agent,\\nnot the author): REJECT", #3041 r15), so the text before it
    is blanked like any closed aside."""
    closes = _aside_closes(text)
    first_open = text.find("(")
    stray = text.find(")")
    if stray >= 0 and (first_open < 0 or stray < first_open):
        for index in range(stray):
            closes[index] = stray
    return closes


# The only "only" that names the scope reviewed: the aside holds nothing after its round
# marker but one fixed phrase, "docs-only", "test-only", "typing-only" or "delta-only"
# (optionally followed by "delta"), or "delta only <sha>..<sha>". Any other "only"
# denies as on main.
_SCOPE_ONLY_ASIDE = re.compile(
    r"(?i:r\d+|round\s*\d+)\s*(?:[,;:]\s*)?"
    r"(?:(?:docs|test|typing|delta)-only(?:\s+delta)?|delta\s+only\s+[0-9a-f]{7,40}\.\.[0-9a-f]{7,40})\s*"
)
# A condition anywhere in the aside keeps every "only" in it a denial.
_ASIDE_COND = re.compile(
    r"\b(?:if|unless|provided|conditional\w*|once|when|after|with|subject|as\s+long\s+as|till"
    r"|until|upon|assuming|on\s+condition)\b|\?",
    re.IGNORECASE,
)


def _aside_denies(aside: str) -> bool:
    """Whether the part of a label aside from its round marker on denies the verdict.

    The same words deny here as in the window, with two exceptions that misread honest
    records: an ``only`` when the aside holds nothing after its round marker but a fixed
    scope phrase (_SCOPE_ONLY_ASIDE; any other ``only`` still denies, "only once CI is
    green", "for merge only"), and an apostrophe ("round 3's items") in an aside stating no
    condition (_ASIDE_COND), which is no quote. Double quotes, REJECT words, a negative ``Verdict:`` and
    every other denial still deny (#3040).
    """
    text = _plain(aside, keep_parens=True)
    if _REJECT.search(text) or _VERDICT_NEGATIVE.search(text) or re.search('["\u201c\u2018]', text):
        return True
    if _ASIDE_COND.search(text) and _QUOTE.search(text):
        return True  # the apostrophe is exempt only in an aside stating no condition
    return any(
        match.group() != "only" or not _SCOPE_ONLY_ASIDE.fullmatch(text)
        for match in _PRE_DENY.finditer(text)
    )


def _struck_spans(text: str) -> list[tuple[int, int]]:
    """Spans of struck-through text on one line, in one pass (no backtracking).

    A tilde run opens when the next character is not a space and the previous one is not
    a word character, and closes the nearest open run of the same length when the
    previous character is not a space and the next one is not a word character ("~2 min,
    ~500 tests" and "2~3 rounds" strike nothing). A tag closes the nearest open tag of its
    name. Openers inside a closed span are dropped.
    """
    spans: list[tuple[int, int]] = []
    opened: dict[str, list[int]] = {"~": [], "~~": [], "del": [], "s": [], "strike": []}
    for match in _STRIKE_MARK.finditer(text):
        begin, end = match.span()
        if match.group(2) is not None:
            key = match.group(2).lower()
            if not match.group(1):
                opened[key].append(begin)
                continue
        else:
            key = match.group()
            prev = text[begin - 1] if begin else " "
            nxt = text[end] if end < len(text) else " "
            closes = bool(opened[key]) and not prev.isspace() and not (nxt.isalnum() or nxt == "_")
            if not closes:
                if not nxt.isspace() and not (prev.isalnum() or prev == "_"):
                    opened[key].append(begin)
                continue
        if opened[key]:
            start = opened[key].pop()
            spans.append((start, end))
            for stack in opened.values():  # openers are in position order: drop inner ones
                while stack and stack[-1] > start:
                    stack.pop()
    return spans


def verdict_clauses(line: str, keep_withdrawn: bool = False) -> list[str]:
    """Clauses of the line whose accepting token sits in verdict position.

    The token must follow ``Verdict:``, ``@``, a colon or dash, a round marker
    (``r3``, ``Round 2 @ sha:``) or start the line; nothing before it in the
    clause may be a wish, condition or negation (``awaiting``, ``should``, ``not``,
    ``cannot``, ``pending``, ``please``, ``if`` ...), and nothing right after it may
    withdraw it (``pending``, ``withheld``, ``only if``, ``?``, ``withdrawn``,
    ``retracted``). Table rows, block quotes, unticked checklist items, pasted commands
    and struck-through text never count. ``keep_withdrawn`` reads a withdrawn or struck
    ACCEPT as before #3041, for the parse structure (section breaks and label lines), which
    a withdrawal must not change.
    """
    return [clause for clause, withdrawn in _verdict_reads(line) if keep_withdrawn or not withdrawn]


def _verdict_reads(line: str) -> list[tuple[str, bool]]:
    """``verdict_clauses`` as before #3041, each with whether it is withdrawn or struck
    through: a withdrawal never changes how the other clauses on the line are read."""
    if _SKIP_LINE.match(line):
        return []
    out: list[tuple[str, bool]] = []
    plain_line = _plain(line, keep_parens=True)
    if len(_ANY_VERDICT_TOKEN.findall(plain_line)) > MAX_VERDICTS_PER_LINE:
        return []
    consumed = 0
    prev_token_end = 0
    aside_closes: list[int | None] | None = None
    struck = _struck_spans(plain_line)
    for clause in _clauses(plain_line):
        start = plain_line.find(clause, consumed)
        consumed = start + len(clause) if start >= 0 else consumed
        span = _verdict_match(clause)
        if span is None:
            continue
        token_at = start + span[0]
        withdrawn = any(begin <= token_at < end for begin, end in struck)  # "~~ACCEPT~~"
        window_start = prev_token_end
        asides: dict[int, int] = {}  # closing index -> start of its last round marker
        for marker in _ROUND_MARKER.finditer(plain_line, prev_token_end, token_at):
            if aside_closes is None:
                aside_closes = _aside_closes(plain_line)
            # A marker inside a parenthetical is part of that aside ("(Round 3, delta only
            # <a>..<b>): ACCEPT", #3040): starting the window there would cut the aside open
            # and read its scope words as the verdict's own. The aside's words from its last
            # marker on ("(round 1 REJECT, round 2)") are still checked, by _aside_denies.
            aside_end = aside_closes[marker.start()]
            if aside_end is not None:
                asides[aside_end] = marker.start()
                continue
            window_start = marker.start()  # "r1 ... with one should-fix, r2 ACCEPT": new round
            asides = {}
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
        if any(_aside_denies(plain_line[at:close]) for close, at in asides.items()):
            continue  # "(r2 not fixed): ACCEPT": a denial inside the aside still denies
        if _VERDICT_NEGATIVE.search(line_before) or _REJECT.search(_plain(clause[span[1] :])):
            continue  # "Verdict: REJECT — ACCEPT after the fixes" is a rejection
        head_of_after = _STOP.split(after, 1)[0]
        if _POST_DENY.match(head_of_after) or _POST_COND.search(head_of_after):
            continue
        # "ACCEPT withdrawn — found a data-loss bug", "ACCEPT (retracted)", "ACCEPT not given"
        withdrawn = withdrawn or bool(_POST_NOT.match(head_of_after))
        withdrawn = withdrawn or (
            start >= 0 and bool(_POST_WITHDRAWN.match(plain_line, start + span[1]))
        )
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
        out.append((clause, withdrawn))
    return out


def is_verdict_line(line: str) -> bool:
    return bool(verdict_clauses(line))


def _outside_closed_asides(text: str, start: int, end: int, closes: list[int | None] | None) -> str:
    """``text[start:end]`` with every parenthetical that closes before ``end`` blanked,
    including one that opened before ``start``; ``closes`` is ``_aside_closes(text)``."""
    if closes is None:
        return text[start:end]
    out = []
    for index in range(start, end):
        close = closes[index]
        if close is None and text[index] == "(" and index + 1 < len(closes):
            close = closes[index + 1]  # an outermost "(" is not inside its own aside
        out.append(" " if close is not None and close < end else text[index])
    return "".join(out)


_LABEL_START = re.compile(
    r"\b(?:codex|gemini|gpt|claude|opus|sonnet|cross-model|cross-family)[a-z0-9.-]*"
    r"|[.!?](?:\s+|$)|\u3002\s*|(?=\b(?i:verdict)\s*:)",
    re.IGNORECASE,
)


def _label_start(window: str) -> int:
    """Where a REJECT's label starts in the window before it: after the last model name
    (with its version, "gpt-5.5-codex"), after the last sentence end, or at the last
    ``Verdict:``."""
    found = list(_LABEL_START.finditer(window))
    return found[-1].end() if found else 0


def _denies_reject(before: str) -> bool:
    """A negation, condition or quote before a REJECT token in its clause."""
    return bool(_REJECT_PRE_DENY.search(_plain(before)) or _QUOTE.search(before))


def _reject_label_only(prefix: str) -> bool:
    """The text before a REJECT holds reviewer labels, round markers and shas only."""
    words = re.findall(r"[a-z0-9][a-z0-9.-]*", _plain(prefix).lower())
    return all(
        word.rstrip(".") in _REJECT_LABEL_WORDS
        or word.rstrip(".") in _REJECT_LABEL_EXTRA
        or _REJECT_LABEL_WORD.fullmatch(word.rstrip("."))
        for word in words
    )


def _resolved_after(text: str, start: int, end: int) -> bool:
    """A status word immediately after a REJECT, not ordinary finding prose."""
    tail = text[start:end]
    tail = re.sub(r"^\s*(?:@|\bat\s+)[0-9a-f]{7,40}\b", "", tail, count=1, flags=re.I)
    tail = re.sub(  # "REJECT at <sha> (why): fixed"; "(fixed ...)" itself is kept
        rf"^\s*\((?!\s*{_RESOLUTION_WORD}\b)[^()]{{0,300}}\)", "", tail, count=1, flags=re.I
    )
    match = re.match(
        rf"\s*(?:[,.:;—–-]\s*|(?:→|->|=>)\s*)?\(?\s*({_RESOLUTION_WORD})(?![\w-])"
        rf"(?=\s*(?:$|[,.;:)(—–→]|-\s|->|=>|(?:in|at|by|as|with|per|via|see|after|before"
        rf"|because|since|to|on|and|all|both|it|them)\b))",
        tail,
        re.I,
    )
    return bool(match and not _UNRESOLVED.search(tail[: match.start(1)]))


def _reject_view(line: str) -> str:
    """The line as read for a REJECT: block-quote markers and an unticked checkbox removed,
    table cell borders read as ``:`` separators."""
    text = re.sub(r"^\s*(?:>\s?)+", "", line)
    text = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+\[ \]\s*", "", text)
    if text.lstrip().startswith("|"):
        text = text.replace("|", " : ")
    return text


def reject_clauses(line: str) -> list[str]:
    """Clauses of the line that carry an open rejecting verdict (#2992).

    The token (``REJECT``, ``REPAIR_REQUIRED``, ``REQUEST_CHANGES``, ``CHANGES_REQUESTED``)
    sits in the same verdict positions as an accepting one and reads as a reviewer's
    verdict: only reviewer labels, round markers and shas stand between it and the
    previous verdict on the line (or the line start), and only punctuation, a sha
    binding or a parenthesis follows it ("**Codex**: r2 REJECT — data loss",
    "r3 @<sha>: REJECT"); so may a reason ("REJECT because ...", "REJECT with two
    findings"), only a word that makes it a value in prose may not. It is not negated,
    conditional or quoted, and nothing from it to the next verdict on the line says it
    was resolved (``r1 REJECT (fixed)``, ``REJECT, rebutted``; "not fixed yet" is not
    resolved). A gate's verdict value in a
    finding ("a tampered receipt: REJECT", "REJECT is returned") and a history heading
    ("Round 1 (<sha>) REJECT items:") are not verdicts. Lines skipped for accepting
    verdicts are read here (r5 R6): a REJECT in a table row (``| Gemini | r1 | REJECT |``,
    cells read as ``:``-separated), a block quote, an unticked checklist item or indented
    code is still a rejection, so a missed one can never let an ACCEPT stand.
    """
    return [clause for clause, _start in _reject_clause_starts(line)]


def _reject_clause_starts(line: str, more: bool = True) -> list[tuple[str, int]]:
    """reject_clauses with each clause's start in ``_plain(_reject_view(line), keep_parens=True)``.

    The caller places the token by this start: finding the clause text again would land on
    an earlier, unread clause of the same text and judge the REJECT there (#3039).
    ``more`` False reads only as main did before #3041 r15; with it, a clause main's
    reading skips is read again with the positions in ``_REJECT_POS_MORE`` and a label
    aside carried over a line break (``_reject_aside_closes``).
    """
    out: list[tuple[str, int]] = []
    plain_line = _plain(_reject_view(line), keep_parens=True)
    tokens = [(m.start(), m.end()) for m in _ANY_VERDICT_TOKEN.finditer(plain_line)]
    if len(tokens) > MAX_VERDICTS_PER_LINE:
        return []
    starts = [start for start, _end in tokens]
    consumed = 0
    closes: dict[bool, list[int | None] | None] = {}

    def reads(clause: str, start: int, match: re.Match[str], extended: bool) -> bool:
        token_start = match.start(1) if match.group(1) else match.start(2)
        token_end = match.end(1) if match.group(1) else match.end(2)
        at, end = start + token_start, start + token_end
        # Each check below has two readings, main's and one that blanks every label aside
        # closing before the token (nested ones included); the REJECT is read when either
        # reading reads it, so nothing main read is dropped (fail closed).
        # Denial: the clause may start inside an aside that closes before the token ("(Opus,
        # separate agent, not the author): REJECT"); the aside's words are not the verdict's,
        # as for an accepting verdict, whose window drops parentheticals.
        if extended not in closes:
            if extended:
                found = "(" in plain_line or ")" in plain_line
                closes[extended] = _reject_aside_closes(plain_line) if found else None
            else:
                closes[extended] = _aside_closes(plain_line) if "(" in plain_line else None
        aside_closes = closes[extended]
        before = _outside_closed_asides(plain_line, start, at, aside_closes)
        if _denies_reject(clause[:token_start]) and _denies_reject(before):
            return False
        index = bisect.bisect_left(starts, at)
        window_start = max(tokens[index - 1][1] if index > 0 else 0, at - 400)
        # (the 400 cap keeps the scan linear on a very long line)
        # Label: from the last model named before it ("After the rebase, Codex r3 on head
        # <sha>:"), else from the previous verdict or the line start; in the blanked reading
        # also from a sentence end or a "Verdict:" label, since what an earlier sentence says
        # is not this verdict's label ("(Gemini via agy, dispatched by the desk (review lane),
        # task X): REJECT", "One finding. Verdict: REJECT").
        window = _plain(plain_line[window_start:at])
        models = list(_NEAREST_MODEL.finditer(window))
        if not _reject_label_only(window[models[-1].end() :] if models else window):
            window = _plain(_outside_closed_asides(plain_line, window_start, at, aside_closes))
            if not _reject_label_only(window[_label_start(window) :]):
                return False
        if _REJECT_NOT_AFTER.match(plain_line, end):
            return False
        following = starts[index + 1] if index + 1 < len(starts) else len(plain_line)
        return not _resolved_after(plain_line, end, following)

    for clause in _clauses(plain_line):
        start = plain_line.find(clause, consumed)
        consumed = start + len(clause) if start >= 0 else consumed
        if start < 0:
            continue
        match = _REJECT_POS.search(clause)
        if match and reads(clause, start, match, extended=False):
            out.append((clause, start))
            continue
        if not more:
            continue
        if match is None:
            match = _REJECT_POS_MORE.search(clause)
            if (
                match
                and re.match(r"\s*-(?!>)", clause[match.start() :])
                and not plain_line[:start].strip()
            ):
                continue  # "- REJECT ...": a list bullet at the line start, as before
        if match and reads(clause, start, match, extended=True):
            out.append((clause, start))
    return out


def _head_labels(lines: list[str], short: bool = False) -> list[tuple[list[str], str | None]]:
    """Per line: every sha a loose ``head ... <sha>`` mention names, and the sha its first
    Head label proper names (``Head reviewed: <sha>``, ``final head <sha>``) or None.
    A parenthetical is neither. ``short`` reads shas of 7+ characters (for a REJECT)."""
    bind, label = (_HEAD_BIND_SHORT, _HEAD_LABEL_SHORT) if short else (_HEAD_BIND, _HEAD_LABEL)
    out: list[tuple[list[str], str | None]] = []
    for line in lines:
        text = _plain(line).lower()
        strict = label.search(text)
        out.append((bind.findall(text), strict.group(1) if strict else None))
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


def _reject_label_binds(labels: list[tuple[list[str], str | None]], index: int, head: str) -> bool:
    """Whether a REJECT on line ``index`` whose own label names no commit is about the head.

    Fail closed: it is, unless the comment's Head labels place it on another commit. The
    nearest Head label proper above it decides; with none above, a loose ``head <sha>``
    mention that never names the head places it elsewhere. A comment that names the head
    only outside Head labels (``ACCEPT@<sha>``, prose) leaves its bare REJECT at the head:
    only comments that name the head reach this parse.
    """
    head = head.lower()
    for _loose, label in reversed(labels[: index + 1]):
        if label is not None:
            return head.startswith(label)
    loose = [found for found_on_line, _label in labels for found in found_on_line]
    return not loose or any(head.startswith(found) for found in loose)


def _bound_after(clause: str, span: tuple[int, int], prose_ok: bool = True) -> str | None:
    """The sha the token itself is bound to (``ACCEPT@<sha>``, ``REJECT at [head] <sha>``).

    ``prose_ok`` False (a REJECT): after ``at``/``on`` the sha must end the binding
    (end, punctuation, a parenthesis or a dash), so "REJECT on ed25519 verification" or
    "REJECT at deadbeef sentinel handling" names a finding, not a commit.
    """
    match = _BOUND_AFTER.match(clause, span[1])
    if match is None:
        return None
    if not prose_ok and match.group(1) != "@" and not _BOUND_END.match(clause, match.end()):
        return None
    return match.group(2).lower()


def _sha_tokens(text: str) -> list[str]:
    """Shas the text names: every run of 7-40 hex characters, all-digit ones too, except a
    7-8 digit count followed by its unit ("317 passed, 1234567 assertions"). Fail closed:
    a token that may be a sha is one."""
    text = text.lower()
    return [
        match.group(1)
        for match in _ANY_SHA.finditer(text)
        if not (len(match.group(1)) <= 8 and _COUNT_UNIT.match(text, match.end()))
        or re.search(r"[a-f]", match.group(1))
    ]


def _binding(
    clause: str, span: tuple[int, int] | None, line: str, head: str, comment_head: bool
) -> bool:
    """An ACCEPT binds to the head by its own sha, else its clause, else its line, else a
    Head label.

    ``ACCEPT@<sha>`` / ``ACCEPT at <sha>`` decides alone. Otherwise every sha in the
    clause, else on the line, must be the head's (``_sha_tokens``: any 7+ hex run,
    all-digit too): a clause or line that also names another commit ("ACCEPT — reviewed
    <old>, head is now <head>") is ambiguous and binds nothing (r5 R3, R7). Only a line
    with no sha-like token at all borrows the comment's Head label.
    """
    head = head.lower()
    own = _bound_after(clause, span) if span else None
    if own is not None:
        return head.startswith(own)
    for text in (clause, line):
        found = _sha_tokens(text)
        if found:
            return all(head.startswith(token) for token in found)
    return comment_head


def _label_sha_binds(label: str, match: re.Match[str]) -> bool:
    """Whether a sha in a REJECT's label binds it to that commit: after ``@``/``at``/``on``/
    ``head``/``commit``/``sha``; or, for a sha with a letter a-f, alone in a parenthetical
    ("Round 1 (<sha>):") or ending the label ("r2 <sha>: REJECT"). A word in an aside
    ("(ed25519 signer)") or a bare all-digit word binds nothing (fail closed)."""
    before, after = label[: match.start()], label[match.end() :]
    if _LABEL_SHA_BEFORE.search(before):
        return True
    if not re.search(r"[a-f]", match.group(1)):
        return False
    if re.search(r"\(\s*$", before) and re.match(r"\s*\)", after):
        return True
    return bool(re.match(r"\s*(?:[:\]]|$)", after))


def _reject_binding(
    clause: str, span: tuple[int, int], line: str, head: str, comment_head: bool
) -> bool:
    """A REJECT is about the head unless its label binds it to another commit (fail closed).

    Only a sha in binding position binds it elsewhere: right after the token
    (``REJECT@<sha>``, ``REJECT at <sha>.``) or in its label after the last model name
    (``r2 @<sha>: REJECT``, ``Round 1 (<sha>): REJECT``). A hex-looking word in the
    finding ("the ed25519 signature", "same bug as fix 1a2b3c4d") never unbinds it (r5
    R1). Otherwise it is about the head when its line names the head anywhere (7+
    characters, all-digit too, r5 R2), else when the comment's Head labels bind it.
    """
    head = head.lower()
    own = _bound_after(clause, span, prose_ok=False)
    if own is not None:
        return head.startswith(own)
    label = _plain(clause[: span[0]], keep_parens=True).lower()  # "Round 1 (<sha>): REJECT"
    models = list(_NEAREST_MODEL.finditer(label))
    label = label[models[-1].end() :] if models else label
    found = list(_ANY_SHA.finditer(label))
    if any(head.startswith(match.group(1)) for match in found):
        return True
    if any(_label_sha_binds(label, match) for match in found):
        return False
    return names_head_loosely(line, head) or comment_head


# Any 7-40 hex characters, all-digit runs included: what a short sha may look like.
_ANY_SHA = re.compile(r"(?<![0-9a-f])([0-9a-f]{7,40})(?![0-9a-f])")
_LABEL_SHA_BEFORE = re.compile(r"(?:@|\b(?:at|on|head|commit|sha))\s*:?\s*$")
# A count's unit after a 7-8 digit number: not a sha.
_COUNT_UNIT = re.compile(
    r"\s+(?:tests?|assertions?|passed|failed|errors?|lines?|bytes?|files?|rows?|runs?"
    r"|items?|cases?|mutants?|tokens?|chars?|characters?|seconds?|ms|calls?|records?)\b"
)
_BOUND_AFTER = re.compile(
    r"\s*(@|at\b|on\b)\s*(?:head\s+)?([0-9a-fA-F]{7,40})(?![0-9a-fA-F])", re.IGNORECASE
)
# What ends a sha binding after a REJECT: end, punctuation, a parenthesis or a dash.
_BOUND_END = re.compile(r"\s*(?:$|[.:;,!)\](\-\u2013\u2014])")
_SHORT_SHA = re.compile(
    r"(?<![0-9a-f])(?=[0-9a-f]{0,39}[a-f])([0-9a-f]{7,40})(?![0-9a-f])",
    re.IGNORECASE,
)


def names_head_loosely(text: str, head: str) -> bool:
    """True when the text names the head by a prefix of 7+ hex characters (digits too)."""
    head = head.lower()
    return any(head.startswith(token) for token in _ANY_SHA.findall(text.lower()))


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


def _label_family(line: str, ignore_status: bool = False) -> str | None:
    """Family named by a heading, bold label, ``Reviewer:`` line or ``<label>:`` prefix.

    ``ignore_status`` reads a label disabled by a not-run word too ("**Codex review** (fix
    in progress)"): a REJECT under it is still that family's (#3004).
    """
    plain = _plain(line, keep_parens=True).strip()
    if not ignore_status and _not_run_label(line):
        # "Codex: unavailable", "Codex adversarial review: pending" open no section; a
        # not-run word inside a parenthetical aside ("Gemini ... (Codex: out of credits)")
        # does not disable the header (#2299, first live false negative on #2296).
        return None
    bold = re.match(r"^\s*(?:[-*]\s+)?\*\*(.+?)\*\*", line)
    if (
        bold
        and not re.match(r"^\s*#", line)
        and not verdict_clauses(line, keep_withdrawn=True)
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


def _round_before(prefix: str, lowest: bool) -> int | None:
    """The round of a verdict from the text before its token in its clause.

    Main read the last round marker, so a finding id in an aside moved it ("r2 (closes
    R7): ACCEPT" read as round 7, "r3 (re R1): REJECT" as round 1). The label's own round
    is the first marker outside parentheses; it is used only where it is safer than
    main's: the lower of the two for an ACCEPT (``lowest``), the higher for a REJECT, so a
    round never lets an ACCEPT outlast a REJECT that main's round would not (#3041).
    """
    found = _ROUND.findall(prefix)
    if not found:
        return None
    last = int(found[-1])
    outside = _ROUND.findall(_plain(prefix))
    label = int(outside[0]) if outside else last
    return min(label, last) if lowest else max(label, last)


def _reject_match(clause: str) -> tuple[int, int] | None:
    match = _REJECT_POS.search(clause) or _REJECT_POS_MORE.search(clause)
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
) -> str | None:
    """Reviewer family of an accepting clause: named before the token in the clause, else
    on the line before it ("Claude: r1 ..., r2 ACCEPT"), else the section header's. None
    when the label naming the model is disabled ("**Codex (not run)**: ACCEPT @ sha").
    A REJECT's family is ``_reject_families``.
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
    return _family(before) or _family(line_before) or header_family


def _reviewer_word(text: str) -> str | None:
    """The model named last in the text (a parenthetical is an aside), lowercased."""
    named = _NEAREST_MODEL.findall(_plain(text))
    return named[-1].lower() if named else None


def _reject_families(
    line_before: str, header: tuple[list[str], str | None]
) -> tuple[list[str], str | None]:
    """Families a REJECT withdraws, and its reviewer (None: unknown, never the same).

    The model named closest before the token decides ("Claude ACCEPT at <sha>;
    Cross-model review (Gemini) REJECT at <sha>" rejects for the cross-model family only);
    a status label never disables it (#3002 F5). With no model on the line it is the
    section's, including a label a not-run word disabled (#3004); when that label and the
    section name different families, the REJECT withdraws both (fail closed). A REJECT
    that no model name reaches (pasted tool output under a plain heading) has no family.
    """
    word = _reviewer_word(line_before)
    if word is not None:
        family = "cross_model" if word == "cross-model" else _family(word)
        return [family or "cross_model"], word
    families, reviewer = header
    return families, (reviewer if len(families) == 1 else None)


def _fixed_later(text: str, end: int) -> bool:
    """A resolution naming its commit ("fixed in <sha>") after the token, before the next
    verdict on the line, and not negated ("not fixed in <sha>")."""
    following = _ANY_VERDICT_TOKEN.search(text, end)
    tail = text[end : following.start() if following else len(text)]
    return any(not _UNRESOLVED.search(tail[: match.start()]) for match in _LATER_FIX.finditer(tail))


def _answered(
    at: tuple[int, int],
    event: dict[str, Any],
    answers: list[tuple[tuple[int, int], str, str | None, int | None]],
) -> bool:
    """A later ACCEPT of a later round by the same named reviewer answers the REJECT."""
    reviewer, reject_round = event.get("reviewer"), event.get("compare", event["round"])
    if reviewer is None or reject_round is None:
        return False
    return any(
        where > at
        and family == event["family"]
        and who == reviewer
        and accept_round is not None
        and accept_round > reject_round
        for where, family, who, accept_round in answers
    )


def standing_families(events: list[dict[str, Any]], renumber: bool = True) -> set[str]:
    """Reviewer families whose ACCEPT at the head still stands after later REJECTs (#2992).

    Events are in posting order (comments oldest first, lines top to bottom). A REJECT
    withdraws every earlier ACCEPT of its family except one from a later round by the
    same reviewer (``r3 ACCEPT`` survives an ``r2 REJECT`` listed after it when both name
    the same model; an unknown reviewer is never the same, r5 R4). A later ACCEPT stands
    again. An unnumbered ACCEPT followed by a numbered REJECT is withdrawn: a round
    history that ends in a REJECT at the head is an open rejection.

    Rounds are compared within one numbering only (``renumber``; off only to choose
    merge-only delta heads as before). A later comment that names a round 1 of the
    reviewer (an event, or a ``round`` marker for a resolved or short-sha line) after an
    earlier comment with one of its rounds above 1 starts a new numbering for all of
    that reviewer's events in it: a new session counts from r1 again, so an older
    ``r3 ACCEPT`` does not outrank its ``r1`` or ``r2 REJECT`` (#3041). A later comment
    without a round 1 (a recap of round 2) keeps the numbering.

    Numbering uses each event's ``round`` (main's reading); the comparison uses its
    ``compare`` round where it has one (``_round_before``), never higher for an ACCEPT
    nor lower for a REJECT than ``round``.
    """
    round_one = {
        (event.get("comment"), event["family"], event.get("reviewer"))
        for event in events
        if renumber and event["round"] == 1
    }
    accepts: dict[str, list[tuple[dict[str, Any], int]]] = {}
    # (family, reviewer) -> (epoch, comments of this numbering with a round above 1)
    numbering: dict[tuple[str, str], tuple[int, set[Any]]] = {}
    for event in events:
        family = event["family"]
        reviewer = event.get("reviewer")
        epoch = 0
        if reviewer is not None:
            comment = event.get("comment")
            epoch, later = numbering.get((family, reviewer), (0, set()))
            if (comment, family, reviewer) in round_one and (
                len(later) > 1 or (later and comment not in later)
            ):
                epoch, later = epoch + 1, set()  # once per comment: it joins ``later`` below
            if event["round"] is not None and event["round"] > 1:
                later.add(comment)
            numbering[(family, reviewer)] = (epoch, later)
        if event["kind"] == "accept":
            accepts.setdefault(family, []).append((event, epoch))
            continue
        if event["kind"] != "reject":
            continue  # a round marker only numbers
        reject_round = event.get("compare", event["round"])
        accepts[family] = [
            (accept, accept_epoch)
            for accept, accept_epoch in accepts.get(family, [])
            if reviewer is not None and accept.get("reviewer") == reviewer
            if accept_epoch == epoch
            if reject_round is not None
            and accept.get("compare", accept["round"]) is not None
            and accept.get("compare", accept["round"]) > reject_round
        ]
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
    return _classify(body, head)


def _classify(body: str, head: str, rejects_only: bool = False) -> dict[str, Any]:
    """``classify_record``'s parse; ``rejects_only`` keeps only the REJECT events (a comment
    that names the head by a 7-8 character prefix only binds no ACCEPT, #3002 F1).

    ACCEPTs are read strictly and REJECTs fail closed: a REJECT is also read inside fenced
    code, a table row, a block quote or indented code (r5 R6), is about the head unless its
    own label binds it to another commit (r5 R1, R2), and is credited to the section's
    family even under a label a not-run word disabled (#3004).
    """
    lines: list[str] = []
    fenced_lines: set[int] = set()
    fenced = False
    for raw in _HTML_COMMENT.sub(" ", body).splitlines():
        if raw.strip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            fenced_lines.add(len(lines))
        lines.append(raw)
    unfenced = ["" if index in fenced_lines else line for index, line in enumerate(lines)]
    labels = _head_labels(unfenced)
    reject_labels = _head_labels(unfenced, short=True)
    verdicts: list[dict[str, Any]] = []
    events: list[tuple[tuple[int, int], dict[str, Any]]] = []
    rebuttals: list[tuple[tuple[int, int], dict[str, Any]]] = []
    section: list[str] = []
    section_start = 0
    header_family: str | None = None
    header_reviewer: str | None = None
    # The families (and reviewer) a REJECT with no model on its line is credited to.
    reject_header: tuple[list[str], str | None] = ([], None)
    header_level = 0  # heading level that opened the section; 99 for a non-heading label
    # REJECTs placed on the head only by _reject_label_binds, and the ACCEPTs placed the
    # same way (position, family, reviewer, round) that may answer them.
    weak_rejects: set[int] = set()
    answers: list[tuple[tuple[int, int], str, str | None, int | None]] = []

    def close_section() -> None:
        # A rebuttal at the cap is a cross-model event at its rebuttal line, so a later
        # REJECT of a later round withdraws it like an ACCEPT (#2992).
        point = _rebuttal_point(section, head) if header_family == "cross_model" else None
        if point is not None and not rejects_only:
            event = {
                "family": "cross_model",
                "reviewer": _reviewer_word(section[0]) if section else None,
                "kind": "accept",
                "rebuttal": True,
                "round": point[1],
                "comment": 0,
                "line": section[point[0]].strip(),
            }
            rebuttals.append(((section_start + point[0], 1 << 30), event))

    for index, line in enumerate(lines):
        in_fence = index in fenced_lines
        reads: list[tuple[str, bool]] = []
        if not in_fence:
            label = _label_family(line)
            disabled = _label_family(line, ignore_status=True) if label is None else None
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
            if label is not None or neutral_heading:
                header_reviewer = _reviewer_word(line) if label is not None else None
                reject_header = ([label] if label is not None else [], header_reviewer)
            if disabled is not None:
                families = sorted(set(reject_header[0]) | {disabled})
                reject_header = (families, _reviewer_word(line) if len(families) == 1 else None)
            if not section:
                section_start = index
            section.append(line)
            reads = _verdict_reads(line)
        line_events: list[tuple[int, dict[str, Any]]] = []
        reject_head = _reject_label_binds(reject_labels, index, head)
        if not rejects_only:
            comment_head = _label_binds(labels, index, head)
            plain_line = _plain(line, keep_parens=True)
            consumed = 0
            for clause, withdrawn in reads:
                span = _verdict_match(clause)
                start = plain_line.find(clause, consumed)
                consumed = start + len(clause) if start >= 0 else consumed
                family = _clause_family(clause, span, plain_line, start, header_family)
                before = plain_line[: start + span[0]] if (span and start >= 0) else ""
                accept_round = _round_before(clause[: span[0]], lowest=True) if span else None
                rounds = _ROUND.findall(clause[: span[0]]) if span else []
                main_round = int(rounds[-1]) if rounds else None
                if (
                    family
                    and not _binding(clause, span, line, head, comment_head)
                    and _binding(clause, span, line, head, reject_head)
                ):
                    answers.append((
                        (index, start + (span[0] if span else 0)),
                        family,
                        _reviewer_word(before) or header_reviewer,
                        accept_round,
                    ))
                if family and _binding(clause, span, line, head, comment_head):
                    line_events.append((
                        start + (span[0] if span else 0),
                        {
                            "family": family,
                            "reviewer": _reviewer_word(before) or header_reviewer,
                            # A withdrawn ACCEPT still numbers its round, as before #3041.
                            "kind": "round" if withdrawn else "accept",
                            "round": main_round,
                            "compare": accept_round,
                            "comment": 0,
                            "line": clause.strip(),
                        },
                    ))
        strict_head = _label_binds(reject_labels, index, head)
        plain_reject = _plain(_reject_view(line), keep_parens=True)
        searched = 0
        # Only the clauses main reads move the search on, so a clause read only since
        # #3041 r15 never takes the earlier position's family away from a later one.
        main_starts = {at for _clause, at in _reject_clause_starts(line, more=False)}
        for clause, start in _reject_clause_starts(line):
            # Where the clause text is first found: before #3039 the REJECT was placed
            # there, and its family read from there still counts (fail closed).
            found = plain_reject.find(clause, searched)
            if start in main_starts:
                searched = found + len(clause) if found >= 0 else searched
            span = _reject_match(clause)
            if span is None:
                continue
            if not _reject_binding(clause, span, plain_reject, head, reject_head):
                continue
            # Weak (see _REJECT_AFTER_PUNCT): a later "fixed in <sha>" before the next
            # verdict on its line closes it, and so does a later round's ACCEPT by the same
            # reviewer in this comment, placed the same way.
            end = start + span[1]
            weak = not _reject_binding(
                clause, span, plain_reject, head, strict_head
            ) or not _REJECT_AFTER_PUNCT.match(plain_reject, end)
            if weak and _fixed_later(plain_reject, end):
                continue
            families, reviewer = _reject_families(plain_reject[: start + span[0]], reject_header)
            if 0 <= found < start:
                earlier, _reviewer = _reject_families(
                    plain_reject[: found + span[0]], reject_header
                )
                families = sorted(set(families) | set(earlier))
                if _reviewer != reviewer:
                    reviewer = None  # read as two reviewers: no later round answers it
            rounds = _ROUND.findall(clause[: span[0]])
            for family in families:
                event = {
                    "family": family,
                    "reviewer": reviewer,
                    "kind": "reject",
                    "round": int(rounds[-1]) if rounds else None,
                    "compare": _round_before(clause[: span[0]], lowest=False),
                    "comment": 0,
                    "line": clause.strip(),
                }
                if weak:
                    weak_rejects.add(id(event))
                line_events.append((start + span[0], event))
        tokens = len(_ANY_VERDICT_TOKEN.findall(line))
        if 0 < tokens <= MAX_VERDICTS_PER_LINE and not names_other_sha(line, head):
            # A round 1 named on a verdict line at the head, read or not (resolved, a
            # short sha): it may start a new numbering in standing_families (#3041).
            marked = _plain(line, keep_parens=True)
            markers = itertools.islice(_ROUND_ONE.finditer(marked), MAX_VERDICTS_PER_LINE)
            for marker in markers:
                families, reviewer = _reject_families(marked[: marker.start()], reject_header)
                if reviewer is None:
                    continue
                for family in families:
                    line_events.append((
                        marker.start(),
                        {
                            "family": family,
                            "reviewer": reviewer,
                            "kind": "round",
                            "round": 1,
                            "comment": 0,
                            "line": line.strip(),
                        },
                    ))
        events.extend(((index, at), event) for at, event in line_events)
        verdicts.extend(e for _, e in line_events if e["kind"] == "accept")
        if not reads:
            continue  # a withdrawn ACCEPT still ends the section's line buffer, as before
        close_section()
        section = []  # the header family persists: a reviewer block lists its rounds
    close_section()
    events = [
        (at, event)
        for at, event in events
        if id(event) not in weak_rejects or not _answered(at, event, answers)
    ]
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


def _is_high_risk(name: str, repo: str = "") -> bool:
    key = repo.strip().lower()
    return (
        name in HIGH_RISK_FILES
        or name.startswith(HIGH_RISK_PREFIXES)
        or name in REPO_HIGH_RISK_FILES.get(key, frozenset())
        or name.startswith(REPO_HIGH_RISK_PREFIXES.get(key, ()))
    )


def high_risk_paths(files: list[Any], repo: str = "") -> list[str]:
    """High-risk paths touched by the PR; a rename counts by its old name too.

    ``repo`` adds that repo's own high-risk paths (``REPO_HIGH_RISK_PREFIXES``). A list
    at the API's file cap may hide a high-risk path, so it counts as high-risk.
    """
    paths: set[str] = {TRUNCATED_FILES} if len(files) >= MAX_PR_FILES else set()
    for entry in files:
        if not isinstance(entry, dict):
            continue
        for key in ("filename", "previous_filename"):
            name = entry.get(key)
            if isinstance(name, str) and _is_high_risk(name, repo):
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


def _short_prefix_rejects(body: str, head: str, number: int) -> list[dict[str, Any]]:
    """REJECT events (and round markers) of a comment that names the head by a 7-8
    character prefix only (``classify_record`` returned None for it): parsed like any
    record, so a model named in the section header or a short sha on a Head line binds
    them too (r5 R2)."""
    if not names_head_loosely(body, head):
        return []
    return [
        dict(event, comment=number)
        for event in _classify(body, head, rejects_only=True)["events"]
        if event["kind"] in ("reject", "round")
    ]


def _evidence_at(
    head: str,
    comments: list[Any],
    reviews: list[Any],
    allow_rebuttal: bool = True,
    renumber: bool = True,
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
            # A 7-8 char sha that is a prefix of the head still binds a REJECT to it. Fold
            # that rejection against an earlier ACCEPT instead of treating it as absent.
            events.extend(_short_prefix_rejects(body, head, number))
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
    standing = standing_families(events, renumber)
    return records, stale, unbound, approved_reviews_at_head(reviews, head), standing


def _contributes(
    head: str,
    comments: list[Any],
    reviews: list[Any],
    allow_rebuttal: bool = True,
    renumber: bool = True,
) -> tuple[bool, bool]:
    """(independent, cross_model) evidence a record at ``head`` provides."""
    records, _stale, _unbound, approved, standing = _evidence_at(
        head, comments, reviews, allow_rebuttal, renumber
    )
    return (
        approved > 0 or "claude" in standing,
        "cross_model" in standing,
    )


def _fold_events_at(head: str, comments: list[Any], allow_rebuttal: bool) -> list[dict[str, Any]]:
    """Events bound to one head in comment order, for carrying a verified delta."""
    events: list[dict[str, Any]] = []
    for number, comment in enumerate(comments):
        body = comment.get("body") if isinstance(comment, dict) else None
        if not isinstance(body, str):
            continue
        record = classify_record(body, head)
        if record is None:
            events.extend(_short_prefix_rejects(body, head, number))
            continue
        for event in record["events"]:
            if allow_rebuttal or not event.get("rebuttal"):
                events.append(dict(event, comment=number))
    return events


def evaluate(
    head: str,
    files: list[Any],
    comments: list[Any],
    reviews: list[Any],
    delta_verified: tuple[str, ...] = (),
    allow_rebuttal: bool = True,
    repo: str = "",
) -> dict[str, Any]:
    """Pure classification of the PR's review evidence at ``head``.

    ``delta_verified`` lists older reviewed heads whose delta to ``head`` the caller has
    verified as merge-only (#2308); a record at one of those counts as a record at the head.
    The caller is the only place that may verify a delta; this function trusts nothing else.
    ``allow_rebuttal`` False (``rebuttal_counts(repo)``) drops rebuttals at the cap.
    ``repo`` adds that repo's own high-risk paths.
    """
    risky = high_risk_paths(files, repo)
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
    # Delta heads are chosen as before #3041 (rounds compared across numberings), so the
    # stricter numbering never folds fewer events than that reading does; it only
    # withdraws more in the fold below.
    floor = _evidence_at(head, comments, reviews, allow_rebuttal, renumber=False)[4]
    floor_ind = approved_reviews > 0 or "claude" in floor
    delta_heads: list[str] = []
    for old in delta_verified:
        if old.lower() == head.lower():
            continue
        old_ind, old_cross = _contributes(old, comments, reviews, allow_rebuttal, renumber=False)
        if (old_ind and not floor_ind) or (
            old_cross and "cross_model" not in floor and bool(risky)
        ):
            delta_heads.append(old)
    if delta_heads:
        carried_events = [
            event for old in delta_heads for event in _fold_events_at(old, comments, allow_rebuttal)
        ]
        folded = standing_families(
            sorted(
                carried_events + _fold_events_at(head, comments, allow_rebuttal),
                key=lambda event: event["comment"],
            )
        )
        independent = (
            approved_reviews > 0
            or "claude" in folded
            or any(approved_reviews_at_head(reviews, old) > 0 for old in delta_heads)
        )
        cross_model = "cross_model" in folded
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
            if any(
                _contributes(old, comments, reviews, allow_rebuttal, renumber=False)
            ) and merge_only_delta(fetch, base, token, old, head, pr_paths, base_ref):
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
        report = evaluate(head, files, comments, reviews, allow_rebuttal=allow, repo=repo)
        if report["status"] != "OK":
            deltas = _verify_deltas(fetch, base, token, head, pull, files, comments, reviews, allow)
            if deltas:
                report = evaluate(
                    head, files, comments, reviews, deltas, allow_rebuttal=allow, repo=repo
                )
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
