"""Trusted default-branch merge-lane binding gate for protected pull requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ENFORCEMENT_START_PR_NUMBER = 1061
BINDING_SCHEMA = "nexus.merge_lane_binding.v1"
REBIND_SCHEMA = "nexus.owner_execution_lane_rebind.v1"
BREAK_GLASS_CONTRACT_KIND = "BREAK_GLASS_OWNER_INTEGRATION"
BREAK_GLASS_LANE = "BREAK_GLASS"
BREAK_GLASS_INTEGRATION_SCHEMA = "nexus.break_glass_owner_integration.v1"
BREAK_GLASS_AUTHORITY_ISSUE = 806
BREAK_GLASS_OWNER = "James3014"
DIRECT_LANES = {"DIRECT_CANONICAL", "DIRECT_DELEGATED"}
ALL_LANES = DIRECT_LANES | {"GOVERNED", BREAK_GLASS_LANE}
CONTRACT_KINDS = {"OWNER_INLINE", "TRACKED_TASK_CARD", BREAK_GLASS_CONTRACT_KIND}
START_MARKER = "<!-- NEXUS_MERGE_LANE_V1"
END_MARKER = "NEXUS_MERGE_LANE_V1 -->"
INTENT_START_MARKER = "<!-- NEXUS_ISSUE_INTENT_V1"
INTENT_END_MARKER = "NEXUS_ISSUE_INTENT_V1 -->"
ON_MERGE_KEEP_OPEN = "KEEP_OPEN"
ON_MERGE_CLOSE = "CLOSE"
VALID_ON_MERGE_ACTIONS = frozenset({ON_MERGE_KEEP_OPEN, ON_MERGE_CLOSE})
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
CLOSING_KEYWORD_PATTERN = re.compile(
    r"(?i)\b("
    + "|".join(CLOSING_KEYWORD_FAMILIES)
    + r")\s+(?:https?://github\.com/[^/\s]+/[^/\s]+/issues/|(?:\b[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+)?#)(\d+)\b"
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TASK_PATH = re.compile(r"^tasks/[A-Za-z0-9._/-]+\.md$")


class LaneBindingError(ValueError):
    pass


class IssueClosureIntentError(LaneBindingError):
    pass


def canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _exact_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise LaneBindingError(f"{label}_MUST_BE_OBJECT")
    return dict(value)


def _exact_str(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise LaneBindingError(f"{label}_INVALID")
    return value


def _exact_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise LaneBindingError(f"{label}_INVALID")
    return value


def _sha(value: Any, label: str, *, size: int) -> str:
    text = _exact_str(value, label)
    pattern = SHA40 if size == 40 else SHA64
    if not pattern.fullmatch(text):
        raise LaneBindingError(f"{label}_INVALID")
    return text


def _safe_id(value: Any, label: str) -> str:
    text = _exact_str(value, label)
    if not SAFE_ID.fullmatch(text):
        raise LaneBindingError(f"{label}_INVALID")
    return text


def _task_path(value: Any) -> str:
    text = _exact_str(value, "TASK_CARD_PATH")
    if not TASK_PATH.fullmatch(text) or ".." in Path(text).parts:
        raise LaneBindingError("TASK_CARD_PATH_INVALID")
    return text


def extract_binding(body: Any) -> dict[str, Any]:
    if type(body) is not str:
        raise LaneBindingError("PR_BODY_REQUIRED")
    if body.count(START_MARKER) != 1 or body.count(END_MARKER) != 1:
        raise LaneBindingError("EXACTLY_ONE_MERGE_LANE_BINDING_REQUIRED")
    start = body.index(START_MARKER) + len(START_MARKER)
    end = body.index(END_MARKER, start)
    payload = body[start:end].strip()
    if not payload:
        raise LaneBindingError("MERGE_LANE_BINDING_JSON_INVALID")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise LaneBindingError("MERGE_LANE_BINDING_JSON_INVALID") from exc
    return _exact_dict(value, "MERGE_LANE_BINDING")


def render_binding(binding: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(binding), ensure_ascii=False, indent=2, sort_keys=True)
    return f"{START_MARKER}\n{payload}\n{END_MARKER}"


def _fetch_break_glass_comment(comment_id: int) -> Mapping[str, Any]:
    if comment_id <= 0:
        raise LaneBindingError("BREAK_GLASS_COMMENT_ID_INVALID")
    url = f"https://api.github.com/repos/James3014/Nexus-new/issues/comments/{comment_id}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "nexus-trusted-merge-lane-gate/1.0",
    }
    token = os.getenv("TRUSTED_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10.0) as response:  # nosec B310 - fixed GitHub HTTPS endpoint
            if response.geturl() != url:
                raise LaneBindingError("BREAK_GLASS_COMMENT_REDIRECT_REJECTED")
            raw = response.read()
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise LaneBindingError("BREAK_GLASS_COMMENT_FETCH_FAILED") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LaneBindingError("BREAK_GLASS_COMMENT_MALFORMED") from exc
    if not isinstance(value, Mapping):
        raise LaneBindingError("BREAK_GLASS_COMMENT_MALFORMED")
    return value


def _parse_break_glass_integration_comment(
    comment: Mapping[str, Any], *, expected_payload_sha256: str
) -> dict[str, Any]:
    try:
        comment_id = int(comment["id"])
        issue_url = str(comment["issue_url"])
        comment_url = str(comment["html_url"])
        owner_login = str(comment["user"]["login"])
        body = str(comment["body"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LaneBindingError("BREAK_GLASS_COMMENT_MALFORMED") from exc
    if issue_url != "https://api.github.com/repos/James3014/Nexus-new/issues/806":
        raise LaneBindingError("BREAK_GLASS_COMMENT_ISSUE_MISMATCH")
    if owner_login != BREAK_GLASS_OWNER:
        raise LaneBindingError("BREAK_GLASS_COMMENT_OWNER_MISMATCH")
    expected_url = f"https://github.com/James3014/Nexus-new/issues/806#issuecomment-{comment_id}"
    if comment_url != expected_url:
        raise LaneBindingError("BREAK_GLASS_COMMENT_URL_MISMATCH")
    hash_matches = re.findall(r"Canonical integration payload SHA-256:\s*`([0-9a-f]{64})`", body)
    json_matches = re.findall(r"```json\s*\n(.*?)\n```", body, flags=re.DOTALL)
    if len(hash_matches) != 1 or len(json_matches) != 1:
        raise LaneBindingError("BREAK_GLASS_INTEGRATION_BLOCK_INVALID")
    try:
        payload = json.loads(json_matches[0])
    except json.JSONDecodeError as exc:
        raise LaneBindingError("BREAK_GLASS_INTEGRATION_JSON_INVALID") from exc
    if type(payload) is not dict:
        raise LaneBindingError("BREAK_GLASS_INTEGRATION_JSON_INVALID")
    declared_hash = hash_matches[0]
    actual_hash = canonical_hash(payload)
    if declared_hash != actual_hash or declared_hash != expected_payload_sha256:
        raise LaneBindingError("BREAK_GLASS_INTEGRATION_HASH_MISMATCH")
    return payload


def _parse_bound_owner_payload(
    comment: Mapping[str, Any],
    *,
    marker: str,
    expected_payload_sha256: str,
    expected_schema: str,
) -> dict[str, Any]:
    try:
        comment_id = int(comment["id"])
        issue_url = str(comment["issue_url"])
        comment_url = str(comment["html_url"])
        owner_login = str(comment["user"]["login"])
        body = str(comment["body"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LaneBindingError("BREAK_GLASS_COMMENT_MALFORMED") from exc
    if issue_url != "https://api.github.com/repos/James3014/Nexus-new/issues/806":
        raise LaneBindingError("BREAK_GLASS_COMMENT_ISSUE_MISMATCH")
    if owner_login != BREAK_GLASS_OWNER:
        raise LaneBindingError("BREAK_GLASS_COMMENT_OWNER_MISMATCH")
    if (
        comment_url
        != f"https://github.com/James3014/Nexus-new/issues/806#issuecomment-{comment_id}"
    ):
        raise LaneBindingError("BREAK_GLASS_COMMENT_URL_MISMATCH")
    hashes = re.findall(rf"{re.escape(marker)}:\s*`([0-9a-f]{{64}})`", body)
    blocks = re.findall(r"```json\s*\n(.*?)\n```", body, flags=re.DOTALL)
    if len(hashes) != 1 or len(blocks) != 1:
        raise LaneBindingError("BREAK_GLASS_EVIDENCE_BLOCK_INVALID")
    try:
        payload = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise LaneBindingError("BREAK_GLASS_EVIDENCE_JSON_INVALID") from exc
    if type(payload) is not dict or payload.get("schema") != expected_schema:
        raise LaneBindingError("BREAK_GLASS_EVIDENCE_SCHEMA_INVALID")
    actual_hash = canonical_hash(payload)
    if hashes[0] != actual_hash or hashes[0] != expected_payload_sha256:
        raise LaneBindingError("BREAK_GLASS_EVIDENCE_HASH_MISMATCH")
    return payload


def _parse_timestamp(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise LaneBindingError(f"{label}_INVALID") from exc
    if parsed.tzinfo is None:
        raise LaneBindingError(f"{label}_INVALID")
    return parsed.astimezone(timezone.utc)


def _validate_break_glass_integration(
    reference: Any,
    *,
    repository: str,
    pull_request_number: int,
    base_sha: str,
    head_sha: str,
    owner_id: str,
    comment_fetcher: Callable[[int], Mapping[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    value = _exact_dict(reference, "BREAK_GLASS_INTEGRATION")
    required_reference_fields = {
        "source_comment_id",
        "verification_comment_id",
        "integration_comment_id",
        "integration_payload_sha256",
    }
    if set(value) != required_reference_fields:
        raise LaneBindingError("BREAK_GLASS_INTEGRATION_REFERENCE_FIELDS_INVALID")
    source_comment_id = _exact_int(value.get("source_comment_id"), "BREAK_GLASS_SOURCE_COMMENT_ID")
    verification_comment_id = _exact_int(
        value.get("verification_comment_id"), "BREAK_GLASS_VERIFICATION_COMMENT_ID"
    )
    comment_id = _exact_int(value.get("integration_comment_id"), "BREAK_GLASS_COMMENT_ID")
    payload_sha256 = _sha(
        value.get("integration_payload_sha256"), "BREAK_GLASS_PAYLOAD_SHA256", size=64
    )
    payload = _parse_break_glass_integration_comment(
        comment_fetcher(comment_id), expected_payload_sha256=payload_sha256
    )
    required_fields = {
        "schema",
        "repository",
        "issue",
        "owner_login",
        "recovery_id",
        "integration_attempt_id",
        "source_attempt_id",
        "source_activation_payload_sha256",
        "verification_payload_sha256",
        "effect_class",
        "pr_number",
        "accepted_head_sha",
        "accepted_tree_sha",
        "accepted_diff_sha256",
        "expected_base_sha",
        "merge_method",
        "checks",
        "issued_at",
        "expires_at",
        "claim_ceiling",
    }
    if set(payload) != required_fields:
        raise LaneBindingError("BREAK_GLASS_INTEGRATION_PAYLOAD_FIELDS_INVALID")
    if payload.get("schema") != BREAK_GLASS_INTEGRATION_SCHEMA:
        raise LaneBindingError("BREAK_GLASS_INTEGRATION_SCHEMA_INVALID")
    if payload.get("repository") != repository:
        raise LaneBindingError("BREAK_GLASS_REPOSITORY_MISMATCH")
    if payload.get("issue") != BREAK_GLASS_AUTHORITY_ISSUE:
        raise LaneBindingError("BREAK_GLASS_AUTHORITY_ISSUE_MISMATCH")
    if payload.get("owner_login") != owner_id or owner_id != BREAK_GLASS_OWNER:
        raise LaneBindingError("BREAK_GLASS_OWNER_MISMATCH")
    if payload.get("effect_class") != "EMERGENCY_INTEGRATION":
        raise LaneBindingError("BREAK_GLASS_EFFECT_CLASS_INVALID")
    if payload.get("claim_ceiling") != "emergency_integration_only":
        raise LaneBindingError("BREAK_GLASS_CLAIM_CEILING_INVALID")
    if payload.get("merge_method") != "merge":
        raise LaneBindingError("BREAK_GLASS_MERGE_METHOD_INVALID")
    if payload.get("pr_number") != pull_request_number:
        raise LaneBindingError("BREAK_GLASS_PR_MISMATCH")
    if payload.get("accepted_head_sha") != head_sha:
        raise LaneBindingError("BREAK_GLASS_HEAD_MISMATCH")
    if payload.get("expected_base_sha") != base_sha:
        raise LaneBindingError("BREAK_GLASS_BASE_MISMATCH")
    _sha(payload.get("accepted_tree_sha"), "BREAK_GLASS_ACCEPTED_TREE_SHA", size=40)
    _sha(payload.get("accepted_diff_sha256"), "BREAK_GLASS_ACCEPTED_DIFF_SHA256", size=64)
    _sha(
        payload.get("source_activation_payload_sha256"),
        "BREAK_GLASS_SOURCE_ACTIVATION_SHA256",
        size=64,
    )
    _sha(payload.get("verification_payload_sha256"), "BREAK_GLASS_VERIFICATION_SHA256", size=64)
    issued_at = _parse_timestamp(payload.get("issued_at"), "BREAK_GLASS_ISSUED_AT")
    expires_at = _parse_timestamp(payload.get("expires_at"), "BREAK_GLASS_EXPIRES_AT")
    if expires_at <= issued_at:
        raise LaneBindingError("BREAK_GLASS_INTEGRATION_WINDOW_INVALID")
    instant = now.astimezone(timezone.utc)
    if instant < issued_at:
        raise LaneBindingError("BREAK_GLASS_INTEGRATION_NOT_YET_VALID")
    if instant >= expires_at:
        raise LaneBindingError("BREAK_GLASS_INTEGRATION_EXPIRED")
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        raise LaneBindingError("BREAK_GLASS_CHECK_SET_INVALID")
    seen_names: set[str] = set()
    seen_runs: set[int] = set()
    for raw_check in checks:
        check = _exact_dict(raw_check, "BREAK_GLASS_CHECK")
        if set(check) != {"schema", "name", "run_id", "head_sha", "conclusion"}:
            raise LaneBindingError("BREAK_GLASS_CHECK_FIELDS_INVALID")
        if check.get("schema") != "nexus.break_glass_check_evidence.v1":
            raise LaneBindingError("BREAK_GLASS_CHECK_SCHEMA_INVALID")
        name = _exact_str(check.get("name"), "BREAK_GLASS_CHECK_NAME")
        run_id = _exact_int(check.get("run_id"), "BREAK_GLASS_CHECK_RUN_ID")
        if name in seen_names or run_id in seen_runs:
            raise LaneBindingError("BREAK_GLASS_CHECK_SET_DUPLICATE")
        seen_names.add(name)
        seen_runs.add(run_id)
        if check.get("head_sha") != head_sha:
            raise LaneBindingError("BREAK_GLASS_CHECK_SUBJECT_MISMATCH")
        if check.get("conclusion") != "success":
            raise LaneBindingError("BREAK_GLASS_CHECK_NOT_SUCCESS")
    recovery_id = _safe_id(payload.get("recovery_id"), "BREAK_GLASS_RECOVERY_ID")
    source_attempt_id = _safe_id(payload.get("source_attempt_id"), "BREAK_GLASS_SOURCE_ATTEMPT_ID")
    source_hash = _sha(
        payload.get("source_activation_payload_sha256"),
        "BREAK_GLASS_SOURCE_ACTIVATION_SHA256",
        size=64,
    )
    verification_hash = _sha(
        payload.get("verification_payload_sha256"), "BREAK_GLASS_VERIFICATION_SHA256", size=64
    )
    source = _parse_bound_owner_payload(
        comment_fetcher(source_comment_id),
        marker="Canonical activation payload SHA-256",
        expected_payload_sha256=source_hash,
        expected_schema="nexus.break_glass_owner_activation.v1",
    )
    verification = _parse_bound_owner_payload(
        comment_fetcher(verification_comment_id),
        marker="Canonical verification payload SHA-256",
        expected_payload_sha256=verification_hash,
        expected_schema="nexus.break_glass_owner_verification.v1",
    )
    if (
        source.get("repository") != repository
        or source.get("issue") != BREAK_GLASS_AUTHORITY_ISSUE
        or source.get("owner_login") != BREAK_GLASS_OWNER
        or source.get("recovery_id") != recovery_id
        or source.get("attempt_id") != source_attempt_id
        or source.get("effect_class") != "SOURCE_REPAIR"
        or source.get("claim_ceiling") != "break_glass_source_candidate_only"
    ):
        raise LaneBindingError("BREAK_GLASS_SOURCE_AUTHORITY_MISMATCH")
    if (
        verification.get("repository") != repository
        or verification.get("issue") != BREAK_GLASS_AUTHORITY_ISSUE
        or verification.get("owner_login") != BREAK_GLASS_OWNER
        or verification.get("recovery_id") != recovery_id
        or verification.get("source_attempt_id") != source_attempt_id
        or verification.get("source_activation_payload_sha256") != source_hash
        or verification.get("claim_ceiling") != "source_repair_verification_only"
    ):
        raise LaneBindingError("BREAK_GLASS_VERIFICATION_AUTHORITY_MISMATCH")
    if (
        verification.get("verified_commit_sha") != head_sha
        or verification.get("verified_tree_sha") != payload.get("accepted_tree_sha")
        or verification.get("verified_diff_sha256") != payload.get("accepted_diff_sha256")
    ):
        raise LaneBindingError("BREAK_GLASS_VERIFICATION_SUBJECT_MISMATCH")
    source_expires = _parse_timestamp(source.get("expires_at"), "BREAK_GLASS_SOURCE_EXPIRES_AT")
    verification_issued = _parse_timestamp(
        verification.get("issued_at"), "BREAK_GLASS_VERIFICATION_ISSUED_AT"
    )
    verification_expires = _parse_timestamp(
        verification.get("expires_at"), "BREAK_GLASS_VERIFICATION_EXPIRES_AT"
    )
    if not (verification_issued <= issued_at < verification_expires and issued_at < source_expires):
        raise LaneBindingError("BREAK_GLASS_EVIDENCE_NOT_CURRENT_AT_INTEGRATION_ISSUANCE")
    return {
        "source_comment_id": source_comment_id,
        "verification_comment_id": verification_comment_id,
        "integration_comment_id": comment_id,
        "integration_payload_sha256": payload_sha256,
        "integration_attempt_id": _safe_id(
            payload.get("integration_attempt_id"), "BREAK_GLASS_INTEGRATION_ATTEMPT_ID"
        ),
        "recovery_id": recovery_id,
    }


def extract_closure_intents(body: Any) -> list[dict[str, Any]]:
    if type(body) is not str:
        return []
    count_start = body.count(INTENT_START_MARKER)
    count_end = body.count(INTENT_END_MARKER)
    if count_start != count_end:
        raise IssueClosureIntentError("MISMATCHED_ISSUE_INTENT_MARKERS")
    if count_start == 0:
        return []
    if count_start > 1:
        raise IssueClosureIntentError("MULTIPLE_ISSUE_INTENT_BLOCKS_FORBIDDEN")

    start = body.index(INTENT_START_MARKER) + len(INTENT_START_MARKER)
    end = body.index(INTENT_END_MARKER, start)
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

        normalized.append(
            {
                "issue_number": issue,
                "on_merge": action,
            }
        )

    return normalized


def strip_markers(body: Any) -> str:
    if type(body) is not str:
        return ""
    text = body
    if INTENT_START_MARKER in text and INTENT_END_MARKER in text:
        start = text.index(INTENT_START_MARKER)
        end = text.index(INTENT_END_MARKER, start) + len(INTENT_END_MARKER)
        text = text[:start] + text[end:]
    if START_MARKER in text and END_MARKER in text:
        start = text.index(START_MARKER)
        end = text.index(END_MARKER, start) + len(END_MARKER)
        text = text[:start] + text[end:]
    return text


def find_closing_keyword_references(text: str) -> list[tuple[str, int]]:
    matches = CLOSING_KEYWORD_PATTERN.findall(text)
    return [(keyword.lower(), int(issue_str)) for keyword, issue_str in matches]


def validate_issue_closure_intent(body: Any) -> dict[str, Any]:
    intents = extract_closure_intents(body)
    cleaned_prose = strip_markers(body)
    detected_refs = find_closing_keyword_references(cleaned_prose)

    detected_by_issue: dict[int, list[str]] = {}
    for kw, num in detected_refs:
        detected_by_issue.setdefault(num, []).append(kw)

    intent_by_issue = {item["issue_number"]: item["on_merge"] for item in intents}

    untracked_issues = set(detected_by_issue.keys()) - set(intent_by_issue.keys())
    if untracked_issues:
        culprits = ", ".join(
            f"#{num} ({', '.join(detected_by_issue[num])})" for num in sorted(untracked_issues)
        )
        raise IssueClosureIntentError(
            f"UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE: PR prose contains GitHub closing keywords targeting {culprits}. "
            "Declare intent in <!-- NEXUS_ISSUE_INTENT_V1 or rephrase using neutral prose (e.g. '#X remains open')."
        )

    for issue_num, action in intent_by_issue.items():
        if action == ON_MERGE_KEEP_OPEN:
            if issue_num in detected_by_issue:
                kws = ", ".join(detected_by_issue[issue_num])
                raise IssueClosureIntentError(
                    f"REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN: PR prose contains closing keyword '{kws}' targeting #{issue_num}, "
                    f"which triggers GitHub auto-close even when negated (e.g. 'does not close #{issue_num}'). "
                    f"Use neutral prose such as '#{issue_num} remains open' instead."
                )
        elif action == ON_MERGE_CLOSE:
            if issue_num not in detected_by_issue:
                raise IssueClosureIntentError(
                    f"MISSING_EXPLICIT_CLOSING_DECLARATION: PR declared on_merge=CLOSE for #{issue_num}, "
                    f"but prose has no explicit closing keyword (e.g. 'Closes #{issue_num}')."
                )

    result: dict[str, Any] = {
        "schema": "nexus.issue_closure_intent.v1",
        "status": "PASS",
        "intents": intents,
        "detected_closing_references": [
            {"issue_number": num, "keyword": kw} for kw, num in detected_refs
        ],
        "claim_ceiling": "PR_ISSUE_CLOSURE_INTENT_VALIDATION_ONLY",
    }
    result["content_sha256"] = canonical_hash(
        {k: v for k, v in result.items() if k != "content_sha256"}
    )
    return result


def render_intent(intents: Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> str:
    items = list(intents) if isinstance(intents, (list, tuple)) else [intents]
    payload = json.dumps(items, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{INTENT_START_MARKER}\n{payload}\n{INTENT_END_MARKER}"


def _git_show(repo_root: Path, revision: str, path: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{revision}:{path}"],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise LaneBindingError("TASK_CARD_NOT_PRESENT_AT_EXACT_REVISION")
    return proc.stdout


def _task_card_metadata(card: bytes) -> tuple[str | None, str | None, str | None]:
    try:
        text = card.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LaneBindingError("TASK_CARD_UTF8_INVALID") from exc
    task = re.search(r"(?m)^task_id:\s*\x60?([^\s\x60]+)\x60?\s*$", text)
    lane = re.search(r"(?m)^execution_lane:\s*\x60?([A-Z_]+)\x60?\s*$", text)
    attempt = re.search(r"(?m)^attempt_id:\s*\x60?([^\s\x60]+)\x60?\s*$", text)
    return (
        task.group(1) if task else None,
        lane.group(1) if lane else None,
        attempt.group(1) if attempt else None,
    )


def _validate_hash_field(payload: dict[str, Any], field: str) -> None:
    expected = _sha(payload.get(field), field.upper(), size=64)
    unsigned = dict(payload)
    unsigned.pop(field, None)
    if canonical_hash(unsigned) != expected:
        raise LaneBindingError(f"{field.upper()}_INVALID")


def _validate_owner(repository: str, owner_id: Any) -> str:
    owner = _exact_str(owner_id, "OWNER_ID")
    repository_owner = repository.split("/", 1)[0]
    if owner != repository_owner:
        raise LaneBindingError("OWNER_ID_REPOSITORY_OWNER_MISMATCH")
    return owner


def _validate_rebind(
    rebind_value: Any,
    *,
    repository: str,
    issue_number: int,
    task_id: str,
    attempt_id: str,
    task_card_path: str,
    task_card_sha256: str,
    pull_request_number: int,
    head_sha: str,
    requested_lane: str,
    owner_id: str,
) -> dict[str, Any]:
    rebind = _exact_dict(rebind_value, "OWNER_LANE_REBIND")
    required = {
        "schema",
        "repository",
        "issue_number",
        "task_id",
        "attempt_id",
        "task_card_path",
        "task_card_sha256",
        "pull_request_number",
        "expected_pr_head_sha",
        "from_lane",
        "to_lane",
        "owner_id",
        "owner_confirmation",
        "record_hash",
    }
    if set(rebind) != required:
        raise LaneBindingError("OWNER_LANE_REBIND_SCHEMA_FIELDS_INVALID")
    if rebind["schema"] != REBIND_SCHEMA:
        raise LaneBindingError("OWNER_LANE_REBIND_SCHEMA_INVALID")
    if rebind["from_lane"] != "GOVERNED" or rebind["to_lane"] != requested_lane:
        raise LaneBindingError("OWNER_LANE_REBIND_LANE_MISMATCH")
    if rebind["owner_confirmation"] is not True:
        raise LaneBindingError("OWNER_LANE_REBIND_OWNER_CONFIRMATION_REQUIRED")
    if (
        rebind["repository"] != repository
        or rebind["issue_number"] != issue_number
        or rebind["task_id"] != task_id
        or rebind["attempt_id"] != attempt_id
        or rebind["task_card_path"] != task_card_path
        or rebind["task_card_sha256"] != task_card_sha256
        or rebind["pull_request_number"] != pull_request_number
        or rebind["expected_pr_head_sha"] != head_sha
        or rebind["owner_id"] != owner_id
    ):
        raise LaneBindingError("OWNER_LANE_REBIND_SUBJECT_MISMATCH")
    _sha(rebind["expected_pr_head_sha"], "EXPECTED_PR_HEAD_SHA", size=40)
    _sha(rebind["task_card_sha256"], "TASK_CARD_SHA256", size=64)
    _safe_id(rebind["task_id"], "TASK_ID")
    _safe_id(rebind["attempt_id"], "ATTEMPT_ID")
    _task_path(rebind["task_card_path"])
    _validate_hash_field(rebind, "record_hash")
    return rebind


def validate_event(
    event: Mapping[str, Any],
    *,
    repo_root: Path,
    enforcement_start_pr_number: int = ENFORCEMENT_START_PR_NUMBER,
    break_glass_comment_fetcher: Callable[[int], Mapping[str, Any]] = _fetch_break_glass_comment,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _exact_dict(event, "EVENT")
    if root.get("event_name") != "pull_request_target":
        raise LaneBindingError("PULL_REQUEST_TARGET_REQUIRED")
    repository_obj = _exact_dict(root.get("repository"), "REPOSITORY")
    repository = _exact_str(repository_obj.get("full_name"), "REPOSITORY_FULL_NAME")
    pr = _exact_dict(root.get("pull_request"), "PULL_REQUEST")
    pr_number = _exact_int(pr.get("number"), "PULL_REQUEST_NUMBER")
    base = _exact_dict(pr.get("base"), "PULL_REQUEST_BASE")
    head = _exact_dict(pr.get("head"), "PULL_REQUEST_HEAD")
    base_sha = _sha(base.get("sha"), "BASE_SHA", size=40)
    head_sha = _sha(head.get("sha"), "HEAD_SHA", size=40)

    if pr_number < enforcement_start_pr_number:
        return {
            "schema": "nexus.trusted_merge_lane_gate_result.v1",
            "status": "PASS",
            "reason": "PRE_ENFORCEMENT_PR_COMPATIBILITY",
            "pull_request_number": pr_number,
            "head_sha": head_sha,
        }

    intent_result = validate_issue_closure_intent(pr.get("body"))

    binding = extract_binding(pr.get("body"))
    if binding.get("schema") != BINDING_SCHEMA:
        raise LaneBindingError("MERGE_LANE_BINDING_SCHEMA_INVALID")
    contract_kind = _exact_str(binding.get("contract_kind"), "CONTRACT_KIND")
    if contract_kind not in CONTRACT_KINDS:
        raise LaneBindingError("CONTRACT_KIND_UNSUPPORTED")
    legacy_binding_fields = {
        "schema",
        "execution_lane",
        "contract_kind",
        "owner_id",
        "issue_number",
        "task_id",
        "attempt_id",
        "task_card_path",
        "task_card_sha256",
        "owner_lane_rebind",
        "binding_hash",
    }
    break_glass_binding_fields = {
        "schema",
        "execution_lane",
        "contract_kind",
        "owner_id",
        "break_glass_integration",
        "binding_hash",
    }
    expected_fields = (
        break_glass_binding_fields
        if contract_kind == BREAK_GLASS_CONTRACT_KIND
        else legacy_binding_fields
    )
    if set(binding) != expected_fields:
        raise LaneBindingError("MERGE_LANE_BINDING_SCHEMA_FIELDS_INVALID")
    _validate_hash_field(binding, "binding_hash")

    lane = _exact_str(binding.get("execution_lane"), "EXECUTION_LANE")
    if lane not in ALL_LANES:
        raise LaneBindingError("EXECUTION_LANE_UNSUPPORTED")
    owner_id = _validate_owner(repository, binding.get("owner_id"))

    if contract_kind == BREAK_GLASS_CONTRACT_KIND:
        if lane != BREAK_GLASS_LANE:
            raise LaneBindingError("BREAK_GLASS_CONTRACT_REQUIRES_BREAK_GLASS_LANE")
        integration = _validate_break_glass_integration(
            binding.get("break_glass_integration"),
            repository=repository,
            pull_request_number=pr_number,
            base_sha=base_sha,
            head_sha=head_sha,
            owner_id=owner_id,
            comment_fetcher=break_glass_comment_fetcher,
            now=now or datetime.now(timezone.utc),
        )
        return {
            "schema": "nexus.trusted_merge_lane_gate_result.v1",
            "status": "PASS",
            "reason": "BREAK_GLASS_OWNER_INTEGRATION_VALID",
            "pull_request_number": pr_number,
            "head_sha": head_sha,
            "execution_lane": lane,
            "binding_hash": binding["binding_hash"],
            "break_glass_integration": integration,
            "issue_closure_intent": intent_result,
        }

    if lane == BREAK_GLASS_LANE:
        raise LaneBindingError("BREAK_GLASS_LANE_REQUIRES_BREAK_GLASS_CONTRACT")

    if contract_kind == "OWNER_INLINE":
        if lane not in DIRECT_LANES:
            raise LaneBindingError("OWNER_INLINE_MUST_BE_DIRECT")
        for field in (
            "issue_number",
            "task_id",
            "attempt_id",
            "task_card_path",
            "task_card_sha256",
            "owner_lane_rebind",
        ):
            if binding[field] is not None:
                raise LaneBindingError("OWNER_INLINE_TRACKED_FIELDS_FORBIDDEN")
        return {
            "schema": "nexus.trusted_merge_lane_gate_result.v1",
            "status": "PASS",
            "reason": "GENUINE_DIRECT_OWNER_INLINE",
            "pull_request_number": pr_number,
            "head_sha": head_sha,
            "execution_lane": lane,
            "binding_hash": binding["binding_hash"],
            "issue_closure_intent": intent_result,
        }

    issue_number = _exact_int(binding.get("issue_number"), "ISSUE_NUMBER")
    task_id = _safe_id(binding.get("task_id"), "TASK_ID")
    attempt_id = _safe_id(binding.get("attempt_id"), "ATTEMPT_ID")
    task_card_path = _task_path(binding.get("task_card_path"))
    task_card_sha256 = _sha(binding.get("task_card_sha256"), "TASK_CARD_SHA256", size=64)

    base_card = _git_show(repo_root, base_sha, task_card_path)
    head_card = _git_show(repo_root, head_sha, task_card_path)
    if base_card != head_card:
        raise LaneBindingError("TASK_CARD_CHANGED_DURING_MERGE_ATTEMPT")
    actual_card_hash = hashlib.sha256(base_card).hexdigest()
    if actual_card_hash != task_card_sha256:
        raise LaneBindingError("TASK_CARD_SHA256_MISMATCH")
    card_task_id, card_lane, card_attempt_id = _task_card_metadata(base_card)
    if card_task_id != task_id:
        raise LaneBindingError("TASK_CARD_TASK_ID_MISMATCH")
    if card_attempt_id is not None and card_attempt_id != attempt_id:
        raise LaneBindingError("TASK_CARD_ATTEMPT_ID_MISMATCH")

    if lane == "GOVERNED":
        if card_lane != "GOVERNED":
            raise LaneBindingError("GOVERNED_BINDING_REQUIRES_GOVERNED_CARD")
        if binding["owner_lane_rebind"] is not None:
            raise LaneBindingError("GOVERNED_BINDING_REBIND_FORBIDDEN")
        return {
            "schema": "nexus.trusted_merge_lane_gate_result.v1",
            "status": "PASS",
            "reason": "GOVERNED_LANE_UNCHANGED",
            "pull_request_number": pr_number,
            "head_sha": head_sha,
            "execution_lane": lane,
            "binding_hash": binding["binding_hash"],
            "issue_closure_intent": intent_result,
        }

    if card_lane == lane:
        if binding["owner_lane_rebind"] is not None:
            raise LaneBindingError("DIRECT_ORIGIN_REBIND_FORBIDDEN")
        return {
            "schema": "nexus.trusted_merge_lane_gate_result.v1",
            "status": "PASS",
            "reason": "TRACKED_TASK_BEGAN_DIRECT",
            "pull_request_number": pr_number,
            "head_sha": head_sha,
            "execution_lane": lane,
            "binding_hash": binding["binding_hash"],
            "issue_closure_intent": intent_result,
        }

    if card_lane != "GOVERNED":
        raise LaneBindingError("DIRECT_REBIND_REQUIRES_GOVERNED_CARD")
    _validate_rebind(
        binding["owner_lane_rebind"],
        repository=repository,
        issue_number=issue_number,
        task_id=task_id,
        attempt_id=attempt_id,
        task_card_path=task_card_path,
        task_card_sha256=task_card_sha256,
        pull_request_number=pr_number,
        head_sha=head_sha,
        requested_lane=lane,
        owner_id=owner_id,
    )
    return {
        "schema": "nexus.trusted_merge_lane_gate_result.v1",
        "status": "PASS",
        "reason": "OWNER_GOVERNED_TO_DIRECT_REBIND_VALID",
        "pull_request_number": pr_number,
        "head_sha": head_sha,
        "execution_lane": lane,
        "binding_hash": binding["binding_hash"],
        "issue_closure_intent": intent_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-json", required=True)
    parser.add_argument("--repo-root", required=True)
    args = parser.parse_args()
    event = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
    try:
        result = validate_event(event, repo_root=Path(args.repo_root))
    except LaneBindingError as exc:
        print(
            json.dumps(
                {
                    "schema": "nexus.trusted_merge_lane_gate_result.v1",
                    "status": "BLOCK",
                    "reason": str(exc),
                },
                sort_keys=True,
            )
        )
        raise SystemExit(1) from exc
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
