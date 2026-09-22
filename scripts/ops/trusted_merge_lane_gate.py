"""Trusted default-branch merge-lane binding gate for protected pull requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

ENFORCEMENT_START_PR_NUMBER = 1061
BINDING_SCHEMA = "nexus.merge_lane_binding.v1"
REBIND_SCHEMA = "nexus.owner_execution_lane_rebind.v1"
DIRECT_LANES = {"DIRECT_CANONICAL", "DIRECT_DELEGATED"}
ALL_LANES = DIRECT_LANES | {"GOVERNED"}
CONTRACT_KINDS = {"OWNER_INLINE", "TRACKED_TASK_CARD"}
START_MARKER = "<!-- NEXUS_MERGE_LANE_V1"
END_MARKER = "NEXUS_MERGE_LANE_V1 -->"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TASK_PATH = re.compile(r"^tasks/[A-Za-z0-9._/-]+\.md$")


class LaneBindingError(ValueError):
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


def render_owner_rebind_comment(rebind: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(rebind), ensure_ascii=False, indent=2, sort_keys=True)
    return f"{OWNER_REBIND_START_MARKER}\n{payload}\n{OWNER_REBIND_END_MARKER}"


def _extract_owner_rebind_comment(body: Any) -> dict[str, Any]:
    if type(body) is not str:
        raise LaneBindingError("OWNER_LANE_REBIND_COMMENT_BODY_INVALID")
    if body.count(OWNER_REBIND_START_MARKER) != 1 or body.count(OWNER_REBIND_END_MARKER) != 1:
        raise LaneBindingError("OWNER_LANE_REBIND_COMMENT_MARKER_INVALID")
    start = body.index(OWNER_REBIND_START_MARKER) + len(OWNER_REBIND_START_MARKER)
    end = body.index(OWNER_REBIND_END_MARKER, start)
    payload = body[start:end].strip()
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise LaneBindingError("OWNER_LANE_REBIND_COMMENT_JSON_INVALID") from exc
    return _exact_dict(value, "OWNER_LANE_REBIND_COMMENT")


def _validate_owner_rebind_comment(
    comments: Any,
    *,
    comment_id: int,
    expected_rebind: Mapping[str, Any],
    owner_id: str,
) -> None:
    if type(comments) is not list:
        raise LaneBindingError("OWNER_LANE_REBIND_COMMENTS_REQUIRED")
    matches = [
        comment
        for comment in comments
        if type(comment) is dict and comment.get("id") == comment_id
    ]
    if len(matches) != 1:
        raise LaneBindingError("OWNER_LANE_REBIND_COMMENT_NOT_FOUND")
    comment = matches[0]
    user = _exact_dict(comment.get("user"), "OWNER_LANE_REBIND_COMMENT_USER")
    if user.get("login") != owner_id or comment.get("author_association") != "OWNER":
        raise LaneBindingError("OWNER_LANE_REBIND_COMMENT_AUTHOR_INVALID")
    actual_rebind = _extract_owner_rebind_comment(comment.get("body"))
    if actual_rebind != dict(expected_rebind):
        raise LaneBindingError("OWNER_LANE_REBIND_COMMENT_SUBJECT_MISMATCH")


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
        }

    if card_lane != "GOVERNED":
        raise LaneBindingError("DIRECT_REBIND_REQUIRES_GOVERNED_CARD")
    rebind = _validate_rebind(
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
    comment_id = _exact_int(
        binding.get("owner_lane_rebind_comment_id"),
        "OWNER_LANE_REBIND_COMMENT_ID",
    )
    _validate_owner_rebind_comment(
        comments,
        comment_id=comment_id,
        expected_rebind=rebind,
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
