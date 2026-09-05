"""Pure bridge from verified External Intelligence closure to canonical Candidate adoption.

This module deliberately does not perform independent acceptance and does not
invoke lifecycle adoption. It only:

1. projects a verified External Intelligence closure into the exact validation
   artifact shape already consumed by ``ExternalCandidateAdoptionRequest``; and
2. after a distinct independent acceptance artifact exists, builds the existing
   closed adoption request without widening lifecycle authority.

The single settlement authority remains ``nexus_candidate_adopt_external`` /
``SelfHostedTaskService.adopt_external_candidate``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from nexus.contracts.lifecycle_action import (
    ApprovalScope,
    ContractKind,
    ExternalCandidateAdoptionRequest,
    LifecycleActionType,
    MutationDomain,
    PermissionProfile,
    build_action_envelope,
    parse_external_adoption_task_card,
)
from nexus.services.external_intelligence_closure import (
    ACCEPTANCE_PACKET_SCHEMA,
    CLAIM_CEILING,
    CLOSURE_CAPSULE_SCHEMA,
    CLOSURE_RUN_SCHEMA,
    TASK_CANDIDATE_SCHEMA,
    WHOLE_VERIFICATION_SCHEMA,
)

_VALIDATION_SCHEMA = "nexus.evidence_producer_bridge.validation_receipt.v1"
_VALIDATION_STATUS = "EVIDENCE_PRODUCER_BRIDGE_VALIDATED"
_ACCEPTANCE_SCHEMA = "nexus.external_candidate_acceptance.v1"
_ACCEPTANCE_DISPOSITION = "ACCEPT_CANDIDATE"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")


class ExternalIntelligenceAdoptionError(RuntimeError):
    """Fail-closed bridge error."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _require_sha(value: Any, *, size: int, field: str) -> str:
    text = str(value or "").strip().lower()
    pattern = _SHA40 if size == 40 else _SHA64
    if not pattern.fullmatch(text):
        raise ExternalIntelligenceAdoptionError(f"{field.upper()}_INVALID")
    return text


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExternalIntelligenceAdoptionError(f"{field.upper()}_INVALID")
    return value


