#!/usr/bin/env python3
"""Validate a machine-readable Nexus Candidate acceptance result."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = "nexus.candidate_acceptance.v3"
VALIDATION_SCHEMA = "nexus.candidate_acceptance.validation.v3"
PACKET_SCHEMA = "nexus.compiled_model_task_packet.v3"
CURRENT_MANIFEST_SCHEMA = "nexus.chatgpt_mcp_execution.v4"
LEGACY_MANIFEST_SCHEMA = "nexus.chatgpt_mcp_execution.v3"
CURRENT_RECEIPT_SCHEMA = "nexus.mcp_execution_receipt.v2"
LEGACY_RECEIPT_SCHEMA = "nexus.mcp_execution_receipt.v1"
RECEIPT_SCHEMAS = {CURRENT_RECEIPT_SCHEMA, LEGACY_RECEIPT_SCHEMA}
VERDICTS = {
    "ACCEPT_CANDIDATE",
    "REJECT_CANDIDATE",
    "ACCEPTANCE_BLOCKED",
    "OWNER_DECISION_REQUIRED",
}
CONTRACT_KINDS = {"TRACKED_TASK_CARD", "OWNER_INLINE"}
AXES = {
    "authority",
    "subject_identity",
    "lineage",
    "independent_behavior",
    "provenance",
    "claim_discipline",
}
AXIS_VERDICTS = {"PASS", "FAIL", "BLOCKED", "NOT_REQUIRED"}
TRANSPORT_MODES = {"LIVE_MCP", "LOCAL_READ_ONLY", "SOURCE_BOUNDED"}
HOST_BINDING = {
    "AVAILABLE",
    "HOST_ACTION_BINDING_GAP",
    "ACTION_RESOLUTION_FAILURE",
    "SERVER_ACTION_NOT_FOUND",
    "NOT_APPLICABLE",
    "UNKNOWN",
}
VERIFY_SURFACES = {"FULL_VERIFY", "OBSERVE_ONLY", "UNAVAILABLE"}
INDEPENDENCE = {"INDEPENDENT_REVIEWER", "PARTIAL_INDEPENDENCE", "UNVERIFIED"}
COMMAND_RESULTS = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}
APPROVAL_STATES = {
    "READY_FOR_OWNER_APPROVAL",
    "BLOCKED_BY_TRANSPORT_FRESHNESS",
    "BLOCKED_BY_HOST_BINDING",
    "BLOCKED_BY_LIFECYCLE_STATE",
    "NOT_EVALUATED",
}
NEXT_GATE_BY_APPROVAL = {
    "READY_FOR_OWNER_APPROVAL": "OWNER_CANDIDATE_APPROVAL",
    "BLOCKED_BY_TRANSPORT_FRESHNESS": "REFRESH_OWNER_APPROVAL_BINDING",
    "BLOCKED_BY_HOST_BINDING": "RESTORE_OWNER_APPROVAL_ACTION_BINDING",
    "BLOCKED_BY_LIFECYCLE_STATE": "RECONCILE_CANDIDATE_LIFECYCLE_STATE",
    "NOT_EVALUATED": "OWNER_REVIEW_ACCEPTANCE_RESULT",
}
MIN_APPROVAL_BINDINGS = {
    "contract_kind",
    "contract_hash",
    "task_id",
    "attempt_id",
    "lifecycle_revision",
    "server_instance_id",
    "tool_manifest_hash",
    "full_tool_schema_hash",
    "permission_policy_hash",
    "candidate_commit_sha",
    "candidate_tree_sha",
    "candidate_state_hash",
    "verified_receipt_hash",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
GIT_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")
SECRET_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._~-]+|api[_-]?key\s*[:=]|password\s*[:=]|private[_-]?key\s*[:=])"
)


class DuplicateKeyError(ValueError):
    pass


def no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(key)
        out[key] = value
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--task-card", type=Path)
    parser.add_argument("--compiled-packet", type=Path)
    parser.add_argument("--execution-manifest", type=Path)
    parser.add_argument("--executor-receipt", type=Path)
    parser.add_argument("--runtime-admission", type=Path)
    return parser.parse_args()


def canonical_sha256(data: dict[str, Any]) -> str:
    cloned = copy.deepcopy(data)
    cloned.setdefault("integrity", {})["sha256"] = "0" * 64
    raw = json.dumps(
        cloned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nullable_nonempty(value: Any) -> bool:
    return value is None or nonempty(value)


def exact(obj: Any, keys: set[str]) -> bool:
    return isinstance(obj, dict) and set(obj) == keys


def validate_hash(
    errors: list[str], path: str, value: Any, *, nullable: bool = False
) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        errors.append(f"{path}: lowercase SHA-256 required")


def validate_git(
    errors: list[str], path: str, value: Any, *, nullable: bool = False
) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not GIT_OID.fullmatch(value):
        errors.append(f"{path}: exactly 40 or 64 lowercase hexadecimal Git OID required")


def validate_nullable_bool(errors: list[str], path: str, value: Any) -> None:
    if value is not None and not isinstance(value, bool):
        errors.append(f"{path}: boolean or null required")


def validate(data: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return {
            "schema": VALIDATION_SCHEMA,
            "valid": False,
            "errors": ["$: object required"],
            "warnings": [],
        }

    required_top = {
        "schema",
        "acceptance_id",
        "created_at",
        "verdict",
        "source",
        "repository",
        "transport",
        "axes",
        "review",
        "approval_readiness",
        "approval_boundary",
        "maximum_supportable_claim",
        "next_gate",
        "blockers",
        "integrity",
    }
    if set(data) != required_top:
        missing = required_top - set(data)
        extra = set(data) - required_top
        if missing:
            errors.append(f"$: missing fields: {', '.join(sorted(missing))}")
        if extra:
            errors.append(f"$: unexpected fields: {', '.join(sorted(extra))}")

    if data.get("schema") != SCHEMA:
        errors.append(f"$.schema: expected {SCHEMA}")
    if not isinstance(data.get("acceptance_id"), str) or not ID_RE.fullmatch(
        data.get("acceptance_id", "")
    ):
        errors.append("$.acceptance_id: invalid identifier")
    try:
        created = datetime.fromisoformat(
            str(data.get("created_at", "")).replace("Z", "+00:00")
        )
        if created.tzinfo is None:
            raise ValueError
    except ValueError:
        errors.append("$.created_at: timezone-aware ISO-8601 required")

    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        errors.append("$.verdict: invalid")

    source_keys = {
        "contract_kind",
        "campaign_id",
        "task_id",
        "contract_hash",
        "task_card_path",
        "task_card_sha256",
        "compiled_packet_sha256",
        "execution_manifest_sha256",
        "executor_receipt_sha256",
        "implementer_attempt_id",
        "reviewer_attempt_id",
    }
    source = data.get("source")
    if not exact(source, source_keys):
        errors.append("$.source: exact source fields required")
        source = {}
    contract_kind = source.get("contract_kind")
    if contract_kind not in CONTRACT_KINDS:
        errors.append("$.source.contract_kind: invalid")
    for key in (
        "task_id",
        "implementer_attempt_id",
        "reviewer_attempt_id",
    ):
        if not nonempty(source.get(key)):
            errors.append(f"$.source.{key}: required")
    if not nullable_nonempty(source.get("campaign_id")):
        errors.append("$.source.campaign_id: string or null required")
    validate_hash(errors, "$.source.contract_hash", source.get("contract_hash"))
    validate_hash(
        errors,
        "$.source.executor_receipt_sha256",
        source.get("executor_receipt_sha256"),
    )
    for key in (
        "task_card_sha256",
        "compiled_packet_sha256",
        "execution_manifest_sha256",
    ):
        validate_hash(errors, f"$.source.{key}", source.get(key), nullable=True)
    if source.get("task_card_path") is not None and not nonempty(
        source.get("task_card_path")
    ):
        errors.append("$.source.task_card_path: string or null required")

    if contract_kind == "TRACKED_TASK_CARD":
        if not nonempty(source.get("campaign_id")):
            errors.append("$.source.campaign_id: required for TRACKED_TASK_CARD")
        if not nonempty(source.get("task_card_path")):
            errors.append("$.source.task_card_path: required for TRACKED_TASK_CARD")
        validate_hash(
            errors,
            "$.source.task_card_sha256",
            source.get("task_card_sha256"),
        )
    elif contract_kind == "OWNER_INLINE":
        if source.get("task_card_path") is not None:
            errors.append("$.source.task_card_path: must be null for OWNER_INLINE")
        if source.get("task_card_sha256") is not None:
            errors.append("$.source.task_card_sha256: must be null for OWNER_INLINE")

    reviewer_distinct = (
        nonempty(source.get("reviewer_attempt_id"))
        and source.get("reviewer_attempt_id") != source.get("implementer_attempt_id")
    )
    if not reviewer_distinct:
        errors.append(
            "$.source.reviewer_attempt_id: reviewer attempt must differ from implementer attempt"
        )

    repo_keys = {
        "root",
        "branch",
        "executor_observed_head",
        "audit_start_head",
        "audit_end_head",
        "expected_base_commit",
        "candidate_commit_sha",
        "candidate_tree_sha",
        "candidate_state_hash",
        "candidate_diff_sha256",
        "verified_receipt_hash",
        "dirty_state",
        "candidate_integrated",
        "repository_drift_during_audit",
    }
    repository = data.get("repository")
    if not exact(repository, repo_keys):
        errors.append("$.repository: exact repository fields required")
        repository = {}
    for key in ("root", "branch", "dirty_state"):
        if not nonempty(repository.get(key)):
            errors.append(f"$.repository.{key}: required")
    for key in (
        "executor_observed_head",
        "audit_start_head",
        "audit_end_head",
        "expected_base_commit",
        "candidate_commit_sha",
        "candidate_tree_sha",
    ):
        validate_git(errors, f"$.repository.{key}", repository.get(key))
    for key in (
        "candidate_state_hash",
        "candidate_diff_sha256",
        "verified_receipt_hash",
    ):
        validate_hash(errors, f"$.repository.{key}", repository.get(key))
    for key in ("candidate_integrated", "repository_drift_during_audit"):
        if not isinstance(repository.get(key), bool):
            errors.append(f"$.repository.{key}: boolean required")

    transport_keys = {
        "mode",
        "server_instance_id",
        "canonical_root",
        "action_contract_hash",
        "tool_manifest_hash",
        "full_tool_schema_hash",
        "permission_policy_hash",
        "lifecycle_revision",
        "host_binding_status",
        "verification_surface",
        "reload_required",
        "action_review_required",
        "permission_review_required",
        "runtime_source_drift",
        "transport_stable",
        "start_evidence_ref",
        "end_evidence_ref",
    }
    transport = data.get("transport")
    if not exact(transport, transport_keys):
        errors.append("$.transport: exact transport fields required")
        transport = {}
    mode = transport.get("mode")
    if mode not in TRANSPORT_MODES:
        errors.append("$.transport.mode: invalid")
    if transport.get("host_binding_status") not in HOST_BINDING:
        errors.append("$.transport.host_binding_status: invalid")
    if transport.get("verification_surface") not in VERIFY_SURFACES:
        errors.append("$.transport.verification_surface: invalid")
    if not isinstance(transport.get("transport_stable"), bool):
        errors.append("$.transport.transport_stable: boolean required")
    for key in (
        "reload_required",
        "action_review_required",
        "permission_review_required",
        "runtime_source_drift",
    ):
        validate_nullable_bool(errors, f"$.transport.{key}", transport.get(key))
    for key in ("server_instance_id", "canonical_root", "lifecycle_revision"):
        if not nullable_nonempty(transport.get(key)):
            errors.append(f"$.transport.{key}: string or null required")
    for key in (
        "action_contract_hash",
        "tool_manifest_hash",
        "full_tool_schema_hash",
        "permission_policy_hash",
    ):
        validate_hash(errors, f"$.transport.{key}", transport.get(key), nullable=True)
    for key in ("start_evidence_ref", "end_evidence_ref"):
        if not nonempty(transport.get(key)):
            errors.append(f"$.transport.{key}: required")

    if mode == "LIVE_MCP":
        for key in ("server_instance_id", "canonical_root", "lifecycle_revision"):
            if not nonempty(transport.get(key)):
                errors.append(f"$.transport.{key}: required for LIVE_MCP")
        for key in (
            "action_contract_hash",
            "tool_manifest_hash",
            "full_tool_schema_hash",
            "permission_policy_hash",
        ):
            validate_hash(errors, f"$.transport.{key}", transport.get(key))
        for key in (
            "reload_required",
            "action_review_required",
            "permission_review_required",
            "runtime_source_drift",
        ):
            if not isinstance(transport.get(key), bool):
                errors.append(f"$.transport.{key}: boolean required for LIVE_MCP")

    axes = data.get("axes")
    if not isinstance(axes, dict) or set(axes) != AXES:
        errors.append("$.axes: exact six evidence axes required")
        axes = {}
    required_axis_values: list[str] = []
    for name in AXES:
        item = axes.get(name)
        if not exact(item, {"required", "verdict", "reason", "evidence_refs"}):
            errors.append(
                f"$.axes.{name}: required/verdict/reason/evidence_refs required"
            )
            continue
        if not isinstance(item.get("required"), bool):
            errors.append(f"$.axes.{name}.required: boolean required")
        axis_verdict = item.get("verdict")
        if axis_verdict not in AXIS_VERDICTS:
            errors.append(f"$.axes.{name}.verdict: invalid")
        if not nonempty(item.get("reason")):
            errors.append(f"$.axes.{name}.reason: required")
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or not all(nonempty(ref) for ref in refs):
            errors.append(f"$.axes.{name}.evidence_refs: string array required")
            refs = []
        if item.get("required") is True:
            required_axis_values.append(axis_verdict)
            if axis_verdict == "NOT_REQUIRED":
                errors.append(f"$.axes.{name}: required axis cannot be NOT_REQUIRED")
        elif axis_verdict != "NOT_REQUIRED":
            warnings.append(
                f"$.axes.{name}: non-required axis is reported as {axis_verdict}"
            )
        if axis_verdict in {"PASS", "FAIL", "BLOCKED"} and not refs:
            errors.append(f"$.axes.{name}: evidence required")

    review_keys = {
        "reviewer_distinct",
        "independence_class",
        "commands",
        "anti_false_green",
        "transport_failures",
    }
    review = data.get("review")
    if not exact(review, review_keys):
        errors.append("$.review: exact review fields required")
        review = {}
    if review.get("reviewer_distinct") is not True or not reviewer_distinct:
        errors.append("$.review.reviewer_distinct: must be true")
    if review.get("independence_class") not in INDEPENDENCE:
        errors.append("$.review.independence_class: invalid")
    commands = review.get("commands")
    if not isinstance(commands, list):
        errors.append("$.review.commands: array required")
        commands = []
    else:
        command_keys = {
            "id",
            "cwd",
            "argv",
            "result_class",
            "exit_code",
            "duration_ms",
            "changed_paths",
            "evidence_ref",
        }
        for index, command in enumerate(commands):
            path = f"$.review.commands[{index}]"
            if not exact(command, command_keys):
                errors.append(f"{path}: exact command fields required")
                continue
            for key in ("id", "cwd", "evidence_ref"):
                if not nonempty(command.get(key)):
                    errors.append(f"{path}.{key}: required")
            argv = command.get("argv")
            if not isinstance(argv, list) or not argv or not all(
                nonempty(item) for item in argv
            ):
                errors.append(f"{path}.argv: non-empty string array required")
            result_class = command.get("result_class")
            if result_class not in COMMAND_RESULTS:
                errors.append(f"{path}.result_class: invalid")
            exit_code = command.get("exit_code")
            if exit_code is not None and not isinstance(exit_code, int):
                errors.append(f"{path}.exit_code: integer or null required")
            duration_ms = command.get("duration_ms")
            if duration_ms is not None and (
                not isinstance(duration_ms, int) or duration_ms < 0
            ):
                errors.append(f"{path}.duration_ms: non-negative integer or null required")
            changed_paths = command.get("changed_paths")
            if not isinstance(changed_paths, list) or not all(
                nonempty(item) for item in changed_paths
            ):
                errors.append(f"{path}.changed_paths: string array required")
            if result_class == "PASS" and exit_code != 0:
                errors.append(f"{path}: PASS requires exit_code 0")
            if result_class in {"BLOCKED", "NOT_RUN"} and exit_code is not None:
                warnings.append(f"{path}: blocked/not-run command normally has null exit")
    if not nonempty(review.get("anti_false_green")):
        errors.append("$.review.anti_false_green: required")
    transport_failures = review.get("transport_failures")
    if not isinstance(transport_failures, list) or not all(
        nonempty(item) for item in transport_failures
    ):
        errors.append("$.review.transport_failures: string array required")

    independent_axis = axes.get("independent_behavior", {})
    if (
        isinstance(independent_axis, dict)
        and independent_axis.get("required") is True
        and independent_axis.get("verdict") == "PASS"
        and not any(
            isinstance(command, dict) and command.get("result_class") == "PASS"
            for command in commands
        )
    ):
        errors.append(
            "$.review.commands: independent_behavior PASS requires at least one PASS command"
        )

    readiness_keys = {
        "status",
        "task_pending_acceptance",
        "exact_binding_match",
        "approval_action_available",
        "approval_contract_created",
        "candidate_already_approved",
        "candidate_already_integrated",
        "required_binding_fields",
        "blockers",
        "evidence_refs",
    }
    readiness = data.get("approval_readiness")
    if not exact(readiness, readiness_keys):
        errors.append("$.approval_readiness: exact fields required")
        readiness = {}
    readiness_status = readiness.get("status")
    if readiness_status not in APPROVAL_STATES:
        errors.append("$.approval_readiness.status: invalid")
    for key in (
        "task_pending_acceptance",
        "exact_binding_match",
        "approval_action_available",
        "candidate_already_approved",
        "candidate_already_integrated",
    ):
        validate_nullable_bool(errors, f"$.approval_readiness.{key}", readiness.get(key))
    if readiness.get("approval_contract_created") is not False:
        errors.append("$.approval_readiness.approval_contract_created: must be false")
    binding_fields = readiness.get("required_binding_fields")
    if not isinstance(binding_fields, list) or not all(
        nonempty(item) for item in binding_fields
    ):
        errors.append("$.approval_readiness.required_binding_fields: string array required")
        binding_fields = []
    if not MIN_APPROVAL_BINDINGS.issubset(set(binding_fields)):
        missing = sorted(MIN_APPROVAL_BINDINGS - set(binding_fields))
        errors.append(
            "$.approval_readiness.required_binding_fields: missing "
            + ", ".join(missing)
        )
    if contract_kind == "TRACKED_TASK_CARD" and "task_card_hash" not in binding_fields:
        errors.append(
            "$.approval_readiness.required_binding_fields: TRACKED_TASK_CARD requires task_card_hash"
        )
    readiness_blockers = readiness.get("blockers")
    if not isinstance(readiness_blockers, list) or not all(
        nonempty(item) for item in readiness_blockers
    ):
        errors.append("$.approval_readiness.blockers: string array required")
        readiness_blockers = []
    readiness_refs = readiness.get("evidence_refs")
    if not isinstance(readiness_refs, list) or not all(
        nonempty(item) for item in readiness_refs
    ):
        errors.append("$.approval_readiness.evidence_refs: string array required")
        readiness_refs = []
    if readiness_status != "NOT_EVALUATED" and not readiness_refs:
        errors.append("$.approval_readiness.evidence_refs: evidence required")

    if readiness_status == "READY_FOR_OWNER_APPROVAL":
        ready_conditions = {
            "task_pending_acceptance": readiness.get("task_pending_acceptance") is True,
            "exact_binding_match": readiness.get("exact_binding_match") is True,
            "approval_action_available": readiness.get("approval_action_available") is True,
            "candidate_already_approved": readiness.get("candidate_already_approved") is False,
            "candidate_already_integrated": readiness.get("candidate_already_integrated") is False,
            "candidate_integrated": repository.get("candidate_integrated") is False,
            "transport_stable": transport.get("transport_stable") is True,
            "host_binding": transport.get("host_binding_status") == "AVAILABLE",
            "reload_required": transport.get("reload_required") is False,
            "action_review_required": transport.get("action_review_required") is False,
            "permission_review_required": transport.get("permission_review_required") is False,
            "runtime_source_drift": transport.get("runtime_source_drift") is False,
        }
        for name, ok in ready_conditions.items():
            if not ok:
                errors.append(
                    f"$.approval_readiness: READY_FOR_OWNER_APPROVAL requires {name}"
                )
        if readiness_blockers:
            errors.append(
                "$.approval_readiness.blockers: ready state requires no blockers"
            )
    else:
        if not readiness_blockers and readiness_status != "NOT_EVALUATED":
            errors.append(
                "$.approval_readiness.blockers: blocked readiness requires blockers"
            )

    if readiness_status == "BLOCKED_BY_HOST_BINDING" and transport.get(
        "host_binding_status"
    ) not in {"HOST_ACTION_BINDING_GAP", "ACTION_RESOLUTION_FAILURE", "UNKNOWN"}:
        errors.append(
            "$.approval_readiness.status: host-binding block requires matching host status"
        )
    if readiness_status == "BLOCKED_BY_TRANSPORT_FRESHNESS":
        freshness_problem = (
            transport.get("transport_stable") is False
            or transport.get("reload_required") is True
            or transport.get("action_review_required") is True
            or transport.get("permission_review_required") is True
            or transport.get("runtime_source_drift") is True
        )
        if not freshness_problem:
            errors.append(
                "$.approval_readiness.status: transport freshness block lacks freshness evidence"
            )
    if readiness_status == "BLOCKED_BY_LIFECYCLE_STATE":
        lifecycle_problem = (
            readiness.get("task_pending_acceptance") is not True
            or readiness.get("exact_binding_match") is not True
            or readiness.get("candidate_already_approved") is True
            or readiness.get("candidate_already_integrated") is True
            or repository.get("candidate_integrated") is True
        )
        if not lifecycle_problem:
            errors.append(
                "$.approval_readiness.status: lifecycle block lacks lifecycle evidence"
            )

    boundary_keys = {
        "acceptance_recommendation_only",
        "candidate_approved",
        "approval_contract_created",
        "integrated",
        "public_claim_allowed",
        "owner_action_required",
    }
    boundary = data.get("approval_boundary")
    if not exact(boundary, boundary_keys):
        errors.append("$.approval_boundary: exact fields required")
        boundary = {}
    if boundary.get("acceptance_recommendation_only") is not True:
        errors.append(
            "$.approval_boundary.acceptance_recommendation_only: must be true"
        )
    for key in (
        "candidate_approved",
        "approval_contract_created",
        "integrated",
        "public_claim_allowed",
    ):
        if boundary.get(key) is not False:
            errors.append(f"$.approval_boundary.{key}: must be false")
    if boundary.get("owner_action_required") is not True:
        errors.append("$.approval_boundary.owner_action_required: must be true")

    if not nonempty(data.get("maximum_supportable_claim")):
        errors.append("$.maximum_supportable_claim: required")
    if not nonempty(data.get("next_gate")):
        errors.append("$.next_gate: required")
    blockers = data.get("blockers")
    if not isinstance(blockers, list) or not all(nonempty(item) for item in blockers):
        errors.append("$.blockers: string array required")
        blockers = []

    if verdict == "ACCEPT_CANDIDATE":
        if any(value != "PASS" for value in required_axis_values):
            errors.append(
                "$.verdict: ACCEPT_CANDIDATE requires all required axes PASS"
            )
        if blockers:
            errors.append("$.blockers: accepted Candidate requires no Candidate blockers")
        if review.get("independence_class") != "INDEPENDENT_REVIEWER":
            errors.append(
                "$.review.independence_class: ACCEPT_CANDIDATE requires INDEPENDENT_REVIEWER"
            )
        expected_gate = NEXT_GATE_BY_APPROVAL.get(readiness_status)
        if expected_gate and data.get("next_gate") != expected_gate:
            errors.append(
                f"$.next_gate: accepted Candidate with {readiness_status} requires {expected_gate}"
            )
    elif verdict == "REJECT_CANDIDATE":
        if "FAIL" not in required_axis_values:
            errors.append("$.verdict: REJECT_CANDIDATE requires a failed required axis")
        if not blockers:
            errors.append("$.blockers: rejected Candidate requires reasons")
        if data.get("next_gate") != "OWNER_REJECT_OR_REWORK_CANDIDATE":
            errors.append(
                "$.next_gate: rejected Candidate requires OWNER_REJECT_OR_REWORK_CANDIDATE"
            )
    elif verdict == "ACCEPTANCE_BLOCKED":
        if "BLOCKED" not in required_axis_values:
            errors.append(
                "$.verdict: ACCEPTANCE_BLOCKED requires a blocked required axis"
            )
        if not blockers:
            errors.append("$.blockers: blocked acceptance requires blockers")
        if data.get("next_gate") != "RESOLVE_ACCEPTANCE_BLOCKER":
            errors.append(
                "$.next_gate: blocked acceptance requires RESOLVE_ACCEPTANCE_BLOCKER"
            )
    elif verdict == "OWNER_DECISION_REQUIRED":
        if any(value in {"FAIL", "BLOCKED"} for value in required_axis_values):
            errors.append(
                "$.verdict: OWNER_DECISION_REQUIRED cannot hide failed or blocked evidence"
            )
        if not blockers:
            errors.append("$.blockers: owner policy decision must be named")
        if data.get("next_gate") != "OWNER_POLICY_DECISION":
            errors.append(
                "$.next_gate: owner decision requires OWNER_POLICY_DECISION"
            )

    integrity = data.get("integrity")
    if not exact(integrity, {"sha256"}):
        errors.append("$.integrity: sha256 only")
    elif integrity.get("sha256") != canonical_sha256(data):
        errors.append("$.integrity.sha256: canonical integrity mismatch")

    if SECRET_RE.search(json.dumps(data, ensure_ascii=False)):
        errors.append("$: possible secret material detected")

    return {
        "schema": VALIDATION_SCHEMA,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def safe_regular_file(path: Path, *, max_size: int = 4 * 1024 * 1024) -> None:
    info = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size > max_size
    ):
        raise OSError(f"unsafe bound source: {path}")


def read_bound_json(path: Path) -> dict[str, Any]:
    safe_regular_file(path)
    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_pairs
    )
    if not isinstance(value, dict):
        raise ValueError(f"bound source must be an object: {path}")
    return value


def file_sha256(path: Path) -> str:
    safe_regular_file(path, max_size=16 * 1024 * 1024)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runtime_admission_validator() -> Any:
    validator_path = Path(__file__).with_name("validate_runtime_admission.py")
    spec = importlib.util.spec_from_file_location(
        "nexus_candidate_runtime_admission_validator", validator_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load runtime admission validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record_physical_finding(
    data: dict[str, Any],
    errors: list[str],
    warnings: list[str],
    message: str,
    *,
    axis: str,
) -> None:
    """Require physical contradictions to be reflected by a non-accept verdict.

    A rejection/block should itself be structurally valid when the physical mismatch is
    exactly the evidence that caused it. ACCEPT_CANDIDATE must fail closed.
    """
    axes = data.get("axes", {}) if isinstance(data.get("axes"), dict) else {}
    axis_item = axes.get(axis, {}) if isinstance(axes.get(axis), dict) else {}
    axis_verdict = axis_item.get("verdict")
    if data.get("verdict") == "ACCEPT_CANDIDATE":
        errors.append(message)
    elif axis_verdict in {"FAIL", "BLOCKED"}:
        warnings.append(f"physical finding reflected by {axis}: {message}")
    else:
        errors.append(
            f"{message}; non-accept result must reflect this finding as FAIL/BLOCKED on {axis}"
        )


def validate_source_bindings(
    data: dict[str, Any],
    *,
    task_card: Path | None,
    packet_path: Path | None,
    manifest_path: Path | None,
    receipt_path: Path | None,
    runtime_admission_path: Path | None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    source = data.get("source", {}) if isinstance(data.get("source"), dict) else {}
    repository = (
        data.get("repository", {}) if isinstance(data.get("repository"), dict) else {}
    )
    packet: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None

    if source.get("contract_kind") == "TRACKED_TASK_CARD" and task_card is None:
        warnings.append("physical Task Card not supplied; Task Card digest is unbound")
    if source.get("compiled_packet_sha256") is not None and packet_path is None:
        warnings.append("physical compiled packet not supplied; packet digest is unbound")
    if source.get("execution_manifest_sha256") is not None and manifest_path is None:
        warnings.append(
            "physical execution manifest not supplied; manifest digest is unbound"
        )
    if receipt_path is None:
        warnings.append("physical executor receipt not supplied; Candidate binding is weaker")
    if runtime_admission_path is not None and packet_path is None:
        warnings.append(
            "runtime Workforce Admission supplied without physical compiled packet; exact model binding cannot be checked"
        )

    try:
        if task_card is not None:
            if source.get("contract_kind") != "TRACKED_TASK_CARD":
                record_physical_finding(
                    data, errors, warnings,
                    "--task-card is not applicable to OWNER_INLINE",
                    axis="authority",
                )
            elif file_sha256(task_card) != source.get("task_card_sha256"):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.task_card_sha256: physical Task Card mismatch",
                    axis="authority",
                )

        if packet_path is not None:
            packet = read_bound_json(packet_path)
            if file_sha256(packet_path) != source.get("compiled_packet_sha256"):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.compiled_packet_sha256: physical compiled packet mismatch",
                    axis="authority",
                )
            if packet.get("schema") != PACKET_SCHEMA:
                record_physical_finding(
                    data, errors, warnings,
                    f"compiled packet schema must be {PACKET_SCHEMA}",
                    axis="authority",
                )
            packet_source = (
                packet.get("source", {})
                if isinstance(packet.get("source"), dict)
                else {}
            )
            if source.get("task_id") != packet_source.get("task_id"):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.task_id: compiled packet mismatch",
                    axis="authority",
                )
            if source.get("campaign_id") != packet_source.get("campaign_id"):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.campaign_id: compiled packet mismatch",
                    axis="authority",
                )
            if (
                source.get("contract_kind") == "TRACKED_TASK_CARD"
                and source.get("task_card_sha256")
                != packet_source.get("task_card_sha256")
            ):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.task_card_sha256: compiled packet lineage mismatch",
                    axis="authority",
                )
            if source.get("implementer_attempt_id") != packet.get("attempt", {}).get(
                "attempt_id"
            ):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.implementer_attempt_id: compiled packet attempt mismatch",
                    axis="authority",
                )
            if isinstance(packet.get("workforce_admission"), dict):
                try:
                    workforce_validator = load_runtime_admission_validator()
                    workforce_report = workforce_validator.validate_compiled_packet_workforce(packet)
                except Exception as exc:  # fail closed for an acceptance claim
                    record_physical_finding(
                        data, errors, warnings,
                        f"compiled packet workforce validation unavailable: {type(exc).__name__}: {exc}",
                        axis="authority",
                    )
                else:
                    for item in workforce_report.get("errors", []):
                        record_physical_finding(
                            data, errors, warnings,
                            f"compiled packet workforce: {item}",
                            axis="authority",
                        )
            else:
                warnings.append(
                    "compiled packet has no embedded workforce_admission; treat as legacy/incomplete model-binding evidence"
                )

        if manifest_path is not None:
            manifest = read_bound_json(manifest_path)
            if file_sha256(manifest_path) != source.get("execution_manifest_sha256"):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.execution_manifest_sha256: physical execution manifest mismatch",
                    axis="authority",
                )
            manifest_schema = manifest.get("schema")
            if manifest_schema not in {CURRENT_MANIFEST_SCHEMA, LEGACY_MANIFEST_SCHEMA}:
                record_physical_finding(
                    data, errors, warnings,
                    "execution manifest schema is unsupported",
                    axis="authority",
                )
            elif manifest_schema == LEGACY_MANIFEST_SCHEMA:
                warnings.append(
                    f"legacy execution manifest {LEGACY_MANIFEST_SCHEMA}; current executor emits {CURRENT_MANIFEST_SCHEMA}"
                )
            manifest_source = (
                manifest.get("source", {})
                if isinstance(manifest.get("source"), dict)
                else {}
            )
            if source.get("task_id") != manifest.get("task_id"):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.task_id: execution manifest mismatch",
                    axis="authority",
                )
            if source.get("campaign_id") != manifest_source.get("campaign_id"):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.campaign_id: execution manifest mismatch",
                    axis="authority",
                )
            if (
                source.get("compiled_packet_sha256")
                != manifest_source.get("compiled_packet_sha256")
            ):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.compiled_packet_sha256: execution manifest lineage mismatch",
                    axis="authority",
                )
            if source.get("implementer_attempt_id") != manifest.get("attempt_id"):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.implementer_attempt_id: execution manifest attempt mismatch",
                    axis="authority",
                )

        if receipt_path is not None:
            receipt = read_bound_json(receipt_path)
            receipt_schema = receipt.get("schema")
            if receipt_schema not in RECEIPT_SCHEMAS:
                record_physical_finding(
                    data, errors, warnings,
                    "executor receipt schema mismatch",
                    axis="authority",
                )
            elif receipt_schema == LEGACY_RECEIPT_SCHEMA:
                warnings.append(
                    f"legacy executor receipt {LEGACY_RECEIPT_SCHEMA}; current executor emits {CURRENT_RECEIPT_SCHEMA}"
                )
            receipt_integrity = receipt.get("integrity")
            if (
                not isinstance(receipt_integrity, dict)
                or not isinstance(receipt_integrity.get("sha256"), str)
                or receipt_integrity.get("sha256") != canonical_sha256(receipt)
            ):
                record_physical_finding(
                    data, errors, warnings,
                    "executor receipt integrity mismatch",
                    axis="subject_identity",
                )
            receipt_authority = (
                receipt.get("authority", {})
                if isinstance(receipt.get("authority"), dict)
                else {}
            )
            if any(
                receipt_authority.get(key) is True
                for key in (
                    "worker_may_approve",
                    "worker_may_integrate",
                    "worker_may_push",
                    "worker_may_cleanup",
                    "authority_expansion",
                )
            ):
                record_physical_finding(
                    data, errors, warnings,
                    "executor receipt claims forbidden worker authority",
                    axis="authority",
                )
            receipt_claim = (
                receipt.get("claim", {})
                if isinstance(receipt.get("claim"), dict)
                else {}
            )
            if receipt_claim.get("public_claim_allowed") is not False:
                record_physical_finding(
                    data, errors, warnings,
                    "executor receipt must not allow a public claim",
                    axis="claim_discipline",
                )
            if receipt_schema == CURRENT_RECEIPT_SCHEMA and receipt_claim.get("claim_amplified") is not False:
                record_physical_finding(
                    data, errors, warnings,
                    "executor receipt must not amplify its source claim",
                    axis="claim_discipline",
                )
            if file_sha256(receipt_path) != source.get("executor_receipt_sha256"):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.executor_receipt_sha256: physical executor receipt mismatch",
                    axis="subject_identity",
                )
            receipt_source = (
                receipt.get("source", {})
                if isinstance(receipt.get("source"), dict)
                else {}
            )
            receipt_attempt = (
                receipt.get("attempt", {})
                if isinstance(receipt.get("attempt"), dict)
                else {}
            )
            receipt_repo = (
                receipt.get("repository", {})
                if isinstance(receipt.get("repository"), dict)
                else {}
            )
            receipt_effects = (
                receipt.get("effects", {})
                if isinstance(receipt.get("effects"), dict)
                else {}
            )
            receipt_verification = (
                receipt.get("verification", {})
                if isinstance(receipt.get("verification"), dict)
                else {}
            )
            receipt_candidate = (
                receipt.get("candidate", {})
                if isinstance(receipt.get("candidate"), dict)
                else {}
            )

            inferred_kind = receipt_source.get("contract_kind")
            if inferred_kind is None:
                inferred_kind = (
                    "TRACKED_TASK_CARD"
                    if receipt_source.get("task_card_sha256")
                    else "OWNER_INLINE"
                )
            if source.get("contract_kind") != inferred_kind:
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.contract_kind: executor receipt mismatch",
                    axis="authority",
                )
            for key in ("task_id", "campaign_id", "contract_hash"):
                if source.get(key) != receipt_source.get(key):
                    record_physical_finding(
                        data, errors, warnings,
                        f"$.source.{key}: executor receipt mismatch",
                        axis="authority",
                    )
            if source.get("contract_kind") == "TRACKED_TASK_CARD":
                for key in ("task_card_path", "task_card_sha256"):
                    if source.get(key) != receipt_source.get(key):
                        record_physical_finding(
                            data, errors, warnings,
                            f"$.source.{key}: executor receipt mismatch",
                            axis="authority",
                        )
            for key in ("compiled_packet_sha256", "execution_manifest_sha256"):
                if source.get(key) != receipt_source.get(key):
                    record_physical_finding(
                        data, errors, warnings,
                        f"$.source.{key}: executor receipt mismatch",
                        axis="authority",
                    )
            if source.get("implementer_attempt_id") != receipt_attempt.get("attempt_id"):
                record_physical_finding(
                    data, errors, warnings,
                    "$.source.implementer_attempt_id: executor receipt mismatch",
                    axis="authority",
                )

            binding = {
                "root": receipt_repo.get("root"),
                "branch": receipt_repo.get("branch"),
                "executor_observed_head": receipt_repo.get("observed_head"),
                "expected_base_commit": receipt_repo.get("expected_head"),
                "candidate_commit_sha": receipt_candidate.get("commit_sha"),
                "candidate_tree_sha": receipt_candidate.get("tree_sha"),
                "candidate_state_hash": receipt_candidate.get("state_hash"),
                "candidate_diff_sha256": receipt_effects.get("candidate_diff_sha256"),
                "verified_receipt_hash": receipt_verification.get(
                    "verified_receipt_hash"
                ),
            }
            for key, value in binding.items():
                if repository.get(key) != value:
                    record_physical_finding(
                        data, errors, warnings,
                        f"$.repository.{key}: executor receipt mismatch",
                        axis="subject_identity",
                    )
            if receipt.get("status") != "IMPLEMENTER_PASS_PENDING_ACCEPTANCE":
                record_physical_finding(
                    data, errors, warnings,
                    "executor receipt must be IMPLEMENTER_PASS_PENDING_ACCEPTANCE",
                    axis="authority",
                )
            if (
                receipt_candidate.get("present") is not True
                or receipt_candidate.get("required") is not True
            ):
                record_physical_finding(
                    data, errors, warnings,
                    "executor receipt must carry a required present Candidate",
                    axis="subject_identity",
                )

            if receipt_schema == CURRENT_RECEIPT_SCHEMA and manifest is not None:
                if manifest.get("schema") != CURRENT_MANIFEST_SCHEMA:
                    record_physical_finding(
                        data, errors, warnings,
                        f"current receipt v2 requires physical manifest {CURRENT_MANIFEST_SCHEMA}",
                        axis="authority",
                    )

            receipt_mode = receipt_source.get("mode")
            if receipt_mode == "COMPILED_PACKET":
                if packet is None:
                    record_physical_finding(
                        data, errors, warnings,
                        "compiled executor receipt requires physical compiled packet for acceptance binding",
                        axis="authority",
                    )
                if runtime_admission_path is None:
                    record_physical_finding(
                        data, errors, warnings,
                        "compiled executor receipt lacks execution-time Workforce Admission side evidence",
                        axis="authority",
                    )
                elif packet is None:
                    warnings.append(
                        "runtime Workforce Admission cannot be checked until the physical compiled packet is supplied"
                    )
                else:
                    runtime_admission = read_bound_json(runtime_admission_path)
                    try:
                        workforce_validator = load_runtime_admission_validator()
                        runtime_report = workforce_validator.validate_runtime_admission(
                            runtime_admission, packet
                        )
                    except Exception as exc:
                        record_physical_finding(
                            data, errors, warnings,
                            f"runtime Workforce Admission validation unavailable: {type(exc).__name__}: {exc}",
                            axis="authority",
                        )
                    else:
                        for item in runtime_report.get("errors", []):
                            record_physical_finding(
                                data, errors, warnings,
                                f"runtime Workforce Admission: {item}",
                                axis="authority",
                            )
            elif runtime_admission_path is not None:
                record_physical_finding(
                    data, errors, warnings,
                    "runtime Workforce Admission side evidence is only applicable to COMPILED_PACKET execution",
                    axis="authority",
                )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        DuplicateKeyError,
        ValueError,
    ) as exc:
        record_physical_finding(
            data, errors, warnings,
            f"source binding failed: {exc}",
            axis="authority",
        )

    return errors, warnings

def main() -> int:
    args = parse_args()
    try:
        info = args.result.lstat()
        if (
            args.result.is_symlink()
            or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size > 4 * 1024 * 1024
        ):
            raise OSError("result must be one regular non-linked file under 4 MiB")
        data = json.loads(
            args.result.read_text(encoding="utf-8"),
            object_pairs_hook=no_duplicate_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateKeyError) as exc:
        report = {
            "schema": VALIDATION_SCHEMA,
            "valid": False,
            "errors": [str(exc)],
            "warnings": [],
        }
    else:
        report = validate(data)
        if report["valid"]:
            binding_errors, binding_warnings = validate_source_bindings(
                data,
                task_card=args.task_card,
                packet_path=args.compiled_packet,
                manifest_path=args.execution_manifest,
                receipt_path=args.executor_receipt,
                runtime_admission_path=args.runtime_admission,
            )
            report["errors"].extend(binding_errors)
            report["warnings"].extend(binding_warnings)
            report["valid"] = not report["errors"]

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
