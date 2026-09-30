"""Trusted default-branch merge-lane binding gate for protected pull requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

ENFORCEMENT_START_PR_NUMBER = 1061
BINDING_SCHEMA = "nexus.merge_lane_binding.v1"
REBIND_SCHEMA = "nexus.owner_execution_lane_rebind.v1"
DIRECT_LANES = {"DIRECT_CANONICAL", "DIRECT_DELEGATED"}
ALL_LANES = DIRECT_LANES | {"GOVERNED"}
CONTRACT_KINDS = {"OWNER_INLINE", "TRACKED_TASK_CARD"}
START_MARKER = "<!-- NEXUS_MERGE_LANE_V1"
END_MARKER = "NEXUS_MERGE_LANE_V1 -->"
INTENT_START_MARKER = "<!-- NEXUS_ISSUE_INTENT_V1"
INTENT_END_MARKER = "NEXUS_ISSUE_INTENT_V1 -->"
ON_MERGE_KEEP_OPEN = "KEEP_OPEN"
ON_MERGE_CLOSE = "CLOSE"
VALID_ON_MERGE_ACTIONS = frozenset({ON_MERGE_KEEP_OPEN, ON_MERGE_CLOSE})
MERGE_INTENT_BINDING_SCHEMA = "nexus.merge_intent_binding.v1"
SUPPORTED_MERGE_METHODS = frozenset({"merge", "squash", "rebase"})
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

        normalized.append({
            "issue_number": issue,
            "on_merge": action,
        })

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
    result["content_sha256"] = canonical_hash({
        k: v for k, v in result.items() if k != "content_sha256"
    })
    return result


def render_intent(intents: Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> str:
    items = list(intents) if isinstance(intents, (list, tuple)) else [intents]
    payload = json.dumps(items, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{INTENT_START_MARKER}\n{payload}\n{INTENT_END_MARKER}"


def validate_final_merge_intent_binding(
    *,
    pr_body: str | None,
    pr_number: int,
    head_sha: str,
    base_sha: str,
    expected_pr_number: int,
    expected_head_sha: str,
    expected_base_sha: str,
    merge_method: str = "squash",
    commit_title: str | None = None,
    commit_message: str | None = None,
) -> dict[str, Any]:
    if pr_body is None or not isinstance(pr_body, str) or not pr_body.strip():
        raise IssueClosureIntentError("PR_BODY_REQUIRED")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        raise IssueClosureIntentError("PR_NUMBER_INVALID")
    if (
        not isinstance(expected_pr_number, int)
        or isinstance(expected_pr_number, bool)
        or expected_pr_number <= 0
    ):
        raise IssueClosureIntentError("EXPECTED_PR_NUMBER_INVALID")
    if pr_number != expected_pr_number:
        raise IssueClosureIntentError(
            f"PR_NUMBER_MISMATCH: expected {expected_pr_number}, got {pr_number}"
        )

    if not isinstance(head_sha, str) or not isinstance(expected_head_sha, str):
        raise IssueClosureIntentError("HEAD_SHA_INVALID")
    if head_sha.strip().lower() != expected_head_sha.strip().lower():
        raise IssueClosureIntentError(
            f"HEAD_SHA_MISMATCH: expected {expected_head_sha}, got {head_sha}"
        )

    if not isinstance(base_sha, str) or not isinstance(expected_base_sha, str):
        raise IssueClosureIntentError("BASE_SHA_INVALID")
    if base_sha.strip().lower() != expected_base_sha.strip().lower():
        raise IssueClosureIntentError(
            f"BASE_SHA_MISMATCH: expected {expected_base_sha}, got {base_sha}"
        )

    norm_method = str(merge_method or "squash").strip().lower()
    if norm_method not in SUPPORTED_MERGE_METHODS:
        raise IssueClosureIntentError(f"UNSUPPORTED_MERGE_METHOD: {merge_method!r}")

    intent_result = validate_issue_closure_intent(pr_body)
    intents = intent_result.get("intents", [])

    final_fields_prose = f"{commit_title or ''}\n\n{commit_message or ''}"
    final_refs = find_closing_keyword_references(final_fields_prose)

    detected_in_final: dict[int, list[str]] = {}
    for kw, num in final_refs:
        detected_in_final.setdefault(num, []).append(kw)

    intent_by_issue = {item["issue_number"]: item["on_merge"] for item in intents}

    untracked_issues = set(detected_in_final.keys()) - set(intent_by_issue.keys())
    if untracked_issues:
        culprits = ", ".join(
            f"#{num} ({', '.join(detected_in_final[num])})" for num in sorted(untracked_issues)
        )
        raise IssueClosureIntentError(
            f"UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE: Final merge fields contain GitHub closing keywords targeting {culprits}. "
            "Remove closing keywords or declare explicit intent in PR body."
        )

    for issue_num, action in intent_by_issue.items():
        if action == ON_MERGE_KEEP_OPEN:
            if issue_num in detected_in_final:
                kws = ", ".join(detected_in_final[issue_num])
                raise IssueClosureIntentError(
                    f"REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN_IN_FINAL_MERGE_FIELDS: Final merge commit fields contain closing keyword '{kws}' targeting #{issue_num}, "
                    f"which contradicts declared KEEP_OPEN intent and would trigger GitHub auto-close."
                )

    result: dict[str, Any] = {
        "schema": MERGE_INTENT_BINDING_SCHEMA,
        "status": "PASS",
        "pr_number": pr_number,
        "head_sha": head_sha.strip().lower(),
        "base_sha": base_sha.strip().lower(),
        "merge_method": norm_method,
        "intents": intents,
        "detected_final_closing_references": [
            {"issue_number": num, "keyword": kw} for kw, num in final_refs
        ],
        "claim_ceiling": "PR_ISSUE_CLOSURE_INTENT_VALIDATION_ONLY",
    }
    result["content_sha256"] = canonical_hash({
        k: v for k, v in result.items() if k != "content_sha256"
    })
    return result


def _git_show(repo_root: Path, revision: str, path: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{revision}:{path}"],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise LaneBindingError("TASK_CARD_NOT_PRESENT_AT_EXACT_REVISION")
    return proc.stdout


def _candidate_commit_messages(repo_root: Path, *, base_sha: str, head_sha: str) -> str:
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "log",
            "--format=%B%x00",
            f"{base_sha}..{head_sha}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise LaneBindingError("CANDIDATE_COMMIT_MESSAGES_UNAVAILABLE")
    return "\n\n".join(part.strip() for part in proc.stdout.split("\x00") if part.strip())


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

    commit_title = pr.get("commit_title")
    if commit_title is None:
        commit_title = pr.get("title")
    commit_message = pr.get("commit_message")
    if commit_message is None:
        commit_message = _candidate_commit_messages(
            repo_root,
            base_sha=base_sha,
            head_sha=head_sha,
        )
    merge_method = pr.get("merge_method") or "squash"

    final_binding = validate_final_merge_intent_binding(
        pr_body=pr.get("body"),
        pr_number=pr_number,
        head_sha=head_sha,
        base_sha=base_sha,
        expected_pr_number=pr_number,
        expected_head_sha=head_sha,
        expected_base_sha=base_sha,
        merge_method=merge_method,
        commit_title=commit_title,
        commit_message=commit_message,
    )

    binding = extract_binding(pr.get("body"))
    if binding.get("schema") != BINDING_SCHEMA:
        raise LaneBindingError("MERGE_LANE_BINDING_SCHEMA_INVALID")
    required_binding_fields = {
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
    if set(binding) != required_binding_fields:
        raise LaneBindingError("MERGE_LANE_BINDING_SCHEMA_FIELDS_INVALID")
    _validate_hash_field(binding, "binding_hash")

    lane = _exact_str(binding.get("execution_lane"), "EXECUTION_LANE")
    if lane not in ALL_LANES:
        raise LaneBindingError("EXECUTION_LANE_UNSUPPORTED")
    contract_kind = _exact_str(binding.get("contract_kind"), "CONTRACT_KIND")
    if contract_kind not in CONTRACT_KINDS:
        raise LaneBindingError("CONTRACT_KIND_UNSUPPORTED")
    owner_id = _validate_owner(repository, binding.get("owner_id"))

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
            "merge_intent_binding": final_binding,
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
            "merge_intent_binding": final_binding,
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
            "merge_intent_binding": final_binding,
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
        "merge_intent_binding": final_binding,
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