def _validated_closure(closure: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    if not isinstance(closure, Mapping):
        raise ExternalIntelligenceAdoptionError("CLOSURE_INVALID")
    if (
        closure.get("schema") != CLOSURE_RUN_SCHEMA
        or closure.get("status") != CLAIM_CEILING
        or closure.get("claim_ceiling") != CLAIM_CEILING
    ):
        raise ExternalIntelligenceAdoptionError("CLOSURE_NOT_READY_FOR_INDEPENDENT_ACCEPTANCE")

    candidate = _require_mapping(closure.get("task_candidate"), "task_candidate")
    whole = _require_mapping(closure.get("whole_verification"), "whole_verification")
    packet = _require_mapping(closure.get("acceptance_packet"), "acceptance_packet")
    capsule = _require_mapping(closure.get("control_capsule"), "control_capsule")

    if candidate.get("schema") != TASK_CANDIDATE_SCHEMA:
        raise ExternalIntelligenceAdoptionError("TASK_CANDIDATE_SCHEMA_INVALID")
    if whole.get("schema") != WHOLE_VERIFICATION_SCHEMA or whole.get("status") != "PASS":
        raise ExternalIntelligenceAdoptionError("WHOLE_TASK_PASS_REQUIRED")
    if packet.get("schema") != ACCEPTANCE_PACKET_SCHEMA:
        raise ExternalIntelligenceAdoptionError("ACCEPTANCE_PACKET_SCHEMA_INVALID")
    if capsule.get("schema") != CLOSURE_CAPSULE_SCHEMA:
        raise ExternalIntelligenceAdoptionError("CLOSURE_CAPSULE_SCHEMA_INVALID")
    if (
        packet.get("whole_task_status") != "PASS"
        or packet.get("current_gate") != "PENDING_INDEPENDENT_ACCEPTANCE"
        or capsule.get("current_gate") != "PENDING_INDEPENDENT_ACCEPTANCE"
        or capsule.get("next_action") != "run_independent_candidate_acceptance_audit"
    ):
        raise ExternalIntelligenceAdoptionError("INDEPENDENT_ACCEPTANCE_GATE_REQUIRED")

    task_candidate_id = str(candidate.get("task_candidate_id") or "")
    if not task_candidate_id or whole.get("task_candidate_id") != task_candidate_id:
        raise ExternalIntelligenceAdoptionError("WHOLE_VERIFICATION_CANDIDATE_MISMATCH")
    if packet.get("task_id") != candidate.get("task_id"):
        raise ExternalIntelligenceAdoptionError("ACCEPTANCE_PACKET_TASK_MISMATCH")

    packet_candidate = _require_mapping(packet.get("task_candidate"), "packet_task_candidate")
    for key, source_key in (
        ("task_candidate_id", "task_candidate_id"),
        ("base_sha", "base_sha"),
        ("candidate_commit", "candidate_commit"),
        ("candidate_tree", "candidate_tree"),
        ("candidate_diff_sha256", "candidate_diff_sha256"),
    ):
        if packet_candidate.get(key) != candidate.get(source_key):
            raise ExternalIntelligenceAdoptionError(f"ACCEPTANCE_PACKET_CANDIDATE_MISMATCH:{key}")
    if list(packet_candidate.get("changed_paths") or []) != list(candidate.get("changed_paths") or []):
        raise ExternalIntelligenceAdoptionError("ACCEPTANCE_PACKET_CHANGED_PATHS_MISMATCH")
    if list(packet_candidate.get("deleted_paths") or []) != list(candidate.get("deleted_paths") or []):
        raise ExternalIntelligenceAdoptionError("ACCEPTANCE_PACKET_DELETED_PATHS_MISMATCH")

    if capsule.get("task_id") != candidate.get("task_id"):
        raise ExternalIntelligenceAdoptionError("CLOSURE_CAPSULE_TASK_MISMATCH")
    if capsule.get("candidate_commit") != candidate.get("candidate_commit"):
        raise ExternalIntelligenceAdoptionError("CLOSURE_CAPSULE_CANDIDATE_MISMATCH")
    if capsule.get("candidate_tree") != candidate.get("candidate_tree"):
        raise ExternalIntelligenceAdoptionError("CLOSURE_CAPSULE_TREE_MISMATCH")
    if capsule.get("candidate_diff_sha256") != candidate.get("candidate_diff_sha256"):
        raise ExternalIntelligenceAdoptionError("CLOSURE_CAPSULE_DIFF_MISMATCH")

    _require_sha(candidate.get("base_sha"), size=40, field="base_sha")
    _require_sha(candidate.get("candidate_commit"), size=40, field="candidate_commit")
    _require_sha(candidate.get("candidate_tree"), size=40, field="candidate_tree")
    _require_sha(candidate.get("candidate_diff_sha256"), size=64, field="candidate_diff_sha256")
    return candidate, packet, capsule


@dataclass(frozen=True)
class ExternalAdoptionValidationArtifact:
    payload: Mapping[str, Any]
    json_bytes: bytes
    sha256: str
    b64: str


def build_external_adoption_validation(
    *,
    repository: str,
    closure: Mapping[str, Any],
    task_card_bytes: bytes,
) -> ExternalAdoptionValidationArtifact:
    """Project verified closure evidence into the existing adoption validation shape.

    This function is deterministic and authority-neutral. It does not create or
    imply independent acceptance.
    """
    candidate, packet, _capsule = _validated_closure(closure)
    repository_id = str(repository or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository_id):
        raise ExternalIntelligenceAdoptionError("REPOSITORY_INVALID")
    if not isinstance(task_card_bytes, bytes) or not task_card_bytes:
        raise ExternalIntelligenceAdoptionError("TASK_CARD_BYTES_INVALID")

    task_card_ref = str(packet.get("task_card_ref") or "").strip()
    task_card_hash = _require_sha(packet.get("task_card_hash"), size=64, field="task_card_hash")
    if hashlib.sha256(task_card_bytes).hexdigest() != task_card_hash:
        raise ExternalIntelligenceAdoptionError("TASK_CARD_HASH_MISMATCH")
    try:
        projection = parse_external_adoption_task_card(task_card_bytes)
    except ValueError as exc:
        raise ExternalIntelligenceAdoptionError("TASK_CARD_CONTRACT_UNRESOLVABLE") from exc

    changed_paths = tuple(str(path) for path in candidate.get("changed_paths") or ())
    deleted_paths = tuple(str(path) for path in candidate.get("deleted_paths") or ())
    if not changed_paths:
        raise ExternalIntelligenceAdoptionError("CANDIDATE_CHANGED_PATHS_REQUIRED")
    if deleted_paths and not projection.allow_deletions:
        raise ExternalIntelligenceAdoptionError("CANDIDATE_DELETION_NOT_AUTHORIZED")
    allowed = tuple(projection.allowed_repository_paths)
    if any(
        not any(path == boundary or (boundary.endswith("/") and path.startswith(boundary)) for boundary in allowed)
        for path in changed_paths
    ):
        raise ExternalIntelligenceAdoptionError("CANDIDATE_SCOPE_OUTSIDE_TASK_CARD")

    payload = {
        "schema": _VALIDATION_SCHEMA,
        "status": _VALIDATION_STATUS,
        "repository": repository_id,
        "task": str(candidate.get("task_id") or ""),
        "task_card": {
            "path": task_card_ref,
            "card_file_sha256": task_card_hash,
        },
        "candidate": {
            "base_commit": str(candidate.get("base_sha") or ""),
            "commit": str(candidate.get("candidate_commit") or ""),
            "tree": str(candidate.get("candidate_tree") or ""),
            "changed_paths": list(changed_paths),
            "deleted_paths": list(deleted_paths),
        },
    }
    if not payload["task"] or not task_card_ref:
        raise ExternalIntelligenceAdoptionError("VALIDATION_IDENTITY_MISSING")
    encoded = _canonical_bytes(payload)
    digest = hashlib.sha256(encoded).hexdigest()
    return ExternalAdoptionValidationArtifact(
        payload=payload,
        json_bytes=encoded,
        sha256=digest,
        b64=base64.b64encode(encoded).decode("ascii"),
    )


def build_external_settlement_handoff(
    *,
    repository: str,
    closure: Mapping[str, Any],
    task_card_bytes: bytes,
) -> dict[str, Any]:
    """Create the durable, non-accepting handoff to the one adoption authority."""
    candidate, packet, _capsule = _validated_closure(closure)
    validation = build_external_adoption_validation(
        repository=repository,
        closure=closure,
        task_card_bytes=task_card_bytes,
    )
    return {
        "schema": "nexus.external_intelligence_settlement_handoff.v1",
        "repository": str(repository),
        "task_id": str(candidate.get("task_id") or ""),
        "task_card_ref": str(packet.get("task_card_ref") or ""),
        "task_card_hash": str(packet.get("task_card_hash") or ""),
        "base_sha": str(candidate.get("base_sha") or ""),
        "candidate_commit": str(candidate.get("candidate_commit") or ""),
        "candidate_tree": str(candidate.get("candidate_tree") or ""),
        "candidate_diff_sha256": str(candidate.get("candidate_diff_sha256") or ""),
        "changed_paths": list(candidate.get("changed_paths") or []),
        "deleted_paths": list(candidate.get("deleted_paths") or []),
        "validation_receipt_sha256": validation.sha256,
        "validation_receipt_b64": validation.b64,
        "required_acceptance_schema": _ACCEPTANCE_SCHEMA,
        "independent_acceptance_required": True,
        "next_action": "nexus_candidate_adopt_external",
        "claim_ceiling": CLAIM_CEILING,
        "automatic_adoption_performed": False,
        "approval_performed": False,
        "integration_performed": False,
    }


def _parse_independent_acceptance(
    *,
    acceptance_bytes: bytes,
    validation: ExternalAdoptionValidationArtifact,
    candidate: Mapping[str, Any],
) -> tuple[Mapping[str, Any], str, str]:
    if not isinstance(acceptance_bytes, bytes) or not acceptance_bytes:
        raise ExternalIntelligenceAdoptionError("INDEPENDENT_ACCEPTANCE_BYTES_REQUIRED")
    try:
        raw = json.loads(acceptance_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalIntelligenceAdoptionError("INDEPENDENT_ACCEPTANCE_JSON_INVALID") from exc
    if not isinstance(raw, Mapping):
        raise ExternalIntelligenceAdoptionError("INDEPENDENT_ACCEPTANCE_INVALID")
    expected_keys = {
        "schema",
        "task_id",
        "candidate_commit_sha",
        "candidate_tree_sha",
        "candidate_diff_sha256",
        "validation_receipt_sha256",
        "reviewer_id",
        "disposition",
    }
    if set(raw) != expected_keys:
        raise ExternalIntelligenceAdoptionError("INDEPENDENT_ACCEPTANCE_SCHEMA_CLOSED")
    if (
        raw.get("schema") != _ACCEPTANCE_SCHEMA
        or raw.get("task_id") != candidate.get("task_id")
        or raw.get("candidate_commit_sha") != candidate.get("candidate_commit")
        or raw.get("candidate_tree_sha") != candidate.get("candidate_tree")
        or raw.get("candidate_diff_sha256") != candidate.get("candidate_diff_sha256")
        or raw.get("validation_receipt_sha256") != validation.sha256
        or raw.get("disposition") != _ACCEPTANCE_DISPOSITION
        or not str(raw.get("reviewer_id") or "").strip()
    ):
        raise ExternalIntelligenceAdoptionError("INDEPENDENT_ACCEPTANCE_BINDING_MISMATCH")
    digest = hashlib.sha256(acceptance_bytes).hexdigest()
    return raw, digest, base64.b64encode(acceptance_bytes).decode("ascii")


def build_external_candidate_adoption_request(
    *,
    repository: str,
    closure: Mapping[str, Any],
    task_card_bytes: bytes,
    independent_acceptance_bytes: bytes,
    controller_revision: str,
    tool_manifest_hash: str,
    full_tool_schema_hash: str,
    permission_policy_hash: str,
    lifecycle_revision: str,
    server_instance_id: str,
) -> ExternalCandidateAdoptionRequest:
    """Build the one existing canonical adoption request after independent acceptance.

    The returned object is only a request. Calling the lifecycle adoption
    authority remains a separate operation with its normal Owner/runtime gates.
    """
    candidate, packet, _capsule = _validated_closure(closure)
    validation = build_external_adoption_validation(
        repository=repository,
        closure=closure,
        task_card_bytes=task_card_bytes,
    )
    _acceptance, acceptance_sha256, acceptance_b64 = _parse_independent_acceptance(
        acceptance_bytes=independent_acceptance_bytes,
        validation=validation,
        candidate=candidate,
    )
    try:
        projection = parse_external_adoption_task_card(task_card_bytes)
    except ValueError as exc:
        raise ExternalIntelligenceAdoptionError("TASK_CARD_CONTRACT_UNRESOLVABLE") from exc

    controller_revision = _require_sha(controller_revision, size=40, field="controller_revision")
    tool_manifest_hash = _require_sha(tool_manifest_hash, size=64, field="tool_manifest_hash")
    full_tool_schema_hash = _require_sha(full_tool_schema_hash, size=64, field="full_tool_schema_hash")
    permission_policy_hash = _require_sha(permission_policy_hash, size=64, field="permission_policy_hash")
    lifecycle_revision = str(lifecycle_revision or "").strip()
    server_instance_id = str(server_instance_id or "").strip()
    if not lifecycle_revision or not server_instance_id:
        raise ExternalIntelligenceAdoptionError("RUNTIME_IDENTITY_MISSING")

    task_id = str(candidate.get("task_id") or "")
    candidate_commit = str(candidate.get("candidate_commit") or "")
    candidate_tree = str(candidate.get("candidate_tree") or "")
    candidate_diff_sha256 = str(candidate.get("candidate_diff_sha256") or "")
    task_card_path = str(packet.get("task_card_ref") or "")
    task_card_hash = str(packet.get("task_card_hash") or "")
    seed = hashlib.sha256(
        _canonical_bytes(
            {
                "repository": repository,
                "task_id": task_id,
                "candidate_commit": candidate_commit,
                "candidate_tree": candidate_tree,
                "candidate_diff_sha256": candidate_diff_sha256,
                "validation_receipt_sha256": validation.sha256,
                "acceptance_receipt_sha256": acceptance_sha256,
                "controller_revision": controller_revision,
                "task_card_hash": task_card_hash,
            }
        )
    ).hexdigest()
    attempt_id = f"attempt-eia-adopt-{seed[:20]}"
    action_id = f"action-eia-adopt-{seed[20:40]}"
    idempotency_key = f"{task_id}:external-intelligence-adopt:{seed}"

    values: dict[str, Any] = {
        "schema": "nexus.external_candidate_adoption_request.v1",
        "repository": str(repository),
        "task_id": task_id,
        "attempt_id": attempt_id,
        "action_id": action_id,
        "idempotency_key": idempotency_key,
        "task_card_path": task_card_path,
        "task_card_hash": task_card_hash,
        "controller_revision": controller_revision,
        "tool_manifest_hash": tool_manifest_hash,
        "full_tool_schema_hash": full_tool_schema_hash,
        "permission_policy_hash": permission_policy_hash,
        "lifecycle_revision": lifecycle_revision,
        "server_instance_id": server_instance_id,
        "target_base_revision": str(candidate.get("base_sha") or ""),
        "candidate_commit_sha": candidate_commit,
        "candidate_tree_sha": candidate_tree,
        "candidate_diff_sha256": candidate_diff_sha256,
        "validation_receipt_sha256": validation.sha256,
        "acceptance_receipt_sha256": acceptance_sha256,
        "validation_receipt_b64": validation.b64,
        "acceptance_receipt_b64": acceptance_b64,
        "allowed_files": tuple(projection.allowed_repository_paths),
        "forbidden_files": tuple(projection.forbidden_repository_paths),
        "authorized_deletions": tuple(candidate.get("deleted_paths") or ())
        if projection.allow_deletions
        else (),
        "verifier_commands": tuple(projection.exact_verification_commands),
        "protected_contracts": (),
    }
    semantic_hash = ExternalCandidateAdoptionRequest.semantic_hash_for(values)
    values["action"] = build_action_envelope(
        task_id=task_id,
        action_type=LifecycleActionType.CANDIDATE_ADOPT_EXTERNAL,
        request={"adoption_request_hash": semantic_hash},
        tool_manifest_hash=tool_manifest_hash,
        expected_head=controller_revision,
        allowed_paths=values["allowed_files"],
        mutation=True,
        mutation_domain=MutationDomain.CANDIDATE_REF,
        permission_profile=PermissionProfile.CANDIDATE,
        approval_scope=ApprovalScope.ALLOW_ACTION_ONCE,
        task_card_path=task_card_path,
        task_card_hash=task_card_hash,
        contract_kind=ContractKind.TRACKED_TASK_CARD,
        attempt_id=attempt_id,
        action_id=action_id,
        idempotency_key=idempotency_key,
    )
    try:
        return ExternalCandidateAdoptionRequest.model_validate(values)
    except Exception as exc:
        raise ExternalIntelligenceAdoptionError(f"ADOPTION_REQUEST_INVALID:{exc}") from exc


__all__ = [
    "ExternalAdoptionValidationArtifact",
    "ExternalIntelligenceAdoptionError",
    "build_external_adoption_validation",
    "build_external_candidate_adoption_request",
    "build_external_settlement_handoff",
]
