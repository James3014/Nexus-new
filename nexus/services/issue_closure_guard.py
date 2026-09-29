"""PR issue closure intent guard for Nexus PR merge workflows (#1199).

Guards against GitHub's native issue auto-closing parser erroneously matching
negated closing phrases (such as 'This does not close #1188'), requires explicit
machine-readable intent declarations, surfaces accidental close keywords targeting
unrelated issues, and verifies post-merge GitHub issue state alignment.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

INTENT_SCHEMA = "nexus.issue_closure_intent.v1"
VERIFICATION_SCHEMA = "nexus.post_merge_issue_state_verification.v1"
CLAIM_CEILING = "PR_ISSUE_CLOSURE_INTENT_VALIDATION_ONLY"

START_MARKER = "<!-- NEXUS_ISSUE_INTENT_V1"
END_MARKER = "NEXUS_ISSUE_INTENT_V1 -->"

ON_MERGE_KEEP_OPEN = "KEEP_OPEN"
ON_MERGE_CLOSE = "CLOSE"
VALID_ON_MERGE_ACTIONS = frozenset({ON_MERGE_KEEP_OPEN, ON_MERGE_CLOSE})

# GitHub recognized closing keywords (case-insensitive)
CLOSING_KEYWORD_FAMILIES = (
    "close",
    "closes",
    "closed",
    "fix",
    "fixes",
    "fixed",
    "resolve",
    "resolves",
    "resolved",
)

# Pattern matching closing keywords targeting issue numbers
# Examples:
#   fixes #1188
#   Closes #1188
#   resolved https://github.com/James3014/Nexus-new/issues/1188
#   does not close #1188 (matches keyword + issue ref)
CLOSING_KEYWORD_PATTERN = re.compile(
    r"(?i)\b("
    + "|".join(CLOSING_KEYWORD_FAMILIES)
    + r")\s+(?:https?://github\.com/[^/\s]+/[^/\s]+/issues/|(?:\b[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+)?#)(\d+)\b"
)


class IssueClosureIntentError(ValueError):
    """Raised when PR issue closure intent is invalid or violated."""


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    ).hexdigest()


def extract_closure_intents(body: str | None) -> list[dict[str, Any]]:
    """Extract machine-readable NEXUS_ISSUE_INTENT_V1 blocks from PR body."""
    if not body or type(body) is not str:
        return []

    count_start = body.count(START_MARKER)
    count_end = body.count(END_MARKER)
    if count_start != count_end:
        raise IssueClosureIntentError("MISMATCHED_ISSUE_INTENT_MARKERS")
    if count_start == 0:
        return []
    if count_start > 1:
        raise IssueClosureIntentError("MULTIPLE_ISSUE_INTENT_BLOCKS_FORBIDDEN")

    start = body.index(START_MARKER) + len(START_MARKER)
    end = body.index(END_MARKER, start)
    raw = body[start:end].strip()
    if not raw:
        raise IssueClosureIntentError("EMPTY_ISSUE_INTENT_BLOCK")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IssueClosureIntentError("INVALID_ISSUE_INTENT_JSON") from exc

    raw_items = data if isinstance(data, list) else [data]
    normalized: list[dict[str, Any]] = []

    for item in raw_items:
        if not isinstance(item, Mapping):
            raise IssueClosureIntentError("INTENT_ITEM_MUST_BE_OBJECT")
        issue = item.get("issue") if "issue" in item else item.get("issue_number")
        if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
            raise IssueClosureIntentError("INTENT_ISSUE_NUMBER_INVALID")

        action = str(item.get("on_merge") or "").strip().upper()
        if action not in VALID_ON_MERGE_ACTIONS:
            raise IssueClosureIntentError(f"INVALID_ON_MERGE_ACTION: {action!r}")

        normalized.append({
            "issue_number": issue,
            "on_merge": action,
        })

    return normalized


def strip_markers(body: str | None) -> str:
    """Return PR body text with all machine-readable comment blocks removed."""
    if not body:
        return ""
    text = body
    # Remove NEXUS_ISSUE_INTENT_V1 blocks
    if START_MARKER in text and END_MARKER in text:
        start = text.index(START_MARKER)
        end = text.index(END_MARKER, start) + len(END_MARKER)
        text = text[:start] + text[end:]
    # Remove NEXUS_MERGE_LANE_V1 blocks
    lane_start = "<!-- NEXUS_MERGE_LANE_V1"
    lane_end = "NEXUS_MERGE_LANE_V1 -->"
    if lane_start in text and lane_end in text:
        start = text.index(lane_start)
        end = text.index(lane_end, start) + len(lane_end)
        text = text[:start] + text[end:]
    return text


def find_closing_keyword_references(text: str) -> list[tuple[str, int]]:
    """Find all (closing_keyword, issue_number) occurrences in text."""
    matches = CLOSING_KEYWORD_PATTERN.findall(text)
    return [(keyword.lower(), int(issue_str)) for keyword, issue_str in matches]


def validate_issue_closure_intent(body: str | None) -> dict[str, Any]:
    """Validate PR body against declared issue closure intent.

    Acceptance criteria:
    - Fixture reproducing 'This does not close #1188' fails before merge;
    - '#1188 remains open' with KEEP_OPEN passes;
    - Explicit positive CLOSE passes;
    - Accidental close keyword targeting a different/unrelated issue is surfaced;
    - No automatic reopen/close authority is created.
    """
    intents = extract_closure_intents(body)
    cleaned_prose = strip_markers(body)
    detected_refs = find_closing_keyword_references(cleaned_prose)

    detected_by_issue: dict[int, list[str]] = {}
    for kw, num in detected_refs:
        detected_by_issue.setdefault(num, []).append(kw)

    intent_by_issue = {item["issue_number"]: item["on_merge"] for item in intents}

    # 1. Accidental closing keywords targeting issues not declared in intent
    untracked_issues = set(detected_by_issue.keys()) - set(intent_by_issue.keys())
    if untracked_issues:
        culprits = ", ".join(
            f"#{num} ({', '.join(detected_by_issue[num])})" for num in sorted(untracked_issues)
        )
        raise IssueClosureIntentError(
            f"UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE: PR prose contains GitHub closing keywords targeting {culprits}. "
            "Declare intent in <!-- NEXUS_ISSUE_INTENT_V1 or rephrase using neutral prose (e.g. '#X remains open')."
        )

    # 2. Check each declared intent
    for issue_num, action in intent_by_issue.items():
        if action == ON_MERGE_KEEP_OPEN:
            # If KEEP_OPEN, reject ANY closing keyword pattern targeting this issue anywhere in PR prose
            if issue_num in detected_by_issue:
                kws = ", ".join(detected_by_issue[issue_num])
                raise IssueClosureIntentError(
                    f"REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN: PR prose contains closing keyword '{kws}' targeting #{issue_num}, "
                    f"which triggers GitHub auto-close even when negated (e.g. 'does not close #{issue_num}'). "
                    f"Use neutral prose such as '#{issue_num} remains open' instead."
                )

        elif action == ON_MERGE_CLOSE:
            # If CLOSE, require explicit positive closing declaration
            if issue_num not in detected_by_issue:
                raise IssueClosureIntentError(
                    f"MISSING_EXPLICIT_CLOSING_DECLARATION: PR declared on_merge=CLOSE for #{issue_num}, "
                    f"but prose has no explicit closing keyword (e.g. 'Closes #{issue_num}')."
                )

    result: dict[str, Any] = {
        "schema": INTENT_SCHEMA,
        "status": "PASS",
        "intents": intents,
        "detected_closing_references": [
            {"issue_number": num, "keyword": kw} for kw, num in detected_refs
        ],
        "claim_ceiling": CLAIM_CEILING,
    }
    result["content_sha256"] = _hash({k: v for k, v in result.items() if k != "content_sha256"})
    return result


def verify_post_merge_state(
    *,
    intents: Sequence[Mapping[str, Any]],
    actual_issue_states: Mapping[int, str],
    merged_pr: Mapping[str, Any],
) -> dict[str, Any]:
    """Post-merge truth check comparing declared on_merge intent against actual GitHub issue state.

    Detects and records durable mismatch failures without trusting session memory.
    """
    head_sha = str(merged_pr.get("head_sha") or "").strip()
    pr_number = merged_pr.get("pr_number")
    if not head_sha or not pr_number:
        raise IssueClosureIntentError("MERGED_PR_IDENTITY_REQUIRED")

    checks: list[dict[str, Any]] = []
    mismatches: list[str] = []

    for item in intents:
        issue = int(item["issue_number"])
        action = str(item["on_merge"]).strip().upper()
        actual_state = str(actual_issue_states.get(issue) or "").strip().lower()

        if not actual_state:
            mismatches.append(f"#{issue}: ACTUAL_STATE_UNKNOWN")
            checks.append({
                "issue_number": issue,
                "declared_intent": action,
                "actual_state": "UNKNOWN",
                "matched": False,
            })
            continue

        if action == ON_MERGE_KEEP_OPEN:
            matched = actual_state == "open"
            if not matched:
                mismatches.append(
                    f"#{issue}: STATE_MISMATCH expected 'open' (KEEP_OPEN), observed '{actual_state}'"
                )
        elif action == ON_MERGE_CLOSE:
            matched = actual_state == "closed"
            if not matched:
                mismatches.append(
                    f"#{issue}: STATE_MISMATCH expected 'closed' (CLOSE), observed '{actual_state}'"
                )
        else:
            matched = False
            mismatches.append(f"#{issue}: UNKNOWN_INTENT_ACTION '{action}'")

        checks.append({
            "issue_number": issue,
            "declared_intent": action,
            "actual_state": actual_state,
            "matched": matched,
        })

    record: dict[str, Any] = {
        "schema": VERIFICATION_SCHEMA,
        "status": "PASS" if not mismatches else "STATE_MISMATCH_DETECTED",
        "merged_pr": {
            "pr_number": pr_number,
            "head_sha": head_sha,
        },
        "checks": checks,
        "mismatches": mismatches,
        "claim_ceiling": CLAIM_CEILING,
    }
    record["content_sha256"] = _hash({k: v for k, v in record.items() if k != "content_sha256"})
    return record


__all__ = [
    "INTENT_SCHEMA",
    "VERIFICATION_SCHEMA",
    "CLAIM_CEILING",
    "ON_MERGE_KEEP_OPEN",
    "ON_MERGE_CLOSE",
    "CLOSING_KEYWORD_FAMILIES",
    "extract_closure_intents",
    "validate_issue_closure_intent",
    "verify_post_merge_state",
    "IssueClosureIntentError",
]
