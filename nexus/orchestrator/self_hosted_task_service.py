"""Durable, restartable service facade for the self-hosted MCP surface."""

from __future__ import annotations

import fcntl
import hashlib
import inspect
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence
from uuid import uuid4

from nexus.contracts.autonomy_goal import AutonomyGoalGrant
from nexus.contracts.collaboration_realm import CollaborationExecutionRealm
from nexus.contracts.lifecycle_action import (
    ContractKind,
    LifecycleActionEnvelope,
    LifecycleActionType,
    canonical_request_hash,
    validate_owner_inline_contract,
)
from nexus.contracts.operator_outcome_receipt import (
    OperatorOutcomeReceipt,
    validate_operator_outcome_receipt,
)
from nexus.contracts.target_integration_lifecycle import (
    ExternalAcceptanceReceipt,
    IntegrationAuthorizationEnvelope,
)
from nexus.contracts.unified_runtime_receipt import build_runtime_development_mapping
from nexus.core.task_continuity import events_from_attempt_records
from nexus.engine.canonical_task_seam import build_canonical_dispatch_envelope
from nexus.events.contracts import build_attempt_transition_event
from nexus.events.transport import NexusEventBus
from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,
    AttemptResolutionVerdict,
    WorkerExecutionReceipt,
    WorkerOutcome,
    resolve_attempt,
)
from nexus.executors.worker_registry import WorkerRegistry
from nexus.orchestrator.acceptance_loop import (
    CandidateAcceptanceRequest,
    CandidateAcceptanceResult,
    IndependentReviewReceipt,
    reduce_candidate_acceptance,
)
from nexus.orchestrator.autonomy_policy import (
    AutonomySubmissionBinding,
    project_autonomy_submission,
)
from nexus.orchestrator.candidate_commit import CandidateCommitter, PromotionApprovalPacket
from nexus.orchestrator.candidate_verifier import CandidateVerifier, VerifiedCandidateReceipt
from nexus.orchestrator.canonical_source_root import CANONICAL_SOURCE_ROOT
from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier
from nexus.orchestrator.governed_integration import (
    ControlledIntegrationManager,
    IntegrationExecutionError,
)
from nexus.orchestrator.lifecycle_guards import (
    pre_action_guard,
    trusted_runtime_manifest_hash,
    validate_approval_grant,
    validate_architecture_approval,
)
from nexus.orchestrator.repository_contract_gate import RepositoryContractGate
from nexus.orchestrator.self_hosted_controller import SelfHostedDevelopmentController
from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle
from nexus.orchestrator.task_contract import (
    AcceptanceProfile,
    ArchitectTaskContract,
    ArchitectureDecision,
    DevelopmentGoal,
    HumanApprovalPolicy,
    MutationMode,
)
from nexus.orchestrator.worker_escalation import WorkerEscalationPolicy
from nexus.orchestrator.worktree_manager import TargetWorktreeLease, WorktreeManager
from nexus.services.model_workforce_policy import WorkforcePolicyLoader
from nexus.services.runtime_workforce_admission import evaluate_runtime_workforce_admission

Runner = Callable[[ArchitectTaskContract, Mapping[str, Any], Callable[[str, dict[str, Any]], None]], dict[str, Any]]
TERMINAL_STATUSES = frozenset({
    "FINAL_BLOCK", "RETAINED_FOR_REVIEW", "REJECTED", "SUPERSEDED",
    "INTEGRATED", "INTEGRATION_FAILED", "CANCELLED", "REHEARSAL_VERIFIED",
    "DIRECT_COMPLETED", "DIRECT_RECONCILE_REQUIRED", "INTEGRATED_AND_CLEANED",
})
PENDING_CANDIDATE_STATUSES = frozenset({
    "PENDING_HUMAN_APPROVAL", "APPROVED", "APPROVAL_INVALIDATED", "INTEGRATING",
})


def _temporary_state_roots() -> tuple[Path, ...]:
    """Return trusted ephemeral roots, including process-provided CI roots.

    GitHub-hosted runners expose their isolated scratch directory through
    ``RUNNER_TEMP`` (and some runners use ``TMPDIR``).  These roots are
    temporary execution surfaces only; they do not alter the canonical state
    root or grant production/promotion authority.
    """
    roots = [Path("/tmp"), Path("/private/tmp"), Path("/private/var/folders")]
    for variable in ("TMPDIR", "RUNNER_TEMP"):
        configured = os.getenv(variable, "").strip()
        if configured:
            roots.append(Path(configured).expanduser().resolve())
    return tuple(dict.fromkeys(roots))


def resolve_contract_identity(
    state: Mapping[str, Any],
    *,
    expected_task_id: str,
    expected_head: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve the approval identity while preserving the service contract hash."""
    contract_kind = str(state.get("contract_kind") or ContractKind.TRACKED_TASK_CARD.value)
    task_card_hash = str(state.get("task_card_hash") or "").strip() or None
    contract_hash = str(state.get("contract_hash") or "").strip() or task_card_hash
    owner_inline_contract = (
        state.get("owner_inline_contract")
        if isinstance(state.get("owner_inline_contract"), Mapping)
        else None
    )
    if contract_kind == ContractKind.OWNER_INLINE.value:
        try:
            owner_inline_contract = validate_owner_inline_contract(
                owner_inline_contract or {},
                expected_task_id=expected_task_id,
                expected_head=expected_head,
            )
        except ValueError as exc:
            raise RuntimeError(
                "CONTRACT_HASH_MISMATCH: persisted Owner Inline contract is invalid"
            ) from exc
        contract_hash = owner_inline_contract["contract_hash"]
        task_card_hash = None
    elif contract_kind != ContractKind.TRACKED_TASK_CARD.value:
        raise RuntimeError("APPROVAL_CONTRACT_KIND_UNSUPPORTED")
    return {
        "contract_kind": contract_kind,
        "contract_hash": contract_hash,
        "task_card_hash": task_card_hash,
        "owner_inline_contract": owner_inline_contract,
    }
RESUMABLE_STATUSES = frozenset({
    "WORKER_COMPLETED",
    "WORKER_ESCALATING",
    "CANDIDATE_CAPTURED",
    "VERIFIED",
})


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return value


def _validate_existing_autonomy_binding(
    state: Mapping[str, Any],
    grant: Optional[AutonomyGoalGrant],
) -> None:
    """Reject any attempt to add or replace autonomy after task creation."""
    raw_binding = state.get("autonomy_submission_binding")
    if grant is None:
        if raw_binding is not None:
            raise ValueError("AUTONOMY_GOAL_GRANT_REQUIRED")
        return
    if raw_binding is None:
        raise ValueError("POST_SUBMISSION_GRANT_INJECTION")
    try:
        binding = AutonomySubmissionBinding.model_validate(raw_binding)
    except Exception as exc:
        raise ValueError("AUTONOMY_SUBMISSION_BINDING_INVALID") from exc
    if binding.task_id != state.get("task_id"):
        raise ValueError("AUTONOMY_SUBMISSION_BINDING_DRIFT")
    if binding.goal_id != grant.goal_id or binding.grant_hash != grant.grant_hash:
        raise ValueError("AUTONOMY_SUBMISSION_BINDING_DRIFT")
    if not project_autonomy_submission(state).get("eligible"):
        raise ValueError("AUTONOMY_SUBMISSION_BINDING_DRIFT")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_failure_text(value: Any, *, limit: int = 512) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _workforce_dispatch_inputs(request: Mapping[str, Any]) -> tuple[Any, Any]:
    """Extract the planner/admission pair without inventing a fallback source."""
    planner = request.get("planner_output")
    if not isinstance(planner, Mapping):
        planner = request.get("planner")
    snapshot = request.get("signal_snapshot")
    if not isinstance(snapshot, Mapping) and isinstance(planner, Mapping):
        snapshot = planner.get("signal_snapshot")
    demands = request.get("workforce_demands")
    if demands is None and isinstance(snapshot, Mapping):
        demands = snapshot.get("workforce_demands")
    admission = request.get("workforce_admission")
    if admission is None and isinstance(planner, Mapping):
        admission = planner.get("workforce_admission")
    if admission is None:
        admission = request.get("admission_binding")
    return demands, admission


def _tracked_dispatch_required(
    request: Mapping[str, Any],
    state: Optional[Mapping[str, Any]] = None,
) -> bool:
    tracked = ContractKind.TRACKED_TASK_CARD.value
    return str(request.get("contract_kind") or "") == tracked or (
        isinstance(state, Mapping)
        and str(state.get("contract_kind") or "") == tracked
    )


def validate_workforce_dispatch_binding(
    request: Mapping[str, Any],
    *,
    require_binding: bool = False,
) -> Optional[dict[str, Any]]:
    """Validate the exact Planner -> admission -> registry dispatch binding.

    The runtime admission service remains the policy authority.  This seam only
    verifies its durable, canonical ALLOW receipt before selecting a registry
    identity; it never resolves a worker or recomputes policy.
    """
    demands, admission = _workforce_dispatch_inputs(request)
    if demands is None and admission is None:
        if require_binding:
            raise RuntimeError("WORKFORCE_ADMISSION_BINDING_MISSING")
        return None
    if demands is None or admission is None:
        raise RuntimeError("WORKFORCE_ADMISSION_BINDING_MISSING")
    if not isinstance(admission, Mapping) or admission.get("overall_decision") != "ALLOW":
        raise RuntimeError("WORKFORCE_ADMISSION_BINDING_INVALID:overall decision is not ALLOW")
    try:
        raw_items = demands.get("demands") if isinstance(demands, Mapping) else None
        records = admission.get("records")
        if not isinstance(raw_items, list) or len(raw_items) != 1:
            raise ValueError("workforce dispatch requires exactly one demand")
        if not isinstance(records, list) or len(records) != 1:
            raise ValueError("workforce dispatch requires exactly one admission record")
        record = records[0]
        record_demand = record.get("demand") if isinstance(record, Mapping) else None
        if not isinstance(record_demand, Mapping) or any(
            record_demand.get(field) != raw_items[0].get(field)
            for field in ("demand_id", "execution_channel")
        ):
            raise ValueError("workforce admission demand/record mismatch")
        record_request = record.get("request")
        if not isinstance(record_request, Mapping):
            raise ValueError("workforce admission record request missing")
        channel = str(raw_items[0].get("execution_channel") or "")
        if channel not in {"local", "online"}:
            raise ValueError("workforce dispatch execution channel invalid")
        binding: dict[str, Any] = {
            "worker_id": record_request.get("requested_worker_id"),
            "provider": record_request.get("provider"),
            "model": record_request.get("model"),
            "controls": record_request.get("provided_controls") or [],
            "explicit_experiment_authorization": bool(
                record_request.get("explicit_experiment_authorization", False)
            ),
        }
        if not binding["worker_id"] and not binding["provider"] and not binding["model"]:
            raise ValueError("workforce admission record identity missing")
        fresh = evaluate_runtime_workforce_admission(
            demands,
            {channel: binding},
            WorkforcePolicyLoader(),
        ).to_dict()
        if fresh != dict(admission):
            raise ValueError("workforce admission receipt is stale or tampered")
        fresh_records = fresh.get("records") or []
        if (
            fresh.get("overall_decision") != "ALLOW"
            or len(fresh_records) != 1
            or (fresh_records[0].get("decision") or {}).get("decision") != "ALLOW"
        ):
            raise ValueError("workforce admission is not a single ALLOW record")
        decision = fresh_records[0].get("decision") or {}
        binding = {
            "worker_id": decision.get("resolved_worker_id"),
            "provider": decision.get("resolved_provider"),
            "model": decision.get("resolved_model"),
            "policy_hash": (fresh.get("policy_identity") or {}).get("policy_hash"),
            "binding_hash": fresh_records[0].get("binding_hash"),
            "aggregate_binding_hash": fresh.get("aggregate_binding_hash"),
        }
        if any(not isinstance(binding[field], str) or not binding[field].strip() for field in (
            "worker_id", "provider", "model", "policy_hash", "binding_hash", "aggregate_binding_hash"
        )):
            raise ValueError("workforce admission resolved identity missing")
    except (TypeError, ValueError, KeyError) as exc:
        raise RuntimeError(f"WORKFORCE_ADMISSION_BINDING_INVALID:{exc}") from exc
    fallback = str(request.get("fallback_worker", request.get("fallback_provider")) or "").strip().lower()
    if fallback and fallback != str(binding["provider"]).strip().lower():
        raise RuntimeError("WORKFORCE_ADMISSION_FALLBACK_UNADMITTED")
    raw_envelope = request.get("canonical_dispatch_envelope")
    result = {
        "demands": _jsonable(demands),
        "admission": _jsonable(admission),
        "demand_id": str(raw_items[0].get("demand_id") or ""),
        "worker_id": str(binding["worker_id"]),
        "provider": str(binding["provider"]),
        "model": str(binding["model"]),
        "policy_hash": str(binding["policy_hash"]),
        "binding_hash": str(binding["binding_hash"]),
        "aggregate_binding_hash": str(binding["aggregate_binding_hash"]),
    }
    if raw_envelope is not None:
        if not isinstance(raw_envelope, Mapping):
            raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_INVALID")
        planner_output = request.get("planner_output")
        if not isinstance(planner_output, Mapping):
            raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_PLANNER_MISSING")
        try:
            envelope = build_canonical_dispatch_envelope(
                planner_output,
                {**binding, "demand_id": str(raw_items[0].get("demand_id") or "")},
                task_id=str(request.get("task_id") or ""),
                attempt_id=str(request.get("attempt_id") or ""),
                task_card_path=str(request.get("task_card_path") or ""),
                task_card_hash=str(request.get("task_card_hash") or ""),
            ).to_dict()
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"WORKFORCE_DISPATCH_ENVELOPE_INVALID:{exc}") from exc
        if dict(raw_envelope) != envelope:
            raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_MISMATCH")
        result["canonical_dispatch_envelope"] = envelope
    return result


def _parse_time(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _task_deadline(contract: ArchitectTaskContract, submitted_at: Optional[str]) -> Optional[float]:
    """Return one absolute wall-clock deadline shared by all attempts."""
    started = _parse_time(submitted_at)
    budget = float(getattr(contract, "maximum_wall_time_seconds", 0) or 0)
    return started + budget if started is not None and budget > 0 else None


def _validated_action_request(
    request: Mapping[str, Any],
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    """Validate the physical action payload before resolving task state."""
    if "action" not in request and "bound_action_request" not in request:
        return dict(request), None

    raw_action = request.get("action")
    if not isinstance(raw_action, Mapping):
        raise ValueError("ACTION_ENVELOPE_INVALID")
    raw_bound = request.get("bound_action_request")
    if not isinstance(raw_bound, Mapping):
        raise ValueError("BOUND_ACTION_REQUEST_REQUIRED")
    try:
        envelope = LifecycleActionEnvelope.model_validate(raw_action)
    except Exception as exc:
        raise ValueError(f"ACTION_ENVELOPE_INVALID: {exc}") from exc
    if envelope.action_type not in {
        LifecycleActionType.TASK_RUN,
        LifecycleActionType.TASK_RETRY,
    }:
        raise ValueError("ACTION_TYPE_UNSUPPORTED_FOR_TASK_SUBMISSION")

    bound = dict(raw_bound)
    if canonical_request_hash(bound) != envelope.request_hash:
        raise ValueError("BOUND_ACTION_REQUEST_HASH_MISMATCH")
    for field in (
        "task_id",
        "attempt_id",
        "action_id",
        "idempotency_key",
        "action_type",
        "contract_kind",
    ):
        if field not in bound:
            raise ValueError(f"ACTION_IDENTITY_MISSING: {field}")
    for field, expected in (
        ("task_card_path", envelope.task_card_path),
        ("task_card_hash", envelope.task_card_hash),
        ("contract_hash", envelope.contract_hash),
    ):
        if expected is not None and field not in bound:
            raise ValueError(f"ACTION_IDENTITY_MISSING: {field}")
    if envelope.expected_head is not None and not {
        "controller_revision",
        "expected_head",
    }.intersection(bound):
        raise ValueError("ACTION_IDENTITY_MISSING: expected_head")
    if not {"allowed_files", "allowed_paths"}.intersection(bound):
        raise ValueError("ACTION_IDENTITY_MISSING: allowed_paths")

    def require_match(source: Mapping[str, Any], field: str, expected: Any) -> None:
        if field in source and source[field] != expected:
            raise ValueError(f"ACTION_IDENTITY_MISMATCH: {field}")

    identity_fields = (
        ("task_id", envelope.task_id),
        ("attempt_id", envelope.attempt_id),
        ("action_id", envelope.action_id),
        ("idempotency_key", envelope.idempotency_key),
        ("action_type", envelope.action_type.value),
        ("task_card_path", envelope.task_card_path),
        ("task_card_hash", envelope.task_card_hash),
        ("contract_kind", envelope.contract_kind.value),
        ("contract_hash", envelope.contract_hash),
    )
    for field, expected in identity_fields:
        require_match(bound, field, expected)
        require_match(request, field, expected)
    require_match(request, "action_request_hash", envelope.request_hash)
    require_match(request, "request_hash", envelope.request_hash)

    for source in (bound, request):
        require_match(source, "controller_revision", envelope.expected_head)
        require_match(source, "expected_head", envelope.expected_head)
    expected_paths = tuple(envelope.allowed_paths)
    for source in (bound, request):
        if "allowed_files" in source and tuple(source["allowed_files"]) != expected_paths:
            raise ValueError("ACTION_IDENTITY_MISMATCH: allowed_paths")
        if "allowed_paths" in source and tuple(source["allowed_paths"]) != expected_paths:
            raise ValueError("ACTION_IDENTITY_MISMATCH: allowed_paths")

    effective = dict(bound)
    effective["action"] = envelope.model_dump(mode="json")
    effective["bound_action_request"] = dict(bound)
    for field, expected in identity_fields:
        if expected is not None:
            effective[field] = expected
    if envelope.expected_head is not None:
        effective["controller_revision"] = envelope.expected_head
    if envelope.allowed_paths and "allowed_files" not in effective:
        effective["allowed_files"] = list(envelope.allowed_paths)
    effective["action_request_hash"] = envelope.request_hash
    return effective, envelope.model_dump(mode="json")


def _retry_request(state: Mapping[str, Any]) -> dict[str, Any]:
    """Create fresh attempt-scoped transport identity for one semantic task."""
    raw_request = state.get("request")
    if not isinstance(raw_request, Mapping):
        raise ValueError("RETRY_REQUEST_MISSING")
    request = json.loads(json.dumps(dict(raw_request)))
    task_id = str(state.get("task_id") or request.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("RETRY_TASK_ID_MISSING")

    token = uuid4().hex
    attempt_id = f"attempt-{token}"
    action_id = f"action-{token}"
    previous_key = str(state.get("idempotency_key") or request.get("idempotency_key") or task_id)
    base_key = previous_key.split(":retry-", 1)[0]
    suffix = f":retry-{token}"
    idempotency_key = f"{base_key[: max(1, 256 - len(suffix))]}{suffix}"

    raw_action = request.get("action")
    if isinstance(raw_action, Mapping):
        raw_bound = request.get("bound_action_request")
        if not isinstance(raw_bound, Mapping):
            raise ValueError("RETRY_BOUND_ACTION_REQUEST_MISSING")
        envelope = LifecycleActionEnvelope.model_validate(raw_action)
        bound = json.loads(json.dumps(dict(raw_bound)))
        bound.update(
            task_id=task_id,
            attempt_id=attempt_id,
            action_id=action_id,
            idempotency_key=idempotency_key,
            action_type=LifecycleActionType.TASK_RETRY.value,
        )
        action_payload = envelope.model_dump(mode="json")
        action_payload.update(
            task_id=task_id,
            attempt_id=attempt_id,
            action_id=action_id,
            idempotency_key=idempotency_key,
            action_type=LifecycleActionType.TASK_RETRY.value,
            request_hash=canonical_request_hash(bound),
        )
        retry_action = LifecycleActionEnvelope.model_validate(action_payload).model_dump(mode="json")
        return {
            **bound,
            "action": retry_action,
            "bound_action_request": bound,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "action_id": action_id,
            "idempotency_key": idempotency_key,
            "action_request_hash": retry_action["request_hash"],
        }

    request.update(
        task_id=task_id,
        attempt_id=attempt_id,
        action_id=action_id,
        idempotency_key=idempotency_key,
    )
    request.pop("action_request_hash", None)
    request["action_request_hash"] = canonical_request_hash(request)
    return request


def _retry_semantic_payload(request: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only attempt-scoped transport identity from a durable request."""
    raw_bound = request.get("bound_action_request")
    source = raw_bound if isinstance(raw_bound, Mapping) else request
    payload = json.loads(json.dumps(dict(source)))
    for field in (
        "attempt_id",
        "action_id",
        "idempotency_key",
        "action_request_hash",
        "action_type",
    ):
        payload.pop(field, None)
    return payload


def _validate_retry_predecessor(
    request: Mapping[str, Any],
    predecessor: Optional[Mapping[str, Any]],
) -> None:
    """Fail closed unless TASK_RETRY is a fresh attempt of one terminal task."""
    if predecessor is None:
        raise ValueError("RETRY_REQUIRES_EXISTING_TASK")

    status = str(predecessor.get("status") or "")
    cleanup_decision = str(predecessor.get("cleanup_decision") or "")
    retained_retry = (
        status == "RETAINED_FOR_REVIEW"
        and predecessor.get("promotion_status") == "NOT_CREATED"
        and cleanup_decision in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
        and not (
            predecessor.get("promotion_packet")
            or predecessor.get("candidate_commit_sha")
            or predecessor.get("candidate_ref")
        )
    )
    retryable_terminal = status in {
        "FINAL_BLOCK",
        "REJECTED",
        "SUPERSEDED",
        "CANCELLED",
        "INTEGRATION_FAILED",
        "INTEGRATED",
    } or retained_retry
    if not retryable_terminal:
        raise ValueError("RETRY_REQUIRES_TERMINAL_TASK")
    if cleanup_decision not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}:
        raise ValueError("RETRY_TARGET_DISPOSITION_REQUIRED")

    attempts = predecessor.get("attempts") or ()
    used_attempt_ids = {
        str(item.get("attempt_id") or "")
        for item in attempts
        if isinstance(item, Mapping)
    }
    used_action_ids = {
        str(item.get("action_id") or "")
        for item in attempts
        if isinstance(item, Mapping)
    }
    used_idempotency_keys = {
        str(item.get("idempotency_key") or "")
        for item in attempts
        if isinstance(item, Mapping)
    }
    used_attempt_ids.add(str(predecessor.get("attempt_id") or ""))
    used_action_ids.add(str(predecessor.get("action_id") or ""))
    used_idempotency_keys.add(str(predecessor.get("idempotency_key") or ""))
    if str(request.get("attempt_id") or "") in used_attempt_ids:
        raise ValueError("RETRY_ATTEMPT_ID_REUSED")
    if str(request.get("action_id") or "") in used_action_ids:
        raise ValueError("RETRY_ACTION_ID_REUSED")
    if str(request.get("idempotency_key") or "") in used_idempotency_keys:
        raise ValueError("RETRY_IDEMPOTENCY_KEY_REUSED")

    previous_request = predecessor.get("request")
    if not isinstance(previous_request, Mapping):
        raise ValueError("RETRY_PREDECESSOR_REQUEST_MISSING")
    if canonical_request_hash(_retry_semantic_payload(request)) != canonical_request_hash(
        _retry_semantic_payload(previous_request)
    ):
        raise ValueError("RETRY_SEMANTIC_TASK_MISMATCH")


def resolve_canonical_target_roots(
    task_id: str,
    campaign_id: Optional[str] = None,
    requested_target_worktree_root: Optional[str] = None,
    requested_target_repo_root: Optional[str] = None,
) -> tuple[Path, Path]:
    override = os.getenv("NEXUS_TARGET_ROOT_OVERRIDE", "").strip()
    if override:
        base_worktree_root = Path(override).expanduser().resolve()
    elif requested_target_worktree_root and "/private/tmp" not in requested_target_worktree_root and "/tmp" not in requested_target_worktree_root:
        base_worktree_root = Path(requested_target_worktree_root).expanduser().resolve()
    else:
        workspace_root = Path.cwd().resolve()
        if workspace_root == CANONICAL_SOURCE_ROOT:
            base_worktree_root = CANONICAL_SOURCE_ROOT.parent / "nexus-runtime-targets"
        elif "nexus-runtime-targets" in workspace_root.parts:
            idx = workspace_root.parts.index("nexus-runtime-targets")
            base_worktree_root = Path(*workspace_root.parts[:idx + 1])
        else:
            base_worktree_root = workspace_root.parent / "nexus-runtime-targets"
        if campaign_id:
            base_worktree_root = base_worktree_root / campaign_id

    if requested_target_repo_root and "/private/tmp" not in requested_target_repo_root and "/tmp" not in requested_target_repo_root:
        target_repo_root = Path(requested_target_repo_root).expanduser().resolve()
    else:
        target_repo_root = base_worktree_root / task_id

    disabled_parts = {"nexus-worktrees"}
    if disabled_parts.intersection(base_worktree_root.parts) or disabled_parts.intersection(target_repo_root.parts):
        raise ValueError("DISABLED_TARGET_ROOT: nexus-worktrees is retired; use /Users/jameschen/Workspace/nexus-runtime-targets")
    return base_worktree_root, target_repo_root


def validate_task_card_binding(contract: ArchitectTaskContract, request: Mapping[str, Any], *, is_ephemeral: bool = False) -> None:
    if request.get("allow_unbound_test_identity") is True and not is_ephemeral:
        raise RuntimeError("TASK_CARD_BINDING_MISMATCH: allow_unbound_test_identity is only permitted when ephemeral=True")

    allow_unbound = (
        is_ephemeral
        and not request.get("task_card_required")
        and not request.get("lifecycle_identity_required")
        and request.get("allow_unbound_test_identity") is not False
    )

    if str(request.get("contract_kind") or "") == ContractKind.OWNER_INLINE.value:
        inline = request.get("owner_inline_contract")
        try:
            validate_owner_inline_contract(
                inline if isinstance(inline, Mapping) else {},
                expected_task_id=contract.task_id,
                expected_head=str(contract.controller_revision or ""),
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        return

    task_id = contract.task_id
    card_path_str = request.get("task_card_path")
    card_path = None
    if card_path_str:
        card_path = _resolve_task_card_path(card_path_str)
    else:
        possible = Path.cwd() / f"tasks/{task_id}.md"
        if possible.exists():
            card_path = possible
        else:
            matches = list(Path.cwd().glob(f"tasks/*/{task_id}.md")) + list(Path.cwd().glob(f"tasks/*/*{task_id}*.md"))
            card_path = matches[0] if matches else None

    if not card_path or not card_path.exists():
        if not allow_unbound:
            raise RuntimeError(f"TASK_CARD_BINDING_MISMATCH: task card does not exist for task_id '{task_id}'")
        return

    content = card_path.read_text(encoding="utf-8")
    if f"task_id: `{task_id}`" not in content and f"task_id: {task_id}" not in content and f"`{task_id}`" not in content and f"task_id: '{task_id}'" not in content:
        raise RuntimeError(f"TASK_CARD_BINDING_MISMATCH: task card task_id does not match lifecycle task_id '{task_id}'")

    if "AUTO_CHAIN: true" in content or "AUTO_CHAIN=true" in content:
        raise RuntimeError("TASK_CARD_BINDING_MISMATCH: AUTO_CHAIN must be false")


def resolve_lifecycle_identity(contract: ArchitectTaskContract, request: Mapping[str, Any], *, is_ephemeral: bool = False) -> dict[str, Any]:
    if request.get("allow_unbound_test_identity") is True and not is_ephemeral:
        raise RuntimeError("LIFECYCLE_REVISION_MISMATCH: allow_unbound_test_identity is only permitted when ephemeral=True")

    allow_unbound = (
        is_ephemeral
        and not request.get("lifecycle_identity_required")
        and not request.get("task_card_required")
        and request.get("allow_unbound_test_identity") is not False
    )

    source_root = Path(__file__).resolve().parents[2]
    current_rev = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root, capture_output=True, text=True
    ).stdout.strip()
    req_rev = request.get("required_lifecycle_revision")
    if req_rev:
        if current_rev != req_rev and not current_rev.startswith(req_rev):
            raise RuntimeError(f"LIFECYCLE_REVISION_MISMATCH: current revision {current_rev} does not match required {req_rev}")

    if str(request.get("contract_kind") or "") == ContractKind.OWNER_INLINE.value:
        inline = request.get("owner_inline_contract")
        try:
            validated = validate_owner_inline_contract(
                inline if isinstance(inline, Mapping) else {},
                expected_task_id=contract.task_id,
                expected_head=str(contract.controller_revision or ""),
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        return {
            "lifecycle_revision": current_rev,
            "lifecycle_executable_path": str(Path(sys.executable).resolve()),
            "worker_module_path": str(Path(__file__).resolve()),
            "controller_revision": contract.controller_revision,
            "contract_kind": ContractKind.OWNER_INLINE.value,
            "contract_hash": validated["contract_hash"],
            "owner_inline_contract": validated,
            "task_card_path": None,
            "task_card_hash": None,
        }

    card_path_str = request.get("task_card_path")
    card_path = None
    if card_path_str:
        card_path = _resolve_task_card_path(card_path_str)
    else:
        task_id = contract.task_id
        possible = Path.cwd() / f"tasks/{task_id}.md"
        if possible.exists():
            card_path = possible
        else:
            matches = list(Path.cwd().glob(f"tasks/*/{task_id}.md")) + list(Path.cwd().glob(f"tasks/*/*{task_id}*.md"))
            card_path = matches[0] if matches else None

    card_path_res = str(card_path.resolve()) if card_path and card_path.exists() else None
    card_hash = None
    if card_path and card_path.exists():
        card_hash = hashlib.sha256(card_path.read_bytes()).hexdigest()

    if not allow_unbound:
        if not current_rev or not card_path_res or not card_hash or not contract.controller_revision:
            raise RuntimeError("LIFECYCLE_REVISION_MISMATCH: missing required lifecycle identity binding fields")

    return {
        "lifecycle_revision": current_rev,
        "lifecycle_executable_path": str(Path(sys.executable).resolve()),
        "worker_module_path": str(Path(__file__).resolve()),
        "controller_revision": contract.controller_revision,
        "contract_kind": ContractKind.TRACKED_TASK_CARD.value if card_hash else ContractKind.NONE.value,
        "contract_hash": None,
        "task_card_path": card_path_res,
        "task_card_hash": card_hash,
    }


def _resolve_task_card_path(value: str | Path) -> Path:
    """Resolve a repository-relative card independent of the Gateway cwd."""
    raw = Path(value).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    direct = raw.resolve()
    if direct.exists():
        return direct
    return (CANONICAL_SOURCE_ROOT / raw).resolve()


def validate_lifecycle_revision(contract: ArchitectTaskContract, request: Mapping[str, Any]) -> None:
    resolve_lifecycle_identity(contract, request)


def check_fast_lane_eligible(contract: ArchitectTaskContract, request: Optional[Mapping[str, Any]] = None) -> bool:
    req = request or {}
    allowed_files = getattr(contract, "allowed_files", ()) or ()
    verifier_commands = getattr(contract, "verifier_commands", ()) or ()
    max_provider_calls = getattr(contract, "maximum_provider_calls", 1)
    max_deleted = getattr(contract, "maximum_deleted_files", 0)

    if len(allowed_files) > 4:
        return False
    if max_provider_calls > 1:
        return False
    if not verifier_commands:
        return False
    if getattr(contract, "deletion_allowed", False) or max_deleted > 0:
        return False
    if req.get("migration_authority") or req.get("schema_authority"):
        return False
    if req.get("route_authority_mutation"):
        return False
    if req.get("security_policy_weakening"):
        return False
    if getattr(contract, "public_claim_allowed", False) or getattr(contract, "production_ready", False):
        return False
    if getattr(contract, "controller_clean", None) is False or getattr(contract, "target_isolated", None) is False:
        return False

    return True


CANONICAL_SOURCE_BRANCH = "nexus/integration/main"


def resolve_execution_lane(
    request: Mapping[str, Any],
    *,
    active_mutation_tasks: int = 0,
) -> dict[str, Any]:
    """Classify ordinary primary-agent work without allocating a Target."""
    # Ordinary primary-agent work is Direct by default; callers opt into an
    # isolated Target when they need delegation, parallelism, or risk fencing.
    requested = str(request.get("execution_lane", "DIRECT_CANONICAL")).strip().upper()
    if requested not in {"DIRECT_CANONICAL", "ISOLATED_TARGET"}:
        raise ValueError("execution_lane must be DIRECT_CANONICAL or ISOLATED_TARGET")
    if requested == "ISOLATED_TARGET":
        return {
            "execution_lane": "ISOLATED_TARGET",
            "eligible": True,
            "blockers": [],
            "next_action": "prepare_governed_target",
        }

    blockers: list[str] = []
    controller = Path(str(request.get("controller_repo_root") or CANONICAL_SOURCE_ROOT)).expanduser().resolve()
    if controller != CANONICAL_SOURCE_ROOT:
        blockers.append("controller_is_not_canonical_source")
    if request.get("primary_agent") is not True:
        blockers.append("primary_agent_attestation_required")
    worker = str(request.get("worker", "primary")).strip().lower()
    if worker not in {"", "primary", "codex"}:
        blockers.append("delegated_worker_forbidden")
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if branch != CANONICAL_SOURCE_BRANCH:
            blockers.append("canonical_branch_mismatch")
        dirty = subprocess.run(
            ["git", "status", "--porcelain=v1"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if dirty:
            blockers.append("canonical_checkout_dirty")
    except OSError:
        blockers.append("canonical_git_probe_failed")
    if len(request.get("allowed_files") or []) > 4:
        blockers.append("allowed_file_limit_exceeded")
    if active_mutation_tasks > 0:
        blockers.append("another_mutation_task_is_active")
    if request.get("authorized_deletions"):
        blockers.append("deletions_forbidden")
    if request.get("generated_change") or request.get("large_change"):
        blockers.append("generated_or_large_change_forbidden")
    lockfile_names = {
        "uv.lock", "poetry.lock", "package-lock.json", "pnpm-lock.yaml",
        "yarn.lock", "Cargo.lock", "Gemfile.lock",
    }
    for raw_path in request.get("allowed_files") or []:
        path = str(raw_path).strip().rstrip("/")
        name = Path(path).name
        if name in lockfile_names:
            blockers.append("lockfile_change_forbidden")
        if path.startswith(("generated/", "dist/", "build/", ".next/")) or name.endswith(".generated.json"):
            blockers.append("generated_or_large_change_forbidden")
    for flag in ("migration_authority", "schema_authority", "route_authority_mutation", "security_policy_weakening", "public_claim_allowed", "production_ready"):
        if request.get(flag):
            blockers.append(f"{flag}_forbidden")
    return {
        "execution_lane": "DIRECT_CANONICAL" if not blockers else "ISOLATED_TARGET",
        "eligible": not blockers,
        "blockers": blockers,
        "next_action": "edit_canonical_checkout" if not blockers else "prepare_governed_target",
    }


class SelfHostedTaskService:
    _CUSTOM_RUNNER_FORBIDDEN_EVIDENCE_FIELDS = frozenset({
        "admission_binding",
        "canonical_dispatch_envelope",
        "execution",
        "executions",
        "execution_outcome",
        "verified_receipt",
        "verified_receipt_hash",
        "worker_preflight",
        "workforce_admission",
        "workforce_aggregate_binding_hash",
        "workforce_binding_hash",
        "workforce_dispatch",
        "workforce_policy_hash",
    })

    @staticmethod
    def canonical_state_dir() -> Path:
        configured = os.getenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        source_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=source_root, capture_output=True, text=True,
        )
        if result.returncode == 0:
            repository_root = Path(result.stdout.strip()).resolve().parent
            return repository_root.parent / f"{repository_root.name}-self-hosted-state"
        return (source_root / ".nexus/self_hosted_tasks").resolve()

    def __init__(
        self,
        state_dir: str | Path | None = None,
        runner: Optional[Runner] = None,
        *,
        stale_after_seconds: float = 30.0,
        auto_reconcile: bool = True,
        worker_registry: Optional[WorkerRegistry] = None,
        ephemeral: bool = False,
    ):
        canonical = self.canonical_state_dir()
        self.state_dir = Path(state_dir).expanduser().resolve() if state_dir is not None else canonical
        temporary_roots = _temporary_state_roots()
        is_temporary = any(root == self.state_dir or root in self.state_dir.parents for root in temporary_roots)
        if self.state_dir != canonical and not ephemeral and not is_temporary:
            raise ValueError(f"production tasks must use canonical state root: {canonical}")
        self.ephemeral = ephemeral or is_temporary
        if runner is not None and not self.ephemeral:
            raise RuntimeError("CUSTOM_RUNNER_REQUIRES_EPHEMERAL_STATE")
        self._custom_runner = runner
        self.runner = runner or self._run_default
        self.stale_after_seconds = stale_after_seconds
        self.worker_registry = worker_registry or WorkerRegistry.default()
        self._threads: dict[str, threading.Thread] = {}
        if auto_reconcile:
            self.reconcile_tasks()

    def _state_path(self, task_id: str) -> Path:
        return self.state_dir / f"{task_id}.json"

    @classmethod
    def _bound_custom_runner_values(cls, values: Mapping[str, Any]) -> dict[str, Any]:
        bounded = {
            key: value
            for key, value in values.items()
            if key not in cls._CUSTOM_RUNNER_FORBIDDEN_EVIDENCE_FIELDS
        }
        bounded.update({
            "execution_authority": "EPHEMERAL_TEST_RUNNER",
            "provider_receipt_authoritative": False,
            "workforce_admission_authoritative": False,
            "public_claim_allowed": False,
            "production_ready": False,
            "promotion_eligible": False,
        })
        return bounded

    def _archive_root(self) -> Path:
        return self.state_dir.parent / "nexus-state-archive"

    def _archive_state_path(self, task_id: str) -> Path:
        return self._archive_root() / f"{task_id}.json"

    def _archive_state_candidates(self, task_id: str) -> list[Path]:
        root = self._archive_root()
        candidates = [self._archive_state_path(task_id)]
        candidates.extend(sorted(root.glob(f"{task_id}--attempt-*.json")) if root.exists() else [])
        return [path for path in candidates if path.exists()]

    @staticmethod
    def _candidate_commit(state: Mapping[str, Any]) -> Optional[str]:
        packet = state.get("promotion_packet") or {}
        return state.get("candidate_commit_sha") or packet.get("candidate_commit_sha")

    def _require_integrated_replacement(self, task_id: str, superseded_by: str) -> None:
        replacement = self._read_state(superseded_by)
        if (
            replacement is None
            or superseded_by == task_id
            or replacement.get("task_id") != superseded_by
            or replacement.get("status") != "INTEGRATED"
            or replacement.get("promotion_status") != "INTEGRATED"
            or not str(replacement.get("integration_result_sha") or "").strip()
        ):
            raise RuntimeError(
                "superseded_by must name an existing INTEGRATED self-hosted task "
                "with promotion_status=INTEGRATED and integration_result_sha"
            )

    @classmethod
    def _terminal_failure_blocker(cls, state: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        if str(state.get("status") or "") not in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW", "INTEGRATION_FAILED"}:
            return None
        raw_error = str(state.get("error") or "")
        error = raw_error.strip()
        if not error:
            return None
        request = state.get("request") if isinstance(state.get("request"), Mapping) else {}
        evidence: dict[str, Any] = {
            "code": "WORKER_EXECUTION_FAILED",
            "detail": _bounded_failure_text("worker execution failed"),
            "error_sha256": hashlib.sha256(raw_error.encode("utf-8")).hexdigest(),
            "failure_stage": "worker_execution",
        }
        provider = str(state.get("worker_provider") or request.get("provider") or "").strip()
        model = str(request.get("model") or "").strip()
        if provider:
            evidence["provider"] = provider
        if model:
            evidence["model"] = model
        if state.get("exit_code") is not None:
            try:
                evidence["exit_code"] = int(state["exit_code"])
            except (TypeError, ValueError):
                pass
        if state.get("execution_outcome"):
            evidence["execution_outcome"] = str(state["execution_outcome"])
        return evidence

    @classmethod
    def _projected_blocker(cls, state: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        if "blocker" in state and state["blocker"] is not None:
            return state["blocker"]
        return cls._terminal_failure_blocker(state)

    @classmethod
    def _settled_candidate_less_final_block(cls, state: Mapping[str, Any]) -> bool:
        """Identify a terminal failure whose retry is historical, not required."""
        if (
            state.get("status") != "FINAL_BLOCK"
            or state.get("promotion_status") != "NOT_CREATED"
            or state.get("cleanup_decision") not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
            or state.get("cleanup_blocker")
            or state.get("reconciliation_required") is True
            or state.get("reconciliation_status") not in {None, "RECONCILED", "NOT_REQUIRED"}
            or state.get("reconciliation_decision") not in {None, "NO_MUTATION_OBSERVED"}
            or state.get("uncertain_mutation") is True
            or state.get("candidate_created") not in {None, False}
            or state.get("candidate_status") not in {None, "", "NOT_CREATED", "FINAL_BLOCK"}
            or state.get("state_retention_status") not in {None, "TERMINAL", "ARCHIVED"}
            or state.get("approved_binding")
            or state.get("integration_receipt")
            or state.get("integration_result_sha")
            or state.get("merge_performed")
        ):
            return False

        candidate = state.get("promotion_packet")
        candidate_fields = (
            "candidate_commit_sha",
            "candidate_tree_sha",
            "candidate_state_hash",
            "verified_receipt_hash",
            "candidate_ref",
        )
        if any(state.get(field) for field in candidate_fields):
            return False
        if isinstance(candidate, Mapping) and any(candidate.get(field) for field in candidate_fields):
            return False
        return True

    @classmethod
    def _task_action_envelope(cls, state: Mapping[str, Any]) -> dict[str, Any]:
        status = str(state.get("status") or "UNKNOWN")
        promotion_status = str(state.get("promotion_status") or "")
        candidate_commit = cls._candidate_commit(state)

        if status == "BLOCKED_INVALID_STATE":
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "inspect_lifecycle_state"
            recommended_tool = None
        elif status == "DIRECT_RECONCILE_REQUIRED" and state.get("reconciliation_decision") == "RETAINED_FOR_REVIEW":
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "inspect_receipt_and_candidate"
            recommended_tool = "nexus_task_status"
        elif status == "DIRECT_RECONCILE_REQUIRED":
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "nexus_task_reconcile"
            recommended_tool = "nexus_task_reconcile"
        elif status == "DIRECT_COMPLETED":
            action_state = "TERMINAL"
            attention_required = False
            next_action = "none"
            recommended_tool = None
        elif status in {"DIRECT_INTENT_RECORDED", "DIRECT_STARTED", "DIRECT_APPLIED", "DIRECT_VERIFIED", "DIRECT_COMMITTED"}:
            action_state = "IN_PROGRESS"
            attention_required = False
            next_action = "nexus_task_finish"
            recommended_tool = "nexus_task_finish"
        elif status == "INTEGRATING":
            action_state = "IN_PROGRESS"
            attention_required = False
            next_action = "wait_for_task"
            recommended_tool = "nexus_self_hosted_wait_task"
        elif status == "INTEGRATION_VERIFY_FAILED_AFTER_APPLY":
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "owner_review_post_apply_failure"
            recommended_tool = "nexus_self_hosted_get_receipt"
        elif status == "INTEGRATION_FAILED_PRE_APPLY":
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "retry_integration_same_task"
            recommended_tool = "nexus_self_hosted_retry_integration"
        elif status == "INTEGRATED_TARGET_RETAINED":
            action_state = "ACTION_REQUIRED"
            attention_required = True
            next_action = "retry_cleanup"
            recommended_tool = "nexus_self_hosted_cleanup"
        elif status in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW", "INTEGRATION_FAILED"}:
            action_state = "FINAL_BLOCK"
            attention_required = True
            cleanup_removed = state.get("cleanup_decision") in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
            verified_uncommitted = bool(
                (state.get("verified_receipt") or {}).get("verified")
                and (state.get("attempt_resolution") or {}).get("verdict") == "PROVEN"
                and not candidate_commit
                and not cleanup_removed
            )
            if status == "INTEGRATION_FAILED" and not state.get("merge_performed"):
                next_action = "retry_integration_same_task"
                recommended_tool = "nexus_self_hosted_retry_integration"
            elif verified_uncommitted:
                next_action = "recover_verified_candidate"
                recommended_tool = "nexus_self_hosted_recover_verified_uncommitted_candidate"
            elif status == "RETAINED_FOR_REVIEW" and state.get("cleanup_decision") == "BLOCKED_BY_UNSAVED_CHANGES":
                next_action = "salvage_or_dispose_retained_target"
                recommended_tool = "nexus_self_hosted_cleanup"
            elif status in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW"} and not candidate_commit and promotion_status == "NOT_CREATED" and cleanup_removed:
                next_action = "retry_same_task"
                recommended_tool = "nexus_self_hosted_retry"
            else:
                next_action = "inspect_receipt_and_candidate"
                recommended_tool = "nexus_self_hosted_get_receipt"
            if cls._settled_candidate_less_final_block(state):
                action_state = "TERMINAL"
                attention_required = False
        elif status in (PENDING_CANDIDATE_STATUSES - {"INTEGRATING"}) or promotion_status in {"PENDING_HUMAN_APPROVAL", "APPROVED", "APPROVAL_INVALIDATED"}:
            action_state = "ACTION_REQUIRED"
            attention_required = True
            if promotion_status == "APPROVED" or status == "APPROVED":
                next_action = "integrate_approved_candidate"
                recommended_tool = "nexus_self_hosted_integrate_approved"
            elif promotion_status == "APPROVAL_INVALIDATED" or status == "APPROVAL_INVALIDATED":
                next_action = "resubmit_exact_approval_binding"
                recommended_tool = "nexus_self_hosted_approve_promotion"
            else:
                next_action = "approve_candidate"
                recommended_tool = "nexus_self_hosted_approve_promotion"
        elif status in TERMINAL_STATUSES:
            action_state = "TERMINAL"
            attention_required = False
            next_action = "none"
            recommended_tool = None
        else:
            action_state = "IN_PROGRESS"
            attention_required = False
            next_action = "wait_for_task"
            recommended_tool = "nexus_self_hosted_wait_task"

        packet = state.get("promotion_packet") or {}
        return {
            "schema": "nexus.self_hosted_task_action.v1",
            "task_id": state.get("task_id"),
            "task_status": status,
            "promotion_status": promotion_status or None,
            "action_state": action_state,
            "attention_required": attention_required,
            "next_action": next_action,
            "recommended_tool": recommended_tool,
            "candidate_commit_sha": candidate_commit,
            "candidate_ref": state.get("candidate_ref"),
            "candidate": {
                "candidate_commit_sha": candidate_commit,
                "candidate_tree_sha": state.get("candidate_tree_sha") or packet.get("candidate_tree_sha"),
                "candidate_state_hash": state.get("candidate_state_hash") or packet.get("candidate_state_hash"),
                "verified_receipt_hash": state.get("verified_receipt_hash") or packet.get("verified_receipt_hash"),
            },
            "cleanup_status": {
                "cleanup_eligible": state.get("cleanup_eligible", False),
                "cleanup_decision": state.get("cleanup_decision"),
                "cleanup_blocker": state.get("cleanup_blocker"),
                "cleanup_performed": state.get("cleanup_performed", False),
                "cleanup_performed_at": state.get("cleanup_performed_at"),
                "state_retention_status": state.get("state_retention_status"),
                "archive_eligible": state.get("archive_eligible", False),
            },
        }

    @classmethod
    def _with_task_action(cls, state: dict[str, Any]) -> dict[str, Any]:
        state = dict(state)
        state["task_action"] = cls._task_action_envelope(state)
        return state

    @staticmethod
    def _approval_requirements(state: Mapping[str, Any]) -> dict[str, Any]:
        """Project durable Architecture Approval inputs without granting approval."""
        input_reasons: list[str] = []

        def approval_source(name: str) -> Mapping[str, Any]:
            if name not in state:
                return {}
            source = state[name]
            if source is None:
                return {}
            if isinstance(source, Mapping):
                if not source:
                    input_reasons.append(
                        f"malformed_source:{name}:empty_or_missing_contract_fields"
                    )
                return source
            input_reasons.append(f"malformed_source:{name}:expected_mapping")
            return {}

        packet = approval_source("promotion_packet")
        candidate = state.get("candidate") if isinstance(state.get("candidate"), Mapping) else {}
        receipt = approval_source("verified_receipt")

        def values(
            field: str,
            *sources: tuple[str, Mapping[str, Any]],
            pattern: str,
        ) -> list[tuple[str, str]]:
            resolved = []
            for name, source in sources:
                raw = source.get(field)
                if raw is None or raw == "":
                    continue
                if type(raw) is not str:
                    input_reasons.append(f"invalid_type:{name}.{field}")
                    continue
                value = raw.strip()
                if not value:
                    continue
                if not re.fullmatch(pattern, value):
                    input_reasons.append(f"invalid_format:{name}.{field}")
                    continue
                resolved.append((name, value))
            return resolved

        required_values = []
        for name, source in (
            ("promotion_packet", packet),
            ("verified_receipt", receipt),
        ):
            raw = source.get("authority_change_required", False)
            if type(raw) is not bool:
                input_reasons.append(f"invalid_type:{name}.authority_change_required")
                raw = False
            required_values.append((name, raw))
        required = any(value for _, value in required_values)

        approval_shaped = any(
            isinstance(value, Mapping) and value.get("architecture_approval") is not None
            for value in (state.get("approved_binding"), packet, receipt)
        )
        binding = {
            "bound_task_id": "",
            "bound_attempt_id": "",
            "candidate_commit_sha": "",
            "candidate_tree_sha": "",
            "authority_findings_sha256": "",
        }
        for state_field, binding_field in (
            ("task_id", "bound_task_id"),
            ("attempt_id", "bound_attempt_id"),
        ):
            raw = state.get(state_field)
            if raw is None or raw == "":
                continue
            if type(raw) is not str:
                input_reasons.append(f"invalid_type:task.{state_field}")
                continue
            binding[binding_field] = raw.strip()
        if state.get("state_valid") is False:
            blocker = state.get("blocker") if isinstance(state.get("blocker"), Mapping) else {}
            source_reasons = blocker.get("approval_requirements_reasons")
            if isinstance(source_reasons, list) and all(
                type(reason) is str and reason for reason in source_reasons
            ):
                input_reasons.extend(source_reasons)
            else:
                code = blocker.get("code") if type(blocker.get("code")) is str else "UNKNOWN"
                input_reasons.append(f"invalid_state:{code}")

        field_sources = {
            "candidate_commit_sha": values(
                "candidate_commit_sha",
                ("task", state),
                ("promotion_packet", packet),
                ("candidate", candidate),
                ("verified_receipt", receipt),
                pattern=r"[0-9a-f]{40}",
            )
            + values(
                "commit_sha",
                ("candidate", candidate),
                pattern=r"[0-9a-f]{40}",
            ),
            "candidate_tree_sha": values(
                "candidate_tree_sha",
                ("task", state),
                ("promotion_packet", packet),
                ("candidate", candidate),
                ("verified_receipt", receipt),
                pattern=r"[0-9a-f]{40}",
            )
            + values(
                "tree_sha",
                ("candidate", candidate),
                pattern=r"[0-9a-f]{40}",
            ),
            "authority_findings_sha256": values(
                "authority_findings_sha256",
                ("promotion_packet", packet),
                ("verified_receipt", receipt),
                pattern=r"[0-9a-f]{64}",
            ),
        }
        missing: list[str] = []
        mismatches: list[str] = []
        for field, source_values in field_sources.items():
            unique_values = {value for _, value in source_values}
            if not source_values:
                missing.append(field)
            elif len(unique_values) > 1:
                mismatches.append(field)
            else:
                binding[field] = source_values[0][1]

        if not binding["bound_task_id"]:
            missing.append("bound_task_id")
        if not binding["bound_attempt_id"]:
            missing.append("bound_attempt_id")
        if required_values[0][1] != required_values[1][1] and any(
            value for _, value in required_values
        ):
            mismatches.append("authority_change_required")
        missing = sorted(set(missing))
        mismatches = sorted(set(mismatches))

        stale = approval_shaped or (
            required
            and state.get("promotion_status") in {"APPROVED", "INTEGRATED", "APPROVAL_INVALIDATED"}
        )
        if not required and input_reasons:
            status = "NOT_APPROVABLE"
            completeness = "INCOMPLETE"
            approvability = "NOT_APPROVABLE"
        elif not required:
            status = "NOT_REQUIRED"
            completeness = "NOT_REQUIRED"
            approvability = "NOT_REQUIRED"
        elif stale:
            status = "NOT_APPROVABLE"
            completeness = "INCOMPLETE"
            approvability = "NOT_APPROVABLE"
            missing.append("stale_approval_requirements")
        elif input_reasons or missing or mismatches:
            status = "NOT_APPROVABLE"
            completeness = "INCOMPLETE"
            approvability = "NOT_APPROVABLE"
        else:
            status = "APPROVABLE"
            completeness = "COMPLETE"
            approvability = "APPROVABLE"

        reasons = list(input_reasons)
        if required:
            reasons.extend(f"missing:{field}" for field in missing)
            reasons.extend(f"mismatch:{field}" for field in mismatches)
        if stale:
            reasons.append("stale:approval_requirements")
        return {
            "schema": "nexus.architecture_approval_requirements.v1",
            "required": required,
            "status": status,
            "completeness": completeness,
            "approvability": approvability,
            "task_id": binding["bound_task_id"],
            "attempt_id": binding["bound_attempt_id"],
            "binding": binding,
            "missing": sorted(set(missing)),
            "mismatches": mismatches,
            "reasons": sorted(set(reasons)),
            "stale": stale,
        }

    @classmethod
    def _invalid_state_status(
        cls,
        task_id: str,
        *,
        code: str,
        detail: str,
        source_path: Path,
        approval_requirements_reasons: Sequence[str] = (),
    ) -> dict[str, Any]:
        blocker: dict[str, Any] = {
            "code": code,
            "detail": detail,
            "source_path": str(source_path),
        }
        if approval_requirements_reasons:
            blocker["approval_requirements_reasons"] = sorted(set(approval_requirements_reasons))
        return cls._with_task_action(
            {
                "schema": "nexus.self_hosted_task_status.v1",
                "task_id": task_id,
                "status": "BLOCKED_INVALID_STATE",
                "found": True,
                "state_valid": False,
                "retry_authorized": False,
                "blocker": blocker,
            }
        )

    @classmethod
    def _load_state_path(cls, path: Path, task_id: str) -> Optional[dict[str, Any]]:
        try:
            payload = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            return cls._invalid_state_status(
                task_id,
                code="STATE_READ_FAILED",
                detail=f"state file could not be read: {type(exc).__name__}",
                source_path=path,
            )
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            return cls._invalid_state_status(
                task_id,
                code="STATE_JSON_INVALID",
                detail=f"state JSON is invalid at line {exc.lineno} column {exc.colno}",
                source_path=path,
            )
        if not isinstance(decoded, Mapping):
            return cls._invalid_state_status(
                task_id,
                code="STATE_NOT_OBJECT",
                detail="state JSON must decode to an object",
                source_path=path,
            )

        state = dict(decoded)
        state_task_id = state.get("task_id")
        status = state.get("status")
        if not isinstance(state_task_id, str) or state_task_id != task_id:
            return cls._invalid_state_status(
                task_id,
                code="STATE_FIELD_INVALID",
                detail="state task_id is missing or does not match its filename",
                source_path=path,
            )
        if not isinstance(status, str) or not status.strip():
            return cls._invalid_state_status(
                task_id,
                code="STATE_FIELD_INVALID",
                detail="state status must be a non-empty string",
                source_path=path,
            )
        for field in ("attempts", "executions"):
            value = state.get(field)
            if field in state and (
                not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value)
            ):
                return cls._invalid_state_status(
                    task_id,
                    code="STATE_FIELD_INVALID",
                    detail=f"state {field} must be a list of objects",
                    source_path=path,
                )
        object_fields = (
            "action",
            "attempt_resolution",
            "contract",
            "lease",
            "promotion_packet",
            "request",
            "verified_receipt",
        )
        invalid_object_fields = [
            field
            for field in object_fields
            if field in state and state[field] is not None and not isinstance(state[field], Mapping)
        ]
        if invalid_object_fields:
            field = invalid_object_fields[0]
            approval_reasons = [
                f"malformed_source:{name}:expected_mapping"
                for name in invalid_object_fields
                if name in {"promotion_packet", "verified_receipt"}
            ]
            return cls._invalid_state_status(
                task_id,
                code="STATE_FIELD_INVALID",
                detail=f"state {field} must be an object",
                source_path=path,
                approval_requirements_reasons=approval_reasons,
            )
        return cls._with_task_action(state)

    def _latest_archived_state(self, task_id: str) -> tuple[Optional[Path], Optional[dict[str, Any]]]:
        latest_path: Optional[Path] = None
        latest_state: Optional[dict[str, Any]] = None
        latest_key: tuple[str, int] = ("", -1)
        for path in self._archive_state_candidates(task_id):
            state = self._load_state_path(path, task_id)
            if state is None:
                continue
            key = (str(state.get("updated_at") or ""), path.stat().st_mtime_ns)
            if latest_state is None or key > latest_key:
                latest_path, latest_state, latest_key = path, state, key
        return latest_path, latest_state

    def _lock_path(self) -> Path:
        return self.state_dir / ".state.lock"

    @contextmanager
    def _state_lock(self) -> Iterator[None]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self._lock_path().open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _write_state_locked(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        normalized = _jsonable(state)
        normalized["task_action"] = self._task_action_envelope(normalized)
        destination = self._state_path(task_id)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.state_dir,
            prefix=f".{task_id}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(normalized, handle, sort_keys=True, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(destination)
        return normalized

    def _write_state(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._state_lock():
            return self._write_state_locked(task_id, state)

    def _create_state(self, task_id: str, state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        with self._state_lock():
            destination = self._state_path(task_id)
            if destination.exists():
                existing = self._load_state_path(destination, task_id)
                if existing is not None:
                    return existing, False
            _, archived = self._latest_archived_state(task_id)
            if archived is not None:
                return archived, False
            return self._write_state_locked(task_id, state), True

    def _read_state(self, task_id: str) -> Optional[dict[str, Any]]:
        path = self._state_path(task_id)
        if not path.exists():
            _, archived = self._latest_archived_state(task_id)
            return archived
        with self._state_lock():
            if not path.exists():
                return None
            return self._load_state_path(path, task_id)

    def _read_state_snapshot(self, task_id: str) -> Optional[dict[str, Any]]:
        """Read a durable snapshot without creating or acquiring the state lock.

        Read-only status and workspace inventory surfaces must not mutate the
        lifecycle store. State writes use atomic ``replace`` semantics, so a
        direct read observes either the previous complete JSON or the next
        complete JSON; a concurrent disappearance is treated as absent.
        """
        state = self._load_state_path(self._state_path(task_id), task_id)
        if state is not None:
            return state
        _, archived = self._latest_archived_state(task_id)
        return archived

    def record_operator_outcome(
        self,
        task_id: str,
        receipt: OperatorOutcomeReceipt | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Persist one privacy-bounded outcome in the existing task state.

        Idempotent replays return the original receipt.  A key reused with a
        different payload, a cross-attempt supersession, or a cycle fails
        closed; this method never changes task authority or lifecycle status.
        """
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task: {task_id}")
        contract = state.get("contract") if isinstance(state.get("contract"), Mapping) else {}
        expected_action_id = str(state.get("action_id") or "").strip() or None
        expected_source_revision = str(
            state.get("controller_revision") or contract.get("controller_revision") or ""
        ).strip() or None
        expected_runtime_receipt_hash = str(
            state.get("runtime_receipt_hash") or ""
        ).strip() or None
        normalized = validate_operator_outcome_receipt(
            receipt,
            task_id=task_id,
            attempt_id=str(state.get("attempt_id") or ""),
            lifecycle_revision=str(state.get("lifecycle_revision") or ""),
        )
        if normalized.action_id is not None and normalized.action_id != expected_action_id:
            raise ValueError("OPERATOR_OUTCOME_ACTION_ID_MISMATCH")
        if normalized.source_revision is not None and (
            expected_source_revision is None
            or normalized.source_revision != expected_source_revision
        ):
            raise ValueError("OPERATOR_OUTCOME_SOURCE_REVISION_MISMATCH")
        if normalized.runtime_receipt_hash is not None and (
            expected_runtime_receipt_hash is None
            or normalized.runtime_receipt_hash != expected_runtime_receipt_hash
        ):
            raise ValueError("OPERATOR_OUTCOME_RUNTIME_RECEIPT_HASH_MISMATCH")

        def mutate(current: dict[str, Any]) -> None:
            current_contract = (
                current.get("contract")
                if isinstance(current.get("contract"), Mapping)
                else {}
            )
            current_action_id = str(current.get("action_id") or "").strip() or None
            current_source_revision = str(
                current.get("controller_revision")
                or current_contract.get("controller_revision")
                or ""
            ).strip() or None
            current_runtime_receipt_hash = str(
                current.get("runtime_receipt_hash") or ""
            ).strip() or None
            validate_operator_outcome_receipt(
                normalized,
                task_id=task_id,
                attempt_id=str(current.get("attempt_id") or ""),
                lifecycle_revision=str(current.get("lifecycle_revision") or ""),
            )
            if normalized.action_id is not None and normalized.action_id != current_action_id:
                raise ValueError("OPERATOR_OUTCOME_ACTION_ID_MISMATCH")
            if normalized.source_revision is not None and (
                current_source_revision is None
                or normalized.source_revision != current_source_revision
            ):
                raise ValueError("OPERATOR_OUTCOME_SOURCE_REVISION_MISMATCH")
            if normalized.runtime_receipt_hash is not None and (
                current_runtime_receipt_hash is None
                or normalized.runtime_receipt_hash != current_runtime_receipt_hash
            ):
                raise ValueError("OPERATOR_OUTCOME_RUNTIME_RECEIPT_HASH_MISMATCH")
            raw_existing = current.get("operator_outcome_receipts", [])
            if type(raw_existing) is not list or any(
                not isinstance(item, Mapping) for item in raw_existing
            ):
                raise ValueError("OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED")
            existing = list(raw_existing)
            singular = current.get("operator_outcome_receipt")
            if (existing and singular is None) or (
                singular is not None
                and (
                    not isinstance(singular, Mapping)
                    or not existing
                    or dict(singular) != dict(existing[-1])
                )
            ):
                raise ValueError("OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED")
            parsed = {}
            for item in existing:
                try:
                    prior = validate_operator_outcome_receipt(
                        item,
                        task_id=task_id,
                        check_freshness=False,
                    )
                except ValueError as exc:
                    raise ValueError("OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED") from exc
                if prior.receipt_id in parsed:
                    raise ValueError("OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED")
                parsed[prior.receipt_id] = prior
            for prior in parsed.values():
                parent_hash = prior.supersedes_receipt_id
                if parent_hash is not None:
                    parent = parsed.get(parent_hash)
                    if parent is None:
                        raise ValueError("OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_TARGET_MISSING")
                    if parent.task_id != task_id or parent.attempt_id != prior.attempt_id:
                        raise ValueError("OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_ATTEMPT_MISMATCH")
                    if prior.observed_at <= parent.observed_at:
                        raise ValueError("OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_ORDER_INVALID")
            for start in parsed.values():
                seen = set()
                cursor = start
                while cursor.supersedes_receipt_id is not None:
                    parent_hash = cursor.supersedes_receipt_id
                    if parent_hash in seen or parent_hash == start.receipt_id:
                        raise ValueError("OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_CYCLE")
                    seen.add(parent_hash)
                    cursor = parsed.get(parent_hash)
                    if cursor is None:
                        raise ValueError("OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_TARGET_MISSING")
            for item in existing:
                if item.get("idempotency_key") != normalized.idempotency_key:
                    continue
                if item.get("receipt_id") != normalized.receipt_id:
                    raise ValueError("OPERATOR_OUTCOME_IDEMPOTENCY_CONFLICT")
                return
            hashes = {str(item.get("receipt_id")) for item in existing}
            if normalized.supersedes_receipt_id is not None:
                if normalized.supersedes_receipt_id not in hashes:
                    raise ValueError("OPERATOR_OUTCOME_SUPERSESSION_TARGET_MISSING")
                if normalized.supersedes_receipt_id == normalized.receipt_id:
                    raise ValueError("OPERATOR_OUTCOME_SUPERSESSION_CYCLE")
                target = next(
                    item
                    for item in existing
                    if item.get("receipt_id") == normalized.supersedes_receipt_id
                )
                if target.get("task_id") != task_id or target.get("attempt_id") != normalized.attempt_id:
                    raise ValueError("OPERATOR_OUTCOME_SUPERSESSION_ATTEMPT_MISMATCH")
                if normalized.observed_at <= parsed[normalized.supersedes_receipt_id].observed_at:
                    raise ValueError("OPERATOR_OUTCOME_SUPERSESSION_ORDER_INVALID")
                seen = set()
                cursor = target
                while cursor.get("supersedes_receipt_id"):
                    parent = str(cursor["supersedes_receipt_id"])
                    if parent in seen or parent == normalized.receipt_id:
                        raise ValueError("OPERATOR_OUTCOME_SUPERSESSION_CYCLE")
                    seen.add(parent)
                    cursor = next(
                        (item for item in existing if item.get("receipt_id") == parent),
                        {},
                    )
            existing.append(normalized.model_dump(mode="json"))
            current["operator_outcome_receipts"] = existing
            current["operator_outcome_receipt"] = existing[-1]

        result = self._mutate_state(task_id, mutate)
        return dict(result.get("operator_outcome_receipt") or normalized.model_dump(mode="json"))

    def _promotion_authority_error(
        self,
        *,
        contract: Optional[ArchitectTaskContract] = None,
        request: Optional[Mapping[str, Any]] = None,
    ) -> Optional[str]:
        """Return a fail-closed reason when a task cannot become promotable.

        Ephemeral services are test/rehearsal surfaces.  A production-bound
        task (one with a task card or lifecycle identity requirement) must be
        backed by the canonical state root and a durable, existing Controller.
        This prevents a temporary rehearsal receipt from becoming an
        approval/integration authority by accident.
        """
        req = request or {}
        production_bound = bool(
            req.get("task_card_required") or req.get("lifecycle_identity_required")
        )
        if self.ephemeral and production_bound:
            return "EPHEMERAL_PROMOTION_FORBIDDEN: rehearsal state cannot become a promotable Candidate"
        if not production_bound or contract is None:
            return None
        if self.state_dir != self.canonical_state_dir():
            return "CANONICAL_STATE_REQUIRED: production Candidate must use the canonical state root"
        controller = Path(contract.controller_repo_root).expanduser().resolve()
        if not controller.is_dir():
            return f"CONTROLLER_MISSING: {controller}"
        temporary_roots = _temporary_state_roots()
        if any(controller == root or root in controller.parents for root in temporary_roots):
            return f"DURABLE_CONTROLLER_REQUIRED: temporary Controller is not promotable: {controller}"
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=controller,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return f"CONTROLLER_PROBE_FAILED: {exc}"
        if result.returncode != 0 or Path(result.stdout.strip()).resolve() != controller:
            return f"CONTROLLER_NOT_A_REPOSITORY: {controller}"
        try:
            current_revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=controller,
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
        except OSError as exc:
            return f"CONTROLLER_REVISION_PROBE_FAILED: {exc}"
        if contract.controller_revision and current_revision != contract.controller_revision:
            return (
                "CONTROLLER_REVISION_MISMATCH: "
                f"expected {contract.controller_revision}, got {current_revision}"
            )
        return None

    def _reactivate_archived_state(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._state_lock():
            path = self._state_path(task_id)
            if path.exists():
                return self._with_task_action(json.loads(path.read_text(encoding="utf-8")))
            if not self._archive_state_candidates(task_id):
                raise RuntimeError("archived task receipt disappeared before retry")
            return self._write_state_locked(task_id, state)

    def _mutate_state(self, task_id: str, mutator: Callable[[dict[str, Any]], None]) -> Optional[dict[str, Any]]:
        with self._state_lock():
            path = self._state_path(task_id)
            if not path.exists():
                return None
            state = json.loads(path.read_text(encoding="utf-8"))
            mutator(state)
            return self._write_state_locked(task_id, state)

    # Issue #129: the claim is deliberately a subrecord of the existing task
    # receipt.  The state lock above is the sole serialization point.
    @staticmethod
    def _claim_identity(request: Mapping[str, Any]) -> dict[str, Any]:
        admission = request.get("workforce_admission", request.get("admission_binding"))
        preflight = request.get("provider_preflight", request.get("realm_preflight"))
        allowed = request.get("allowed_files", request.get("mutation_domain", []))
        if isinstance(allowed, str):
            allowed = [allowed]
        identity = {
            "repository": str(request.get("repository") or request.get("repo") or "").strip(),
            "issue": str(request.get("issue") or request.get("issue_number") or "").strip(),
            "task_id": str(request.get("task_id") or "").strip(),
            "attempt_id": str(request.get("attempt_id") or "").strip(),
            "action_id": str(request.get("action_id") or "").strip(),
            "worker_id": str(request.get("worker_id") or request.get("worker") or "").strip(),
            "provider": str(request.get("provider") or "").strip(),
            "model": str(request.get("model") or "").strip(),
            "role": str(request.get("role") or request.get("worker_role") or "").strip(),
            "claim_ceiling": str(request.get("claim_ceiling") or "").strip(),
            "base_revision": str(request.get("base_revision") or request.get("target_base_revision") or "").strip(),
            "source_hash": str(request.get("source_hash") or request.get("source_revision") or "").strip(),
            "task_card_path": str(request.get("task_card_path") or "").strip(),
            "allowed_files": sorted({str(item).strip() for item in allowed if str(item).strip()}),
            "admission_identity": hashlib.sha256(json.dumps(_jsonable(admission), sort_keys=True, separators=(",", ":")).encode()).hexdigest() if admission is not None else "",
            "provider_preflight_identity": hashlib.sha256(json.dumps(_jsonable(preflight), sort_keys=True, separators=(",", ":")).encode()).hexdigest() if preflight is not None else "",
        }
        return identity

    @classmethod
    def _claim_hash(cls, identity: Mapping[str, Any]) -> str:
        return hashlib.sha256(json.dumps(_jsonable(identity), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _claim_request(request: Mapping[str, Any]) -> dict[str, Any]:
        identity = SelfHostedTaskService._claim_identity(request)
        return {"identity": identity, "identity_hash": SelfHostedTaskService._claim_hash(identity),
                "claim_id": str(request.get("claim_id") or uuid4()),
                "generation": int(request.get("generation") or 1),
                "fencing_token": str(request.get("fencing_token") or "")}

    @classmethod
    def _validate_claim_record(cls, record: Mapping[str, Any]) -> None:
        if not isinstance(record, Mapping) or not isinstance(record.get("identity"), Mapping) or not record.get("identity"):
            raise RuntimeError("WORK_CLAIM_MALFORMED")
        if not isinstance(record.get("identity_hash"), str) or record.get("identity_hash") != cls._claim_hash(record["identity"]):
            raise RuntimeError("WORK_CLAIM_TAMPERED")
        if not isinstance(record.get("generation"), int) or isinstance(record.get("generation"), bool) or record["generation"] < 1 or not isinstance(record.get("claim_id"), str) or not record["claim_id"]:
            raise RuntimeError("WORK_CLAIM_MALFORMED")

    @classmethod
    def _validate_claim_locked(cls, state: Mapping[str, Any], request: Mapping[str, Any]) -> Mapping[str, Any]:
        record = state.get("work_claim")
        cls._validate_claim_record(record)
        expected = cls._claim_identity(request)
        if record["identity_hash"] != cls._claim_hash(expected):
            raise RuntimeError("WORK_CLAIM_FENCE_MISMATCH")
        expected_fencing_token = f"{record['claim_id']}:{record['generation']}"
        if (
            not isinstance(record.get("fencing_token"), str)
            or record["fencing_token"] != expected_fencing_token
            or not isinstance(request.get("claim_id"), str)
            or request["claim_id"] != record["claim_id"]
            or not isinstance(request.get("generation"), int)
            or isinstance(request.get("generation"), bool)
            or request["generation"] != record["generation"]
            or not isinstance(request.get("fencing_token"), str)
            or request["fencing_token"] != expected_fencing_token
        ):
            raise RuntimeError("WORK_CLAIM_STALE_FENCE")
        return record

    def acquire_work_claim(self, request: Mapping[str, Any]) -> dict[str, Any]:
        candidate = self._claim_request(request)
        task_id = candidate["identity"]["task_id"]
        if not task_id:
            return {"status": "BLOCKED", "reason": "TASK_ID_REQUIRED"}
        with self._state_lock():
            path = self._state_path(task_id)
            if not path.exists():
                return {"status": "BLOCKED", "reason": "TASK_NOT_FOUND"}
            state = json.loads(path.read_text(encoding="utf-8"))
            existing = state.get("work_claim")
            if existing is not None:
                self._validate_claim_record(existing)
                if existing["identity_hash"] == candidate["identity_hash"]:
                    return {"status": "ALREADY_CLAIMED", "claim": existing}
                return {"status": "BLOCKED", "reason": "ALREADY_CLAIMED", "claim": existing}
            candidate["generation"] = 1
            candidate["fencing_token"] = f"{candidate['claim_id']}:{candidate['generation']}"
            candidate["status"] = "CLAIMED"
            candidate["claimed_at"] = _utc_now()
            state["work_claim"] = candidate
            self._write_state_locked(task_id, state)
            return {"status": "CLAIMED", "claim": candidate}

    claim_work = acquire_work_claim

    def validate_work_claim(self, request: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(request.get("task_id") or "")
        with self._state_lock():
            path = self._state_path(task_id)
            if not path.exists():
                raise RuntimeError("WORK_CLAIM_NOT_FOUND")
            state = json.loads(path.read_text(encoding="utf-8"))
            record = self._validate_claim_locked(state, request)
            return {"status": "CLAIMED", "claim": record}

    def release_work_claim(self, request: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(request["task_id"])
        with self._state_lock():
            state = json.loads(self._state_path(task_id).read_text(encoding="utf-8"))
            self._validate_claim_locked(state, request)
            state.pop("work_claim", None)
            self._write_state_locked(task_id, state)
        return {"status": "RELEASED", "task_id": task_id}

    def recover_work_claim(self, request: Mapping[str, Any], *, reason: str = "RECOVERY") -> dict[str, Any]:
        task_id = str(request["task_id"])
        with self._state_lock():
            state = json.loads(self._state_path(task_id).read_text(encoding="utf-8"))
            record = self._validate_claim_locked(state, request)
            generation = int(record["generation"]) + 1
            record["generation"] = generation
            record["fencing_token"] = f"{record['claim_id']}:{generation}"
            record["recovery_reason"] = _bounded_failure_text(reason)
            record["recovered_at"] = _utc_now()
            self._write_state_locked(task_id, state)
            return {"status": "CLAIMED", "claim": record}

    renew_work_claim = validate_work_claim

    def _record_event_append_failure(self, task_id: str, error: Exception) -> None:
        """Persist the state/event reconciliation debt without emitting another event."""
        now = _utc_now()

        def mutate(state: dict[str, Any]) -> None:
            state["event_reconciliation_required"] = True
            state["event_append_failure"] = {
                "status": "BLOCKED",
                "error_type": type(error).__name__,
                "error_sha256": hashlib.sha256(str(error).encode("utf-8")).hexdigest(),
                "at": now,
            }
            state["updated_at"] = now

        self._mutate_state(task_id, mutate)

    def _emit_bound_attempt_transition(
        self, result: Optional[Mapping[str, Any]], task_id: str
    ) -> None:
        try:
            self._emit_attempt_transition(result, task_id)
        except Exception as exc:
            self._record_event_append_failure(task_id, exc)
            raise

    @staticmethod
    def _emit_attempt_transition(result: Optional[Mapping[str, Any]], task_id: str) -> None:
        if not result or not result.get("attempt_id"):
            return
        sequence = NexusEventBus.next_attempt_sequence(
            str(result.get("task_id") or task_id), str(result.get("attempt_id"))
        )
        candidate_refs = tuple(str(value) for value in (
            result.get("candidate_commit_sha"),
            (result.get("promotion_packet") or {}).get("candidate_tree_sha"),
        ) if value)
        evidence_refs = tuple(str(value) for value in (
            result.get("verified_receipt_hash"),
            (result.get("verified_receipt") or {}).get("receipt_ref"),
        ) if value)
        # Persistence/sequence failures are deterministic event blocks.  They
        # must remain visible to the caller; silently dropping them creates a
        # false lifecycle receipt while leaving the lifecycle authority intact.
        request = result.get("request") if isinstance(result.get("request"), Mapping) else {}
        status = str(result.get("status"))
        rejected_states = frozenset({"ATTEMPT_REJECTED", "REJECTED"})
        explicit_type = result.get("continuity_event_type") or request.get("continuity_event_type")
        if explicit_type is not None:
            if not isinstance(explicit_type, str) or not explicit_type.strip():
                raise ValueError("continuity_event_type must be a non-empty string")
            if status in rejected_states and explicit_type != "ATTEMPT_REJECTED":
                raise ValueError("rejected state requires ATTEMPT_REJECTED continuity type")
            continuity_event_type = explicit_type
        else:
            continuity_event_type = (
                "ATTEMPT_REJECTED" if status in rejected_states else "OBSERVATION_RECORDED"
            )

        def continuity_list(name: str, alias: str = "") -> tuple[str, ...]:
            value = result.get(name)
            if value is None and alias:
                value = result.get(alias)
            if value is None:
                value = request.get(name)
            if value is None and alias:
                value = request.get(alias)
            if value is None:
                return ()
            if isinstance(value, str):
                return (value,)
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"{name} must be a list/tuple of non-empty strings")
            if any(not isinstance(item, str) or not item.strip() for item in value):
                raise ValueError(f"{name} must contain non-empty strings")
            return tuple(value)

        NexusEventBus.emit_attempt_transition(build_attempt_transition_event(
            task_id=str(result.get("task_id") or task_id),
            attempt_id=str(result.get("attempt_id")), sequence=sequence,
            state=status, reason=str(result.get("error") or result.get("reason") or ""),
            continuity_event_type=continuity_event_type,
            strategy_delta=str(result.get("strategy_delta") or request.get("strategy_delta") or ""),
            do_not_repeat=continuity_list("do_not_repeat", "rejected_strategies"),
            unresolved_risks=continuity_list("unresolved_risks"),
            unknowns=continuity_list("unknowns"),
            next_action=str(result.get("next_action") or request.get("next_action") or ""),
            claim_ceiling=str(result.get("claim_ceiling") or request.get("claim_ceiling") or ""),
            candidate_refs=candidate_refs, evidence_refs=evidence_refs,
            source_revision=str(result.get("source_revision") or request.get("controller_revision") or "unknown"),
            contract_revision=str(result.get("contract_revision") or request.get("contract_hash") or "unknown"),
        ))

    @staticmethod
    def read_canonical_attempt_events(task_id: str, attempt_id: str) -> list[dict[str, Any]]:
        """Read attempt events from the canonical EventBus log, without mutation."""
        # Read the validated canonical store directly.  The EventBus observer
        # facade intentionally serves best-effort dashboards and swallows
        # integrity failures; continuity recovery must preserve those errors.
        if NexusEventBus._log_store.event_log_path != NexusEventBus._event_log_path:
            NexusEventBus._log_store.event_log_path = NexusEventBus._event_log_path
        records = NexusEventBus._log_store.read_recent(event_type="attempt_transition", limit=10_000)
        selected = []
        for record in records:
            payload = record.get("payload") if isinstance(record, Mapping) else None
            if not isinstance(payload, Mapping):
                raise ValueError("attempt transition payload is missing")
            if payload.get("task_id") == task_id and payload.get("attempt_id") == attempt_id:
                selected.append(dict(record))
        if not selected:
            raise ValueError("attempt continuity stream is empty")
        return selected

    @staticmethod
    def read_canonical_attempt_continuity(task_id: str, attempt_id: str) -> list[Any]:
        """Consume the canonical JSONL attempt log as validated continuity events."""
        return events_from_attempt_records(
            SelfHostedTaskService.read_canonical_attempt_events(task_id, attempt_id),
            task_id=task_id,
            attempt_id=attempt_id,
        )

    @staticmethod
    def _request_hash(request: Mapping[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(dict(request), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def _record_direct_failure(self, task_id: str, blocker: str, error: str = "") -> Optional[dict[str, Any]]:
        """Persist an uncertain Direct/Assisted outcome without allocating a Target."""
        now = _utc_now()

        def mutate(state: dict[str, Any]) -> None:
            if state.get("status") == "DIRECT_COMPLETED":
                return
            action = dict(state.get("canonical_action") or {})
            reconciliation = dict(action.get("reconciliation") or {})
            reconciliation.update({
                "status": "REQUIRED",
                "blocker": blocker,
                "error": error,
                "at": now,
            })
            action["reconciliation"] = reconciliation
            state["canonical_action"] = action
            state["status"] = "DIRECT_RECONCILE_REQUIRED"
            state["error"] = error or blocker
            state["reconciliation_required"] = True
            state["updated_at"] = now
            state.setdefault("status_history", []).append({"status": state["status"], "at": now})

        result = self._mutate_state(task_id, mutate)
        self._emit_bound_attempt_transition(result, task_id)
        return result

    def record_canonical_action_failure(self, task_id: str, blocker: str, error: str = "") -> Optional[dict[str, Any]]:
        """Public observer-safe hook for an Assisted provider/apply failure."""
        return self._record_direct_failure(task_id, blocker, error)

    def _checkpoint(
        self,
        task_id: str,
        status: str,
        values: Optional[Mapping[str, Any]] = None,
        *,
        attempt_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        now = _utc_now()

        def mutate(state: dict[str, Any]) -> None:
            if attempt_id is not None and state.get("attempt_id") != attempt_id:
                raise RuntimeError("task attempt ownership changed")
            previous = state.get("status")
            state["status"] = status
            if values:
                updates = _jsonable(dict(values))
                updates.pop("submitted_at", None)
                state.update(updates)
            state["updated_at"] = now
            state["heartbeat_at"] = now
            history = list(state.get("status_history", []))
            if previous != status:
                history.append({"status": status, "at": now})
            state["status_history"] = history
            submitted_at = _parse_time(state.get("submitted_at"))
            started_at = _parse_time(state.get("worker_started_at"))
            if submitted_at is not None:
                wall_time_ms = max(0, int((time.time() - submitted_at) * 1000))
                worker_wall_time_ms = max(0, int((time.time() - started_at) * 1000)) if started_at is not None else 0
                previous_telemetry = state.get("telemetry") or {}
                executions = state.get("executions") or ([state.get("execution")] if state.get("execution") else [])
                provider_time_ms = sum(int(item.get("wall_time_ms") or 0) for item in executions if isinstance(item, Mapping))
                provider_calls = sum(int(item.get("provider_calls") or 0) for item in executions if isinstance(item, Mapping))
                provider_attempts = sum(
                    int(item.get("provider_attempt_count"))
                    if item.get("provider_attempt_count") is not None
                    else 1
                    for item in executions
                    if isinstance(item, Mapping)
                )
                verified = state.get("verified_receipt") or {}
                verifier_time_ms = sum(int(item.get("wall_time_ms") or 0) for item in verified.get("verifier_evidence") or [] if isinstance(item, Mapping))
                worktree_time_ms = int(previous_telemetry.get("worktree_time_ms") or 0)
                commit_hook_time_ms = int(previous_telemetry.get("commit_hook_time_ms") or 0)
                cleanup_time_ms = int(previous_telemetry.get("cleanup_time_ms") or 0)
                measured_ms = provider_time_ms + verifier_time_ms + worktree_time_ms + commit_hook_time_ms + cleanup_time_ms
                state["telemetry"] = {
                    "wall_time_ms": wall_time_ms,
                    "worker_wall_time_ms": worker_wall_time_ms,
                    "provider_time_ms": provider_time_ms,
                    "provider_calls": provider_calls,
                    "provider_attempts": provider_attempts,
                    "tokens": None,
                    "cost": None,
                    "token_status": "unmeasured",
                    "cost_status": "unmeasured",
                    "savings_claim_allowed": False,
                    "verifier_time_ms": verifier_time_ms,
                    "worktree_time_ms": worktree_time_ms,
                    "commit_hook_time_ms": commit_hook_time_ms,
                    "cleanup_time_ms": cleanup_time_ms,
                    "overhead_ms": max(0, wall_time_ms - measured_ms),
                }
            if status in TERMINAL_STATUSES:
                state["worker_finished_at"] = now
                state["worker_child_pgid"] = None
            for attempt in state.get("attempts") or []:
                if attempt.get("attempt_id") == state.get("attempt_id"):
                    attempt["last_status"] = status
                    attempt["updated_at"] = now
                    if status in TERMINAL_STATUSES or status == "PENDING_HUMAN_APPROVAL":
                        attempt["finished_at"] = now
            lease = state.get("lease") or {}
            if lease:
                state.update({
                    "controller_worktree": (state.get("contract") or {}).get("controller_repo_root"),
                    "controller_status_sha256": lease.get("controller_status_sha256"),
                    "target_worktree": lease.get("target_worktree"),
                    "target_initial_revision": lease.get("initial_head"),
                    "target_branch": lease.get("target_branch"),
                    "target_created_at": state.get("target_created_at") or now,
                })
            execution = state.get("execution") or {}
            if execution:
                state["execution_outcome"] = execution.get("outcome")
            resolution = state.get("attempt_resolution") or {}
            if resolution:
                state["verification_verdict"] = resolution.get("verdict")
            packet = state.get("promotion_packet") or {}
            if packet:
                for field in (
                    "candidate_commit_sha", "candidate_tree_sha",
                    "candidate_state_hash", "verified_receipt_hash",
                ):
                    state[field] = packet.get(field)
            action_id = str(state.get("action_id") or f"action-{state.get('attempt_id') or task_id}")
            promotion_status = str(state.get("promotion_status") or "NOT_CREATED")
            integrated = state.get("status") == "INTEGRATED" or promotion_status == "INTEGRATED"
            runtime_phase = str(state.get("runtime_phase") or "").strip().upper()
            runtime_terminal_state = str(state.get("runtime_terminal_state") or "").strip().upper()
            state["runtime_development_mapping"] = build_runtime_development_mapping(
                task_id=str(state.get("task_id") or task_id),
                attempt_id=str(state.get("attempt_id") or attempt_id or "attempt-unknown"),
                action_id=action_id,
                runtime_phase=runtime_phase,
                runtime_terminal_state=runtime_terminal_state,
                development_status=str(state.get("status") or "UNKNOWN"),
                runtime_success=(
                    runtime_phase == "C" and runtime_terminal_state == "COMPLETE"
                ),
                candidate_status=str(state.get("candidate_status") or promotion_status),
                candidate_accepted=promotion_status in {"APPROVED", "INTEGRATED"},
                integration_status=promotion_status,
                integrated=integrated,
                runtime_receipt_ref=str(state.get("runtime_receipt_ref") or ""),
                development_receipt_ref=str(state.get("verified_receipt_hash") or ""),
            )

        result = self._mutate_state(task_id, mutate)
        self._emit_bound_attempt_transition(result, task_id)
        return result

    def _heartbeat(self, task_id: str, attempt_id: str, stop: threading.Event) -> None:
        while not stop.wait(1.0):
            try:
                self._mutate_state(
                    task_id,
                    lambda state: self._touch_owned_state(state, attempt_id),
                )
            except (RuntimeError, OSError, json.JSONDecodeError):
                return

    @staticmethod
    def _touch_owned_state(state: dict[str, Any], attempt_id: str) -> None:
        if state.get("attempt_id") != attempt_id or state.get("status") in TERMINAL_STATUSES:
            raise RuntimeError("task is no longer owned by this attempt")
        now = _utc_now()
        state["heartbeat_at"] = now
        state["updated_at"] = now

    def build_contract(self, request: Mapping[str, Any]) -> ArchitectTaskContract:
        if "prompt" in request:
            raise ValueError("prompt is not accepted; submit WHAT and WHY")
        dispatch_binding = validate_workforce_dispatch_binding(request)
        if dispatch_binding is not None:
            requested_provider = str(request.get("worker", "auto")).strip().lower()
            if requested_provider not in {"", "auto", dispatch_binding["provider"]}:
                raise RuntimeError("WORKFORCE_ADMISSION_PROVIDER_MISMATCH")
            caller_provider = str(request.get("provider") or "").strip().lower()
            if caller_provider and caller_provider != dispatch_binding["provider"].lower():
                raise RuntimeError("WORKFORCE_ADMISSION_PROVIDER_MISMATCH")
            caller_worker_id = str(request.get("worker_id") or "").strip()
            if caller_worker_id and caller_worker_id != dispatch_binding["worker_id"]:
                raise RuntimeError("WORKFORCE_ADMISSION_WORKER_MISMATCH")
            requested_model = str(request.get("model") or "").strip()
            if requested_model and requested_model != dispatch_binding["model"]:
                raise RuntimeError("WORKFORCE_ADMISSION_MODEL_MISMATCH")
            request = dict(request)
            request.update({
                "worker": dispatch_binding["provider"],
                "provider": dispatch_binding["provider"],
                "model": dispatch_binding["model"],
                "worker_id": dispatch_binding["worker_id"],
                "worker_order": [dispatch_binding["provider"]],
            })
        worker = str(request.get("worker", "codex")).strip().lower()
        requested_worker = worker
        if worker not in SUPPORTED_WORKER_PROVIDERS:
            if worker != "auto":
                raise ValueError(
                    "worker must be one of: auto, " + ", ".join(SUPPORTED_WORKER_PROVIDERS)
                )
        provider_order = request.get("worker_order")
        if provider_order is None:
            provider_order = (
                list(SUPPORTED_WORKER_PROVIDERS)
                if requested_worker == "auto"
                else [worker]
            )
        provider_order = [str(provider).strip().lower() for provider in provider_order]
        if worker == "auto" and not provider_order:
            raise ValueError("worker_order must be non-empty for auto selection")
        if worker == "auto" and (set(provider_order) - set(SUPPORTED_WORKER_PROVIDERS) or len(set(provider_order)) != len(provider_order)):
            raise ValueError("worker_order contains an unknown or duplicate provider")
        if worker == "auto":
            worker = provider_order[0]
        fallback_worker = request.get("fallback_worker", request.get("fallback_provider"))
        if fallback_worker is not None:
            fallback_worker = str(fallback_worker).strip().lower()
            if fallback_worker not in SUPPORTED_WORKER_PROVIDERS:
                raise ValueError(
                    "fallback_worker must be one of: " + ", ".join(SUPPORTED_WORKER_PROVIDERS)
                )
            if fallback_worker == worker:
                raise ValueError("fallback_worker must differ from worker")
            if fallback_worker not in provider_order:
                provider_order.append(fallback_worker)
        what = str(request.get("what", "")).strip()
        why = str(request.get("why", "")).strip()
        if not what or not why:
            raise ValueError("what and why are required")
        task_id = str(request.get("task_id") or f"mcp-{uuid4().hex[:12]}")
        decisions = request.get("architecture_decisions") or [
            {
                "decision_id": "target-boundary",
                "selected_option": "Target-only mutation",
                "rationale": "Preserve Controller immutability during worker execution",
                "rejected_alternatives": ["Controller mutation"],
            }
        ]
        decision_models = [
            item if isinstance(item, ArchitectureDecision) else ArchitectureDecision(**item)
            for item in decisions
        ]
        verifier_commands = [str(item) for item in request.get("verifier_commands", [])]
        protected_contracts = [str(item) for item in request.get("protected_contracts", [])]
        if (
            request.get("worker_candidate_ingress")
            and str(request.get("contract_kind") or "") == ContractKind.OWNER_INLINE.value
        ):
            authority_confirmation = request.get("authority_change_candidate_confirmation", False)
            if not isinstance(authority_confirmation, bool):
                raise RuntimeError("AUTHORITY_CHANGE_CONFIRMATION_INVALID")
            marker_present = "repository-authority-change.v1" in protected_contracts
            if marker_present != authority_confirmation:
                raise RuntimeError("AUTHORITY_CHANGE_CONFIRMATION_MARKER_MISMATCH")
            inline = request.get("owner_inline_contract")
            if not isinstance(inline, Mapping) or inline.get("authority_change_candidate_confirmation", False) is not authority_confirmation:
                raise RuntimeError("AUTHORITY_CHANGE_CONFIRMATION_CONTRACT_MISMATCH")
        authorized_deletions = [str(item) for item in request.get("authorized_deletions", [])]
        base_worktree_root, target_repo_root = resolve_canonical_target_roots(
            task_id=task_id,
            campaign_id=request.get("campaign_id"),
            requested_target_worktree_root=request.get("target_worktree_root"),
            requested_target_repo_root=request.get("target_repo_root"),
        )
        controller_repo_root = request.get("controller_repo_root")
        if not controller_repo_root:
            controller_repo_root = str(Path.cwd().resolve())
        else:
            controller_repo_root = str(Path(controller_repo_root).expanduser().resolve())

        controller_revision = request.get("controller_revision")
        if not controller_revision:
            res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=controller_repo_root, capture_output=True, text=True)
            controller_revision = res.stdout.strip() if res.returncode == 0 else "HEAD"
        else:
            controller_revision = str(controller_revision)

        target_base_revision = request.get("target_base_revision")
        if not target_base_revision:
            target_base_revision = controller_revision
        else:
            target_base_revision = str(target_base_revision)

        raw_collaboration_realm = request.get("collaboration_realm")
        collaboration_realm: Optional[CollaborationExecutionRealm] = None
        if raw_collaboration_realm is not None:
            if not isinstance(raw_collaboration_realm, Mapping):
                raise ValueError("COLLABORATION_REALM_INVALID")
            try:
                collaboration_realm = CollaborationExecutionRealm.model_validate(raw_collaboration_realm)
            except Exception as exc:
                raise ValueError("COLLABORATION_REALM_INVALID") from exc

        return ArchitectTaskContract(
            task_id=task_id,
            objective=what,
            goal=DevelopmentGoal(what=what, why=why),
            architecture_decisions=decision_models,
            acceptance_profile=AcceptanceProfile(
                verifier_commands=verifier_commands,
                protected_contracts=protected_contracts,
                authorized_deletions=authorized_deletions,
                required_evidence=["candidate_state_hash", "controller_unchanged", "verified_candidate_receipt"],
            ),
            human_approval_policy=HumanApprovalPolicy(
                approver_roles=list(request.get("approver_roles", ["James"])),
            ),
            controller_revision=controller_revision,
            target_base_revision=target_base_revision,
            controller_repo_root=controller_repo_root,
            target_repo_root=str(target_repo_root),
            target_worktree_root=str(base_worktree_root),
            allowed_files=list(request["allowed_files"]),
            forbidden_files=list(request.get("forbidden_files", [])),
            authorized_deletions=authorized_deletions,
            verifier_commands=verifier_commands,
            protected_contracts=protected_contracts,
            preferred_provider=worker,
            fallback_provider=fallback_worker or (provider_order[1] if len(provider_order) > 1 else None),
            provider_order=provider_order,
            maximum_provider_calls=len(provider_order) if requested_worker == "auto" else (2 if fallback_worker else 1),
            maximum_replans=0,
            maximum_attempts_per_task=int(request.get("maximum_attempts_per_task", 5) or 5),
            maximum_wall_time_seconds=float(request.get("maximum_wall_time_seconds", 0) or 0),
            maximum_changed_files=int(request.get("maximum_changed_files", 0) or 0),
            maximum_deleted_files=int(request.get("maximum_deleted_files", 0) or 0),
            mutation_mode=MutationMode.WORKING_TREE_ONLY,
            human_approval_required=True,
            collaboration_realm=collaboration_realm,
        )

    @staticmethod
    def _terminal_retry_revision_refresh_allowed(
        existing: Mapping[str, Any],
        request: Mapping[str, Any],
        contract: ArchitectTaskContract,
    ) -> bool:
        previous_request = dict(existing.get("request") or {})
        next_request = _jsonable(dict(request))
        for field in ("controller_revision", "target_base_revision"):
            previous_request.pop(field, None)
            next_request.pop(field, None)
        if previous_request != next_request:
            return False

        previous_contract = existing.get("contract") or {}
        previous_controller = str(previous_contract.get("controller_revision") or "")
        previous_target = str(previous_contract.get("target_base_revision") or "")
        revisions = (
            (previous_controller, contract.controller_revision),
            (previous_target, contract.target_base_revision),
        )
        if not all(old and new for old, new in revisions):
            return False
        if all(old == new for old, new in revisions):
            return False

        controller_root = Path(contract.controller_repo_root).expanduser().resolve()
        return all(
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", old, new],
                cwd=controller_root,
                capture_output=True,
                text=True,
            ).returncode == 0
            for old, new in revisions
        )

    def _contract_from_state(self, state: Mapping[str, Any]) -> ArchitectTaskContract:
        request = state.get("request")
        if isinstance(request, Mapping):
            return self.build_contract(request)
        contract = state.get("contract")
        if not isinstance(contract, Mapping):
            raise RuntimeError("task state is missing its contract")
        return ArchitectTaskContract.model_validate(contract)

    @staticmethod
    def _prompt(contract: ArchitectTaskContract) -> str:
        allowed = ", ".join(contract.allowed_files)
        verifiers = "\n".join(f"- {command}" for command in contract.verifier_commands)
        return (
            f"WHAT: {contract.goal.what}\n"
            f"WHY: {contract.goal.why}\n"
            f"Allowed files: {allowed}\n"
            "Work only in the isolated Target. Do not edit, delete, stage, commit, merge, push, or reset "
            "outside the allowed scope. Run every verifier command below after making the change; if any "
            "verifier fails, diagnose and repair within the allowed files before returning.\n"
            f"Required verifier commands:\n{verifiers}\n"
            "Return a concise summary only after all required verifiers pass."
        )

    def _set_child_pgid(self, task_id: str, attempt_id: str, pgid: Optional[int]) -> None:
        def mutate(state: dict[str, Any]) -> None:
            if state.get("attempt_id") == attempt_id and state.get("status") not in TERMINAL_STATUSES:
                state["worker_child_pgid"] = pgid
                state["updated_at"] = _utc_now()

        self._mutate_state(task_id, mutate)

    def _lease_from_state(self, state: Mapping[str, Any]) -> TargetWorktreeLease:
        raw = state.get("lease")
        if not isinstance(raw, Mapping):
            raise RuntimeError("durable lease evidence is missing")
        return TargetWorktreeLease(**dict(raw))

    def _capture_resumed_candidate(
        self,
        contract: ArchitectTaskContract,
        controller: SelfHostedDevelopmentController,
        lease: TargetWorktreeLease,
        state: Mapping[str, Any],
    ):
        candidate = controller.collect_candidate(contract, lease)
        stored = state.get("candidate") or {}
        if stored.get("candidate_state_hash") and stored["candidate_state_hash"] != candidate.candidate_state_hash:
            raise RuntimeError("candidate state changed during recovery")
        return candidate

    @staticmethod
    def _receipt_from_state(value: Any) -> Optional[WorkerExecutionReceipt]:
        if isinstance(value, WorkerExecutionReceipt):
            return value
        if not isinstance(value, Mapping) or "outcome" not in value:
            return None
        try:
            payload = dict(value)
            payload["argv"] = tuple(payload.get("argv", ()))
            return WorkerExecutionReceipt(**payload)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _escalation_policy(contract: ArchitectTaskContract) -> Optional[WorkerEscalationPolicy]:
        if not contract.preferred_provider or not contract.fallback_provider:
            return None
        return WorkerEscalationPolicy(
            cheap_provider=contract.preferred_provider,
            strong_provider=contract.fallback_provider,
            provider_order=tuple(contract.provider_order or (contract.preferred_provider, contract.fallback_provider)),
        )

    def _select_initial_provider(
        self,
        contract: ArchitectTaskContract,
        *,
        before_preflight: Callable[[str], None],
    ) -> tuple[str, Any]:
        providers = list(contract.provider_order or [str(contract.preferred_provider or "codex")])
        failures: list[str] = []
        for provider in providers:
            before_preflight(provider)
            preflight = self.worker_registry.preflight(provider)
            if preflight.ready:
                return provider, preflight
            failures.append(f"{provider}: {preflight.reason}")
        raise RuntimeError("worker preflight failed: " + "; ".join(failures))

    def _next_ready_provider(
        self,
        policy: WorkerEscalationPolicy,
        attempts: Sequence[WorkerExecutionReceipt],
        *,
        before_preflight: Callable[[str], None],
    ) -> Optional[str]:
        attempted = {attempt.provider for attempt in attempts}
        for provider in policy.provider_order or (policy.strong_provider,):
            if provider in attempted:
                continue
            before_preflight(provider)
            if self.worker_registry.preflight(provider).ready:
                return provider
        return None

    @staticmethod
    def _assert_persisted_workforce_dispatch(
        state: Mapping[str, Any],
        request: Mapping[str, Any],
        binding: Optional[Mapping[str, Any]],
        *,
        active_provider: Optional[str] = None,
    ) -> None:
        if binding is None:
            return
        persisted = state.get("workforce_dispatch")
        if not isinstance(persisted, Mapping):
            raise RuntimeError("WORKFORCE_DISPATCH_STATE_DRIFT")
        original_demands, original_admission = _workforce_dispatch_inputs(request)
        if persisted.get("demands") != _jsonable(original_demands) or persisted.get("admission") != _jsonable(original_admission):
            raise RuntimeError("WORKFORCE_DISPATCH_STATE_DRIFT")
        expected = {
            "selected_worker_id": binding["worker_id"],
            "selected_provider": binding["provider"],
            "selected_model": binding["model"],
            "workforce_policy_hash": binding["policy_hash"],
            "workforce_binding_hash": binding["binding_hash"],
            "workforce_aggregate_binding_hash": binding["aggregate_binding_hash"],
        }
        if any(str(state.get(field) or "") != str(value or "") for field, value in expected.items()):
            raise RuntimeError("WORKFORCE_DISPATCH_STATE_DRIFT")
        expected_envelope = binding.get("canonical_dispatch_envelope")
        persisted_envelope = state.get("canonical_dispatch_envelope")
        if isinstance(expected_envelope, Mapping) or "canonical_dispatch_envelope" in request:
            if not isinstance(expected_envelope, Mapping) or dict(persisted_envelope or {}) != dict(expected_envelope):
                raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_STATE_DRIFT")
            persisted_identity = {
                "task_id": state.get("task_id"),
                "attempt_id": state.get("attempt_id"),
                "task_card_path": state.get("task_card_path"),
                "task_card_hash": state.get("task_card_hash"),
            }
            if any(expected_envelope.get(field) != value for field, value in persisted_identity.items()):
                raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_IDENTITY_DRIFT")
        if active_provider is not None and str(active_provider) != str(binding["provider"]):
            raise RuntimeError("WORKFORCE_DISPATCH_ACTIVE_PROVIDER_DRIFT")

    def _revalidate_tracked_dispatch_task_card(
        self,
        contract: ArchitectTaskContract,
        request: Mapping[str, Any],
        state: Mapping[str, Any],
        binding: Optional[Mapping[str, Any]],
    ) -> None:
        """Re-read the tracked card immediately before provider-side work."""
        if binding is None:
            if _tracked_dispatch_required(request, state):
                raise RuntimeError("WORKFORCE_ADMISSION_BINDING_MISSING")
            return
        envelope = binding.get("canonical_dispatch_envelope")
        if not isinstance(envelope, Mapping):
            raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_MISSING")
        if str(request.get("contract_kind") or "") != ContractKind.TRACKED_TASK_CARD.value:
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: tracked dispatch card required")

        validate_task_card_binding(contract, request, is_ephemeral=self.ephemeral)
        identity = resolve_lifecycle_identity(
            contract,
            request,
            is_ephemeral=self.ephemeral,
        )
        requested_path = str(request.get("task_card_path") or "")
        expected = {
            "task_id": contract.task_id,
            "attempt_id": str(request.get("attempt_id") or ""),
            "task_card_path": requested_path,
            "task_card_hash": str(request.get("task_card_hash") or ""),
        }
        if not all(expected.values()):
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: tracked identity incomplete")
        if any(str(envelope.get(field) or "") != value for field, value in expected.items()):
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: dispatch envelope identity drifted")
        persisted = {
            "task_id": str(state.get("task_id") or ""),
            "attempt_id": str(state.get("attempt_id") or ""),
            "task_card_path": str(state.get("task_card_path") or ""),
            "task_card_hash": str(state.get("task_card_hash") or ""),
        }
        if persisted != expected:
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: persisted card identity drifted")
        if str(state.get("contract_kind") or "") != ContractKind.TRACKED_TASK_CARD.value:
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: persisted tracked contract missing")
        if (
            identity.get("contract_kind") != ContractKind.TRACKED_TASK_CARD.value
            or str(identity.get("task_card_path") or "")
            != str(_resolve_task_card_path(requested_path))
            or str(identity.get("task_card_hash") or "") != expected["task_card_hash"]
        ):
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: tracked card changed after submit")

    def _revalidate_provider_boundary(
        self,
        contract: ArchitectTaskContract,
        request: Mapping[str, Any],
        task_id: str,
        binding: Optional[Mapping[str, Any]],
        *,
        active_provider: Optional[str] = None,
    ) -> None:
        """Re-read all governed identity immediately before provider-side work."""
        state = self._read_state(task_id) or {}
        self._revalidate_tracked_dispatch_task_card(contract, request, state, binding)
        self._assert_persisted_workforce_dispatch(
            state,
            request,
            binding,
            active_provider=active_provider,
        )

    @staticmethod
    def _replace_failed_target(
        manager: WorktreeManager,
        controller: SelfHostedDevelopmentController,
        contract: ArchitectTaskContract,
        lease: TargetWorktreeLease,
        *,
        task_states: Optional[Mapping[str, dict]] = None,
    ) -> TargetWorktreeLease:
        manager.verify_controller_unchanged(
            contract,
            expected_status_sha256=lease.controller_status_sha256,
        )
        target_head = manager._run_git(["rev-parse", "HEAD"], cwd=lease.target_worktree)
        if target_head != lease.initial_head:
            raise RuntimeError("failed worker changed Target HEAD; escalation is blocked")
        manager.cleanup(contract.task_id, force=True)
        prepare_task = controller.prepare_task
        if "task_states" in inspect.signature(prepare_task).parameters:
            return prepare_task(contract, task_states=task_states)
        return prepare_task(contract)

    def _run_default_resumable(
        self,
        contract: ArchitectTaskContract,
        request: Mapping[str, Any],
        update: Callable[[str, dict[str, Any]], None],
        *,
        task_id: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        state = self._read_state(task_id) or {}
        deadline = _task_deadline(contract, state.get("submitted_at"))
        if deadline is not None and time.time() >= deadline:
            raise RuntimeError("WALL_TIME_BUDGET_EXHAUSTED")
        status = str(state.get("status"))
        dispatch_binding = validate_workforce_dispatch_binding(
            request,
            require_binding=_tracked_dispatch_required(request, state),
        )
        self._assert_persisted_workforce_dispatch(state, request, dispatch_binding)
        self._revalidate_tracked_dispatch_task_card(
            contract,
            request,
            state,
            dispatch_binding,
        )
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        controller = SelfHostedDevelopmentController(worktree_manager=manager)
        policy = self._escalation_policy(contract)
        attempts = [
            receipt
            for raw in state.get("executions") or []
            if (receipt := self._receipt_from_state(raw)) is not None
        ]
        maximum_attempts = int(getattr(contract, "maximum_attempts_per_task", 1) or 1)
        if len(state.get("attempts") or ()) > maximum_attempts:
            raise RuntimeError("ATTEMPT_BUDGET_EXHAUSTED")
        is_fast_lane = check_fast_lane_eligible(contract, request)
        fast_lane_values = {
            "execution_lane": "FAST_LANE" if is_fast_lane else "STANDARD",
            "fast_lane_eligible": is_fast_lane,
            "maximum_provider_calls": 1 if is_fast_lane else contract.maximum_provider_calls,
            "maximum_replans": 0 if is_fast_lane else 3,
            "fallback_disabled": is_fast_lane,
        }

        if status == "SUBMITTED":
            self._assert_persisted_workforce_dispatch(state, request, dispatch_binding)
            self._revalidate_tracked_dispatch_task_card(
                contract,
                request,
                state,
                dispatch_binding,
            )
            provider, preflight = self._select_initial_provider(
                contract,
                before_preflight=lambda provider: self._revalidate_provider_boundary(
                    contract,
                    request,
                    task_id,
                    dispatch_binding,
                    active_provider=provider,
                ),
            )
            worktree_started = time.perf_counter()
            # Snapshot durable ownership immediately before leasing.  The
            # manager uses this to distinguish passive retained evidence from
            # a live mutation Target; missing/unknown ownership fails closed.
            task_states = self._workspace_task_states()
            prepare_task = controller.prepare_task
            if "task_states" in inspect.signature(prepare_task).parameters:
                lease = prepare_task(contract, task_states=task_states)
            else:
                # Keep narrow test/double compatibility; the production
                # controller always accepts and forwards the snapshot.
                lease = prepare_task(contract)
            worktree_time_ms = max(0, int((time.perf_counter() - worktree_started) * 1000))
            update(
                "TARGET_LEASED",
                {
                    "lease": lease,
                    "worker_preflight": preflight,
                    "active_provider": provider,
                    "telemetry": {"worktree_time_ms": worktree_time_ms},
                    **fast_lane_values,
                },
            )
            update("WORKER_RUNNING", {"active_provider": provider, **fast_lane_values})
            state = self._read_state(task_id) or {}
            status = "WORKER_RUNNING"
        elif status == "WORKER_ESCALATING":
            if is_fast_lane:
                raise RuntimeError("Fast Lane escalation is forbidden")
            lease = self._lease_from_state(state)
            provider = str(state.get("next_provider") or "")
            if not provider:
                raise RuntimeError("escalation state is missing next_provider")
            self._assert_persisted_workforce_dispatch(
                state, request, dispatch_binding, active_provider=provider
            )
            self._revalidate_tracked_dispatch_task_card(
                contract,
                request,
                state,
                dispatch_binding,
            )
            lease = self._replace_failed_target(
                manager,
                controller,
                contract,
                lease,
                task_states=self._workspace_task_states(),
            )
            self._revalidate_provider_boundary(
                contract,
                request,
                task_id,
                dispatch_binding,
                active_provider=provider,
            )
            preflight = self.worker_registry.preflight(provider)
            if not preflight.ready:
                raise RuntimeError(f"worker preflight failed: {preflight.reason}")
            update(
                "TARGET_LEASED",
                {
                    "lease": lease,
                    "worker_preflight": preflight,
                    "active_provider": provider,
                    "next_provider": None,
                },
            )
            update("WORKER_RUNNING", {"active_provider": provider})
            state = self._read_state(task_id) or {}
            status = "WORKER_RUNNING"
        elif status == "TARGET_LEASED":
            raise RuntimeError("worker lost before execution receipt; recovery is fail-closed")
        else:
            lease = self._lease_from_state(state)

        # Pure contract/verifier validation must complete before the first
        # provider invocation.  This also catches unmatched shlex quotes and
        # malformed manifests without consuming provider budget.
        static_validator = getattr(CandidateVerifier, "validate_static_contract", None)
        if static_validator is not None:
            static_validator(contract, lease.target_worktree)

        execution = state.get("execution")
        while status in {"WORKER_RUNNING", "WORKER_COMPLETED"}:
            if status == "WORKER_RUNNING":
                def on_process_group(pgid: Optional[int]) -> None:
                    self._set_child_pgid(task_id, attempt_id, pgid)

                provider = str(
                    state.get("active_provider")
                    or contract.preferred_provider
                    or "codex"
                )
                self._assert_persisted_workforce_dispatch(
                    state, request, dispatch_binding, active_provider=provider
                )
                self._revalidate_tracked_dispatch_task_card(
                    contract,
                    request,
                    state,
                    dispatch_binding,
                )
                consumed_calls = sum(max(0, int(item.provider_calls or 0)) for item in attempts)
                consumed_attempts = sum(
                    max(0, int(item.provider_attempt_count or 0))
                    for item in attempts
                )
                configured_budget = int(fast_lane_values["maximum_provider_calls"])
                remaining_calls = configured_budget - consumed_calls
                # Provider attempts are a distinct aggregate ceiling from
                # provider calls.  The task-level attempt budget is the
                # durable cap and is intentionally measured across retained
                # execution receipts from every retry/fallback.
                attempt_ceiling = int(
                    getattr(contract, "maximum_attempts_per_task", 1) or 1
                )
                remaining_attempts = attempt_ceiling - consumed_attempts
                if remaining_calls <= 0:
                    raise RuntimeError("maximum_provider_calls aggregate budget exhausted")
                if remaining_attempts <= 0:
                    raise RuntimeError("maximum_provider_attempts aggregate budget exhausted")
                if deadline is not None and time.time() >= deadline:
                    raise RuntimeError("WALL_TIME_BUDGET_EXHAUSTED")
                invoke_contract = contract
                if remaining_calls != configured_budget and hasattr(contract, "model_copy"):
                    invoke_contract = contract.model_copy(update={"maximum_provider_calls": remaining_calls})
                self._revalidate_provider_boundary(
                    contract,
                    request,
                    task_id,
                    dispatch_binding,
                    active_provider=provider,
                )
                configured_timeout = float(request.get("timeout_seconds", 900.0))
                remaining_timeout = (
                    max(0.0, deadline - time.time()) if deadline is not None else configured_timeout
                )
                if remaining_timeout <= 0:
                    raise RuntimeError("WALL_TIME_BUDGET_EXHAUSTED")
                execution_receipt = self.worker_registry.invoke(
                    provider,
                    invoke_contract,
                    lease,
                    prompt=self._prompt(contract),
                    model=(
                        str(
                            (dispatch_binding.get("canonical_dispatch_envelope") or {}).get(
                                "model", dispatch_binding["model"]
                            )
                        )
                        if dispatch_binding is not None
                        else str(request.get("model") or "").strip() or None
                    ),
                    timeout_seconds=min(configured_timeout, remaining_timeout),
                    on_process_group=on_process_group,
                )
                if deadline is not None and time.time() >= deadline:
                    raise RuntimeError("WALL_TIME_BUDGET_EXHAUSTED")
                reported_calls = int(execution_receipt.provider_calls)
                reported_attempts = execution_receipt.provider_attempt_count
                if reported_calls < 0 or reported_calls > remaining_calls:
                    raise RuntimeError("provider execution receipt exceeded aggregate call budget")
                if reported_attempts is not None and (
                    int(reported_attempts) < 0
                    or int(reported_attempts) > remaining_attempts
                ):
                    raise RuntimeError("provider execution receipt exceeded aggregate attempt budget")
                attempts.append(execution_receipt)
                execution = execution_receipt
                update(
                    "WORKER_COMPLETED",
                    {
                        "execution": execution_receipt,
                        "executions": attempts,
                        "active_provider": provider,
                        **fast_lane_values,
                    },
                )
                state = self._read_state(task_id) or {}
                status = "WORKER_COMPLETED"
                continue

            latest = attempts[-1] if attempts else self._receipt_from_state(execution)
            if latest is None:
                raise RuntimeError("worker execution receipt is missing common outcome evidence")
            if latest.outcome == WorkerOutcome.EXECUTION_COMPLETED.value and latest.evidence_complete:
                break

            if is_fast_lane:
                raise RuntimeError(latest.failure_reason or f"Fast Lane provider execution failed with outcome {latest.outcome}; escalation/fallback disabled")

            decision = policy.decide(attempts) if policy else None
            if decision is not None and decision.action in ("VERIFY", "ACCEPT"):
                break
            if decision is None or decision.action != "ESCALATE" or not decision.next_provider:
                raise RuntimeError(
                    latest.failure_reason or f"worker execution did not complete: {latest.outcome}"
                )
            if policy is None:
                raise RuntimeError("worker escalation policy is missing")
            next_provider = self._next_ready_provider(
                policy,
                attempts,
                before_preflight=lambda provider: self._revalidate_provider_boundary(
                    contract,
                    request,
                    task_id,
                    dispatch_binding,
                    active_provider=provider,
                ),
            )
            if not next_provider:
                raise RuntimeError("no unattempted ready provider remains for escalation")
            update(
                "WORKER_ESCALATING",
                {
                    "executions": attempts,
                    "next_provider": next_provider,
                    "escalation_reason": decision.reason,
                    "fallback_lineage": list(state.get("fallback_lineage") or []) + [{
                        "from_provider": str(latest.provider),
                        "to_provider": next_provider,
                        "reason": decision.reason,
                        "admission_binding_hash": (
                            dispatch_binding.get("binding_hash") if dispatch_binding else None
                        ),
                    }],
                },
            )
            self._revalidate_provider_boundary(
                contract,
                request,
                task_id,
                dispatch_binding,
                active_provider=next_provider,
            )
            lease = self._replace_failed_target(
                manager,
                controller,
                contract,
                lease,
                task_states=self._workspace_task_states(),
            )
            self._revalidate_provider_boundary(
                contract,
                request,
                task_id,
                dispatch_binding,
                active_provider=next_provider,
            )
            preflight = self.worker_registry.preflight(next_provider)
            if not preflight.ready:
                raise RuntimeError(f"worker preflight failed: {preflight.reason}")
            update(
                "TARGET_LEASED",
                {
                    "lease": lease,
                    "worker_preflight": preflight,
                    "active_provider": next_provider,
                    "next_provider": None,
                },
            )
            update("WORKER_RUNNING", {"active_provider": next_provider})
            state = self._read_state(task_id) or {}
            status = "WORKER_RUNNING"

        if status == "WORKER_COMPLETED":
            candidate = self._capture_resumed_candidate(contract, controller, lease, state)
            update("CANDIDATE_CAPTURED", {"candidate": candidate})
            state = self._read_state(task_id) or {}
            status = "CANDIDATE_CAPTURED"
        else:
            candidate = self._capture_resumed_candidate(contract, controller, lease, state)

        verified = CandidateVerifier(manager).verify(
            contract,
            lease,
            candidate,
            protected_paths=request.get("protected_paths") or {},
        )
        latest_execution = attempts[-1] if attempts else self._receipt_from_state(execution)
        if latest_execution is None:
            raise RuntimeError("worker execution receipt is missing for attempt resolution")
        resolution = resolve_attempt(latest_execution, candidate, verified)

        update("VERIFIED", {
            "verified_receipt": verified,
            "attempt_resolution": resolution,
        })

        if resolution.verdict != AttemptResolutionVerdict.PROVEN.value:
            reasons = ", ".join(resolution.failure_reasons) or f"verdict is {resolution.verdict}"
            raise RuntimeError(f"candidate verification failed: {reasons}")

        authority_error = self._promotion_authority_error(
            contract=contract,
            request=request,
        )
        if authority_error:
            cleanup = manager.cleanup_terminal_target(contract, lease)
            cleanup_ok = cleanup.decision in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
            terminal_status = (
                "REHEARSAL_VERIFIED"
                if self.ephemeral and cleanup_ok
                else "RETAINED_FOR_REVIEW"
                if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES"
                else "FINAL_BLOCK"
            )
            update(terminal_status, {
                "error": authority_error,
                "candidate_status": "REHEARSAL_VERIFIED" if self.ephemeral and cleanup_ok else terminal_status,
                "promotion_status": "NOT_CREATED",
                "promotion_eligible": False,
                "verification_verdict": "PROVEN" if self.ephemeral and cleanup_ok else "FAILED",
                "verified_receipt": verified,
                "attempt_resolution": resolution,
                "cleanup_decision": cleanup.decision,
                "cleanup_blocker": cleanup.blocker,
                "cleanup_performed": cleanup.performed,
                "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                "cleanup_eligible": cleanup.eligible,
                "terminal_status": terminal_status,
                "state_retention_status": "TERMINAL",
                "archive_eligible": False,
            })
            return {
                "execution": execution,
                "candidate": candidate,
                "verified_receipt": verified,
                "attempt_resolution": resolution,
                "candidate_status": "REHEARSAL_VERIFIED" if self.ephemeral and cleanup_ok else terminal_status,
                "promotion_status": "NOT_CREATED",
                "promotion_eligible": False,
                "cleanup_decision": cleanup.decision,
                "cleanup_performed": cleanup.performed,
                "terminal_status": terminal_status,
                "error": authority_error,
            }

        commit_started = time.perf_counter()
        packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)
        commit_hook_time_ms = max(0, int((time.perf_counter() - commit_started) * 1000))
        candidate_values = {
            "execution": execution,
            "candidate": candidate,
            "verified_receipt": verified,
            "attempt_resolution": resolution,
            "promotion_packet": packet,
            "promotion_status": packet.promotion_status,
            "candidate_commit_created": packet.candidate_commit_created,
            "public_claim_allowed": packet.public_claim_allowed,
            "production_ready": packet.production_ready,
            "merge_performed": packet.merge_performed,
            "push_performed": packet.push_performed,
            "telemetry": {"commit_hook_time_ms": commit_hook_time_ms},
        }
        update("CANDIDATE_COMMITTED", candidate_values)
        try:
            candidate_ref = manager.protect_candidate(contract, lease, packet.candidate_commit_sha)
            update("CANDIDATE_REF_PROTECTED", {"candidate_ref": candidate_ref})
        except Exception as exc:
            update("RETAINED_FOR_REVIEW", {
                "error": f"candidate ref protection failed: {exc}",
                "promotion_status": "NOT_CREATED",
                "candidate_status": "RETAINED_FOR_REVIEW",
                "terminal_status": "RETAINED_FOR_REVIEW",
                "state_retention_status": "ACTIVE",
                "recovery_action": "recover_retained_candidate",
            })
            raise RuntimeError(f"candidate ref protection failed: {exc}")
        cleanup_started = time.perf_counter()
        cleanup = manager.cleanup_terminal_target(
            contract,
            lease,
            candidate_commit=packet.candidate_commit_sha,
            candidate_ref=candidate_ref,
        )
        cleanup_time_ms = max(0, int((time.perf_counter() - cleanup_started) * 1000))
        if cleanup.decision != "REMOVED":
            raise RuntimeError(f"candidate Target cleanup failed: {cleanup.decision}")
        update("TARGET_CLEANED", {
            "cleanup_eligible": cleanup.eligible,
            "cleanup_decision": cleanup.decision,
            "cleanup_blocker": cleanup.blocker,
            "cleanup_performed": cleanup.performed,
            "cleanup_performed_at": _utc_now(),
            "telemetry": {"cleanup_time_ms": cleanup_time_ms},
        })
        result = {
            **candidate_values,
            "candidate_ref": candidate_ref,
            "candidate_status": "PENDING_HUMAN_APPROVAL",
            "cleanup_decision": cleanup.decision,
            "cleanup_blocker": cleanup.blocker,
            "cleanup_performed": cleanup.performed,
            "cleanup_performed_at": _utc_now(),
            "terminal_status": "PENDING_HUMAN_APPROVAL",
            "cleanup_eligible": cleanup.eligible,
            "state_retention_status": "ACTIVE",
            "archive_eligible": False,
        }
        return result

    def _run_default(self, contract, request, update):
        return self._run_default_resumable(
            contract,
            request,
            update,
            task_id=contract.task_id,
            attempt_id=str((self._read_state(contract.task_id) or {}).get("attempt_id", "")),
        )

    def _run_owned_task(self, task_id: str, attempt_id: str) -> None:
        state = self._read_state(task_id)
        if state is None or state.get("attempt_id") != attempt_id:
            return
        owner_pid = os.getpid()
        if state.get("worker_pid") not in (None, owner_pid):
            return
        stop = threading.Event()
        heartbeat = threading.Thread(target=self._heartbeat, args=(task_id, attempt_id, stop), daemon=True)
        heartbeat.start()

        def update(status: str, values: dict[str, Any]) -> None:
            if self._custom_runner is not None:
                values = self._bound_custom_runner_values(values)
            self._checkpoint(task_id, status, values, attempt_id=attempt_id)

        try:
            contract = self.build_contract(state["request"])
            if self._custom_runner is None:
                result = self._run_default_resumable(
                    contract,
                    state["request"],
                    update,
                    task_id=task_id,
                    attempt_id=attempt_id,
                )
            else:
                result = self._custom_runner(contract, state["request"], update)
                result = self._bound_custom_runner_values(result)
            current = self._read_state(task_id) or {}
            if current.get("status") not in TERMINAL_STATUSES:
                final_status = "PENDING_HUMAN_APPROVAL" if result.get("promotion_status") == "PENDING_HUMAN_APPROVAL" else "CANDIDATE_COMMITTED"
                self._checkpoint(task_id, final_status, result, attempt_id=attempt_id)
        except Exception as exc:
            self._terminate_owned_processes(task_id, exclude_pid=owner_pid)
            current = self._read_state(task_id) or {}
            verified_rcpt = current.get("verified_receipt") or {}
            attempt_res = current.get("attempt_resolution") or {}
            is_verified = bool(verified_rcpt.get("verified")) and attempt_res.get("verdict") == "PROVEN"

            if is_verified:
                self._checkpoint(
                    task_id,
                    "RETAINED_FOR_REVIEW",
                    {
                        "error": str(exc),
                        "promotion_status": "NOT_CREATED",
                        "terminal_status": "RETAINED_FOR_REVIEW",
                        "state_retention_status": "ACTIVE",
                        "recovery_action": "recover_verified_uncommitted_candidate",
                        "cleanup_eligible": False,
                        "cleanup_performed": False,
                        "cleanup_decision": "PRESERVED_FOR_REVIEW",
                    },
                    attempt_id=attempt_id,
                )
            else:
                cleanup_values: dict[str, Any] = {
                    "cleanup_decision": "ALREADY_REMOVED",
                    "cleanup_blocker": None,
                    "cleanup_performed": False,
                    "terminal_status": "FINAL_BLOCK",
                    "state_retention_status": "TERMINAL",
                }
                if current.get("lease"):
                    try:
                        contract = self.build_contract(current["request"])
                        lease = self._lease_from_state(current)
                        manager = WorktreeManager(root_dir=contract.target_worktree_root)
                        cleanup = manager.cleanup_terminal_target(contract, lease)
                        cleanup_values.update({
                            "cleanup_decision": cleanup.decision,
                            "cleanup_blocker": cleanup.blocker,
                            "cleanup_performed": cleanup.performed,
                            "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                        })
                        cleanup_values["cleanup_eligible"] = cleanup.eligible
                        if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES":
                            cleanup_values["terminal_status"] = "RETAINED_FOR_REVIEW"
                            try:
                                salvage = manager.create_salvage_snapshot(contract, lease, attempt_id)
                                salvage_commit = str(salvage.get("salvage_commit_sha", "") or "")
                                salvage_ref = str(salvage.get("salvage_ref", "") or "")
                                cleanup = manager.cleanup_terminal_target(
                                    contract, lease,
                                    salvage_commit=salvage_commit,
                                    salvage_ref=salvage_ref,
                                )
                                cleanup_values.update({
                                    "cleanup_decision": cleanup.decision,
                                    "cleanup_blocker": cleanup.blocker,
                                    "cleanup_performed": cleanup.performed,
                                    "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                                    **salvage,
                                })
                                if cleanup.decision in {"REMOVED", "ALREADY_REMOVED"} and salvage_commit and salvage_ref:
                                    try:
                                        restore_result = manager.restore_task_branch_for_retry(
                                            contract, lease, salvage_commit, salvage_ref,
                                        )
                                        cleanup_values.update({
                                            "task_branch_restore_decision": restore_result["decision"],
                                            "task_branch_restored_to": restore_result["restored_to"],
                                            "task_branch_restore_performed": True,
                                            "task_branch_restore_verified": True,
                                            "terminal_status": "FINAL_BLOCK",
                                            "state_retention_status": "TERMINAL",
                                        })
                                    except Exception as restore_exc:
                                        cleanup_values.update({
                                            "task_branch_restore_decision": "RESTORE_BLOCKED",
                                            "task_branch_restore_performed": False,
                                            "task_branch_restore_verified": False,
                                            "terminal_status": "RETAINED_FOR_REVIEW",
                                        })
                            except Exception as salvage_exc:
                                cleanup_values.update({
                                    "cleanup_decision": "CLEANUP_BLOCKED",
                                    "cleanup_blocker": str(salvage_exc),
                                    "cleanup_performed": False,
                                    "cleanup_eligible": False,
                                })
                    except Exception as cleanup_exc:
                        cleanup_values.update({
                            "cleanup_decision": "CLEANUP_BLOCKED",
                            "cleanup_blocker": str(cleanup_exc),
                        })
                self._checkpoint(
                    task_id,
                    str(cleanup_values["terminal_status"]),
                    {"error": str(exc), "promotion_status": "NOT_CREATED", **cleanup_values},
                    attempt_id=attempt_id,
                )
        finally:
            stop.set()
            heartbeat.join(timeout=2.0)

    def _wait_for_owner(self, task_id: str, attempt_id: str, pid: int) -> bool:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            state = self._read_state(task_id)
            if state is None or state.get("attempt_id") != attempt_id:
                return False
            if state.get("worker_pid") == pid:
                return True
            time.sleep(0.05)
        return False

    def _launch_worker(self, task_id: str, attempt_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None or state.get("attempt_id") != attempt_id:
            return state
        if state.get("worker_pid") and self._pid_alive(int(state["worker_pid"])):
            return state
        if self._custom_runner is not None:
            thread = threading.Thread(target=self._run_owned_task, args=(task_id, attempt_id), daemon=True)
            self._threads[task_id] = thread
            self._mutate_state(
                task_id,
                lambda current: current.update({
                    "worker_pid": os.getpid(),
                    "worker_pgid": os.getpgrp(),
                    "worker_mode": "thread",
                    "worker_started_at": _utc_now(),
                    "heartbeat_at": _utc_now(),
                }),
            )
            thread.start()
            return self._read_state(task_id)
        command = [
            sys.executable,
            "-m",
            "nexus.orchestrator.self_hosted_task_worker",
            "--state-dir",
            str(self.state_dir),
            "--task-id",
            task_id,
            "--attempt-id",
            attempt_id,
        ]
        env = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
        process = subprocess.Popen(
            command,
            cwd=source_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pgid = os.getpgid(process.pid)
        return self._mutate_state(
            task_id,
            lambda current: current.update({
                "worker_pid": process.pid,
                "worker_pgid": pgid,
                "worker_mode": "process",
                "worker_started_at": _utc_now(),
                "heartbeat_at": _utc_now(),
            }),
        )

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except PermissionError:
            return True
        except (OSError, ProcessLookupError):
            return False
        return True

    def _terminate_owned_processes(self, task_id: str, *, exclude_pid: Optional[int] = None) -> None:
        state = self._read_state(task_id) or {}
        current_pgid = os.getpgrp()
        for raw_pgid in (state.get("worker_child_pgid"), state.get("worker_pgid")):
            if not raw_pgid:
                continue
            pgid = int(raw_pgid)
            if pgid in {current_pgid, exclude_pid}:
                continue
            try:
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.05)
                os.killpg(pgid, signal.SIGKILL)
            except (PermissionError, ProcessLookupError):
                continue

    def _reconcile_direct_action(self, task_id: str) -> Optional[dict[str, Any]]:
        """Classify an interrupted canonical action without replaying it."""
        state = self._read_state(task_id)
        if state is None:
            return None
        if state.get("status") == "DIRECT_INTENT_RECORDED":
            return state
        request = state.get("request") or {}
        controller_raw = request.get("controller_repo_root") or state.get("controller_worktree")
        controller = Path(str(controller_raw or CANONICAL_SOURCE_ROOT)).expanduser().resolve()
        base = str(request.get("controller_revision") or state.get("controller_revision") or "")
        observed: dict[str, Any] = {
            "controller_repo_root": str(controller),
            "expected_head": base,
            "current_head": None,
            "dirty": None,
            "commits_since_base": [],
            "working_tree_changes": [],
        }
        try:
            observed["current_head"] = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=controller, capture_output=True, text=True, check=False,
            ).stdout.strip()
            observed["dirty"] = bool(subprocess.run(
                ["git", "status", "--porcelain=v1"], cwd=controller, capture_output=True, text=True, check=False,
            ).stdout.strip())
            if len(base) == 40:
                observed["commits_since_base"] = subprocess.run(
                    ["git", "diff", "--name-only", f"{base}..HEAD"], cwd=controller,
                    capture_output=True, text=True, check=False,
                ).stdout.splitlines()
            observed["working_tree_changes"] = subprocess.run(
                ["git", "diff", "--name-only"], cwd=controller, capture_output=True, text=True, check=False,
            ).stdout.splitlines()
        except OSError as exc:
            observed["probe_error"] = str(exc)
        return self._record_direct_failure(
            task_id,
            "UNKNOWN_REQUIRES_RECONCILE",
            json.dumps(observed, sort_keys=True, separators=(",", ":")),
        )

    def _reconcile_direct_failure(self, task_id: str) -> Optional[dict[str, Any]]:
        """Close a no-mutation Direct failure without replaying its action."""
        state = self._read_state(task_id)
        if state is None:
            return None
        if state.get("status") != "DIRECT_RECONCILE_REQUIRED":
            return state
        request = state.get("request") if isinstance(state.get("request"), Mapping) else {}
        controller = Path(
            str(request.get("controller_repo_root") or state.get("controller_worktree") or CANONICAL_SOURCE_ROOT)
        ).expanduser().resolve()
        expected_head = str(request.get("controller_revision") or state.get("controller_revision") or "").strip()
        allowed = {str(path).rstrip("/") for path in request.get("allowed_files") or () if str(path).strip()}
        observed: dict[str, Any] = {
            "controller_repo_root": str(controller),
            "expected_head": expected_head,
            "current_head": None,
            "expected_head_is_ancestor": False,
            "commits_since_base": [],
            "working_tree_changes": [],
            "staged_changes": [],
            "allowed_paths": sorted(allowed),
            "target_created": bool(state.get("target_worktree") or state.get("lease")),
            "candidate_created": bool(state.get("candidate_ref") or state.get("candidate_commit_sha") or state.get("promotion_packet")),
        }
        probe_error = ""
        try:
            observed["current_head"] = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=controller, capture_output=True, text=True, check=False,
            ).stdout.strip()
            if len(expected_head) == 40 and observed["current_head"]:
                ancestor = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", expected_head, str(observed["current_head"])],
                    cwd=controller, capture_output=True, text=True, check=False,
                )
                observed["expected_head_is_ancestor"] = ancestor.returncode == 0
                if observed["expected_head_is_ancestor"]:
                    observed["commits_since_base"] = subprocess.run(
                        ["git", "diff", "--name-only", f"{expected_head}..HEAD"],
                        cwd=controller, capture_output=True, text=True, check=False,
                    ).stdout.splitlines()
            observed["working_tree_changes"] = subprocess.run(
                ["git", "diff", "--name-only"], cwd=controller, capture_output=True, text=True, check=False,
            ).stdout.splitlines()
            observed["staged_changes"] = subprocess.run(
                ["git", "diff", "--cached", "--name-only"], cwd=controller, capture_output=True, text=True, check=False,
            ).stdout.splitlines()
        except OSError as exc:
            probe_error = str(exc)
            observed["probe_error"] = probe_error

        touched = {
            str(path)
            for path in (
                list(observed.get("commits_since_base") or [])
                + list(observed.get("working_tree_changes") or [])
                + list(observed.get("staged_changes") or [])
            )
        }
        allowed_touched = sorted(
            path
            for path in touched
            if any(path == boundary or boundary.endswith("/") and path.startswith(boundary) for boundary in allowed)
        )
        observed["allowed_paths_touched"] = allowed_touched
        safe_no_mutation = bool(
            not probe_error
            and len(expected_head) == 40
            and bool(observed.get("current_head"))
            and observed.get("expected_head_is_ancestor") is True
            and not observed.get("target_created")
            and not observed.get("candidate_created")
            and not allowed_touched
        )
        action = dict(state.get("canonical_action") or {})
        reconciliation = dict(action.get("reconciliation") or {})
        now = _utc_now()
        if safe_no_mutation:
            reconciliation.update({
                "status": "RECONCILED",
                "decision": "NO_MUTATION_OBSERVED",
                "evidence": observed,
                "reconciled_at": now,
            })
            action["reconciliation"] = reconciliation
            return self._checkpoint(
                task_id,
                "FINAL_BLOCK",
                {
                    "canonical_action": action,
                    "reconciliation_status": "RECONCILED",
                    "reconciliation_decision": "NO_MUTATION_OBSERVED",
                    "reconciliation_evidence": observed,
                    "reconciliation_required": False,
                    "cleanup_decision": "ALREADY_REMOVED",
                    "cleanup_eligible": True,
                    "cleanup_performed": False,
                    "promotion_status": "NOT_CREATED",
                    "terminal_status": "FINAL_BLOCK",
                    "state_retention_status": "TERMINAL",
                    "archive_eligible": True,
                },
                attempt_id=state.get("attempt_id"),
            )

        reconciliation.update({
            "status": "REQUIRED",
            "decision": "RETAINED_FOR_REVIEW",
            "evidence": observed,
            "reconciled_at": now,
        })
        action["reconciliation"] = reconciliation
        return self._checkpoint(
            task_id,
            "DIRECT_RECONCILE_REQUIRED",
            {
                "canonical_action": action,
                "reconciliation_status": "REQUIRED",
                "reconciliation_decision": "RETAINED_FOR_REVIEW",
                "reconciliation_evidence": observed,
                "reconciliation_required": True,
            },
            attempt_id=state.get("attempt_id"),
        )

    @staticmethod
    def _projected_pre_apply_recovery_evidence(
        state: Mapping[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Return bounded evidence for an exact lost pre-apply projection.

        Older reconciliation projected a non-applied integration failure to
        FINAL_BLOCK/NOT_CREATED while retaining the original PRE_APPLY packet.
        Only that exact, fully bound projection may be restored to the native
        pre-apply status for a fresh closure rebind.
        """
        if (
            state.get("status") != "FINAL_BLOCK"
            or state.get("promotion_status") != "NOT_CREATED"
            or state.get("terminal_status") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("final_disposition") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("integration_status") != "NOT_APPLIED"
            or state.get("merge_performed")
            or state.get("integration_result_sha")
            or state.get("integration_receipt")
        ):
            return None
        execution = state.get("integration_execution")
        closure = state.get("integration_closure_binding")
        grant = state.get("integration_approval_grant")
        acceptance = state.get("external_acceptance")
        preview = state.get("integration_preview")
        authorization = state.get("integration_authorization")
        packet = state.get("promotion_packet")
        approved = state.get("approved_binding")
        if not all(
            isinstance(value, Mapping) and bool(value)
            for value in (
                execution,
                closure,
                grant,
                acceptance,
                preview,
                authorization,
                packet,
                approved,
            )
        ):
            return None
        if (
            execution.get("stage") != "PRE_APPLY"
            or execution.get("merge_performed") is not False
            or execution.get("post_apply_verified") is not False
            or execution.get("branch_head_before")
            != execution.get("branch_head_after")
            or not closure.get("binding_hash")
            or not grant.get("approval_id")
            or not grant.get("consumed_at")
        ):
            return None
        identity = {
            "task_id": str(state.get("task_id") or ""),
            "attempt_id": str(state.get("attempt_id") or ""),
            "candidate_commit_sha": str(packet.get("candidate_commit_sha") or ""),
            "candidate_tree_sha": str(packet.get("candidate_tree_sha") or ""),
            "candidate_state_hash": str(packet.get("candidate_state_hash") or ""),
            "verified_receipt_hash": str(packet.get("verified_receipt_hash") or ""),
        }
        if not identity["task_id"] or not identity["attempt_id"] or any(
            not identity[key]
            for key in (
                "candidate_commit_sha",
                "candidate_tree_sha",
                "candidate_state_hash",
                "verified_receipt_hash",
            )
        ):
            return None
        status_history = state.get("status_history")
        if (
            not isinstance(status_history, list)
            or len(status_history) < 2
            or not all(isinstance(item, Mapping) for item in status_history[-2:])
            or [item.get("status") for item in status_history[-2:]]
            != ["INTEGRATION_FAILED_PRE_APPLY", "FINAL_BLOCK"]
            or not str(state.get("integration_error") or "").strip()
        ):
            return None
        for key, expected in identity.items():
            if key in closure and str(closure.get(key) or "") != expected:
                return None
            if key.startswith("candidate_") or key == "verified_receipt_hash":
                if str(approved.get(key) or "") != expected:
                    return None
        if str(execution.get("candidate_commit_sha") or identity["candidate_commit_sha"]) != identity["candidate_commit_sha"]:
            return None
        acceptance_hash = str(closure.get("acceptance_receipt_hash") or "")
        authorization_hash = str(closure.get("authorization_hash") or "")
        if (
            str(grant.get("bound_task_id") or "") != identity["task_id"]
            or str(grant.get("bound_attempt_id") or "") != identity["attempt_id"]
            or str(grant.get("bound_action_type") or "")
            != LifecycleActionType.CANDIDATE_INTEGRATE.value
            or str(acceptance.get("task_id") or "") != identity["task_id"]
            or str(acceptance.get("attempt_id") or "") != identity["attempt_id"]
            or str(acceptance.get("candidate_commit") or "")
            != identity["candidate_commit_sha"]
            or acceptance.get("passed") is not True
            or str(acceptance.get("receipt_hash") or "") != acceptance_hash
            or str(preview.get("task_id") or "") != identity["task_id"]
            or str(preview.get("candidate_commit") or "")
            != identity["candidate_commit_sha"]
            or str(preview.get("acceptance_receipt_hash") or "") != acceptance_hash
            or str(authorization.get("task_id") or "") != identity["task_id"]
            or str(authorization.get("attempt_id") or "") != identity["attempt_id"]
            or str(authorization.get("candidate_commit") or "")
            != identity["candidate_commit_sha"]
            or str(authorization.get("candidate_tree_sha") or "")
            != identity["candidate_tree_sha"]
            or str(authorization.get("candidate_state_hash") or "")
            != identity["candidate_state_hash"]
            or str(authorization.get("candidate_receipt_hash") or "")
            != identity["verified_receipt_hash"]
            or str(authorization.get("acceptance_receipt_hash") or "")
            != acceptance_hash
            or str(authorization.get("authorization_hash") or "")
            != authorization_hash
        ):
            return None
        for key, expected in {
            "candidate_commit_sha": identity["candidate_commit_sha"],
            "candidate_tree_sha": identity["candidate_tree_sha"],
            "candidate_state_hash": identity["candidate_state_hash"],
            "verified_receipt_hash": identity["verified_receipt_hash"],
            "acceptance_receipt_hash": acceptance_hash,
        }.items():
            if str(grant.get(key) or "") != expected:
                return None
        projection = {
            **identity,
            "closure_binding_hash": str(closure.get("binding_hash")),
            "integration_approval_id": str(grant.get("approval_id")),
            "integration_execution_sha256": hashlib.sha256(
                json.dumps(
                    _jsonable(dict(execution)),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode()
            ).hexdigest(),
        }
        projection["projection_sha256"] = hashlib.sha256(
            json.dumps(
                projection,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        return projection

    def _reconcile_projected_pre_apply_failure(
        self,
        task_id: str,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        now = _utc_now()

        def mutate(current: dict[str, Any]) -> None:
            current_evidence = self._projected_pre_apply_recovery_evidence(current)
            if current_evidence is None or dict(current_evidence) != dict(evidence):
                raise RuntimeError("PRE_APPLY_RECONCILIATION_CONCURRENCY_DRIFT")
            history = current.get("integration_reconciliation_history")
            if "integration_reconciliation_history" in current and not isinstance(history, list):
                raise RuntimeError("PRE_APPLY_RECONCILIATION_HISTORY_MALFORMED")
            if history is None:
                history = []
                current["integration_reconciliation_history"] = history
            if history and history[-1].get("projection_sha256") == evidence.get("projection_sha256"):
                return
            history.append({
                "schema": "nexus.pre_apply_reconciliation.v1",
                **_jsonable(dict(evidence)),
                "reconciled_at": now,
                "decision": "RESTORE_NATIVE_PRE_APPLY_STATUS",
            })
            current["status"] = "INTEGRATION_FAILED_PRE_APPLY"
            current["promotion_status"] = "INTEGRATION_FAILED_PRE_APPLY"
            current["terminal_status"] = "INTEGRATION_FAILED_PRE_APPLY"
            current["final_disposition"] = "INTEGRATION_FAILED_PRE_APPLY"
            current["reconciliation_status"] = "RECONCILED"
            current["reconciliation_decision"] = "RESTORE_NATIVE_PRE_APPLY_STATUS"
            current["state_retention_status"] = "ACTIVE"
            current["archive_eligible"] = False
            current["cleanup_eligible"] = False
            status_history = current.get("status_history")
            if not isinstance(status_history, list):
                raise RuntimeError("PRE_APPLY_RECONCILIATION_STATUS_HISTORY_MALFORMED")
            status_history.append({
                "at": now,
                "status": "INTEGRATION_FAILED_PRE_APPLY",
                "reason": "projected_pre_apply_reconciled",
            })
            current["updated_at"] = now

        persisted = self._mutate_state(task_id, mutate)
        if persisted is None:
            raise KeyError(f"unknown task_id: {task_id}")
        return persisted

    def reconcile_task(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None:
            return state
        if state.get("state_valid") is False:
            return state
        if state.get("status") == "DIRECT_RECONCILE_REQUIRED":
            return self._reconcile_direct_failure(task_id)
        if state.get("status") in {"DIRECT_STARTED", "DIRECT_APPLIED", "DIRECT_VERIFIED", "DIRECT_COMMITTED"}:
            return self._reconcile_direct_action(task_id)
        projected_pre_apply = self._projected_pre_apply_recovery_evidence(state)
        if projected_pre_apply is not None:
            return self._reconcile_projected_pre_apply_failure(
                task_id,
                projected_pre_apply,
            )
        if (
            state.get("status") == "INTEGRATION_FAILED_PRE_APPLY"
            and state.get("promotion_status") == "INTEGRATION_FAILED_PRE_APPLY"
            and state.get("terminal_status") == "INTEGRATION_FAILED_PRE_APPLY"
        ):
            return state
        if state.get("status") in TERMINAL_STATUSES:
            return state
        if state.get("status") in PENDING_CANDIDATE_STATUSES:
            return state
        if state.get("status") in {"CANDIDATE_COMMITTED", "CANDIDATE_REF_PROTECTED", "TARGET_CLEANED"}:
            owner_pid = state.get("worker_pid")
            owner_heartbeat = _parse_time(state.get("heartbeat_at"))
            owner_fresh = owner_heartbeat is not None and time.time() - owner_heartbeat <= self.stale_after_seconds
            if owner_pid and self._pid_alive(int(owner_pid)) and owner_fresh:
                return state
            if owner_pid and self._pid_alive(int(owner_pid)):
                self._terminate_owned_processes(task_id)
            packet = state.get("promotion_packet") or {}
            candidate_commit = packet.get("candidate_commit_sha")
            if not candidate_commit:
                return self._checkpoint(
                    task_id, "FINAL_BLOCK",
                    {
                        "error": "candidate checkpoint is missing its promotion packet",
                        "cleanup_decision": "BLOCKED_BY_MISSING_REF",
                        "cleanup_blocker": "candidate commit is missing",
                        "cleanup_performed": False,
                        "terminal_status": "FINAL_BLOCK",
                    },
                    attempt_id=state.get("attempt_id"),
                )
            if state.get("status") != "TARGET_CLEANED":
                contract = self._contract_from_state(state)
                lease = self._lease_from_state(state)
                manager = WorktreeManager(root_dir=contract.target_worktree_root)
                candidate_ref = state.get("candidate_ref")
                if not candidate_ref:
                    candidate_ref = manager.protect_candidate(contract, lease, candidate_commit)
                    state = self._checkpoint(
                        task_id, "CANDIDATE_REF_PROTECTED",
                        {"candidate_ref": candidate_ref},
                        attempt_id=state.get("attempt_id"),
                    ) or state
                cleanup = manager.cleanup_terminal_target(
                    contract, lease,
                    candidate_commit=candidate_commit,
                    candidate_ref=str(candidate_ref),
                )
                if cleanup.decision not in {"REMOVED", "ALREADY_REMOVED"}:
                    terminal = "RETAINED_FOR_REVIEW" if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES" else "FINAL_BLOCK"
                    return self._checkpoint(task_id, terminal, {
                        "cleanup_decision": cleanup.decision,
                        "cleanup_blocker": cleanup.blocker,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_eligible": cleanup.eligible,
                        "terminal_status": terminal,
                    }, attempt_id=state.get("attempt_id"))
                state = self._checkpoint(task_id, "TARGET_CLEANED", {
                    "cleanup_decision": cleanup.decision,
                    "cleanup_blocker": cleanup.blocker,
                    "cleanup_performed": cleanup.performed,
                    "cleanup_eligible": cleanup.eligible,
                    "cleanup_performed_at": _utc_now() if cleanup.performed else state.get("cleanup_performed_at"),
                }, attempt_id=state.get("attempt_id")) or state
            return self._checkpoint(task_id, "PENDING_HUMAN_APPROVAL", {
                "promotion_status": "PENDING_HUMAN_APPROVAL",
                "candidate_status": "PENDING_HUMAN_APPROVAL",
                "terminal_status": "PENDING_HUMAN_APPROVAL",
                "state_retention_status": "ACTIVE",
                "archive_eligible": False,
            }, attempt_id=state.get("attempt_id"))
        pid = state.get("worker_pid")
        heartbeat_at = _parse_time(state.get("heartbeat_at"))
        stale = heartbeat_at is not None and time.time() - heartbeat_at > self.stale_after_seconds
        if pid and self._pid_alive(int(pid)) and not stale:
            return state
        if pid and self._pid_alive(int(pid)) and stale:
            self._terminate_owned_processes(task_id)
            return self._checkpoint(
                task_id,
                "FINAL_BLOCK",
                {"error": "stale task heartbeat; owned process group terminated", "promotion_status": "NOT_CREATED"},
                attempt_id=state.get("attempt_id"),
            )
        if state.get("status") == "TARGET_LEASED":
            contract = state.get("contract") or {}
            target = Path(str(contract.get("target_repo_root", ""))).expanduser().resolve()
            controller = Path(str(contract.get("controller_repo_root", ""))).expanduser().resolve()
            target_exists = target.is_dir()
            manager = WorktreeManager(root_dir=str(contract.get("target_worktree_root") or target.parent))
            entry = manager._worktree_entry(controller, target) if target_exists and controller.is_dir() else None
            head = manager._run_git(["rev-parse", "HEAD"], cwd=target) if entry else None
            dirty = bool(manager._status_bytes(target)) if entry else None
            evidence = {
                "worker_alive": False,
                "heartbeat_fresh": False,
                "target_exists": target_exists,
                "target_registered": entry is not None,
                "target_clean": not dirty if dirty is not None else None,
                "target_head": head,
                "candidate_exists": bool(head and head != contract.get("target_base_revision")),
            }
            if entry and dirty:
                return self._checkpoint(task_id, "RETAINED_FOR_REVIEW", {
                    **evidence,
                    "reconcile_decision": "RETAINED_FOR_REVIEW",
                    "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
                    "cleanup_blocker": "dirty target has no durable snapshot",
                    "cleanup_performed": False,
                    "terminal_status": "RETAINED_FOR_REVIEW",
                    "state_retention_status": "TERMINAL",
                }, attempt_id=state.get("attempt_id"))
            if entry and head != contract.get("target_base_revision"):
                if state.get("candidate") and state.get("execution"):
                    resumed = self._checkpoint(
                        task_id, "CANDIDATE_CAPTURED",
                        {**evidence, "reconcile_decision": "RESUME_CANDIDATE_VERIFICATION"},
                        attempt_id=state.get("attempt_id"),
                    )
                    return self._launch_worker(task_id, str(state.get("attempt_id"))) or resumed
                return self._checkpoint(task_id, "RETAINED_FOR_REVIEW", {
                    **evidence,
                    "reconcile_decision": "RETAINED_FOR_REVIEW",
                    "cleanup_decision": "BLOCKED_BY_MISSING_REF",
                    "cleanup_blocker": "candidate HEAD lacks recoverable receipt evidence",
                    "cleanup_performed": False,
                    "terminal_status": "RETAINED_FOR_REVIEW",
                    "state_retention_status": "TERMINAL",
                }, attempt_id=state.get("attempt_id"))
            cleanup_decision = "ALREADY_REMOVED"
            cleanup_performed = entry is None
            cleanup_blocker = None
            cleanup_eligible = True
            if entry:
                lease_data = state.get("lease") or {
                    "schema": "nexus.target_worktree_lease.v1",
                    "lease_id": manager._lease_id(
                        self._contract_from_state(state),
                        target,
                        f"nexus/task/{task_id}",
                    ),
                    "task_id": task_id,
                    "controller_revision": contract.get("controller_revision"),
                    "target_base_revision": contract.get("target_base_revision"),
                    "target_worktree": str(target),
                    "target_branch": f"nexus/task/{task_id}",
                    "initial_head": contract.get("target_base_revision"),
                    "initial_status_sha256": hashlib.sha256(b"").hexdigest(),
                    "controller_status_sha256": hashlib.sha256(b"").hexdigest(),
                    "created_from_exact_revision": True,
                    "commit_created": False,
                    "merge_performed": False,
                }
                cleanup = manager.cleanup_terminal_target(
                    self._contract_from_state(state),
                    TargetWorktreeLease(**lease_data),
                )
                cleanup_decision = cleanup.decision
                cleanup_performed = cleanup.performed
                cleanup_blocker = cleanup.blocker
                cleanup_eligible = cleanup.eligible
            return self._checkpoint(task_id, "FINAL_BLOCK", {
                **evidence,
                "reconcile_decision": cleanup_decision,
                "cleanup_decision": cleanup_decision,
                "cleanup_blocker": cleanup_blocker,
                "cleanup_eligible": cleanup_eligible,
                "cleanup_performed": cleanup_performed,
                "cleanup_performed_at": _utc_now() if cleanup_performed else None,
                "terminal_status": "FINAL_BLOCK",
                "state_retention_status": "TERMINAL",
                "archive_eligible": True,
            }, attempt_id=state.get("attempt_id"))
        if state.get("status") == "SUBMITTED" or state.get("status") in RESUMABLE_STATUSES:
            return {
                **self._with_task_action(state),
                "reconciliation_required": True,
                "reconciliation_decision": "EXPLICIT_RESUME_REQUIRED",
                "mutation_replayed": False,
                "route_replanned": False,
                "task_card_created": False,
            }
        self._terminate_owned_processes(task_id)
        return self._checkpoint(
            task_id,
            "FINAL_BLOCK",
            {"error": "worker lost before recoverable execution evidence", "promotion_status": "NOT_CREATED"},
            attempt_id=state.get("attempt_id"),
        )

    def recover_retained_candidate(self, task_id: str) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("status") != "RETAINED_FOR_REVIEW":
            raise RuntimeError("only a retained candidate can enter recovery")
        packet = state.get("promotion_packet") or {}
        verified = state.get("verified_receipt") or {}
        candidate_commit = str(packet.get("candidate_commit_sha") or "")
        candidate_tree = str(packet.get("candidate_tree_sha") or "")
        if not candidate_commit or not candidate_tree or not verified:
            raise RuntimeError("retained candidate lacks verified durable recovery evidence")
        contract = self._contract_from_state(state)
        lease = self._lease_from_state(state)
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        target = Path(lease.target_worktree).resolve()
        controller = Path(contract.controller_repo_root).resolve()
        if manager._worktree_entry(controller, target) is None:
            raise RuntimeError("retained candidate Target is not a registered worktree")
        if manager.process_checker(target):
            raise RuntimeError("active process uses retained candidate Target")
        if manager._status_bytes(target):
            raise RuntimeError("retained candidate Target has unsaved working-tree changes")
        if manager._run_git(["rev-parse", "HEAD"], cwd=target) != candidate_commit:
            raise RuntimeError("retained candidate HEAD does not match promotion packet")
        if manager._run_git(["rev-parse", "HEAD^{tree}"], cwd=target) != candidate_tree:
            raise RuntimeError("retained candidate tree does not match promotion packet")
        self._checkpoint(task_id, "CANDIDATE_COMMITTED", {
            "error": None,
            "promotion_status": str(packet.get("promotion_status") or "PENDING_HUMAN_APPROVAL"),
            "cleanup_decision": None,
            "cleanup_blocker": None,
            "cleanup_performed": False,
            "terminal_status": None,
            "state_retention_status": "ACTIVE",
            "archive_eligible": False,
        }, attempt_id=state.get("attempt_id"))
        recovered = self.reconcile_task(task_id)
        if recovered is None:
            raise RuntimeError("retained candidate recovery lost task state")
        return recovered

    def reconcile_tasks(self) -> list[dict[str, Any]]:
        if not self.state_dir.exists():
            return []
        states = []
        for path in sorted(self.state_dir.glob("*.json")):
            state = self.reconcile_task(path.stem)
            if state is not None:
                states.append(state)
        return states

    def resume_task(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None:
            return None
        if state.get("status") == "SUBMITTED" or state.get("status") in RESUMABLE_STATUSES:
            attempt_id = str(state.get("attempt_id") or "")
            if not attempt_id:
                return {
                    **self._with_task_action(state),
                    "reconciliation_required": True,
                    "reconciliation_decision": "BLOCKED_MISSING_ATTEMPT_ID",
                    "mutation_replayed": False,
                    "route_replanned": False,
                    "task_card_created": False,
                }
            return self._launch_worker(task_id, attempt_id) or self._with_task_action(state)
        return self.reconcile_task(task_id)

    def wait_task(
        self,
        task_id: str,
        *,
        timeout_seconds: float = 10.0,
        poll_interval_seconds: float = 0.25,
        include_details: bool = False,
    ) -> Optional[dict[str, Any]]:
        timeout_seconds = float(timeout_seconds)
        poll_interval_seconds = float(poll_interval_seconds)
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if timeout_seconds > 60.0:
            raise ValueError("timeout_seconds must be <= 60")

        deadline = time.monotonic() + timeout_seconds
        while True:
            # Waiting is a read-only operator surface.  Do not reconcile or
            # acquire the lifecycle write lock while polling durable state.
            state = self._read_state_snapshot(task_id)
            if state is not None:
                state = self._with_task_action(state)
            if state is None:
                return None
            envelope = state.get("task_action") or self._task_action_envelope(state)
            detailed_state = dict(state)
            detailed_state.pop("operator_outcome_receipt", None)
            detailed_state.pop("operator_outcome_receipts", None)
            if envelope.get("action_state") != "IN_PROGRESS":
                result = {
                    **(detailed_state if include_details else {
                        "schema": "nexus.self_hosted_task_status.v1",
                        "task_id": state.get("task_id"),
                        "status": state.get("status"),
                        "promotion_status": state.get("promotion_status"),
                        "verification_verdict": state.get("verification_verdict"),
                        "found": state.get("found", True),
                        "state_valid": state.get("state_valid", True),
                        "blocker": self._projected_blocker(state),
                        "retry_authorized": state.get("retry_authorized"),
                        "task_action": envelope,
                    }),
                    "wait": {
                        "timed_out": False,
                        "timeout_seconds": timeout_seconds,
                        "poll_interval_seconds": poll_interval_seconds,
                    },
                }
                return result
            if time.monotonic() >= deadline:
                envelope = {**envelope, "wait_timed_out": True}
                return {
                    **(detailed_state if include_details else {
                        "schema": "nexus.self_hosted_task_status.v1",
                        "task_id": state.get("task_id"),
                        "status": state.get("status"),
                        "promotion_status": state.get("promotion_status"),
                        "verification_verdict": state.get("verification_verdict"),
                        "found": state.get("found", True),
                        "state_valid": state.get("state_valid", True),
                        "blocker": self._projected_blocker(state),
                        "retry_authorized": state.get("retry_authorized"),
                        "task_action": envelope,
                    }),
                    "task_action": envelope,
                    "wait": {
                        "timed_out": True,
                        "timeout_seconds": timeout_seconds,
                        "poll_interval_seconds": poll_interval_seconds,
                    },
                }
            time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))

    def list_actionable_tasks(self, *, include_details: bool = False) -> dict[str, Any]:
        """Return action envelopes without reconciling or mutating task state.

        The default response is intentionally compact.  Callers that need the
        full durable state must opt in with ``include_details=True`` or use
        ``get_task``/``get_receipt`` for one task.  This keeps status polling
        from repeatedly traversing Target worktrees and from creating hidden
        lifecycle mutations.
        """
        tasks = []
        for path in sorted(self.state_dir.glob("*.json")) if self.state_dir.exists() else []:
            state = self._read_state_snapshot(path.stem)
            if state is None:
                continue
            action = self._task_action_envelope(state)
            if action.get("attention_required") is True:
                if include_details:
                    tasks.append(state)
                else:
                    tasks.append({**action, "task_action": action})
        return {
            "schema": "nexus.self_hosted_actionable_tasks.v1",
            "actionable_count": len(tasks),
            "details_included": include_details,
            "tasks": tasks,
        }

    def _workspace_task_states(self) -> dict[str, dict[str, Any]]:
        """Load durable task snapshots without invoking reconciliation."""
        if not self.state_dir.exists():
            return {}
        states: dict[str, dict[str, Any]] = {}
        for path in sorted(self.state_dir.glob("*.json")):
            state = self._read_state_snapshot(path.stem)
            if state is not None:
                states[path.stem] = state
        return states

    def _submission_task_states(self) -> dict[str, dict[str, Any]]:
        """Fail closed when submission authority cannot trust durable state."""
        states = self._workspace_task_states()
        invalid = [
            state
            for state in states.values()
            if state.get("state_valid") is False
        ]
        if invalid:
            blockers = ",".join(
                f"{state.get('task_id') or 'unknown'}:"
                f"{(state.get('blocker') or {}).get('code') or 'STATE_INVALID'}"
                for state in invalid
            )
            raise RuntimeError(
                f"INVALID_DURABLE_STATE_BLOCKS_SUBMISSION:{blockers}"
            )
        return states

    def workspace_inventory(
        self,
        *,
        controller_root: Optional[str | Path] = None,
    ) -> dict[str, Any]:
        """Read-only inventory of registered worktrees and lifecycle ownership."""
        states = self._workspace_task_states()
        root = Path(controller_root or Path.cwd()).resolve()
        manager = WorktreeManager(root_dir=str(root.parent / "nexus-runtime-targets"), create_root=False)
        inventory = manager.get_workspace_inventory(
            controller_root=root,
            task_states=states,
        )
        return _jsonable(inventory)

    def state_root_inventory(self) -> dict[str, Any]:
        """Inventory canonical and nested lifecycle state without mutation."""
        canonical = self.canonical_state_dir()
        entries: list[dict[str, Any]] = []
        if canonical.exists():
            candidates = sorted(canonical.glob("**/*.json"))
        else:
            candidates = []
        for path in candidates:
            if path.name.startswith("manifest-"):
                continue
            try:
                raw = path.read_bytes()
                state = json.loads(raw)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(state, Mapping) or not state.get("task_id"):
                continue
            relative_parent = path.parent.relative_to(canonical)
            if str(relative_parent) == ".":
                authority = "CANONICAL_AUTHORITY"
            elif "nexus-state-archive" in path.parts:
                authority = "ARCHIVE_EVIDENCE"
            else:
                authority = "REHEARSAL_EVIDENCE"
            entries.append({
                "path": str(path),
                "authority": authority,
                "task_id": state.get("task_id"),
                "attempt_id": state.get("attempt_id"),
                "status": state.get("status"),
                "promotion_status": state.get("promotion_status"),
                "candidate_commit_sha": state.get("candidate_commit_sha"),
                "candidate_ref": state.get("candidate_ref"),
                "state_sha256": hashlib.sha256(raw).hexdigest(),
                "updated_at": state.get("updated_at"),
            })
        by_task: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            by_task.setdefault(str(entry["task_id"]), []).append(entry)
        canonical_authority_counts = {
            task_id: sum(1 for value in values if value["authority"] == "CANONICAL_AUTHORITY")
            for task_id, values in by_task.items()
        }
        conflicts = sorted(task_id for task_id, count in canonical_authority_counts.items() if count > 1)
        evidence_duplicates = sorted(task_id for task_id, values in by_task.items() if len(values) > 1 and task_id not in conflicts)
        return {
            "schema": "nexus.lifecycle_state_root_inventory.v1",
            "canonical_state_root": str(canonical),
            "entry_count": len(entries),
            "task_count": len(by_task),
            "conflict_task_ids": conflicts,
            "authority_conflict": bool(conflicts),
            "evidence_duplicate_task_ids": evidence_duplicates,
            "entries": entries,
            "inventory_sha256": hashlib.sha256(
                json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }

    def workspace_convergence_plan(
        self,
        *,
        controller_root: Optional[str | Path] = None,
        expected_controller_revision: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a stable dry-run plan; no state or workspace mutation occurs."""
        states = self._workspace_task_states()
        root = Path(controller_root or Path.cwd()).resolve()
        manager = WorktreeManager(root_dir=str(root.parent / "nexus-runtime-targets"), create_root=False)
        inventory = manager.get_workspace_inventory(
            controller_root=root,
            task_states=states,
        )
        expected = expected_controller_revision or inventory.controller_head
        plan = manager.plan_convergence(inventory, expected_controller_revision=expected)
        return _jsonable(plan)

    def workspace_slot_status(
        self,
        *,
        campaign_id: str = "default",
        slot_index: int = 0,
        controller_root: Optional[str | Path] = None,
    ) -> dict[str, Any]:
        """Read-only reusable-slot readiness check."""
        states = self._workspace_task_states()
        root = Path(controller_root or Path.cwd()).resolve()
        manager = WorktreeManager(root_dir=str(root.parent / "nexus-runtime-targets"), create_root=False)
        status = manager.get_reusable_slot_status(
            campaign_id=campaign_id,
            slot_index=slot_index,
            controller_root=root,
            task_states=states,
        )
        return _jsonable(status)

    def workspace_slot_prepare(
        self,
        request: Mapping[str, Any],
        *,
        campaign_id: str = "default",
        slot_index: int = 0,
    ) -> dict[str, Any]:
        """Prepare one reusable slot through WorktreeManager authority."""
        contract = self.build_contract(request)
        states = self._workspace_task_states()
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        prepared = manager.prepare_reusable_slot(
            contract,
            campaign_id=campaign_id,
            slot_index=slot_index,
            task_states=states,
        )
        return _jsonable(prepared)

    def apply_workspace_convergence(
        self,
        *,
        controller_root: Optional[str | Path] = None,
        expected_controller_revision: str,
        expected_plan_hash: str,
        apply: bool = False,
    ) -> dict[str, Any]:
        """Apply only lifecycle-bound terminal cleanup through existing authority.

        The default is a dry-run.  Unbound redundant worktrees remain blocked
        because they have no task contract through which existing cleanup
        authority can safely operate.
        """
        root = Path(controller_root or Path.cwd()).resolve()
        states = self._workspace_task_states()
        manager = WorktreeManager(
            root_dir=str(root.parent / "nexus-runtime-targets"),
            create_root=False,
        )
        inventory = manager.get_workspace_inventory(controller_root=root, task_states=states)
        if inventory.controller_head != expected_controller_revision:
            raise RuntimeError(
                f"CONTROLLER_REVISION_DRIFT: current controller {inventory.controller_head} "
                f"does not match expected {expected_controller_revision}"
            )
        plan = manager.plan_convergence(
            inventory,
            expected_controller_revision=expected_controller_revision,
        )
        if plan.plan_hash != expected_plan_hash:
            raise RuntimeError(
                f"PLAN_HASH_MISMATCH: current plan {plan.plan_hash} "
                f"does not match expected {expected_plan_hash}"
            )
        if not apply:
            return {
                **_jsonable(plan),
                "applied": False,
                "next_gate": "EXPLICIT_APPLY",
            }

        decisions: list[dict[str, Any]] = []
        path_to_state = {
            str(Path((state.get("lease") or {}).get("target_worktree") or "").resolve()): state
            for state in states.values()
            if (state.get("lease") or {}).get("target_worktree")
        }
        for path in plan.releasable_paths:
            if Path(path).resolve() == Path("/Users/jameschen/Workspace/nexus").resolve():
                raise RuntimeError("LEGACY_ROOT_APPLY_FORBIDDEN: legacy root cannot be released")
            state = path_to_state.get(str(Path(path).resolve()))
            if state is None:
                decisions.append({
                    "path": path,
                    "cleanup_decision": "BLOCKED_UNBOUND_WORKSPACE",
                    "cleanup_blocker": "no lifecycle task contract owns this worktree",
                    "cleanup_performed": False,
                })
                continue
            task_id = str(state.get("task_id"))
            result = self.cleanup_tasks(task_id=task_id, dry_run=False)
            decisions.extend(result.get("decisions", []))

        return {
            **_jsonable(plan),
            "applied": True,
            "decisions": decisions,
            "next_gate": "OWNER_REVIEW",
        }

    def _submit_direct_canonical(self, request: Mapping[str, Any], task_id: str) -> dict[str, Any]:
        """Record a Target-free canonical mutation intent exactly once."""
        inline_contract = None
        if str(request.get("contract_kind") or "") == ContractKind.OWNER_INLINE.value:
            try:
                inline_contract = validate_owner_inline_contract(
                    request.get("owner_inline_contract") if isinstance(request.get("owner_inline_contract"), Mapping) else {},
                    expected_task_id=task_id,
                    expected_head=str(request.get("controller_revision") or ""),
                )
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
        action = request.get("action") if isinstance(request.get("action"), Mapping) else {}
        action_id = str(request.get("action_id") or action.get("action_id") or f"action-{uuid4().hex}")
        attempt_id = str(request.get("attempt_id") or action.get("attempt_id") or f"attempt-{uuid4().hex}")
        idempotency_key = str(request.get("idempotency_key") or action.get("idempotency_key") or f"{task_id}:{self._request_hash(request)}")
        request_hash = str(request.get("action_request_hash") or action.get("request_hash") or self._request_hash(request))
        canonical_execution = (
            _jsonable(dict(request["canonical_execution_identity"]))
            if isinstance(request.get("canonical_execution_identity"), Mapping)
            else None
        )
        canonical_execution_hashes = (
            {
                name: str(canonical_execution.get(name) or "")
                for name in (
                    "context_hash",
                    "plan_hash",
                    "decision_hash",
                    "projection_hash",
                )
            }
            if canonical_execution is not None
            else None
        )
        if idempotency_key and self.state_dir.exists():
            for current in self._submission_task_states().values():
                if str(current.get("idempotency_key") or "") != idempotency_key:
                    continue
                current_hash = str(current.get("action_request_hash") or current.get("request_hash") or "")
                if current_hash and current_hash != request_hash:
                    raise ValueError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
                return {
                    "schema": "nexus.self_hosted_direct_handoff.v1",
                    "task_id": current.get("task_id"),
                    "status": "DIRECT_CANONICAL_READY",
                    "durable_status": current.get("status"),
                    "execution_lane": "DIRECT_CANONICAL",
                    "target_created": False,
                    "state_created": False,
                    "duplicate": True,
                    "action_id": current.get("action_id"),
                    "attempt_id": current.get("attempt_id"),
                    "idempotency_key": current.get("idempotency_key"),
                    "action_request_hash": current.get("action_request_hash"),
                    "canonical_execution_identity": current.get(
                        "canonical_execution_identity"
                    ),
                    "task_action": current.get("task_action") or self._task_action_envelope(current),
                    "next_action": (current.get("task_action") or {}).get("next_action", "nexus_task_finish"),
                }
        state = self._read_state_snapshot(task_id)
        if state is not None:
            existing_key = str(state.get("idempotency_key") or "")
            existing_hash = str(state.get("action_request_hash") or state.get("request_hash") or "")
            if existing_key == idempotency_key and existing_hash and existing_hash != request_hash:
                raise ValueError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
            if existing_key and existing_key != idempotency_key and existing_hash and existing_hash != request_hash:
                raise ValueError("DIRECT_TASK_ID_REUSED_WITH_DIFFERENT_REQUEST")
            return {
                "schema": "nexus.self_hosted_direct_handoff.v1",
                "task_id": task_id,
                "status": "DIRECT_CANONICAL_READY",
                "durable_status": state.get("status"),
                "execution_lane": "DIRECT_CANONICAL",
                "target_created": False,
                "state_created": False,
                "duplicate": True,
                "action_id": state.get("action_id"),
                "attempt_id": state.get("attempt_id"),
                "idempotency_key": state.get("idempotency_key"),
                "action_request_hash": state.get("action_request_hash"),
                "canonical_execution_identity": state.get(
                    "canonical_execution_identity"
                ),
                "task_action": state.get("task_action") or self._task_action_envelope(state),
                "next_action": (state.get("task_action") or {}).get("next_action", "nexus_task_finish"),
            }
        now = _utc_now()
        base = str(request.get("controller_revision") or "")
        canonical_action = {
            "schema": "nexus.canonical_action.v1",
            "action_id": action_id,
            "attempt_id": attempt_id,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "canonical_execution_identity": canonical_execution,
            "canonical_execution_hashes": canonical_execution_hashes,
            "execution_lane": "DIRECT_CANONICAL",
            "intent": {
                "status": "RECORDED",
                "at": now,
                "base_sha": base,
                "allowed_paths": list(request.get("allowed_files") or ()),
            },
            "application": {"status": "PENDING"},
            "verification": {"status": "PENDING"},
            "commit": {"status": "PENDING"},
            "reconciliation": {"status": "PENDING"},
        }
        durable_state = {
            "schema": "nexus.self_hosted_task_state.v1",
            "task_id": task_id,
            "status": "DIRECT_INTENT_RECORDED",
            "submitted_at": now,
            "updated_at": now,
            "heartbeat_at": now,
            "status_history": [{"status": "DIRECT_INTENT_RECORDED", "at": now}],
            "request": _jsonable(dict(request)),
            "action": _jsonable(dict(action)) if action else None,
            "action_id": action_id,
            "attempt_id": attempt_id,
            "attempts": [{
                "attempt_id": attempt_id,
                "action_id": action_id or None,
                "idempotency_key": idempotency_key or None,
                "action_request_hash": request_hash or None,
                "started_at": now,
            }],
            "idempotency_key": idempotency_key,
            "action_request_hash": request_hash,
            "request_hash": request_hash,
            "canonical_execution_identity": canonical_execution,
            "canonical_execution_hashes": canonical_execution_hashes,
            "controller_worktree": str(request.get("controller_repo_root") or CANONICAL_SOURCE_ROOT),
            "controller_revision": base,
            "contract_kind": str(request.get("contract_kind") or ContractKind.NONE.value),
            "contract_hash": str(request.get("contract_hash") or "") or None,
            "owner_inline_contract": _jsonable(inline_contract),
            "execution_lane": "DIRECT_CANONICAL",
            "target_worktree": None,
            "target_created_at": None,
            "canonical_action": canonical_action,
            "direct_receipt": None,
            "reconciliation_required": False,
            "promotion_status": "NOT_CREATED",
            "candidate_created": False,
            "cleanup_eligible": False,
            "cleanup_decision": None,
            "cleanup_performed": False,
            "state_retention_status": "ACTIVE",
            "archive_eligible": False,
            "archive_location": None,
            "worker_pid": None,
            "worker_pgid": None,
            "push_performed": False,
        }
        created_state, created = self._create_state(task_id, durable_state)
        return {
            "schema": "nexus.self_hosted_direct_handoff.v1",
            "task_id": task_id,
            "status": "DIRECT_CANONICAL_READY",
            "durable_status": created_state.get("status"),
            "execution_lane": "DIRECT_CANONICAL",
            "controller_repo_root": str(request.get("controller_repo_root") or CANONICAL_SOURCE_ROOT),
            "controller_branch": CANONICAL_SOURCE_BRANCH,
            "target_created": False,
            "state_created": created,
            "duplicate": not created,
            "action_id": created_state.get("action_id"),
            "attempt_id": created_state.get("attempt_id"),
            "idempotency_key": created_state.get("idempotency_key"),
            "action_request_hash": created_state.get("action_request_hash"),
            "canonical_execution_identity": created_state.get(
                "canonical_execution_identity"
            ),
            "next_action": "nexus_task_finish",
            "required_surface": "nexus_self_hosted_direct_complete",
            "required_gate": ["scoped_verifiers", "git_diff_check", "staged_review", "scoped_commit"],
            "task_action": created_state.get("task_action") or self._task_action_envelope(created_state),
        }

    def complete_direct_canonical(
        self,
        request: Mapping[str, Any],
        *,
        expected_commit_sha: Optional[str] = None,
    ) -> dict[str, Any]:
        """Complete one durable Target-free canonical action idempotently."""
        task_id = str(request.get("task_id") or "")
        if not task_id:
            raise RuntimeError("DIRECT_ACTION_ID_REQUIRED")
        state = self._read_state_snapshot(task_id)
        if state is None:
            raise RuntimeError("DIRECT_ACTION_NOT_FOUND_RECONCILE_REQUIRED")
        if state.get("status") == "DIRECT_COMPLETED":
            receipt = dict(state.get("direct_receipt") or {})
            if expected_commit_sha and receipt.get("commit_sha") != expected_commit_sha:
                raise RuntimeError("DIRECT_CANONICAL_COMMIT_MISMATCH: duplicate finish commit differs")
            receipt.update({"duplicate": True, "state_created": True, "target_created": False})
            return receipt
        if state.get("status") == "DIRECT_RECONCILE_REQUIRED":
            raise RuntimeError("DIRECT_RECONCILE_REQUIRED: reconcile before retry")
        stored_request = state.get("request") if isinstance(state.get("request"), Mapping) else {}
        effective_request = dict(stored_request)
        effective_request.update(dict(request))
        action = dict(state.get("canonical_action") or {})
        now = _utc_now()
        self._mutate_state(task_id, lambda current: (
            current.update({
                "status": "DIRECT_STARTED",
                "updated_at": now,
                "heartbeat_at": now,
                "canonical_action": {
                    **dict(current.get("canonical_action") or {}),
                    "application": {"status": "STARTED", "at": now},
                },
            }),
            current.setdefault("status_history", []).append({"status": "DIRECT_STARTED", "at": now}),
        ))
        try:
            receipt = dict(self._complete_direct_canonical_physical(effective_request, expected_commit_sha=expected_commit_sha))
        except Exception as exc:
            self._record_direct_failure(task_id, "DIRECT_CANONICAL_FAILED", str(exc))
            raise
        commit_sha = str(receipt.get("commit_sha") or "")
        controller = Path(str(effective_request.get("controller_repo_root") or CANONICAL_SOURCE_ROOT)).resolve()
        tree_sha = ""
        if commit_sha:
            tree_sha = subprocess.run(
                ["git", "rev-parse", f"{commit_sha}^{{tree}}"], cwd=controller,
                capture_output=True, text=True, check=False,
            ).stdout.strip()
        completed_at = _utc_now()
        action = dict(state.get("canonical_action") or action)
        action.update({
            "application": {"status": "APPLIED", "at": completed_at},
            "verification": {
                "status": "PASSED",
                "at": completed_at,
                "evidence": receipt.get("verifier_evidence") or {},
            },
            "commit": {"status": "COMMITTED", "at": completed_at, "sha": commit_sha, "tree_sha": tree_sha},
            "reconciliation": {"status": "RECONCILED", "at": completed_at},
        })
        receipt.update({
            "state_created": True,
            "target_created": False,
            "duplicate": False,
            "action_id": state.get("action_id"),
            "attempt_id": state.get("attempt_id"),
            "idempotency_key": state.get("idempotency_key"),
            "action_request_hash": state.get("action_request_hash"),
            "base_sha": state.get("controller_revision"),
            "candidate_tree_sha": tree_sha,
            "reconciliation_status": "RECONCILED",
        })
        self._mutate_state(task_id, lambda current: (
            current.update({
                "status": "DIRECT_COMPLETED",
                "updated_at": completed_at,
                "heartbeat_at": completed_at,
                "canonical_action": action,
                "direct_receipt": receipt,
                "commit_sha": commit_sha,
                "candidate_tree_sha": tree_sha,
                "reconciliation_required": False,
                "terminal_status": "DIRECT_COMPLETED",
            }),
            current.setdefault("status_history", []).append({"status": "DIRECT_COMPLETED", "at": completed_at}),
        ))
        return receipt

    def _complete_direct_canonical_physical(
        self,
        request: Mapping[str, Any],
        *,
        expected_commit_sha: Optional[str] = None,
    ) -> dict[str, Any]:
        """Verify a primary-agent commit already made on the canonical checkout.

        This is the physical post-commit gate. The public wrapper records the
        durable action state before and after this method; this helper only
        proves the commit and verifiers.
        """
        current_task_id = str(request.get("task_id") or "")
        active = sum(
            1
            for state in self._workspace_task_states().values()
            if state.get("task_id") != current_task_id
            if state.get("status") not in TERMINAL_STATUSES
            and state.get("status") not in {"PENDING_HUMAN_APPROVAL", "APPROVED"}
        )
        lane = resolve_execution_lane(request, active_mutation_tasks=active)
        if str(request.get("execution_lane", "")).strip().upper() != "DIRECT_CANONICAL":
            raise RuntimeError("DIRECT_CANONICAL completion requires explicit execution_lane")
        if not lane["eligible"]:
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: " + ",".join(lane["blockers"]))
        controller = CANONICAL_SOURCE_ROOT
        started = time.perf_counter()
        status = subprocess.run(
            ["git", "status", "--porcelain=v1"], cwd=controller,
            capture_output=True, text=True, check=False,
        )
        if status.returncode != 0 or status.stdout.strip():
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: canonical checkout must be clean after commit")
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if branch != CANONICAL_SOURCE_BRANCH:
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: canonical branch drift")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if expected_commit_sha and head != expected_commit_sha:
            raise RuntimeError("DIRECT_CANONICAL_COMMIT_MISMATCH: HEAD differs from expected commit")
        worktree_manager = WorktreeManager(
            root_dir=str(controller.parent / "nexus-runtime-targets"),
            create_root=False,
        )
        worktree_audit = worktree_manager.audit_direct_completion(
            controller_root=controller,
            expected_head=head,
            expected_branch=CANONICAL_SOURCE_BRANCH,
            allowed_files=request.get("allowed_files") or (),
            task_states=self._workspace_task_states(),
        )
        if worktree_audit["blockers"]:
            raise RuntimeError(
                "DIRECT_CANONICAL_BLOCKED: "
                + ",".join(worktree_audit["blockers"])
            )
        base = str(request.get("controller_revision") or "").strip()
        if len(base) != 40:
            raise RuntimeError("DIRECT_CANONICAL_REVISION_REQUIRED: controller_revision must be an exact SHA")
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, head], cwd=controller,
            capture_output=True, check=False,
        )
        if ancestry.returncode != 0:
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: commit is not descended from controller_revision")
        changed = subprocess.run(
            ["git", "diff", "--name-only", f"{base}..{head}"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.splitlines()
        deleted = subprocess.run(
            ["git", "diff", "--diff-filter=D", "--name-only", f"{base}..{head}"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.splitlines()
        allowed = tuple(str(path).rstrip("/") for path in request.get("allowed_files") or ())
        if not changed:
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: commit has no scoped changes")
        if deleted or any(
            not any(path == boundary or boundary.endswith("/") and path.startswith(boundary) for boundary in allowed)
            for path in changed
        ):
            raise RuntimeError("DIRECT_CANONICAL_SCOPE_MISMATCH: commit changed files outside allowed scope")
        diff_check = subprocess.run(
            ["git", "diff", "--check", f"{base}..{head}"], cwd=controller,
            capture_output=True, text=True, check=False,
        )
        if diff_check.returncode != 0:
            raise RuntimeError("DIRECT_CANONICAL_DIFF_CHECK_FAILED: " + diff_check.stdout.strip())
        commit_shape = subprocess.run(
            ["git", "rev-list", "--parents", "-n", "1", head], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.split()
        if len(commit_shape) != 2:
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: merge commit is not allowed")
        verifier_started = time.perf_counter()
        verifier_contract = type("DirectVerifierContract", (), {
            "verifier_commands": tuple(str(command) for command in request.get("verifier_commands") or ())
        })()
        passed, evidence, failures = CandidateVerifier._run_verifiers(verifier_contract, str(controller))
        verifier_time_ms = max(0, int((time.perf_counter() - verifier_started) * 1000))
        if not passed:
            raise RuntimeError("DIRECT_CANONICAL_VERIFIER_FAILED: " + ",".join(failures))
        total_time_ms = max(0, int((time.perf_counter() - started) * 1000))
        telemetry = {
            "wall_time_ms": total_time_ms,
            "provider_time_ms": 0,
            "verifier_time_ms": verifier_time_ms,
            "worktree_time_ms": 0,
            "commit_hook_time_ms": 0,
            "cleanup_time_ms": 0,
            "overhead_ms": max(0, total_time_ms - verifier_time_ms),
        }
        receipt = {
            "schema": "nexus.self_hosted_direct_receipt.v1",
            "task_id": str(request.get("task_id") or f"direct-{head[:12]}"),
            "execution_lane": "DIRECT_CANONICAL",
            "status": "DIRECT_CANONICAL_COMPLETED",
            "controller_repo_root": str(controller),
            "controller_branch": branch,
            "commit_sha": head,
            "changed_files": changed,
            "candidate_created": False,
            "target_created": False,
            "state_created": False,
            "worktree_audit": worktree_audit,
            "verifier_evidence": _jsonable(evidence),
            "telemetry": telemetry,
        }
        receipt["receipt_hash"] = hashlib.sha256(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return receipt

    @staticmethod
    def _resolve_current_execution_task_id(request: Mapping[str, Any]) -> str:
        """Resolve durable identity before any route or Target decision."""
        requested_task_id = str(request.get("task_id") or "").strip()
        canonical_identity = request.get("canonical_execution_identity")
        if canonical_identity is not None:
            if not isinstance(canonical_identity, Mapping):
                raise RuntimeError("CURRENT_EXECUTION_IDENTITY_INVALID")
            from nexus.contracts.canonical_execution import (
                validate_canonical_execution_identity,
            )

            try:
                validate_canonical_execution_identity(canonical_identity)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"CURRENT_EXECUTION_IDENTITY_INVALID:{exc}") from exc
            identity_task_id = str(canonical_identity.get("task_id") or "").strip()
            if requested_task_id and requested_task_id != identity_task_id:
                raise RuntimeError("CURRENT_EXECUTION_TASK_ID_MISMATCH")
            return identity_task_id
        if requested_task_id:
            return requested_task_id
        raise RuntimeError("CURRENT_EXECUTION_IDENTITY_REQUIRED")

    def submit_task(self, request: Mapping[str, Any]) -> dict[str, Any]:
        request, _ = _validated_action_request(request)
        task_id = self._resolve_current_execution_task_id(request)
        raw_autonomy_grant = request.get("autonomy_goal_grant")
        autonomy_grant: Optional[AutonomyGoalGrant] = None
        if raw_autonomy_grant is not None:
            if not isinstance(raw_autonomy_grant, Mapping):
                raise ValueError("AUTONOMY_GOAL_GRANT_INVALID")
            try:
                autonomy_grant = AutonomyGoalGrant.model_validate(raw_autonomy_grant)
            except Exception as exc:
                raise ValueError("AUTONOMY_GOAL_GRANT_INVALID") from exc
            now = datetime.now(timezone.utc)
            if autonomy_grant.issued_at > now:
                raise ValueError("AUTONOMY_GOAL_GRANT_NOT_YET_VALID")
            if autonomy_grant.expires_at <= now:
                raise ValueError("AUTONOMY_GOAL_GRANT_EXPIRED")
        action = request.get("action") if isinstance(request.get("action"), Mapping) else {}
        if action and not self.ephemeral:
            # The service remains lifecycle authority; this synchronous guard
            # only validates the caller's already-built envelope before any
            # state, Target, or worker mutation is allowed.
            trusted_manifest = trusted_runtime_manifest_hash()
            if trusted_manifest is None:
                raise RuntimeError("TOOL_MANIFEST_UNAVAILABLE: service cannot accept an unbound runtime manifest")
            pre_action_guard(
                action,
                request=request,
                canonical_root=CANONICAL_SOURCE_ROOT,
                tool_manifest_hash=trusted_manifest,
            )
        action_id = str(request.get("action_id") or action.get("action_id") or "")
        attempt_id_hint = str(request.get("attempt_id") or action.get("attempt_id") or "")
        idempotency_key = str(request.get("idempotency_key") or action.get("idempotency_key") or "")
        action_request_hash = str(
            request.get("action_request_hash")
            or action.get("request_hash")
            or self._request_hash(request)
        )
        states = self._submission_task_states()
        for current in states.values():
            if current.get("task_id") != task_id:
                continue
            _validate_existing_autonomy_binding(current, autonomy_grant)
        if request.get("worker_candidate_ingress") and str(request.get("contract_kind") or "") == ContractKind.OWNER_INLINE.value:
            semantic_fields = (
                "what", "why", "allowed_files", "verifier_commands", "worker", "worker_id",
                "provider", "model", "controller_revision", "target_base_revision",
                "controller_repo_root", "target_repo_root", "target_worktree_root",
                "collaboration_realm", "authority_change_candidate_confirmation",
                "protected_contracts",
                "provider_probe_evidence_hash", "provider_binary_path",
                "provider_binary_sha256", "provider_cli_version_sha256",
                "provider_probe_expires_at", "provider_authentication_evidence",
            )
            for current in states.values():
                if current.get("task_id") != task_id or not current.get("request"):
                    continue
                prior = current.get("request") if isinstance(current.get("request"), Mapping) else {}
                if prior.get("worker_candidate_ingress") is not True or str(prior.get("contract_kind") or "") != ContractKind.OWNER_INLINE.value:
                    raise ValueError("WORKER_CANDIDATE_TASK_ID_CONFLICT")
                if all(
                    (bool(prior.get(field)) == bool(request.get(field)))
                    if field == "authority_change_candidate_confirmation"
                    else prior.get(field) == request.get(field)
                    for field in semantic_fields
                ):
                    return {**self._with_task_action(current), "duplicate": True, "duplicate_action_id": current.get("action_id"), "idempotency_key": current.get("idempotency_key")}
                raise ValueError("WORKER_CANDIDATE_TASK_ID_CONFLICT")
        if action and idempotency_key:
            for current in states.values():
                if str(current.get("idempotency_key") or "") != idempotency_key:
                    continue
                current_hash = str(current.get("action_request_hash") or "")
                if current_hash and action_request_hash and current_hash != action_request_hash:
                    raise ValueError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
                return {
                    **self._with_task_action(current),
                    "duplicate": True,
                    "duplicate_action_id": current.get("action_id"),
                    "idempotency_key": idempotency_key,
                }
        if action.get("action_type") == LifecycleActionType.TASK_RETRY.value:
            _validate_retry_predecessor(request, self._read_state_snapshot(task_id))
        active_mutations = sum(
            1 for state in states.values()
            if state.get("task_id") != task_id
            if not idempotency_key or str(state.get("idempotency_key") or "") != idempotency_key
            if state.get("status") not in TERMINAL_STATUSES
            and state.get("status") not in {"PENDING_HUMAN_APPROVAL", "APPROVED"}
        )
        lane = resolve_execution_lane(request, active_mutation_tasks=active_mutations)
        requested_lane = str(request.get("execution_lane") or "").strip().upper()
        if requested_lane in {"", "DIRECT_CANONICAL"}:
            if lane["eligible"]:
                if request.get("collaboration_realm") is not None:
                    raise ValueError("COLLABORATION_REALM_DIRECT_CANONICAL_UNSUPPORTED")
                if autonomy_grant is not None:
                    raise ValueError("AUTONOMY_DIRECT_CANONICAL_UNSUPPORTED")
                return self._submit_direct_canonical(request, task_id)
            if requested_lane == "DIRECT_CANONICAL" and str(request.get("worker", "primary")).strip().lower() in {"", "primary", "codex"}:
                raise RuntimeError("DIRECT_CANONICAL_BLOCKED: " + ",".join(lane["blockers"]))
        contract = self.build_contract(request)
        dispatch_binding = validate_workforce_dispatch_binding(request)
        tracked_dispatch_required = _tracked_dispatch_required(request)
        if dispatch_binding is not None and not isinstance(
            dispatch_binding.get("canonical_dispatch_envelope"), Mapping
        ):
            raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_MISSING")
        state_request = dict(request)
        if dispatch_binding is not None:
            state_request.update({
                "worker": dispatch_binding["provider"],
                "provider": dispatch_binding["provider"],
                "model": dispatch_binding["model"],
                "worker_id": dispatch_binding["worker_id"],
                "worker_order": [dispatch_binding["provider"]],
            })
        validate_task_card_binding(contract, request, is_ephemeral=self.ephemeral)
        identity = resolve_lifecycle_identity(contract, request, is_ephemeral=self.ephemeral)
        if (
            request.get("worker_candidate_ingress")
            and str(request.get("contract_kind") or "") == ContractKind.TRACKED_TASK_CARD.value
        ):
            requested_card_path = request.get("task_card_path")
            if not requested_card_path or not request.get("task_card_hash"):
                raise RuntimeError("TASK_CARD_BINDING_MISMATCH: tracked path/hash pair required")
            if (
                identity.get("contract_kind") != ContractKind.TRACKED_TASK_CARD.value
                or identity.get("task_card_path") != str(_resolve_task_card_path(requested_card_path))
                or identity.get("task_card_hash") != request.get("task_card_hash")
            ):
                raise RuntimeError("TASK_CARD_BINDING_MISMATCH: tracked identity drifted")
        collaboration_provenance = CollaborationRealmVerifier.verify_submission(contract)
        if autonomy_grant is not None:
            if autonomy_grant.collaboration_base.head_sha != contract.controller_revision:
                raise ValueError("AUTONOMY_COLLABORATION_BASE_MISMATCH")
            try:
                scope_allowed = all(
                    autonomy_grant.path_policy.allows(str(path).rstrip("/"))
                    for path in contract.allowed_files
                )
            except ValueError as exc:
                raise ValueError("AUTONOMY_TASK_SCOPE_INVALID") from exc
            if not scope_allowed:
                raise ValueError("AUTONOMY_TASK_SCOPE_EXCEEDED")
            if contract.collaboration_realm is not None:
                collaboration = contract.collaboration_realm.collaboration
                if autonomy_grant.repository != collaboration.repository:
                    raise ValueError("AUTONOMY_COLLABORATION_REPOSITORY_MISMATCH")
                if autonomy_grant.collaboration_base != collaboration.base:
                    raise ValueError("AUTONOMY_COLLABORATION_BASE_MISMATCH")
        existing_states = list(self._submission_task_states().values())
        for current in existing_states:
            current_key = str(current.get("idempotency_key") or "")
            if idempotency_key and current_key == idempotency_key:
                current_hash = str(current.get("action_request_hash") or "")
                if current_hash and action_request_hash and current_hash != action_request_hash:
                    raise ValueError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
                return {
                    **self._with_task_action(current),
                    "duplicate": True,
                    "duplicate_action_id": current.get("action_id"),
                    "idempotency_key": idempotency_key,
                }
            if (
                current.get("task_id") != contract.task_id
                and identity.get("task_card_hash")
                and current.get("task_card_hash") == identity["task_card_hash"]
                and current.get("status") not in {"SUPERSEDED", "CANCELLED"}
            ):
                existing = self._with_task_action(current)
                return {
                    **existing,
                    "duplicate": {
                        "code": "DUPLICATE_LOGICAL_TASK",
                        "existing_task_id": current.get("task_id"),
                        "next_action": (existing.get("task_action") or {}).get("next_action"),
                        "recommended_tool": (existing.get("task_action") or {}).get("recommended_tool"),
                    },
                }
            if current.get("status") in TERMINAL_STATUSES:
                continue
            current_controller = (current.get("contract") or {}).get("controller_repo_root")
            if current_controller and Path(current_controller).resolve() != Path(contract.controller_repo_root).resolve():
                raise RuntimeError("active Controller lease belongs to a different controller worktree")
            if (
                current.get("task_id") != contract.task_id
                and current.get("status") in {"TARGET_LEASED", "WORKER_RUNNING", "WORKER_COMPLETED", "CANDIDATE_CAPTURED", "VERIFIED"}
                and not request.get("competition_id")
            ):
                raise RuntimeError("serial Target budget exceeded: another task owns the active Target")
        attempt_id = attempt_id_hint if action else uuid4().hex
        now = _utc_now()
        state: dict[str, Any] = {
            "schema": "nexus.self_hosted_task_state.v1",
            "task_id": contract.task_id,
            "status": "SUBMITTED",
            "submitted_at": now,
            "lifecycle_revision": identity["lifecycle_revision"],
            "lifecycle_executable_path": identity["lifecycle_executable_path"],
            "worker_module_path": identity["worker_module_path"],
            "controller_revision": identity["controller_revision"],
            "contract_kind": identity.get("contract_kind", ContractKind.NONE.value),
            "contract_hash": identity.get("contract_hash"),
            "owner_inline_contract": identity.get("owner_inline_contract"),
            "task_card_path": (
                request.get("task_card_path")
                if request.get("worker_candidate_ingress")
                and identity.get("contract_kind") == ContractKind.TRACKED_TASK_CARD.value
                else identity["task_card_path"]
            ),
            "task_card_hash": identity["task_card_hash"],
            "status_history": [{"status": "SUBMITTED", "at": now}],
            "request": _jsonable(state_request),
            "action": _jsonable(dict(action)) if action else None,
            "action_id": action_id or None,
            "attempt_id_hint": attempt_id_hint or None,
            "idempotency_key": idempotency_key or None,
            "action_request_hash": action_request_hash or None,
            "contract": contract.model_dump(mode="json"),
            "contract_hash": contract.contract_hash,
            "controller_worktree": contract.controller_repo_root,
            "controller_revision": contract.controller_revision,
            "controller_status_sha256": None,
            "target_worktree": contract.target_repo_root,
            "target_initial_revision": contract.target_base_revision,
            "target_branch": f"nexus/task/{contract.task_id}",
            "target_created_at": None,
            "worker_provider": (
                None
                if tracked_dispatch_required and dispatch_binding is None
                else contract.preferred_provider
            ),
            "selected_worker_id": (
                dispatch_binding["worker_id"]
                if dispatch_binding
                else None if tracked_dispatch_required else request.get("worker_id")
            ),
            "selected_provider": (
                dispatch_binding["provider"]
                if dispatch_binding
                else None if tracked_dispatch_required else contract.preferred_provider
            ),
            "selected_model": (
                dispatch_binding["model"]
                if dispatch_binding
                else None if tracked_dispatch_required else str(request.get("model") or "")
            ),
            "provider_order": (
                []
                if tracked_dispatch_required and dispatch_binding is None
                else list(contract.provider_order)
            ),
            "workforce_dispatch": dispatch_binding,
            "canonical_dispatch_envelope": (
                dispatch_binding.get("canonical_dispatch_envelope")
                if dispatch_binding else None
            ),
            "workforce_policy_hash": dispatch_binding["policy_hash"] if dispatch_binding else None,
            "workforce_binding_hash": dispatch_binding["binding_hash"] if dispatch_binding else None,
            "workforce_aggregate_binding_hash": dispatch_binding["aggregate_binding_hash"] if dispatch_binding else None,
            "fallback_lineage": [],
            "execution_lane": lane["execution_lane"],
            "execution_lane_blockers": lane["blockers"],
            "worker_selection_mode": str(
                request.get(
                    "worker_selection_mode",
                    "auto" if str(request.get("worker", "codex")).strip().lower() == "auto" else "explicit",
                )
            ),
            "attempt_id": attempt_id,
            "attempts": [{
                "attempt_id": attempt_id,
                "action_id": action_id or None,
                "idempotency_key": idempotency_key or None,
                "action_request_hash": action_request_hash or None,
                "started_at": now,
            }],
            "worker_pid": None,
            "worker_pgid": None,
            "worker_child_pgid": None,
            "worker_started_at": None,
            "worker_finished_at": None,
            "heartbeat_at": now,
            "updated_at": now,
            "promotion_status": "NOT_CREATED",
            "execution_authority": (
                "EPHEMERAL_TEST_RUNNER"
                if self._custom_runner is not None
                else "WORKER_REGISTRY"
            ),
            "provider_receipt_authoritative": self._custom_runner is None,
            "workforce_admission_authoritative": self._custom_runner is None,
            "public_claim_allowed": False,
            "production_ready": False,
            "execution_outcome": None,
            "verification_verdict": None,
            "candidate_commit_sha": None,
            "candidate_tree_sha": None,
            "candidate_ref": None,
            "candidate_state_hash": None,
            "verified_receipt_hash": None,
            "salvage_commit_sha": None,
            "salvage_ref": None,
            "salvage_only": False,
            "promotion_eligible": False,
            "approved_binding": None,
            "integration_branch": None,
            "integration_base_sha": None,
            "integration_result_sha": None,
            "terminal_status": None,
            "cleanup_eligible": False,
            "cleanup_decision": None,
            "cleanup_blocker": None,
            "cleanup_performed": False,
            "cleanup_performed_at": None,
            "state_retention_status": "ACTIVE",
            "archive_eligible": False,
            "archive_location": None,
            "merge_performed": False,
            "push_performed": False,
            "collaboration_realm": (
                contract.collaboration_realm.model_dump(mode="json")
                if contract.collaboration_realm is not None else None
            ),
            "submission_collaboration_provenance": collaboration_provenance or None,
            "collaboration_provenance": collaboration_provenance or None,
        }
        if autonomy_grant is not None:
            autonomy_binding = AutonomySubmissionBinding.issue(
                task_id=contract.task_id,
                initial_attempt_id=attempt_id,
                action_request_hash=action_request_hash,
                contract_hash=contract.contract_hash,
                controller_revision=contract.controller_revision,
                repository=autonomy_grant.repository,
                collaboration_base=autonomy_grant.collaboration_base,
                allowed_paths=tuple(
                    str(path).rstrip("/") for path in contract.allowed_files
                ),
                goal_id=autonomy_grant.goal_id,
                grant_hash=autonomy_grant.grant_hash,
            )
            state.update({
                "autonomy_goal_id": autonomy_grant.goal_id,
                "autonomy_goal_grant_hash": autonomy_grant.grant_hash,
                "autonomy_mode": "SHADOW",
                "autonomy_submission_binding": autonomy_binding.model_dump(
                    mode="json"
                ),
            })
        existing, created = self._create_state(contract.task_id, state)
        if not created:
            _validate_existing_autonomy_binding(existing, autonomy_grant)
            retained_retry = (
                existing.get("status") == "RETAINED_FOR_REVIEW"
                and existing.get("promotion_status") == "NOT_CREATED"
                and existing.get("cleanup_decision") in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
                and not (existing.get("promotion_packet") or existing.get("candidate_commit_sha") or existing.get("candidate_ref"))
            )
            terminal_retry = existing.get("status") in {
                "FINAL_BLOCK", "REJECTED", "SUPERSEDED", "CANCELLED",
                "INTEGRATION_FAILED", "INTEGRATED",
            } or retained_retry
            contract_refreshed = existing.get("contract_hash") != contract.contract_hash
            if contract_refreshed and not (
                terminal_retry
                and existing.get("cleanup_decision") in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
                and self._terminal_retry_revision_refresh_allowed(existing, request, contract)
            ):
                raise ValueError("task_id already exists with a different contract")
            if existing.get("status") in PENDING_CANDIDATE_STATUSES or existing.get("promotion_status") in {"PENDING_HUMAN_APPROVAL", "APPROVED"}:
                return existing
            if terminal_retry:
                if existing.get("cleanup_decision") not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}:
                    raise RuntimeError("terminal retry blocked until previous Target disposition")
                existing = self._reactivate_archived_state(contract.task_id, existing)
                attempt_id = attempt_id_hint or uuid4().hex
                def retry(current: dict[str, Any]) -> None:
                    packet = current.get("promotion_packet") or {}
                    if packet.get("candidate_commit_sha") or current.get("candidate_ref"):
                        current.setdefault("candidate_history", []).append({
                            "candidate_commit": packet.get("candidate_commit_sha"),
                            "candidate_ref": current.get("candidate_ref"),
                            "candidate_state_hash": packet.get("candidate_state_hash"),
                            "verified_receipt_hash": packet.get("verified_receipt_hash"),
                            "approval_binding": current.get("approved_binding"),
                            "integration_branch": current.get("integration_branch"),
                            "integration_commit": current.get("integration_result_sha"),
                            "final_disposition": current.get("final_disposition") or current.get("status"),
                        })
                    if contract_refreshed:
                        previous_contract = current.get("contract") or {}
                        retry_collaboration_provenance = (
                            CollaborationRealmVerifier.verify_submission(contract) or None
                        )
                        current.setdefault("contract_history", []).append({
                            "attempt_id": current.get("attempt_id"),
                            "contract_hash": current.get("contract_hash"),
                            "controller_revision": previous_contract.get("controller_revision"),
                            "target_base_revision": previous_contract.get("target_base_revision"),
                            "final_disposition": current.get("final_disposition") or current.get("status"),
                        })
                        current.update({
                            "request": _jsonable(dict(request)),
                            "contract": contract.model_dump(mode="json"),
                            "contract_hash": contract.contract_hash,
                            "controller_worktree": contract.controller_repo_root,
                            "controller_revision": contract.controller_revision,
                            "controller_status_sha256": None,
                            "target_worktree": contract.target_repo_root,
                            "target_initial_revision": contract.target_base_revision,
                            "target_branch": f"nexus/task/{contract.task_id}",
                            "target_created_at": None,
                            "worker_provider": contract.preferred_provider,
                            "collaboration_realm": (
                                contract.collaboration_realm.model_dump(mode="json")
                                if contract.collaboration_realm is not None else None
                            ),
                            "submission_collaboration_provenance": retry_collaboration_provenance,
                            "collaboration_provenance": retry_collaboration_provenance,
                        })
                    current.update({
                        "request": _jsonable(state_request),
                        "action": _jsonable(dict(action)) if action else None,
                        "action_id": action_id or None,
                        "attempt_id_hint": attempt_id_hint or None,
                        "idempotency_key": idempotency_key or None,
                        "action_request_hash": action_request_hash or None,
                    })
                    if dispatch_binding is not None:
                        current.update({
                            "worker_provider": dispatch_binding["provider"],
                            "selected_worker_id": dispatch_binding["worker_id"],
                            "selected_provider": dispatch_binding["provider"],
                            "selected_model": dispatch_binding["model"],
                            "provider_order": [dispatch_binding["provider"]],
                            "workforce_dispatch": _jsonable(dispatch_binding),
                            "canonical_dispatch_envelope": _jsonable(
                                dispatch_binding.get("canonical_dispatch_envelope")
                            ),
                            "workforce_policy_hash": dispatch_binding["policy_hash"],
                            "workforce_binding_hash": dispatch_binding["binding_hash"],
                            "workforce_aggregate_binding_hash": dispatch_binding[
                                "aggregate_binding_hash"
                            ],
                        })
                    # Enforce the task-scoped attempt ceiling before mutating
                    # durable lineage.  A rejected retry must not append a
                    # phantom attempt or reset any aggregate budgets.
                    max_attempts = int(getattr(contract, "maximum_attempts_per_task", 1) or 1)
                    if len(current.get("attempts") or ()) >= max_attempts:
                        raise RuntimeError("ATTEMPT_BUDGET_EXHAUSTED")
                    current["attempt_id"] = attempt_id
                    current.setdefault("attempts", []).append({
                        "attempt_id": attempt_id,
                        "action_id": action_id or None,
                        "idempotency_key": idempotency_key or None,
                        "action_request_hash": action_request_hash or None,
                        "canonical_dispatch_envelope": _jsonable(
                            dispatch_binding.get("canonical_dispatch_envelope")
                        )
                        if dispatch_binding is not None
                        else None,
                        "workforce_dispatch": _jsonable(dispatch_binding),
                        "started_at": now,
                    })
                    current["status"] = "SUBMITTED"
                    current.setdefault("status_history", []).append({"status": "ATTEMPT_INCREMENTED", "at": now})
                    current["lease"] = None
                    current["worker_pid"] = None
                    current["worker_pgid"] = None
                    current["worker_child_pgid"] = None
                    current["worker_started_at"] = None
                    current["worker_finished_at"] = None
                    current["worker_preflight"] = None
                    current["heartbeat_at"] = now
                    current["error"] = None
                    current["active_provider"] = None
                    current["execution"] = None
                    # Keep immutable execution history across retries so
                    # aggregate provider calls/attempts cannot be reset.
                    # ``execution`` below is the current attempt only.
                    current["execution_outcome"] = None
                    current["attempt_resolution"] = None
                    current["verification_verdict"] = None
                    current["promotion_status"] = "NOT_CREATED"
                    current["candidate_status"] = None
                    current["candidate"] = None
                    current["candidate_commit_sha"] = None
                    current["candidate_tree_sha"] = None
                    current["candidate_ref"] = None
                    current["candidate_state_hash"] = None
                    current["verified_receipt_hash"] = None
                    current["salvage_commit_sha"] = None
                    current["salvage_ref"] = None
                    current["salvage_only"] = False
                    current["promotion_eligible"] = False
                    current["verified_receipt"] = None
                    current["promotion_packet"] = None
                    current["approved_binding"] = None
                    current["integration_branch"] = None
                    current["integration_base_sha"] = None
                    current["integration_result_sha"] = None
                    current["integration_receipt"] = None
                    current["final_disposition"] = None
                    current["terminal_status"] = None
                    current["cleanup_eligible"] = False
                    current["cleanup_decision"] = None
                    current["cleanup_blocker"] = None
                    current["cleanup_performed"] = False
                    current["cleanup_performed_at"] = None
                    current["state_retention_status"] = "ACTIVE"
                    current["archive_eligible"] = False
                    current["archive_location"] = None
                    current["merge_performed"] = False
                    current["push_performed"] = False
                self._mutate_state(contract.task_id, retry)
                return self._launch_worker(contract.task_id, attempt_id) or self._with_task_action(existing)
            return self.reconcile_task(contract.task_id) or existing
        return self._launch_worker(contract.task_id, attempt_id) or self._with_task_action(state)

    def retry_task(self, task_id: str) -> dict[str, Any]:
        """Retry one durable task without creating a second task or Target.

        Only a terminal task whose previous Target disposition is already
        removed/cleaned may be reactivated. Active, pending, and retained
        tasks return a structured block so callers do not blindly resubmit.
        """
        state = self._read_state_snapshot(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("state_valid") is False:
            return {
                **state,
                "retry": {
                    "task_id": task_id,
                    "previous_status": state.get("status"),
                    "previous_attempt_id": None,
                    "decision": "BLOCKED_INVALID_STATE",
                    "blocker": (state.get("blocker") or {}).get("code"),
                },
            }

        status = str(state.get("status") or "UNKNOWN")
        cleanup_decision = str(state.get("cleanup_decision") or "")
        retry_meta = {
            "task_id": task_id,
            "previous_status": status,
            "previous_attempt_id": state.get("attempt_id"),
            "decision": None,
            "blocker": None,
        }
        try:
            retry_contract = self.build_contract(state.get("request") or {})
            max_attempts = int(getattr(retry_contract, "maximum_attempts_per_task", 1) or 1)
            if len(state.get("attempts") or ()) >= max_attempts:
                retry_meta.update(decision="BLOCK", blocker="ATTEMPT_BUDGET_EXHAUSTED")
                return {**state, "retry": retry_meta}
        except Exception:
            pass
        retained_retry = (
            status == "RETAINED_FOR_REVIEW"
            and state.get("promotion_status") == "NOT_CREATED"
            and cleanup_decision in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
            and not (state.get("promotion_packet") or state.get("candidate_commit_sha") or state.get("candidate_ref"))
        )
        if status == "RETAINED_FOR_REVIEW" and not retained_retry:
            retry_meta.update(
                decision="BLOCKED_RETAINED_REVIEW",
                blocker="human disposition or retained-candidate recovery is required before retry; clean no-Candidate retention may retry only after formal cleanup",
            )
            return {**state, "retry": retry_meta}
        if status not in TERMINAL_STATUSES:
            retry_meta.update(
                decision="NO_DUPLICATE_ACTIVE_TASK",
                blocker=f"task is {status}; wait for its existing attempt instead of resubmitting",
            )
            return {**state, "retry": retry_meta}
        if cleanup_decision not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}:
            retry_meta.update(
                decision="BLOCKED_TARGET_DISPOSITION",
                blocker="previous Target disposition is not removed/cleaned",
            )
            return {**state, "retry": retry_meta}

        request = state.get("request")
        if not isinstance(request, Mapping):
            retry_meta.update(
                decision="BLOCKED_MISSING_REQUEST",
                blocker="durable request is missing; cannot safely reconstruct the task",
            )
            return {**state, "retry": retry_meta}
        # A REPAIRABLE acceptance must rebind through the canonical Planner /
        # Workforce admission envelope; caller-supplied worker identity is
        # never accepted as a selector.
        repair_dispatch: Optional[dict[str, Any]] = None
        if str(state.get("acceptance_decision") or "") == "REPAIRABLE":
            planner = request.get("planner_output")
            if not isinstance(planner, Mapping):
                return {**state, "retry": {**retry_meta, "decision": "BLOCK", "blocker": "WORKFORCE_ADMISSION_BINDING_MISSING"}}
            try:
                dispatch = validate_workforce_dispatch_binding({**request, "planner_output": planner}, require_binding=True)
            except RuntimeError as exc:
                return {**state, "retry": {**retry_meta, "decision": "BLOCK", "blocker": str(exc)}}
            worker_id = str((dispatch or {}).get("worker_id") or "")
            if not worker_id:
                return {**state, "retry": {**retry_meta, "decision": "BLOCK", "blocker": "WORKFORCE_REPAIR_WORKER_MISSING"}}
            request = dict(request)
            request["repair_worker_id"] = worker_id
            repair_dispatch = dict(dispatch or {})

        # Generate fresh attempt transport identity first, then rebuild the
        # canonical dispatch envelope against that identity.  The old receipt
        # and binding remain immutable in history; a mismatch blocks before
        # any worker invocation.
        retry_source = dict(state)
        retry_source["request"] = request
        retry_request = _retry_request(retry_source)
        if repair_dispatch is not None:
            retry_request = dict(retry_request)
            retry_request["planner_output"] = request.get("planner_output")
            try:
                retry_request["canonical_dispatch_envelope"] = build_canonical_dispatch_envelope(
                    request["planner_output"],
                    {
                        **repair_dispatch,
                        "demand_id": repair_dispatch.get("demand_id"),
                    },
                    task_id=str(retry_request.get("task_id") or ""),
                    attempt_id=str(retry_request.get("attempt_id") or ""),
                    task_card_path=str(retry_request.get("task_card_path") or ""),
                    task_card_hash=str(retry_request.get("task_card_hash") or ""),
                ).to_dict()
            except (TypeError, ValueError) as exc:
                return {**state, "retry": {**retry_meta, "decision": "BLOCK", "blocker": f"WORKFORCE_REBIND_FAILED:{exc}"}}
            fresh_dispatch = validate_workforce_dispatch_binding(
                retry_request, require_binding=True
            )
            if not isinstance(fresh_dispatch, Mapping):
                return {**state, "retry": {**retry_meta, "decision": "BLOCK", "blocker": "WORKFORCE_REBIND_FAILED"}}
            retry_request.update({
                "worker": fresh_dispatch["provider"],
                "provider": fresh_dispatch["provider"],
                "model": fresh_dispatch["model"],
                "worker_id": fresh_dispatch["worker_id"],
                "worker_order": [fresh_dispatch["provider"]],
                "workforce_dispatch": fresh_dispatch,
                "canonical_dispatch_envelope": fresh_dispatch.get("canonical_dispatch_envelope"),
            })
        result = dict(self.submit_task(retry_request))
        retry_meta.update(
            decision="REUSED_TASK_ID",
            new_attempt_id=result.get("attempt_id"),
            new_action_id=result.get("action_id"),
            new_idempotency_key=result.get("idempotency_key"),
            attempts=len(result.get("attempts") or ()),
        )
        result["retry"] = retry_meta
        return result

    @staticmethod
    def _pre_apply_rejection_evidence(
        state: Mapping[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Return exact evidence permitting rejection of a stale pre-apply Candidate.

        A failed pre-apply integration is not a normal pending Candidate.  It
        may be rejected only after the durable record proves that no apply,
        result, or integration receipt exists, the owned Target was removed,
        and every Candidate identity remains bound across the packet and the
        consumed approval.  This helper is deliberately narrow: it never
        authorizes SUPERSEDED or any post-apply disposition.
        """
        if (
            state.get("status") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("promotion_status") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("terminal_status") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("final_disposition") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("integration_status") != "NOT_APPLIED"
            or state.get("merge_performed") is not False
            or state.get("integration_result_sha")
            or state.get("integration_receipt")
            or state.get("cleanup_decision") not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
            or state.get("cleanup_performed") is not True
            or state.get("reconciliation_status") != "RECONCILED"
            or state.get("reconciliation_decision") != "RESTORE_NATIVE_PRE_APPLY_STATUS"
        ):
            return None
        reconciliation_history = state.get("integration_reconciliation_history")
        status_history = state.get("status_history")
        if (
            not isinstance(reconciliation_history, list)
            or not reconciliation_history
            or not isinstance(reconciliation_history[-1], Mapping)
            or not isinstance(status_history, list)
            or not status_history
            or not isinstance(status_history[-1], Mapping)
            or status_history[-1].get("status") != "INTEGRATION_FAILED_PRE_APPLY"
            or status_history[-1].get("reason") != "projected_pre_apply_reconciled"
            or not str(state.get("integration_error") or "").strip()
        ):
            return None
        # Reuse the strict legacy projection validator as the evidence oracle:
        # a reconciled native state must still prove the exact projection that
        # was restored, including closure, acceptance, preview, authorization,
        # consumed grant, history, and execution bindings.
        projected = dict(state)
        projected_history = list(status_history)
        projected_history.pop()
        projected.update({
            "status": "FINAL_BLOCK",
            "promotion_status": "NOT_CREATED",
            "status_history": projected_history,
        })
        projection = SelfHostedTaskService._projected_pre_apply_recovery_evidence(projected)
        if projection is None:
            return None
        recorded = reconciliation_history[-1]
        if (
            recorded.get("decision") != "RESTORE_NATIVE_PRE_APPLY_STATUS"
            or recorded.get("projection_sha256") != projection.get("projection_sha256")
            or any(recorded.get(key) != value for key, value in projection.items())
        ):
            return None
        execution = state.get("integration_execution")
        packet = state.get("promotion_packet")
        approved = state.get("approved_binding")
        if not all(isinstance(value, Mapping) and value for value in (execution, packet, approved)):
            return None
        if (
            execution.get("stage") != "PRE_APPLY"
            or execution.get("merge_performed") is not False
            or execution.get("post_apply_verified") is not False
            or execution.get("branch_head_before") != execution.get("branch_head_after")
        ):
            return None
        identity = {
            "task_id": str(state.get("task_id") or ""),
            "attempt_id": str(state.get("attempt_id") or ""),
            "candidate_commit_sha": str(packet.get("candidate_commit_sha") or ""),
            "candidate_tree_sha": str(packet.get("candidate_tree_sha") or ""),
            "candidate_state_hash": str(packet.get("candidate_state_hash") or ""),
            "verified_receipt_hash": str(packet.get("verified_receipt_hash") or ""),
        }
        candidate_ref = str(state.get("candidate_ref") or "")
        if (
            not all(identity.values())
            or not re.fullmatch(
                rf"refs/nexus-candidates/{re.escape(identity['task_id'])}/{re.escape(identity['candidate_commit_sha'])}",
                candidate_ref,
            )
        ):
            return None
        for key in (
            "candidate_commit_sha",
            "candidate_tree_sha",
            "candidate_state_hash",
            "verified_receipt_hash",
        ):
            if str(approved.get(key) or "") != identity[key]:
                return None
        if (
            str(approved.get("bound_task_id") or identity["task_id"]) != identity["task_id"]
            or str(approved.get("bound_attempt_id") or identity["attempt_id"]) != identity["attempt_id"]
        ):
            return None
        return {
            **identity,
            "candidate_ref": candidate_ref,
            "cleanup_decision": str(state["cleanup_decision"]),
            "cleanup_performed": True,
            "stage": "PRE_APPLY",
            "merge_performed": False,
            "integration_status": "NOT_APPLIED",
        }

    def dispose_candidate(
        self,
        task_id: str,
        *,
        disposition: str,
        superseded_by: Optional[str] = None,
    ) -> dict[str, Any]:
        disposition = disposition.upper()
        if disposition not in {"REJECTED", "SUPERSEDED"}:
            raise ValueError("candidate disposition must be REJECTED or SUPERSEDED")
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if str(state.get("task_id") or "") != task_id:
            raise RuntimeError("CLOSURE_TASK_ID_DRIFT")
        if disposition == "REJECTED" and state.get("status") == "REJECTED":
            history = state.get("candidate_history") or []
            if history and isinstance(history[-1], Mapping) and history[-1].get("pre_apply_disposition_basis"):
                return {**state, "duplicate": True}
        pre_apply_basis = None
        if disposition == "REJECTED" and state.get("status") == "INTEGRATION_FAILED_PRE_APPLY":
            pre_apply_basis = self._pre_apply_rejection_evidence(state)
            if pre_apply_basis is None:
                raise RuntimeError("PRE_APPLY_REJECTION_EVIDENCE_REQUIRED")
        if state.get("promotion_status") not in {"PENDING_HUMAN_APPROVAL", "APPROVED"}:
            if pre_apply_basis is None:
                raise RuntimeError("candidate is not pending disposition")
        candidate_record = {
            "candidate_commit": (state.get("promotion_packet") or {}).get("candidate_commit_sha"),
            "candidate_ref": state.get("candidate_ref"),
            "candidate_state_hash": (state.get("promotion_packet") or {}).get("candidate_state_hash"),
            "verified_receipt_hash": (state.get("promotion_packet") or {}).get("verified_receipt_hash"),
            "approval_binding": state.get("approved_binding"),
            "final_disposition": disposition,
            "supersedes": state.get("supersedes"),
            "superseded_by": superseded_by if disposition == "SUPERSEDED" else None,
        }
        if pre_apply_basis is not None:
            candidate_record["pre_apply_disposition_basis"] = pre_apply_basis
        return self._checkpoint(task_id, disposition, {
            "promotion_status": disposition,
            "candidate_status": disposition,
            "final_disposition": disposition,
            "superseded_by": superseded_by if disposition == "SUPERSEDED" else None,
            "candidate_history": [*state.get("candidate_history", []), candidate_record],
            "terminal_status": disposition,
            "cleanup_decision": state.get("cleanup_decision", "REMOVED"),
            "cleanup_performed": state.get("cleanup_performed", True),
            "state_retention_status": "TERMINAL",
            "archive_eligible": True,
        }, attempt_id=state.get("attempt_id")) or state

    def close_task_without_candidate(
        self,
        task_id: str,
        *,
        superseded_by: str,
    ) -> dict[str, Any]:
        if not superseded_by or not str(superseded_by).strip():
            raise ValueError("superseded_by evidence identifier is required and non-empty")
        superseded_by = str(superseded_by).strip()

        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")

        if state.get("status") not in {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}:
            raise RuntimeError(f"task {task_id} is not in RETAINED_FOR_REVIEW or FINAL_BLOCK status")

        if state.get("promotion_status") != "NOT_CREATED":
            raise RuntimeError("promotion_status must be NOT_CREATED")

        packet = state.get("promotion_packet") or {}
        candidate_commit = packet.get("candidate_commit_sha") or state.get("candidate_commit_sha")
        candidate_ref = state.get("candidate_ref")
        candidate_dict = state.get("candidate") or {}
        candidate_created = (
            state.get("candidate_commit_created")
            or packet.get("candidate_commit_created")
            or candidate_dict.get("commit_created")
        )
        if (
            packet
            or candidate_commit
            or candidate_ref
            or candidate_created
        ):
            raise RuntimeError("task has candidate evidence present")

        worker_pid = state.get("worker_pid")
        if worker_pid and self._pid_alive(int(worker_pid)):
            raise RuntimeError("active worker process is running for task")

        child_pgid = state.get("worker_child_pgid")
        if child_pgid and self._pid_alive(int(child_pgid)):
            raise RuntimeError("active worker child process is running for task")

        contract = state.get("contract") or {}
        lease = state.get("lease") or {}
        target_raw = state.get("target_worktree") or lease.get("target_worktree") or contract.get("target_repo_root")
        cleanup_values: dict[str, Any] = {
            "cleanup_decision": state.get("cleanup_decision") or "ALREADY_REMOVED",
            "cleanup_eligible": state.get("cleanup_eligible", True),
            "cleanup_performed": state.get("cleanup_performed", False),
            "cleanup_performed_at": state.get("cleanup_performed_at"),
        }
        if target_raw:
            target_path = Path(str(target_raw)).expanduser().resolve()
            controller_raw = state.get("controller_worktree") or contract.get("controller_repo_root")
            lease_object = TargetWorktreeLease(**dict(lease)) if lease else None
            if target_path.exists() and (not controller_raw or not lease_object):
                raise RuntimeError(f"recorded Target path exists: {target_path}")
            if target_path.exists() and controller_raw and lease_object:
                controller_path = Path(str(controller_raw)).expanduser().resolve()
                if not controller_path.is_dir():
                    raise RuntimeError(f"recorded Target path exists: {target_path}")
                manager = WorktreeManager(
                    root_dir=str(contract.get("target_worktree_root") or target_path.parent)
                )
                entry = manager._worktree_entry(controller_path, target_path)
                if entry is not None:
                    if state.get("status") != "RETAINED_FOR_REVIEW":
                        raise RuntimeError(f"recorded Target path exists: {target_path}")
                    has_recorded_salvage = bool(
                        state.get("salvage_commit_sha") and state.get("salvage_ref")
                    )
                    target_dirty = bool(manager._status_bytes(target_path))
                    if not target_dirty and not has_recorded_salvage:
                        target_head = manager._run_git(["rev-parse", "HEAD"], cwd=target_path)
                        if target_head != lease_object.initial_head:
                            raise RuntimeError(
                                "recorded clean Target HEAD changed without durable snapshot"
                            )
                    self._require_integrated_replacement(task_id, superseded_by)
                    salvage = {
                        "salvage_commit_sha": state.get("salvage_commit_sha"),
                        "salvage_ref": state.get("salvage_ref"),
                        "salvage_only": state.get("salvage_only"),
                        "promotion_eligible": state.get("promotion_eligible"),
                    }
                    try:
                        if not salvage["salvage_commit_sha"] or not salvage["salvage_ref"]:
                            if target_dirty:
                                salvage = manager.create_salvage_snapshot(
                                    self._contract_from_state(state),
                                    lease_object,
                                    str(state.get("attempt_id") or ""),
                                )
                            else:
                                salvage = {}
                        elif salvage["salvage_only"] is not True or salvage["promotion_eligible"] is not False:
                            raise RuntimeError("recorded salvage metadata is invalid")
                        if salvage:
                            self._checkpoint(
                                task_id,
                                "RETAINED_FOR_REVIEW",
                                {
                                    **salvage,
                                    "promotion_status": "NOT_CREATED",
                                    "superseded_by": superseded_by,
                                    "cleanup_decision": "SALVAGED",
                                    "cleanup_blocker": None,
                                    "cleanup_performed": False,
                                    "cleanup_eligible": False,
                                    "state_retention_status": "TERMINAL",
                                },
                                attempt_id=state.get("attempt_id"),
                            )
                            cleanup = manager.cleanup_terminal_target(
                                self._contract_from_state(state),
                                lease_object,
                                salvage_commit=str(salvage["salvage_commit_sha"]),
                                salvage_ref=str(salvage["salvage_ref"]),
                            )
                        else:
                            cleanup = manager.cleanup_terminal_target(
                                self._contract_from_state(state),
                                lease_object,
                            )
                    except Exception as exc:
                        retained = self._checkpoint(
                            task_id,
                            "RETAINED_FOR_REVIEW",
                            {
                                **salvage,
                                "promotion_status": "NOT_CREATED",
                                "superseded_by": superseded_by,
                                "cleanup_decision": "CLEANUP_BLOCKED",
                                "cleanup_blocker": str(exc),
                                "cleanup_performed": False,
                                "cleanup_eligible": False,
                                "state_retention_status": "TERMINAL",
                            },
                            attempt_id=state.get("attempt_id"),
                        ) or state
                        return retained
                    if cleanup.decision not in {"REMOVED", "ALREADY_REMOVED"}:
                        return self._checkpoint(
                            task_id,
                            "RETAINED_FOR_REVIEW",
                            {
                                **salvage,
                                "promotion_status": "NOT_CREATED",
                                "superseded_by": superseded_by,
                                "cleanup_decision": cleanup.decision,
                                "cleanup_blocker": cleanup.blocker,
                                "cleanup_performed": cleanup.performed,
                                "cleanup_eligible": cleanup.eligible,
                                "state_retention_status": "TERMINAL",
                            },
                            attempt_id=state.get("attempt_id"),
                        ) or state
                    cleanup_values = {
                        "cleanup_decision": cleanup.decision,
                        "cleanup_eligible": cleanup.eligible,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                        **salvage,
                    }
                else:
                    cleanup = manager.cleanup_terminal_target(
                        self._contract_from_state(state),
                        lease_object,
                    )
                    if cleanup.decision not in {"REMOVED", "ALREADY_REMOVED"}:
                        raise RuntimeError(f"recorded Target path exists: {target_path}")
                    cleanup_values = {
                        "cleanup_decision": cleanup.decision,
                        "cleanup_eligible": cleanup.eligible,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                    }

        return self._checkpoint(
            task_id,
            "SUPERSEDED",
            {
                "promotion_status": "NOT_CREATED",
                "final_disposition": "SUPERSEDED",
                "superseded_by": superseded_by,
                "terminal_status": "SUPERSEDED",
                "state_retention_status": "TERMINAL",
                "archive_eligible": True,
                "merge_performed": False,
                "push_performed": False,
                **cleanup_values,
            },
            attempt_id=state.get("attempt_id"),
        ) or state

    close_without_candidate = close_task_without_candidate

    def close_retained_without_candidate(
        self,
        task_id: str,
        *,
        superseded_by: str,
    ) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")

        if state.get("status") != "RETAINED_FOR_REVIEW":
            raise RuntimeError(f"task {task_id} is not in RETAINED_FOR_REVIEW status")

        return self.close_task_without_candidate(task_id, superseded_by=superseded_by)

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("status") in TERMINAL_STATUSES:
            return state
        pid = state.get("worker_pid")
        if pid and self._pid_alive(int(pid)):
            raise RuntimeError("active process must stop before cancellation cleanup")
        cancelled = self._checkpoint(task_id, "CANCELLED", {
            "promotion_status": "CANCELLED",
            "terminal_status": "CANCELLED",
            "final_disposition": "CANCELLED",
            "state_retention_status": "TERMINAL",
            "archive_eligible": True,
            "push_performed": False,
        }, attempt_id=state.get("attempt_id")) or state
        result = self.cleanup_tasks(task_id=task_id, dry_run=False)
        return self._read_state(task_id) or {**cancelled, "cleanup": result}

    def lifecycle_status(self) -> dict[str, Any]:
        states = [
            state
            for path in sorted(self.state_dir.glob("*.json")) if self.state_dir.exists()
            if (state := self._read_state_snapshot(path.stem)) is not None
        ]
        invalid_states = [state for state in states if state.get("state_valid") is False]
        valid_states = [state for state in states if state.get("state_valid") is not False]

        def has_active_target(state: Mapping[str, Any]) -> bool:
            target_worktree = (state.get("lease") or {}).get("target_worktree")
            return bool(
                target_worktree
                and state.get("status") not in TERMINAL_STATUSES
                and Path(str(target_worktree)).is_dir()
            )

        return {
            "canonical_state_root": str(self.state_dir),
            "tasks": len(states),
            "active_tasks": sum(state.get("status") not in TERMINAL_STATUSES for state in valid_states),
            "active_targets": sum(has_active_target(state) for state in valid_states),
            "invalid_states": len(invalid_states),
            "blockers": [state["blocker"] for state in invalid_states],
        }

    def _cleanup_authority_blocker(
        self,
        state: Mapping[str, Any],
        contract: Any,
        lease: TargetWorktreeLease,
    ) -> Optional[str]:
        """Revalidate persisted acceptance, authorization, integration, and refs."""
        if state.get("status") != "INTEGRATED" or state.get("promotion_status") != "INTEGRATED":
            return "cleanup requires INTEGRATED lifecycle state"
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        binding = state.get("approved_binding") if isinstance(state.get("approved_binding"), Mapping) else {}
        raw_acceptance = state.get("external_acceptance") or binding.get("external_acceptance")
        raw_authorization = state.get("integration_authorization") or binding.get("integration_authorization")
        if raw_acceptance is None:
            return "external acceptance receipt is missing"
        if raw_authorization is None:
            return "Owner cleanup authorization is missing"
        try:
            acceptance = raw_acceptance if isinstance(raw_acceptance, ExternalAcceptanceReceipt) else ExternalAcceptanceReceipt(**dict(raw_acceptance))
            authorization = raw_authorization if isinstance(raw_authorization, IntegrationAuthorizationEnvelope) else IntegrationAuthorizationEnvelope(**{key: value for key, value in dict(raw_authorization).items() if key != "authorization_hash"})
        except (TypeError, ValueError) as exc:
            return f"cleanup authority binding invalid: {exc}"
        if acceptance.task_id != state.get("task_id") or acceptance.candidate_commit != packet.get("candidate_commit_sha"):
            return "external acceptance binding mismatch"
        if authorization.task_id != state.get("task_id") or authorization.candidate_commit != packet.get("candidate_commit_sha"):
            return "cleanup authorization candidate mismatch"
        if authorization.attempt_id not in {"", str(state.get("attempt_id") or "")}:
            return "cleanup authorization attempt mismatch"
        if authorization.acceptance_receipt_hash != acceptance.receipt_hash:
            return "cleanup authorization acceptance mismatch"
        if state.get("task_card_hash") and authorization.task_card_hash != state.get("task_card_hash"):
            return "cleanup authorization task card mismatch"
        if authorization.candidate_tree_sha != str(packet.get("candidate_tree_sha") or ""):
            return "cleanup authorization candidate tree mismatch"
        if authorization.candidate_state_hash != str(packet.get("candidate_state_hash") or ""):
            return "cleanup authorization candidate state mismatch"
        if "CLEANUP_OWNED_TARGET" not in authorization.action_set or not authorization.cleanup_requested:
            return "cleanup authorization does not include CLEANUP_OWNED_TARGET"
        grant = binding.get("approval_grant") if isinstance(binding.get("approval_grant"), Mapping) else None
        if not grant or not grant.get("consumed_at") or grant.get("approval_scope") != "ALLOW_ACTION_ONCE":
            return "one-shot Owner approval grant is missing or invalid"
        receipt = state.get("integration_receipt") if isinstance(state.get("integration_receipt"), Mapping) else None
        if not receipt or not receipt.get("verifier_passed") or not receipt.get("merge_performed") or not receipt.get("post_apply_verified"):
            return "post-apply integration receipt is missing or incomplete"
        if receipt.get("acceptance_receipt_hash") != acceptance.receipt_hash:
            return "integration receipt acceptance mismatch"
        if receipt.get("authorization_hash") != authorization.authorization_hash:
            return "integration receipt authorization mismatch"
        integration_sha = str(receipt.get("integration_commit_sha") or "")
        candidate_sha = str(packet.get("candidate_commit_sha") or "")
        if not integration_sha or integration_sha != str(state.get("integration_result_sha") or ""):
            return "integration receipt result binding is missing"
        controller = Path(contract.controller_repo_root).resolve()
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        candidate_ref = str(state.get("candidate_ref") or "")
        if not candidate_ref:
            return "candidate durable ref is missing"
        if authorization.durable_ref != candidate_ref:
            return "cleanup authorization durable ref mismatch"
        if Path(authorization.canonical_root).resolve() != controller:
            return "cleanup authorization canonical root mismatch"
        if str(state.get("integration_branch") or authorization.canonical_branch) != authorization.canonical_branch:
            return "cleanup authorization integration branch mismatch"
        try:
            if manager._run_git(["rev-parse", f"{candidate_ref}^{{commit}}"], cwd=controller) != candidate_sha:
                return "candidate durable ref mismatch"
            if manager._run_git(["merge-base", "--is-ancestor", candidate_sha, integration_sha], cwd=controller) is None:
                return "candidate is not an ancestor of integration result"
            branch = str(state.get("integration_branch") or authorization.canonical_branch)
            if manager._run_git(["merge-base", "--is-ancestor", integration_sha, branch], cwd=controller) is None:
                return "canonical branch does not contain integration result"
        except RuntimeError as exc:
            return f"integration ancestry/ref verification failed: {exc}"
        if Path(lease.target_worktree).resolve() != Path(authorization.cleanup_target_path).resolve():
            return "cleanup target path binding mismatch"
        return None

    def cleanup_tasks(self, *, task_id: Optional[str] = None, dry_run: bool = True) -> dict[str, Any]:
        ids = [task_id] if task_id else [path.stem for path in sorted(self.state_dir.glob("*.json"))]
        decisions = []
        for item in ids:
            state = (self._read_state_snapshot(item) if dry_run else self._read_state(item)) or {}
            if not dry_run and not self._state_path(item).exists():
                _, archived = self._latest_archived_state(item)
                if archived and archived.get("status") == "INTEGRATED":
                    state = self._reactivate_archived_state(item, archived)
            if not state:
                decisions.append({"task_id": item, "cleanup_decision": "ALREADY_REMOVED", "cleanup_blocker": "task state not found", "cleanup_performed": False})
                continue
            if state.get("status") == "INTEGRATION_VERIFY_FAILED_AFTER_APPLY":
                decision = {
                    "task_id": item,
                    "status": state.get("status"),
                    "cleanup_decision": "BLOCKED_BY_POST_APPLY_FAILURE",
                    "cleanup_blocker": "post-apply verification failed after physical integration apply",
                    "cleanup_performed": False,
                    "cleanup_eligible": False,
                    "target_present_after": True,
                }
                decisions.append(decision)
                if not dry_run:
                    self._checkpoint(item, str(state.get("status")), decision, attempt_id=state.get("attempt_id"))
                continue
            if state.get("status") == "INTEGRATION_FAILED_PRE_APPLY":
                decision = {
                    "task_id": item,
                    "status": state.get("status"),
                    "cleanup_decision": "BLOCKED_BY_PRE_APPLY_FAILURE",
                    "cleanup_blocker": "integration was not applied; retry integration before cleanup",
                    "cleanup_performed": False,
                    "cleanup_eligible": False,
                    "target_present_after": True,
                }
                decisions.append(decision)
                if not dry_run:
                    self._checkpoint(item, str(state.get("status")), decision, attempt_id=state.get("attempt_id"))
                continue
            if state.get("status") == "RETAINED_FOR_REVIEW":
                worker_pid = state.get("worker_pid")
                child_pgid = state.get("worker_child_pgid")
                if ((worker_pid and self._pid_alive(int(worker_pid))) or
                        (child_pgid and self._pid_alive(int(child_pgid)))):
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": "BLOCKED_BY_PROCESS",
                        "cleanup_blocker": "active process uses Target",
                        "cleanup_performed": False, "cleanup_eligible": False,
                    })
                    continue
                if not state.get("lease") or not state.get("request"):
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
                        "cleanup_blocker": "retained task lacks lease or request authority",
                        "cleanup_performed": False, "cleanup_eligible": False,
                    })
                    continue
                contract = self.build_contract(state["request"])
                lease = TargetWorktreeLease(**state["lease"])
                manager = WorktreeManager(root_dir=contract.target_worktree_root)
                target = Path(lease.target_worktree).resolve()
                controller = Path(contract.controller_repo_root).resolve()
                attempt_id = str(state.get("attempt_id") or "")
                if not attempt_id:
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
                        "cleanup_blocker": "retained task lacks attempt identity",
                        "cleanup_performed": False, "cleanup_eligible": False,
                    })
                    continue
                if dry_run:
                    entry = manager._worktree_entry(controller, target)
                    if not target.exists() and entry is None:
                        planned = "ALREADY_REMOVED"
                    elif entry is None:
                        planned = "BLOCKED_BY_UNSAVED_CHANGES"
                    elif manager.process_checker(target):
                        planned = "BLOCKED_BY_PROCESS"
                    else:
                        dirty = bool(manager._status_bytes(target))
                        head = manager._run_git(["rev-parse", "HEAD"], cwd=target)
                        if dirty:
                            planned = "WOULD_SALVAGE_AND_REMOVE"
                        elif head != lease.initial_head:
                            planned = "WOULD_PROTECT_HEAD_AND_REMOVE"
                        else:
                            planned = "WOULD_REMOVE"
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": planned,
                        "cleanup_blocker": None,
                        "cleanup_performed": False,
                        "cleanup_eligible": planned not in {
                            "BLOCKED_BY_PROCESS", "BLOCKED_BY_UNSAVED_CHANGES"
                        },
                    })
                    continue

                salvage_commit = state.get("salvage_commit_sha")
                salvage_ref = state.get("salvage_ref")
                salvage: dict[str, Any] = {}
                try:
                    entry = manager._worktree_entry(controller, target)
                    if not target.exists() and entry is None:
                        cleanup = manager.cleanup_terminal_target(contract, lease)
                    else:
                        if entry is None:
                            raise RuntimeError("retained Target is not a registered worktree")
                        if manager.process_checker(target):
                            raise RuntimeError("active process uses Target")
                        dirty = bool(manager._status_bytes(target))
                        head = manager._run_git(["rev-parse", "HEAD"], cwd=target)
                        deterministic_ref = manager.salvage_ref_for(item, attempt_id)
                        if salvage_commit or salvage_ref:
                            if (state.get("salvage_only") is not True or
                                    state.get("promotion_eligible") is not False or
                                    not salvage_commit or not salvage_ref):
                                raise RuntimeError("recorded salvage metadata is invalid")
                            protected = manager._run_git(
                                ["rev-parse", f"{salvage_ref}^{{commit}}"], cwd=controller
                            )
                            if protected != salvage_commit or head != salvage_commit:
                                raise RuntimeError("salvage ref is missing or mismatched")
                            salvage = {
                                "salvage_commit_sha": salvage_commit,
                                "salvage_ref": salvage_ref,
                                "salvage_only": True,
                                "promotion_eligible": False,
                            }
                        else:
                            try:
                                protected = manager._run_git(
                                    ["rev-parse", f"{deterministic_ref}^{{commit}}"],
                                    cwd=controller,
                                )
                            except RuntimeError:
                                protected = ""
                            if protected:
                                if protected != head:
                                    raise RuntimeError(
                                        "salvage ref already exists with different commit"
                                    )
                                salvage = {
                                    "salvage_commit_sha": protected,
                                    "salvage_ref": deterministic_ref,
                                    "salvage_only": True,
                                    "promotion_eligible": False,
                                }
                            elif dirty:
                                salvage = manager.create_salvage_snapshot(
                                    contract, lease, attempt_id
                                )
                            elif head != lease.initial_head:
                                salvage = manager.protect_salvage_head(
                                    contract, lease, attempt_id
                                )
                        cleanup = manager.cleanup_terminal_target(
                            contract,
                            lease,
                            salvage_commit=salvage.get("salvage_commit_sha"),
                            salvage_ref=salvage.get("salvage_ref"),
                        )
                    decision = {
                        "task_id": item,
                        "status": "RETAINED_FOR_REVIEW",
                        "promotion_status": "NOT_CREATED",
                        "cleanup_decision": cleanup.decision,
                        "cleanup_blocker": cleanup.blocker,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_eligible": cleanup.eligible,
                        "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                        **salvage,
                    }
                except Exception as exc:
                    decision = {
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "promotion_status": "NOT_CREATED",
                        "cleanup_decision": "CLEANUP_BLOCKED",
                        "cleanup_blocker": str(exc),
                        "cleanup_performed": False, "cleanup_eligible": False,
                        **salvage,
                    }
                decisions.append(decision)
                self._checkpoint(
                    item, "RETAINED_FOR_REVIEW", decision,
                    attempt_id=state.get("attempt_id"),
                )
                continue
            if state.get("status") not in TERMINAL_STATUSES and state.get("status") not in {"CANDIDATE_COMMITTED", "TARGET_CLEANED", "PENDING_HUMAN_APPROVAL"}:
                decisions.append({"task_id": item, "status": state.get("status"), "cleanup_decision": "BLOCKED_BY_PROCESS", "cleanup_blocker": "task is active", "cleanup_performed": False})
                continue
            if not state.get("lease"):
                decision = {"task_id": item, "status": state.get("status"), "cleanup_decision": "ALREADY_REMOVED", "cleanup_blocker": None, "cleanup_performed": False, "cleanup_eligible": True}
                decisions.append(decision)
                if not dry_run:
                    self._checkpoint(item, str(state.get("status")), decision, attempt_id=state.get("attempt_id"))
                continue
            contract = self.build_contract(state["request"])
            lease = TargetWorktreeLease(**state["lease"])
            packet = state.get("promotion_packet") or {}
            binding = state.get("approved_binding") or {}
            authority_blocker = self._cleanup_authority_blocker(state, contract, lease)
            if authority_blocker:
                decisions.append({
                    "task_id": item,
                    "status": state.get("status"),
                    "cleanup_decision": "BLOCKED_BY_AUTHORITY",
                    "cleanup_blocker": authority_blocker,
                    "cleanup_performed": False,
                    "cleanup_eligible": False,
                })
                continue
            if state.get("promotion_status") in {"APPROVED", "INTEGRATED"} and any(
                binding.get(field) != packet.get(field)
                for field in (
                    "candidate_commit_sha", "candidate_tree_sha",
                    "candidate_state_hash", "verified_receipt_hash",
                )
            ):
                decisions.append({
                    "task_id": item, "status": state.get("status"),
                    "cleanup_decision": "BLOCKED_BY_MISSING_REF",
                    "cleanup_blocker": "approval binding mismatch",
                    "cleanup_performed": False, "cleanup_eligible": False,
                })
                continue
            cleanup = WorktreeManager(root_dir=contract.target_worktree_root).cleanup_terminal_target(
                contract,
                lease,
                candidate_commit=packet.get("candidate_commit_sha"),
                candidate_ref=state.get("candidate_ref"),
                dry_run=dry_run,
            )
            cleanup_receipt = asdict(cleanup)
            cleanup_receipt_hash = hashlib.sha256(
                json.dumps(
                    cleanup_receipt,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            decision = {
                "task_id": item,
                "status": state.get("status"),
                "cleanup_decision": cleanup.decision,
                "cleanup_blocker": cleanup.blocker,
                "cleanup_performed": cleanup.performed,
                "cleanup_eligible": cleanup.eligible,
                "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                "cleanup_receipt": cleanup_receipt,
                "cleanup_receipt_hash": cleanup_receipt_hash,
            }
            cleanup_receipt["target_present_after"] = Path(lease.target_worktree).resolve().exists()
            cleanup_receipt_hash = hashlib.sha256(
                json.dumps(
                    cleanup_receipt,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            decision["cleanup_receipt"] = cleanup_receipt
            decision["cleanup_receipt_hash"] = cleanup_receipt_hash
            decision["target_present_after"] = cleanup_receipt["target_present_after"]
            decisions.append(decision)
            if not dry_run:
                terminal = "RETAINED_FOR_REVIEW" if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES" else str(state.get("status"))
                self._checkpoint(item, terminal, decision, attempt_id=state.get("attempt_id"))
        return {"dry_run": dry_run, "decisions": decisions}

    def archive_states(self, *, dry_run: bool = True) -> dict[str, Any]:
        archive_root = self._archive_root()
        entries = []
        for path in sorted(self.state_dir.glob("*.json")) if self.state_dir.exists() else []:
            payload = path.read_bytes()
            state = json.loads(payload)
            if state.get("status") not in {"FINAL_BLOCK", "INTEGRATED", "INTEGRATED_AND_CLEANED", "REJECTED", "SUPERSEDED", "CANCELLED"}:
                continue
            if state.get("status") == "INTEGRATED" and state.get("cleanup_status") not in {None, "CLEANED"}:
                continue
            digest = hashlib.sha256(payload).hexdigest()
            destination = archive_root / path.name
            if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                attempt_id = str(state.get("attempt_id") or "unknown")
                destination = archive_root / f"{path.stem}--attempt-{attempt_id}.json"
            entries.append({
                "task_id": path.stem,
                "terminal_status": state.get("terminal_status") or state.get("status"),
                "candidate_commit": (state.get("promotion_packet") or {}).get("candidate_commit_sha"),
                "source": str(path),
                "archive_location": str(destination),
                "receipt_hash": digest,
                "archive_time": state.get("updated_at"),
            })
        manifest_bytes = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path = archive_root / f"manifest-{manifest_hash}.json"
        if not dry_run and entries:
            archive_root.mkdir(parents=True, exist_ok=True)
            for entry in entries:
                source = Path(entry["source"])
                destination = Path(entry["archive_location"])
                if destination.exists():
                    if hashlib.sha256(destination.read_bytes()).hexdigest() != entry["receipt_hash"]:
                        raise RuntimeError(f"archive receipt hash mismatch: {destination}")
                    source.unlink(missing_ok=True)
                else:
                    source.replace(destination)
                if hashlib.sha256(destination.read_bytes()).hexdigest() != entry["receipt_hash"]:
                    raise RuntimeError(f"archive receipt verification failed: {destination}")
            manifest_payload = {
                "schema": "nexus.self_hosted_state_archive_manifest.v1",
                "manifest_hash": manifest_hash,
                "entries": entries,
            }
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=archive_root,
                prefix=".manifest.", suffix=".tmp", delete=False,
            ) as handle:
                json.dump(manifest_payload, handle, sort_keys=True, indent=2)
                handle.write("\n")
                temporary = Path(handle.name)
            temporary.replace(manifest_path)
        return {"dry_run": dry_run, "entries": entries, "manifest_hash": manifest_hash, "manifest_path": str(manifest_path)}



    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        result = self.get_task_snapshot(task_id, include_details=True)
        if result is not None:
            result.pop("operator_outcome_receipt", None)
            result.pop("operator_outcome_receipts", None)
        return result

    def get_task_snapshot(
        self, task_id: str, *, include_details: bool = False
    ) -> Optional[dict[str, Any]]:
        """Read status without reconciliation or state-lock acquisition."""
        state = self._read_state_snapshot(task_id)
        if state is None:
            return None
        approval_requirements = self._approval_requirements(state)
        if include_details:
            details = {**state, "approval_requirements": approval_requirements}
            details.pop("operator_outcome_receipt", None)
            details.pop("operator_outcome_receipts", None)
            return details
        action = state.get("task_action") or self._task_action_envelope(state)
        return {
            "schema": "nexus.self_hosted_task_status.v1",
            "task_id": state.get("task_id"),
            "status": state.get("status"),
            "promotion_status": state.get("promotion_status"),
            "verification_verdict": state.get("verification_verdict"),
            "found": state.get("found", True),
            "state_valid": state.get("state_valid", True),
            "blocker": self._projected_blocker(state),
            "retry_authorized": state.get("retry_authorized"),
            "task_action": action,
            "autonomy": project_autonomy_submission(state),
            "approval_requirements": approval_requirements,
        }

    def get_receipt(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None:
            return None
        contract = state.get("contract") or {}
        lease = state.get("lease") or {}
        packet = state.get("promotion_packet") or {}
        candidate = state.get("candidate") or {}
        verified_receipt = state.get("verified_receipt") or {}
        candidate_collaboration_provenance = (
            candidate.get("collaboration_provenance")
            or verified_receipt.get("collaboration_provenance")
            or packet.get("collaboration_provenance")
            or lease.get("collaboration_provenance")
        )
        collaboration_provenance = (
            candidate_collaboration_provenance
            or state.get("collaboration_provenance")
        )
        archived_path, _ = self._latest_archived_state(task_id)
        return {
            "task_id": task_id,
            "attempt_id": state.get("attempt_id"),
            "status": state.get("status"),
            "submitted_at": state.get("submitted_at"),
            "telemetry": state.get("telemetry") or {"wall_time_ms": 0, "overhead_ms": 0},
            "contract_hash": state.get("contract_hash"),
            "controller_worktree": state.get("controller_worktree") or contract.get("controller_repo_root"),
            "controller_revision": state.get("controller_revision") or contract.get("controller_revision"),
            "controller_status_sha256": state.get("controller_status_sha256") or lease.get("controller_status_sha256"),
            "target_worktree": state.get("target_worktree") or lease.get("target_worktree") or contract.get("target_repo_root"),
            "target_initial_revision": state.get("target_initial_revision") or lease.get("initial_head") or contract.get("target_base_revision"),
            "target_branch": state.get("target_branch") or lease.get("target_branch"),
            "target_created_at": state.get("target_created_at"),
            "worker_provider": state.get("worker_provider"),
            "worker_pid": state.get("worker_pid"),
            "heartbeat_at": state.get("heartbeat_at"),
            "execution_outcome": state.get("execution_outcome"),
            "verification_verdict": state.get("verification_verdict"),
            "candidate_commit_sha": state.get("candidate_commit_sha") or packet.get("candidate_commit_sha"),
            "candidate_tree_sha": state.get("candidate_tree_sha") or packet.get("candidate_tree_sha"),
            "candidate_ref": state.get("candidate_ref"),
            "candidate_state_hash": state.get("candidate_state_hash") or packet.get("candidate_state_hash"),
            "verified_receipt_hash": state.get("verified_receipt_hash") or packet.get("verified_receipt_hash"),
            "salvage_commit_sha": state.get("salvage_commit_sha"),
            "salvage_ref": state.get("salvage_ref"),
            "salvage_only": state.get("salvage_only", False),
            "promotion_eligible": state.get("promotion_eligible", False),
            "promotion_status": state.get("promotion_status"),
            "approved_binding": state.get("approved_binding"),
            "integration_branch": state.get("integration_branch"),
            "integration_base_sha": state.get("integration_base_sha"),
            "integration_result_sha": state.get("integration_result_sha"),
            "terminal_status": state.get("terminal_status"),
            "superseded_by": state.get("superseded_by"),
            "cleanup_eligible": state.get("cleanup_eligible"),
            "cleanup_decision": state.get("cleanup_decision"),
            "cleanup_blocker": state.get("cleanup_blocker"),
            "cleanup_performed": state.get("cleanup_performed"),
            "cleanup_performed_at": state.get("cleanup_performed_at"),
            "state_retention_status": "ARCHIVED" if archived_path is not None else state.get("state_retention_status"),
            "archive_eligible": state.get("archive_eligible"),
            "archive_location": str(archived_path) if archived_path is not None else state.get("archive_location"),
            "execution": state.get("execution"),
            "candidate": state.get("candidate"),
            "verified_receipt": state.get("verified_receipt"),
            "execution_authority": state.get("execution_authority"),
            "provider_receipt_authoritative": state.get(
                "provider_receipt_authoritative", False
            ),
            "workforce_admission_authoritative": state.get(
                "workforce_admission_authoritative", False
            ),
            "runtime_development_mapping": state.get("runtime_development_mapping"),
            "collaboration_realm": state.get("collaboration_realm") or contract.get("collaboration_realm"),
            "submission_collaboration_provenance": (
                state.get("submission_collaboration_provenance")
                or state.get("collaboration_provenance")
            ),
            "collaboration_provenance": collaboration_provenance,
            "candidate_collaboration_provenance": candidate_collaboration_provenance,
            "error": state.get("error"),
            "operator_outcome_receipt": state.get("operator_outcome_receipt"),
            "operator_outcome_receipts": state.get("operator_outcome_receipts", []),
        }

    def get_promotion_packet(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self.get_task(task_id)
        if state is None:
            return None
        return {
            "task_id": task_id,
            "promotion_status": state.get("promotion_status"),
            "promotion_packet": state.get("promotion_packet"),
            "candidate_commit_created": state.get("candidate_commit_created", False),
            "public_claim_allowed": state.get("public_claim_allowed", False),
            "production_ready": state.get("production_ready", False),
            "merge_performed": state.get("merge_performed", False),
            "push_performed": state.get("push_performed", False),
        }

    @staticmethod
    def _snapshot_target_integrity(target_path: Path) -> tuple[str, Optional[str]]:
        """Hash Target entries and contents without following external links.

        Read-only verification executes commands supplied by the durable task
        contract.  A verifier is not allowed to create, delete, or rewrite
        anything in its Target, even when the command exits successfully.
        Missing or unreadable entries are represented as explicit integrity
        errors so the caller can fail closed instead of trusting a partial
        digest.
        """
        try:
            if not target_path.exists():
                return "MISSING", f"target worktree missing: {target_path}"
            if not target_path.is_dir():
                return "NOT_DIRECTORY", f"target worktree is not a directory: {target_path}"
        except OSError as exc:
            return "UNREADABLE", f"unable to inspect target worktree: {exc}"

        digest = hashlib.sha256()
        try:
            for root, dirs, files in os.walk(target_path, topdown=True, followlinks=False):
                dirs.sort()
                files.sort()
                for name, kind in [(name, "dir") for name in dirs] + [(name, "file") for name in files]:
                    path = Path(root) / name
                    relative = path.relative_to(target_path).as_posix()
                    try:
                        metadata = path.lstat()
                    except OSError as exc:
                        return f"UNREADABLE:{relative}", f"unable to stat {relative}: {exc}"

                    digest.update(f"{kind}:{relative}\0".encode("utf-8"))
                    digest.update(
                        f"mode={metadata.st_mode & 0o7777};size={metadata.st_size};mtime={metadata.st_mtime_ns}\0".encode(
                            "utf-8"
                        )
                    )
                    if stat.S_ISLNK(metadata.st_mode):
                        try:
                            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
                        except OSError as exc:
                            return f"UNREADABLE:{relative}", f"unable to read link {relative}: {exc}"
                    elif stat.S_ISREG(metadata.st_mode):
                        try:
                            digest.update(path.read_bytes())
                        except OSError as exc:
                            return f"UNREADABLE:{relative}", f"unable to read {relative}: {exc}"
                    else:
                        digest.update(f"special={metadata.st_mode}\0".encode("utf-8"))
        except OSError as exc:
            return "UNREADABLE", f"unable to walk target worktree: {exc}"
        return digest.hexdigest(), None

    @staticmethod
    def evaluate_candidate_acceptance(
        request: CandidateAcceptanceRequest | Mapping[str, Any],
        review: IndependentReviewReceipt | Mapping[str, Any],
        *,
        verified_repair_evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate independent evidence without mutating lifecycle state."""
        request_obj = (
            request
            if isinstance(request, CandidateAcceptanceRequest)
            else CandidateAcceptanceRequest(**dict(request))
        )
        review_obj = (
            review
            if isinstance(review, IndependentReviewReceipt)
            else IndependentReviewReceipt(**dict(review))
        )
        result: CandidateAcceptanceResult = reduce_candidate_acceptance(
            request_obj,
            review_obj,
            verified_repair_evidence=verified_repair_evidence,
        )
        return result.to_dict()

    def verify_task(self, task_id: str) -> dict[str, Any]:
        """Read-only verification of a self-hosted task.

        Proves:
        - verifier commands only from durable task contract/state
        - reuses CandidateVerifier._run_verifiers() for command execution
        - provider_calls == 0 (deterministic commands only)
        - full state/contract/attempt binding checked
        - durable state digest verified before/after
        - integration result is verifiable ancestor when present
        - Target, lease, candidate, receipt or durable binding missing -> fail closed
        - verify must not commit, cleanup, approve, integrate, push, or modify state
        - repeated verify on same immutable state -> consistent verdict
        """
        # --- Phase 1: Pre-read durable state ---
        state_before = self._read_state_snapshot(task_id)
        if state_before is None:
            return {
                "task_id": task_id,
                "verdict": "STATE_MISSING",
                "verified": False,
                "failure_reasons": ["state_not_found"],
                "provider_calls": 0,
            }

        attempt_id = state_before.get("attempt_id")
        contract_hash = state_before.get("contract_hash")
        status = state_before.get("status")

        # --- Phase 2: State integrity + full binding check ---
        failures: list[str] = []

        # Compute pre-verification state digest
        state_digest_before = hashlib.sha256(
            json.dumps(state_before, sort_keys=True, default=str).encode()
        ).hexdigest()

        # State deletion/replacement check
        state_mid = self._read_state_snapshot(task_id)
        if state_mid is None:
            return {
                "task_id": task_id,
                "verdict": "STATE_DELETED",
                "verified": False,
                "failure_reasons": ["state_deleted_between_reads"],
                "provider_calls": 0,
            }

        # Hash drift check
        if state_mid.get("contract_hash") != contract_hash:
            failures.append("contract_hash_drift")

        # Attempt drift check
        if state_mid.get("attempt_id") != attempt_id:
            failures.append("attempt_drift")

        # --- Phase 3: Contract, lease, candidate binding validation (fail-closed) ---
        contract_data = state_mid.get("contract")
        if not contract_data:
            failures.append("contract_missing")
        lease_data = state_mid.get("lease")
        if not lease_data:
            failures.append("lease_missing")

        candidate_commit = state_mid.get("candidate_commit_sha")
        candidate_ref = state_mid.get("candidate_ref")
        promotion_packet = state_mid.get("promotion_packet") or {}

        # If candidate state exists, binding must be complete
        if candidate_commit and not candidate_ref:
            failures.append("candidate_ref_missing")
        if candidate_commit and not promotion_packet.get("candidate_state_hash"):
            failures.append("candidate_state_hash_missing")

        # --- Phase 4: Target or durable post-cleanup Candidate validation ---
        target_worktree = (
            state_mid.get("target_worktree")
            or (lease_data.get("target_worktree") if lease_data else None)
            or (contract_data.get("target_repo_root") if contract_data else None)
        )
        verification_mode = "target"
        durable_candidate_mode = False
        verified_receipt = state_mid.get("verified_receipt") or {}
        cleanup_decision = state_mid.get("cleanup_decision")
        target_integrity_before = "SKIPPED"
        target_integrity_after = "SKIPPED"
        target_integrity_error_before: Optional[str] = None
        target_integrity_error_after: Optional[str] = None

        if not target_worktree:
            failures.append("target_worktree_missing")
        else:
            target_path = Path(target_worktree)
            if (
                cleanup_decision in {"REMOVED", "ALREADY_REMOVED"}
                and candidate_commit
                and candidate_ref
                and promotion_packet
                and verified_receipt
            ):
                verification_mode = "durable_candidate_receipt"
                durable_candidate_mode = True
                target_integrity_before = "DURABLE_CANDIDATE"
                target_integrity_after = "DURABLE_CANDIDATE"
                import re

                candidate_tree = state_mid.get("candidate_tree_sha") or promotion_packet.get("candidate_tree_sha")
                candidate_state_hash = state_mid.get("candidate_state_hash") or promotion_packet.get("candidate_state_hash")
                verified_receipt_hash = state_mid.get("verified_receipt_hash") or promotion_packet.get("verified_receipt_hash")
                controller_root = (
                    state_mid.get("controller_worktree")
                    or (contract_data.get("controller_repo_root") if contract_data else None)
                )
                candidate_ref_pattern = re.compile(
                    rf"refs/nexus-(?:candidates|candidate-commits)/{re.escape(task_id)}/[0-9a-f]{{40}}"
                )

                if not re.fullmatch(r"[0-9a-f]{40}", str(candidate_commit)):
                    failures.append("candidate_commit_invalid_format")
                if not re.fullmatch(r"[0-9a-f]{40}", str(candidate_tree or "")):
                    failures.append("candidate_tree_invalid_format")
                if not re.fullmatch(r"[0-9a-f]{64}", str(candidate_state_hash or "")):
                    failures.append("candidate_state_hash_invalid_format")
                if not re.fullmatch(r"[0-9a-f]{64}", str(verified_receipt_hash or "")):
                    failures.append("verified_receipt_hash_invalid_format")
                if not candidate_ref_pattern.fullmatch(str(candidate_ref)):
                    failures.append("candidate_ref_namespace_invalid")
                if not controller_root or not Path(controller_root).is_dir():
                    failures.append("controller_repo_unavailable")
                else:
                    try:
                        resolved_ref = subprocess.run(
                            ["git", "rev-parse", "--verify", str(candidate_ref)],
                            cwd=controller_root,
                            capture_output=True,
                            text=True,
                            timeout=10.0,
                        )
                        if resolved_ref.returncode != 0:
                            failures.append("candidate_ref_unresolved")
                        elif resolved_ref.stdout.strip() != candidate_commit:
                            failures.append("candidate_ref_commit_mismatch")

                        resolved_tree = subprocess.run(
                            ["git", "rev-parse", "--verify", f"{candidate_ref}^{{tree}}"],
                            cwd=controller_root,
                            capture_output=True,
                            text=True,
                            timeout=10.0,
                        )
                        if resolved_tree.returncode != 0:
                            failures.append("candidate_ref_tree_unresolved")
                        elif resolved_tree.stdout.strip() != candidate_tree:
                            failures.append("candidate_ref_tree_mismatch")
                    except (subprocess.TimeoutExpired, OSError) as exc:
                        failures.append(f"candidate_ref_verification_error:{exc}")

                for field, expected in (
                    ("task_id", task_id),
                    ("contract_hash", contract_hash),
                    ("lease_id", lease_data.get("lease_id") if lease_data else None),
                    ("candidate_state_hash", candidate_state_hash),
                ):
                    if verified_receipt.get(field) != expected:
                        failures.append(f"verified_receipt_{field}_mismatch")

                if not verified_receipt.get("verified"):
                    failures.append("verified_receipt_not_verified")
                if not verified_receipt.get("candidate_commit_allowed"):
                    failures.append("verified_receipt_commit_not_allowed")
                if verified_receipt.get("public_claim_allowed") is not False:
                    failures.append("verified_receipt_public_claim_boundary_invalid")
                if verified_receipt.get("production_ready") is not False:
                    failures.append("verified_receipt_production_boundary_invalid")
                if verified_receipt.get("merge_performed") is not False:
                    failures.append("verified_receipt_merge_boundary_invalid")

                canonical_receipt = json.dumps(
                    verified_receipt,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
                actual_receipt_hash = hashlib.sha256(canonical_receipt).hexdigest()
                if actual_receipt_hash != verified_receipt_hash:
                    failures.append("verified_receipt_hash_mismatch")

                for field in (
                    "task_id",
                    "contract_hash",
                    "controller_revision",
                    "target_base_revision",
                    "candidate_commit_sha",
                    "candidate_tree_sha",
                    "candidate_state_hash",
                    "verified_receipt_hash",
                ):
                    expected = {
                        "task_id": task_id,
                        "contract_hash": contract_hash,
                        "controller_revision": contract_data.get("controller_revision") if contract_data else None,
                        "target_base_revision": contract_data.get("target_base_revision") if contract_data else None,
                        "candidate_commit_sha": candidate_commit,
                        "candidate_tree_sha": candidate_tree,
                        "candidate_state_hash": candidate_state_hash,
                        "verified_receipt_hash": verified_receipt_hash,
                    }[field]
                    if promotion_packet.get(field) != expected:
                        failures.append(f"promotion_packet_{field}_mismatch")
            elif cleanup_decision in {"REMOVED", "ALREADY_REMOVED"}:
                verification_mode = "durable_candidate_receipt"
                failures.append("durable_candidate_binding_missing")
            elif target_path.exists():
                if not target_path.is_dir():
                    failures.append("target_not_directory")
                else:
                    try:
                        list(target_path.iterdir())
                    except PermissionError:
                        failures.append("target_unreadable")
                    target_integrity_before, target_integrity_error_before = self._snapshot_target_integrity(target_path)
                    if target_integrity_error_before:
                        failures.append(
                            f"target_integrity_before_verification:{target_integrity_error_before}"
                        )
            else:
                failures.append("target_missing")
                target_integrity_before, target_integrity_error_before = self._snapshot_target_integrity(target_path)

        # --- Phase 5: Integration SHA validation (actual ancestor check) ---
        integration_result_sha = state_mid.get("integration_result_sha")
        if integration_result_sha:
            import re
            if not re.fullmatch(r"[0-9a-f]{40}", integration_result_sha):
                failures.append("integration_sha_invalid_format")
            else:
                controller_root = (
                    state_mid.get("controller_worktree")
                    or (contract_data.get("controller_repo_root") if contract_data else None)
                )
                controller_rev = (
                    state_mid.get("controller_revision")
                    or (contract_data.get("controller_revision") if contract_data else None)
                )
                if controller_root and controller_rev:
                    try:
                        anc_result = subprocess.run(
                            [
                                "git", "-c", "core.hooksPath=/dev/null",
                                "merge-base", "--is-ancestor",
                                integration_result_sha, controller_rev,
                            ],
                            cwd=controller_root,
                            capture_output=True,
                            timeout=10.0,
                        )
                        if anc_result.returncode != 0:
                            failures.append("integration_ancestry_failed")
                    except (subprocess.TimeoutExpired, OSError) as exc:
                        failures.append(f"integration_ancestry_error:{exc}")

        # --- Phase 6: Verifier command execution via CandidateVerifier._run_verifiers ---
        verifier_commands = (
            contract_data.get("verifier_commands") if contract_data else []
        ) or []
        verifier_evidence: list[dict[str, Any]] = []
        verifier_commands_executed: list[str] = []

        if durable_candidate_mode:
            verifier_evidence = list(verified_receipt.get("verifier_evidence") or [])
        elif (
            target_worktree
            and Path(target_worktree).is_dir()
            and verifier_commands
            and target_integrity_error_before is None
        ):
            class _MinimalContract:
                pass
            _min = _MinimalContract()
            _min.verifier_commands = verifier_commands

            try:
                passed, evidence_tuple, ver_failures = CandidateVerifier._run_verifiers(
                    _min, target_worktree,
                )
                for ev in evidence_tuple:
                    verifier_evidence.append({
                        "command": ev.command,
                        "status": ev.status,
                        "exit_code": ev.exit_code,
                        "stdout_sha256": ev.stdout_sha256,
                        "stderr_sha256": ev.stderr_sha256,
                        "wall_time_ms": ev.wall_time_ms,
                        "executable_identity": ev.executable_identity,
                        "timed_out": ev.timed_out,
                    })
                    verifier_commands_executed.append(ev.command)
                failures.extend(ver_failures)
            except Exception as exc:
                failures.append(f"verifier_runner_error:{exc}")

        if not durable_candidate_mode and target_worktree and target_integrity_before != "SKIPPED":
            target_integrity_after, target_integrity_error_after = self._snapshot_target_integrity(
                Path(target_worktree)
            )
            if target_integrity_error_after:
                failures.append(
                    f"target_integrity_after_verification:{target_integrity_error_after}"
                )
            if target_integrity_before != target_integrity_after:
                failures.append("target_digest_drift_during_verification")

        # --- Phase 7: Post-read state consistency + digest comparison ---
        state_after = self._read_state_snapshot(task_id)
        if state_after is None:
            failures.append("state_deleted_after_verification")
        else:
            if state_after.get("contract_hash") != contract_hash:
                failures.append("contract_hash_drift_after_verification")
            elif state_after.get("attempt_id") != attempt_id:
                failures.append("attempt_drift_after_verification")

            # Full state digest comparison
            state_digest_after = hashlib.sha256(
                json.dumps(state_after, sort_keys=True, default=str).encode()
            ).hexdigest()
            if state_digest_before != state_digest_after:
                failures.append("state_digest_drift_during_verification")

        verified = not failures
        action_state = self._task_action_envelope(state_after or state_before)
        return {
            "task_id": task_id,
            "verdict": "VERIFIED" if verified else "FAILED",
            "verified": verified,
            "failure_reasons": failures,
            "provider_calls": 0,
            "verification_mode": verification_mode,
            "verifier_commands_executed": verifier_commands_executed,
            "verifier_evidence": verifier_evidence,
            "status": status,
            "contract_hash": contract_hash,
            "attempt_id": attempt_id,
            "state_digest_before": state_digest_before,
            "state_intact": state_after is not None and state_after.get("contract_hash") == contract_hash,
            "target_integrity_before": target_integrity_before,
            "target_integrity_after": target_integrity_after,
            "target_integrity_error": target_integrity_error_before or target_integrity_error_after,
            "task_action": action_state,
            "action_state": action_state.get("action_state"),
            "attention_required": action_state.get("attention_required"),
            "next_action": action_state.get("next_action"),
            "recommended_tool": action_state.get("recommended_tool"),
        }


    def approve_promotion(
        self,
        task_id: str,
        *,
        candidate_commit_sha: str,
        candidate_tree_sha: str,
        candidate_state_hash: str,
        verified_receipt_hash: str,
        approval_context: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        if self._custom_runner is not None:
            raise RuntimeError("CUSTOM_RUNNER_PRODUCTION_CLAIM_FORBIDDEN")
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        request = state.get("request") or {}
        if self.ephemeral and (
            request.get("task_card_required") or request.get("lifecycle_identity_required")
        ):
            raise RuntimeError("EPHEMERAL_PROMOTION_FORBIDDEN: rehearsal state cannot be approved")
        identity = resolve_contract_identity(
            state,
            expected_task_id=task_id,
            expected_head=str(state.get("controller_revision") or ""),
        )
        packet = state.get("promotion_packet") or {}
        expected = {
            "candidate_commit_sha": candidate_commit_sha,
            "candidate_tree_sha": candidate_tree_sha,
            "candidate_state_hash": candidate_state_hash,
            "verified_receipt_hash": verified_receipt_hash,
        }

        valid = bool(packet) and not any(packet.get(k) != v for k, v in expected.items())
        status = "APPROVED" if valid else "APPROVAL_INVALIDATED"
        grant = dict(approval_context or {}) if approval_context is not None else None
        public_grant_identity_fields = (
            "bound_task_id",
            "bound_attempt_id",
            "bound_action_type",
            "contract_kind",
            "contract_hash",
            "tool_manifest_hash",
            "full_tool_schema_hash",
            "permission_policy_hash",
            "lifecycle_revision",
            "server_instance_id",
        )
        complete_public_grant = grant is not None and all(
            str(grant.get(field) or "").strip() for field in public_grant_identity_fields
        )
        if identity["contract_kind"] == ContractKind.OWNER_INLINE.value or complete_public_grant:
            validate_approval_grant(
                grant,
                task_id=task_id,
                attempt_id=str(state.get("attempt_id") or ""),
                action_type=LifecycleActionType.CANDIDATE_APPROVE.value,
                task_card_hash=identity["task_card_hash"],
                contract_kind=identity["contract_kind"],
                contract_hash=identity["contract_hash"],
                owner_inline_contract=identity["owner_inline_contract"],
                tool_manifest_hash=str(grant.get("tool_manifest_hash") or ""),
                full_tool_schema_hash=str(grant.get("full_tool_schema_hash") or ""),
                permission_policy_hash=str(grant.get("permission_policy_hash") or ""),
                lifecycle_revision=str(grant.get("lifecycle_revision") or ""),
                server_instance_id=str(grant.get("server_instance_id") or ""),
            )
        architecture_approval = grant.get("architecture_approval") if isinstance(grant, Mapping) else None
        receipt = state.get("verified_receipt") if isinstance(state.get("verified_receipt"), Mapping) else {}
        authority_required = bool(packet.get("authority_change_required") or receipt.get("authority_change_required"))
        authority_hash = str(packet.get("authority_findings_sha256") or receipt.get("authority_findings_sha256") or "")
        validate_architecture_approval(
            architecture_approval,
            required=authority_required,
            task_id=task_id,
            attempt_id=str(state.get("attempt_id") or ""),
            candidate_commit_sha=candidate_commit_sha,
            candidate_tree_sha=candidate_tree_sha,
            authority_findings_sha256=authority_hash,
        )
        external_acceptance: dict[str, Any] | None = None
        integration_authorization: dict[str, Any] | None = None
        if grant is not None:
            if str(grant.get("schema") or "") != "nexus.approval.v2":
                raise RuntimeError("APPROVAL_LEGACY_BINDING_INVALIDATED")
            if grant.get("consumed_at"):
                raise RuntimeError("APPROVAL_ALREADY_CONSUMED")
            if str(grant.get("approval_scope") or "ALLOW_ACTION_ONCE") != "ALLOW_ACTION_ONCE":
                raise RuntimeError("APPROVAL_SCOPE_UNSUPPORTED")
            raw_acceptance = grant.get("external_acceptance")
            raw_authorization = grant.get("integration_authorization")
            if (raw_acceptance is None) != (raw_authorization is None):
                raise RuntimeError("AUTHORIZED_CLOSURE_BINDING_INCOMPLETE")
            if raw_acceptance is not None and raw_authorization is not None:
                acceptance_obj = raw_acceptance if isinstance(raw_acceptance, ExternalAcceptanceReceipt) else ExternalAcceptanceReceipt(**dict(raw_acceptance))
                authorization_obj = raw_authorization if isinstance(raw_authorization, IntegrationAuthorizationEnvelope) else IntegrationAuthorizationEnvelope(**{key: value for key, value in dict(raw_authorization).items() if key != "authorization_hash"})
                if acceptance_obj.task_id != task_id or acceptance_obj.candidate_commit != candidate_commit_sha:
                    raise RuntimeError("EXTERNAL_ACCEPTANCE_BINDING_MISMATCH")
                if authorization_obj.task_id != task_id or authorization_obj.candidate_commit != candidate_commit_sha:
                    raise RuntimeError("INTEGRATION_AUTHORIZATION_BINDING_MISMATCH")
                expected_authorization = {
                    "attempt_id": str(state.get("attempt_id") or ""),
                    "task_card_hash": str(state.get("task_card_hash") or grant.get("task_card_hash") or ""),
                    "candidate_tree_sha": candidate_tree_sha,
                    "candidate_state_hash": candidate_state_hash,
                    "candidate_receipt_hash": verified_receipt_hash,
                }
                authorization_values = {
                    "attempt_id": authorization_obj.attempt_id,
                    "task_card_hash": authorization_obj.task_card_hash,
                    "candidate_tree_sha": authorization_obj.candidate_tree_sha,
                    "candidate_state_hash": authorization_obj.candidate_state_hash,
                    "candidate_receipt_hash": authorization_obj.candidate_receipt_hash,
                }
                authorization_drift = [
                    key for key, expected_value in expected_authorization.items()
                    if str(authorization_values[key]) != str(expected_value)
                ]
                if authorization_drift:
                    raise RuntimeError(
                        "INTEGRATION_AUTHORIZATION_BINDING_MISMATCH: "
                        + ", ".join(authorization_drift)
                    )
                if authorization_obj.acceptance_receipt_hash != acceptance_obj.receipt_hash:
                    raise RuntimeError("INTEGRATION_AUTHORIZATION_ACCEPTANCE_MISMATCH")
                external_acceptance = acceptance_obj.to_dict()
                integration_authorization = authorization_obj.to_dict()
                integration_authorization["authorization_hash"] = authorization_obj.authorization_hash
        now = _utc_now()
        duplicate = False
        initial_status = state.get("status")
        initial_promotion_status = state.get("promotion_status")
        service_contract_hash = str(state.get("contract_hash") or "")
        packet_snapshot = json.dumps(
            _jsonable(packet), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        receipt_snapshot = json.dumps(
            _jsonable(receipt), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

        def mutate(current: dict[str, Any]) -> None:
            nonlocal duplicate
            if current.get("attempt_id") != state.get("attempt_id"):
                raise RuntimeError("task attempt ownership changed")
            current_identity = resolve_contract_identity(
                current,
                expected_task_id=task_id,
                expected_head=str(current.get("controller_revision") or ""),
            )
            current_packet = (
                current.get("promotion_packet")
                if isinstance(current.get("promotion_packet"), Mapping)
                else {}
            )
            current_receipt = (
                current.get("verified_receipt")
                if isinstance(current.get("verified_receipt"), Mapping)
                else {}
            )
            if (
                current.get("status") != initial_status
                or current.get("promotion_status") != initial_promotion_status
                or str(current.get("contract_hash") or "") != service_contract_hash
                or current_identity != identity
                or json.dumps(
                    _jsonable(current_packet),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                != packet_snapshot
                or json.dumps(
                    _jsonable(current_receipt),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                != receipt_snapshot
            ):
                raise RuntimeError("APPROVAL_BINDING_CONCURRENCY_DRIFT")
            existing = current.get("approved_binding") if isinstance(current.get("approved_binding"), Mapping) else {}
            existing_grant = existing.get("approval_grant") if isinstance(existing.get("approval_grant"), Mapping) else None
            if grant is not None and current.get("promotion_status") == "APPROVED" and existing_grant:
                same_request = (
                    str(existing_grant.get("approval_id")) == str(grant.get("approval_id"))
                    and all(existing.get(key) == value for key, value in expected.items())
                    and all(existing_grant.get(key) == grant.get(key) for key in ("contract_kind", "contract_hash", "task_card_hash"))
                )
                if same_request:
                    duplicate = True
                    return
                raise RuntimeError("APPROVAL_ALREADY_CONSUMED")
            consumed = dict(grant) if valid and grant is not None else None
            if consumed is not None:
                consumed["approval_scope"] = "ALLOW_ACTION_ONCE"
                consumed["consumed_at"] = now
                if isinstance(consumed.get("architecture_approval"), Mapping):
                    nested = dict(consumed["architecture_approval"])
                    nested["consumed_at"] = now
                    consumed["architecture_approval"] = nested
            current.update({
                "status": status,
                "promotion_status": status,
                "candidate_status": status,
                "approved_binding": ({
                    **expected,
                    "approval_grant": consumed,
                    "external_acceptance": external_acceptance,
                    "integration_authorization": integration_authorization,
                    "architecture_approval": (consumed or {}).get("architecture_approval") if consumed is not None else architecture_approval,
                } if valid else None),
                "external_acceptance": external_acceptance,
                "integration_authorization": integration_authorization,
                "approval_error": None if valid else "promotion binding does not match candidate packet",
                "merge_performed": False,
                "push_performed": False,
                "updated_at": now,
            })
            current.setdefault("status_history", []).append({"status": status, "at": now})

        result = self._mutate_state(task_id, mutate) or state
        if duplicate:
            result = dict(result)
            result["duplicate"] = True
        return result

    def owner_finish(
        self,
        task_id: str,
        *,
        candidate_commit_sha: str,
        candidate_tree_sha: str,
        candidate_state_hash: str,
        verified_receipt_hash: str,
        integration_branch: str = "nexus/integration/main",
        approval_context: Optional[Mapping[str, Any]] = None,
        external_acceptance: Optional[Mapping[str, Any]] = None,
        integration_authorization: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Owner-only terminal finish: approve, integrate, cleanup/retain, then archive."""
        if external_acceptance is None or integration_authorization is None:
            raise RuntimeError("owner finish requires external acceptance and Owner authorization")
        existing = self._read_state(task_id)
        if existing and existing.get("finalization_receipt") and existing.get("status") in {
            "INTEGRATED_AND_CLEANED", "INTEGRATED_TARGET_RETAINED",
        }:
            return {
                **existing,
                "duplicate": True,
                "owner_finish": {
                    "approval_status": "ALREADY_FINALIZED",
                    "integration_status": existing.get("integration_status"),
                    "cleanup_status": existing.get("cleanup_status"),
                    "archive": {"dry_run": False, "entries": []},
                },
            }
        context = dict(approval_context or {})
        context["external_acceptance"] = dict(external_acceptance)
        context["integration_authorization"] = dict(integration_authorization)
        approved = self.approve_promotion(
            task_id,
            candidate_commit_sha=candidate_commit_sha,
            candidate_tree_sha=candidate_tree_sha,
            candidate_state_hash=candidate_state_hash,
            verified_receipt_hash=verified_receipt_hash,
            approval_context=context,
        )
        if approved.get("status") != "APPROVED" or approved.get("promotion_status") != "APPROVED":
            raise RuntimeError("owner finish requires an exact approved candidate binding")
        integrated = self.integrate_approved(task_id, integration_branch=integration_branch)
        authorization = dict(integration_authorization)
        state_after_integration = self._read_state(task_id) or integrated
        lease_target = str((state_after_integration.get("lease") or {}).get("target_worktree") or "")
        requested_target = str(authorization.get("cleanup_target_path") or lease_target)
        target_path = Path(requested_target).expanduser().resolve() if requested_target else None
        temp_roots = _temporary_state_roots()
        controller_root = Path(str((state_after_integration.get("contract") or {}).get("controller_repo_root") or "")).expanduser().resolve()
        cleanup_allowed = bool(
            self.ephemeral
            and authorization.get("cleanup_requested") is True
            and "CLEANUP_OWNED_TARGET" in (authorization.get("action_set") or [])
            and target_path is not None
            and any(target_path == root or root in target_path.parents for root in temp_roots)
            and target_path != controller_root
        )
        if cleanup_allowed:
            cleanup_result = self.cleanup_tasks(task_id=task_id, dry_run=False)
        else:
            cleanup_result = {
                "dry_run": False,
                "decisions": [{
                    "task_id": task_id,
                    "cleanup_decision": "RETAINED_OUTSIDE_EPHEMERAL_SCOPE",
                    "cleanup_blocker": "live or non-ephemeral cleanup authority is disabled",
                    "cleanup_performed": False,
                    "cleanup_eligible": False,
                    "target_present_after": True,
                }],
            }
        decisions = [d for d in cleanup_result.get("decisions", []) if d.get("task_id", task_id) == task_id]
        decision = decisions[0] if decisions else {
            "cleanup_decision": "CLEANUP_BLOCKED",
            "cleanup_blocker": "cleanup authority returned no decision",
            "cleanup_performed": False,
            "cleanup_eligible": False,
            "target_present_after": True,
        }
        cleanup_receipt = dict(decision.get("cleanup_receipt") or {})
        cleanup_receipt.setdefault("schema", "nexus.target_cleanup_receipt.v1")
        cleanup_receipt.setdefault("task_id", task_id)
        cleanup_receipt.setdefault("decision", decision.get("cleanup_decision"))
        cleanup_receipt.setdefault("blocker", decision.get("cleanup_blocker"))
        cleanup_receipt.setdefault("performed", bool(decision.get("cleanup_performed")))
        cleanup_receipt.setdefault("eligible", bool(decision.get("cleanup_eligible")))
        cleanup_receipt.setdefault(
            "target_present_after",
            bool(decision.get("target_present_after", decision.get("cleanup_decision") != "ALREADY_REMOVED")),
        )
        cleanup_receipt_hash = hashlib.sha256(json.dumps(cleanup_receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        cleaned = (
            not bool(cleanup_receipt.get("target_present_after"))
            and (bool(cleanup_receipt.get("performed")) or cleanup_receipt.get("decision") == "ALREADY_REMOVED")
        )
        final_status = "INTEGRATED_AND_CLEANED" if cleaned else "INTEGRATED_TARGET_RETAINED"
        finalization_status = "CLEANED" if cleaned else "RETAINED"
        retention_reason = None if cleaned else str(cleanup_receipt.get("blocker") or cleanup_receipt.get("decision") or "cleanup was not performed")
        integration_receipt = integrated.get("integration_receipt") or {}
        finalization = {
            "schema": "nexus.task_finalization_receipt.v1",
            "identity": {"task_id": task_id, "campaign_id": (state_after_integration.get("request") or {}).get("campaign_id"), "attempt_id": state_after_integration.get("attempt_id"), "task_card_hash": state_after_integration.get("task_card_hash")},
            "candidate": {"commit_sha": candidate_commit_sha, "tree_sha": candidate_tree_sha, "state_hash": candidate_state_hash, "verified_receipt_hash": verified_receipt_hash},
            "acceptance": {"receipt_hash": authorization.get("acceptance_receipt_hash") or dict(external_acceptance).get("receipt_hash"), "reviewer_id": dict(external_acceptance).get("reviewer_id")},
            "authorization": {"authorization_hash": authorization.get("authorization_hash"), "approval_id": ((state_after_integration.get("approved_binding") or {}).get("approval_grant") or {}).get("approval_id"), "consumed_at": ((state_after_integration.get("approved_binding") or {}).get("approval_grant") or {}).get("consumed_at"), "action_set": list(authorization.get("action_set") or [])},
            "integration": {"status": "INTEGRATED", "branch": integrated.get("integration_branch") or integration_branch, "head_before": integrated.get("integration_base_sha"), "staging_commit": integration_receipt.get("staging_commit_sha"), "head_after": integrated.get("integration_result_sha"), "candidate_is_ancestor": True, "merge_performed": bool(integrated.get("merge_performed", True)), "staging_verified": bool(integration_receipt.get("staging_verified", True)), "post_apply_verified": bool(integration_receipt.get("post_apply_verified", True)), "receipt_hash": hashlib.sha256(json.dumps(integration_receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest(), "failure_reason": None},
            "cleanup": {"status": finalization_status, "target_id": authorization.get("cleanup_target_id"), "target_path": requested_target, "target_present_after": bool(cleanup_receipt.get("target_present_after")), "performed": bool(cleanup_receipt.get("performed")), "eligible": bool(cleanup_receipt.get("eligible")), "blocker": cleanup_receipt.get("blocker"), "receipt_hash": cleanup_receipt_hash},
            "terminal": {"final_status": final_status, "retention_reason": retention_reason, "next_action": "none" if cleaned else "retry_cleanup", "archive_eligible": cleaned},
            "created_at": _utc_now(),
        }
        finalization["receipt_hash"] = hashlib.sha256(json.dumps(finalization, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        values = {"status": final_status, "promotion_status": "INTEGRATED", "candidate_status": "INTEGRATED", "integration_status": "INTEGRATED", "cleanup_status": finalization_status, "target_present": bool(cleanup_receipt.get("target_present_after")), "cleanup_receipt": cleanup_receipt, "cleanup_receipt_hash": cleanup_receipt_hash, "finalization_receipt": finalization, "retention_reason": retention_reason, "next_action": "none" if cleaned else "retry_cleanup", "terminal_status": final_status, "final_disposition": final_status, "archive_eligible": cleaned, "state_retention_status": "TERMINAL" if cleaned else "ACTIONABLE"}
        persisted = self._checkpoint(task_id, final_status, values, attempt_id=state_after_integration.get("attempt_id"))
        if persisted is None:
            persisted = dict(state_after_integration)
            persisted.update(values)
            persisted["task_id"] = task_id
            self._write_state(task_id, persisted)
        archive = {"dry_run": False, "entries": []}
        if cleaned:
            archive = self.archive_states(dry_run=False)
        fresh = self._read_state(task_id) or persisted
        return {**fresh, "duplicate": False, "owner_finish": {"approval_status": "APPROVED", "integration_status": "INTEGRATED", "cleanup_status": finalization_status, "archive": archive}}

    def recover_verified_uncommitted_candidate(self, task_id: str) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        
        status = state.get("status")
        if status not in {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}:
            raise RuntimeError(f"task status '{status}' is not eligible for uncommitted recovery; status must be RETAINED_FOR_REVIEW or FINAL_BLOCK")

        verified_receipt = state.get("verified_receipt") or {}
        if not verified_receipt.get("verified"):
            raise RuntimeError("candidate must be verified before recovery")

        attempt_res = state.get("attempt_resolution") or {}
        if attempt_res.get("verdict") != "PROVEN":
            raise RuntimeError("attempt_resolution verdict must be PROVEN")

        execution = state.get("execution") or {}
        if execution.get("outcome") != "EXECUTION_COMPLETED":
            raise RuntimeError("execution outcome must be EXECUTION_COMPLETED")

        if not verified_receipt.get("verifier_gate_passed"):
            raise RuntimeError("verifier_gate_passed must be True")
        if not verified_receipt.get("controller_gate_passed"):
            raise RuntimeError("controller_gate_passed must be True")
        if not verified_receipt.get("scope_gate_passed"):
            raise RuntimeError("scope_gate_passed must be True")
        if not verified_receipt.get("deletion_gate_passed"):
            raise RuntimeError("deletion_gate_passed must be True")
        if not verified_receipt.get("protected_contract_gate_passed"):
            raise RuntimeError("protected_contract_gate_passed must be True")

        contract_dict = state.get("contract") or {}
        lease_dict = state.get("lease") or {}
        contract_fields = set(ArchitectTaskContract.model_fields.keys()) if hasattr(ArchitectTaskContract, "model_fields") else set()
        lease_fields = set(TargetWorktreeLease.model_fields.keys()) if hasattr(TargetWorktreeLease, "model_fields") else set()

        clean_lease = {k: v for k, v in lease_dict.items() if k in lease_fields} if lease_fields else lease_dict

        if isinstance(contract_dict, dict):
            c_dict = contract_dict.copy()
            if not c_dict.get("what"):
                c_dict["what"] = c_dict.get("objective", "Recover candidate")
            if not c_dict.get("why"):
                c_dict["why"] = c_dict.get("objective", "Recover candidate")
            contract = self.build_contract(c_dict)
        else:
            contract = contract_dict
        lease = TargetWorktreeLease(**clean_lease) if isinstance(lease_dict, dict) else lease_dict

        target_path = Path(lease.target_worktree).resolve()
        if not target_path.exists():
            raise RuntimeError("target worktree path does not exist")

        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        controller_root = Path(contract.controller_repo_root).resolve()
        entry = manager._worktree_entry(controller_root, target_path)
        if entry is None:
            raise RuntimeError(f"target path is not a registered Git worktree under controller {controller_root}")

        if manager._path_has_process(target_path):
            raise RuntimeError("target worktree has active running process")

        target_head = manager._run_git(["rev-parse", "HEAD"], cwd=target_path)
        receipt_obj = VerifiedCandidateReceipt(**verified_receipt)

        if target_head != lease.initial_head:
            raise RuntimeError("verified-uncommitted recovery rejected: target HEAD moved from initial_head; use recover_retained_candidate()")

        current = manager.capture_candidate(contract, lease)
        expected_state_hash = state.get("candidate_state_hash") or verified_receipt.get("candidate_state_hash")
        if current.candidate_state_hash != expected_state_hash:
            raise RuntimeError("candidate state hash changed after verification")
        committer = CandidateCommitter(manager)
        packet = committer.create_candidate_commit(contract, lease, receipt_obj)

        candidate_ref = manager.protect_candidate(contract, lease, packet.candidate_commit_sha)

        updates = {
            "candidate_commit_sha": packet.candidate_commit_sha,
            "candidate_tree_sha": packet.candidate_tree_sha,
            "candidate_ref": candidate_ref,
            "candidate_state_hash": packet.candidate_state_hash,
            "verified_receipt_hash": packet.verified_receipt_hash,
            "promotion_packet": asdict(packet),
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "candidate_status": "COMMITTED",
            "status": "PENDING_HUMAN_APPROVAL",
            "error": None,
            "cleanup_decision": "PROTECTED_BY_CANDIDATE_REF",
            "cleanup_eligible": False,
        }
        res = self._checkpoint(task_id, "PENDING_HUMAN_APPROVAL", updates, attempt_id=state.get("attempt_id"))
        return res or self._read_state(task_id) or state

    def bind_candidate_integration_closure(
        self,
        task_id: str,
        *,
        external_acceptance: ExternalAcceptanceReceipt,
        approval: Mapping[str, Any],
        runtime_identity: Mapping[str, Any],
        expected_canonical_head: str,
        integration_branch: str = "nexus/integration/main",
    ) -> dict[str, Any]:
        """Bind external acceptance and a fresh integrate approval, without applying.

        The public Gateway supplies only these two typed inputs.  This service
        derives the preview and authorization envelope from the persisted
        APPROVED Candidate (or its exact non-applied PRE_APPLY failure), current
        repository HEAD, and runtime identity, then atomically records the
        closure binding for the existing integrate path.
        """
        if not isinstance(external_acceptance, ExternalAcceptanceReceipt):
            raise RuntimeError("EXTERNAL_ACCEPTANCE_TYPED_REQUIRED")
        approval_keys = {"schema", "approval_id", "approved_by", "issued_at", "expires_at", "bound_task_id", "bound_attempt_id", "bound_action_type", "approval_scope", "contract_kind", "contract_hash", "task_card_hash", "tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash", "lifecycle_revision", "server_instance_id", "expected_canonical_head", "integration_branch", "candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash", "acceptance_receipt_hash"}
        if set(approval) - approval_keys:
            raise RuntimeError("CLOSURE_APPROVAL_SCHEMA_CLOSED")
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if str(state.get("task_id") or "") != task_id:
            raise RuntimeError("CLOSURE_TASK_ID_DRIFT")
        identity = resolve_contract_identity(
            state,
            expected_task_id=task_id,
            expected_head=str(state.get("controller_revision") or ""),
        )
        runtime_identity = dict(runtime_identity)
        for key in ("contract_kind", "contract_hash", "task_card_hash", "owner_inline_contract"):
            if key in runtime_identity and runtime_identity[key] != identity[key]:
                raise RuntimeError("CLOSURE_RUNTIME_IDENTITY_MISMATCH")
        runtime_identity.update(identity)
        failed_pre_apply = (
            state.get("status") == "INTEGRATION_FAILED_PRE_APPLY"
            and state.get("promotion_status") == "INTEGRATION_FAILED_PRE_APPLY"
        )
        if not failed_pre_apply and (
            state.get("status") != "APPROVED"
            or state.get("promotion_status") != "APPROVED"
        ):
            raise RuntimeError("CLOSURE_APPROVED_CANDIDATE_REQUIRED")
        if failed_pre_apply:
            failed_execution = state.get("integration_execution")
            if (
                state.get("merge_performed")
                or state.get("integration_result_sha")
                or state.get("integration_receipt")
                or not isinstance(failed_execution, Mapping)
                or failed_execution.get("stage") != "PRE_APPLY"
                or failed_execution.get("merge_performed") is not False
                or failed_execution.get("branch_head_before")
                != failed_execution.get("branch_head_after")
            ):
                raise RuntimeError("CLOSURE_PRE_APPLY_FAILURE_REQUIRED")
        if "integration_closure_binding" in state and (not isinstance(state.get("integration_closure_binding"), Mapping) or not state.get("integration_closure_binding")):
            raise RuntimeError("CLOSURE_BINDING_MALFORMED")
        existing = state.get("integration_closure_binding") if isinstance(state.get("integration_closure_binding"), Mapping) else None
        if existing:
            if "integration_approval_grant" not in state or not isinstance(state.get("integration_approval_grant"), Mapping) or not state.get("integration_approval_grant"):
                raise RuntimeError("CLOSURE_BINDING_MALFORMED")
            if state.get("merge_performed") or state.get("integration_receipt") or state.get("integration_result_sha") or (state.get("integration_execution") and not failed_pre_apply) or state.get("status") in {"INTEGRATED", "INTEGRATED_AND_CLEANED", "INTEGRATED_TARGET_RETAINED", "INTEGRATION_VERIFY_FAILED_AFTER_APPLY"}:
                raise RuntimeError("CLOSURE_REBIND_AFTER_INTEGRATION_FORBIDDEN")
            prior_history = state.get("integration_closure_history")
            if "integration_closure_history" in state and not isinstance(prior_history, list):
                raise RuntimeError("CLOSURE_HISTORY_MALFORMED")
            persisted_grant = state.get("integration_approval_grant") if isinstance(state.get("integration_approval_grant"), Mapping) else {}
            packet_for_rebind = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
            immutable_state = {
                "task_id": task_id,
                "attempt_id": str(state.get("attempt_id") or ""),
                "candidate_commit_sha": str(packet_for_rebind.get("candidate_commit_sha") or state.get("candidate_commit_sha") or ""),
                "candidate_tree_sha": str(packet_for_rebind.get("candidate_tree_sha") or state.get("candidate_tree_sha") or ""),
                "candidate_state_hash": str(packet_for_rebind.get("candidate_state_hash") or state.get("candidate_state_hash") or ""),
                "verified_receipt_hash": str(packet_for_rebind.get("verified_receipt_hash") or state.get("verified_receipt_hash") or ""),
                "contract_kind": identity["contract_kind"],
                "contract_hash": identity["contract_hash"] or "",
                "task_card_hash": identity["task_card_hash"] or "",
            }
            for field, value in immutable_state.items():
                prior_value = existing.get(field)
                if field not in existing and field not in {"contract_kind", "contract_hash", "task_card_hash"}:
                    raise RuntimeError("CLOSURE_IMMUTABLE_BINDING_DRIFT")
                if not prior_value and field == "contract_kind":
                    prior_value = persisted_grant.get("contract_kind") or ContractKind.TRACKED_TASK_CARD.value
                if not prior_value and field == "contract_hash":
                    prior_value = persisted_grant.get("contract_hash") or ""
                if not prior_value and field == "task_card_hash":
                    prior_value = persisted_grant.get("task_card_hash") or ""
                if prior_value is not None and str(prior_value or "") != value:
                    raise RuntimeError("CLOSURE_IMMUTABLE_BINDING_DRIFT")
            if str(existing.get("acceptance_receipt_hash") or "") != str(external_acceptance.receipt_hash) or str(existing.get("canonical_branch") or "") != str(integration_branch) or str(existing.get("bound_action_type") or persisted_grant.get("bound_action_type") or "") != LifecycleActionType.CANDIDATE_INTEGRATE.value or str(existing.get("approval_scope") or persisted_grant.get("approval_scope") or "") != "ALLOW_ACTION_ONCE":
                raise RuntimeError("CLOSURE_IMMUTABLE_BINDING_DRIFT")
            persisted_acceptance = state.get("external_acceptance")
            if not isinstance(persisted_acceptance, Mapping) or dict(persisted_acceptance) != external_acceptance.to_dict():
                raise RuntimeError("CLOSURE_IMMUTABLE_BINDING_DRIFT")
            replay = (
                str(existing.get("task_id") or "") == task_id
                and str(existing.get("attempt_id") or "") == str(state.get("attempt_id") or "")
                and str(existing.get("candidate_commit_sha") or "") == immutable_state["candidate_commit_sha"]
                and str(existing.get("candidate_tree_sha") or "") == immutable_state["candidate_tree_sha"]
                and str(existing.get("candidate_state_hash") or "") == immutable_state["candidate_state_hash"]
                and str(existing.get("verified_receipt_hash") or "") == immutable_state["verified_receipt_hash"]
                and str(existing.get("acceptance_receipt_hash") or "") == str(external_acceptance.receipt_hash)
                and str(existing.get("canonical_branch") or "") == str(integration_branch)
                and str(existing.get("expected_canonical_head") or existing.get("canonical_head") or "") == str(expected_canonical_head)
                and dict(existing.get("runtime_identity") or {}) == dict(runtime_identity)
                and str(existing.get("approval_id") or persisted_grant.get("approval_id") or "") == str(approval.get("approval_id") or "")
                and str(existing.get("approval_issued_at") or persisted_grant.get("issued_at") or "") == str(approval.get("issued_at") or "")
                and str(existing.get("approval_expires_at") or persisted_grant.get("expires_at") or "") == str(approval.get("expires_at") or "")
                and dict(existing.get("approval_projection") or {key: persisted_grant.get(key) for key in approval_keys}) == {key: approval.get(key) for key in approval_keys}
            )
            projection = dict(existing.get("approval_projection") or {key: persisted_grant.get(key) for key in approval_keys})
            same_approval_id = str(existing.get("approval_id") or persisted_grant.get("approval_id") or "") == str(approval.get("approval_id") or "")
            if failed_pre_apply and same_approval_id:
                raise RuntimeError("CLOSURE_FAILED_APPROVAL_REUSE")
            if same_approval_id and projection != {key: approval.get(key) for key in approval_keys}:
                raise RuntimeError("CLOSURE_APPROVAL_REPLAY_DRIFT")
            if replay and not failed_pre_apply:
                return {**state, "closure_binding": dict(existing), "duplicate": True, "integration_performed": False}
        attempt_id = str(state.get("attempt_id") or "")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        candidate_commit = str(packet.get("candidate_commit_sha") or state.get("candidate_commit_sha") or "")
        candidate_tree = str(packet.get("candidate_tree_sha") or state.get("candidate_tree_sha") or "")
        candidate_state = str(packet.get("candidate_state_hash") or state.get("candidate_state_hash") or "")
        verified_receipt_hash = str(packet.get("verified_receipt_hash") or state.get("verified_receipt_hash") or "")
        approved_binding = state.get("approved_binding") if isinstance(state.get("approved_binding"), Mapping) else {}
        old_approval = approved_binding.get("approval_grant") if isinstance(approved_binding.get("approval_grant"), Mapping) else {}
        if not approved_binding or not old_approval.get("consumed_at") or old_approval.get("approval_scope") != "ALLOW_ACTION_ONCE":
            raise RuntimeError("CLOSURE_APPROVED_BINDING_REQUIRED")
        for field in ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash"):
            if not approved_binding.get(field) or str(approved_binding.get(field)) != str(packet.get(field)):
                raise RuntimeError("CLOSURE_CANDIDATE_BINDING_DRIFT")
        if external_acceptance.task_id != task_id or external_acceptance.attempt_id != attempt_id:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_BINDING_MISMATCH")
        if external_acceptance.candidate_commit != candidate_commit:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_BINDING_MISMATCH")
        approval_binding = {"candidate_commit_sha": candidate_commit, "candidate_tree_sha": candidate_tree, "candidate_state_hash": candidate_state, "verified_receipt_hash": verified_receipt_hash, "acceptance_receipt_hash": external_acceptance.receipt_hash}
        if any(str(approval.get(key) or "") != str(value) for key, value in approval_binding.items()):
            raise RuntimeError("CLOSURE_CANDIDATE_BINDING_DRIFT")
        artifact_path = Path(external_acceptance.verifier_artifact).expanduser()
        evidence_root = (self.state_dir / "acceptance-artifacts" / task_id).resolve()
        try:
            artifact_path.resolve().relative_to(evidence_root)
        except ValueError as exc:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_REQUIRED") from exc
        if not artifact_path.is_absolute() or ".git" in artifact_path.parts or not artifact_path.is_file():
            raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_REQUIRED")
        try:
            artifact_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_UNREADABLE") from exc
        if artifact_digest != external_acceptance.receipt_hash:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_HASH_MISMATCH")
        contract_kind = identity["contract_kind"]
        contract_hash = identity["contract_hash"]
        task_card_hash = identity["task_card_hash"]
        owner_inline_contract = identity["owner_inline_contract"]
        approval_validated = validate_approval_grant(
            approval,
            task_id=task_id,
            attempt_id=attempt_id,
            action_type=LifecycleActionType.CANDIDATE_INTEGRATE.value,
            task_card_hash=str(task_card_hash) if task_card_hash else None,
            contract_kind=contract_kind,
            contract_hash=contract_hash or None,
            owner_inline_contract=owner_inline_contract,
            tool_manifest_hash=str(runtime_identity.get("tool_manifest_hash") or ""),
            full_tool_schema_hash=str(runtime_identity.get("full_tool_schema_hash") or ""),
            permission_policy_hash=str(runtime_identity.get("permission_policy_hash") or ""),
            lifecycle_revision=str(runtime_identity.get("lifecycle_revision") or ""),
            server_instance_id=str(runtime_identity.get("server_instance_id") or ""),
            allow_consumed=False,
        )
        contract_data = state.get("contract") if isinstance(state.get("contract"), Mapping) else {}
        verifier_manifest = ControlledIntegrationManager._admitted_manifest(
            state,
            contract_data,
        )
        verifier_manifest_payload = [dict(item) for item in verifier_manifest]
        verifier_manifest_hash = hashlib.sha256(
            json.dumps(
                verifier_manifest_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        controller_root = Path(str(contract_data.get("controller_repo_root") or CANONICAL_SOURCE_ROOT)).expanduser().resolve()
        manager = WorktreeManager(root_dir=str(contract_data.get("target_worktree_root") or controller_root))
        current_head = manager._run_git(["rev-parse", "HEAD"], cwd=controller_root)
        if not re.fullmatch(r"[0-9a-f]{40}", expected_canonical_head) or current_head != expected_canonical_head:
            raise RuntimeError("CLOSURE_CANONICAL_HEAD_DRIFT")
        if str(approval.get("expected_canonical_head") or expected_canonical_head) != expected_canonical_head:
            raise RuntimeError("CLOSURE_HEAD_BINDING_MISMATCH")
        status = manager._run_git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=controller_root)
        if status:
            raise RuntimeError("CLOSURE_CANONICAL_DIRTY")
        if not approval.get("integration_branch") or integration_branch != str(approval.get("integration_branch")):
            raise RuntimeError("CLOSURE_BRANCH_BINDING_MISMATCH")
        current_branch = manager._run_git(["branch", "--show-current"], cwd=controller_root)
        if current_branch != integration_branch:
            raise RuntimeError("CLOSURE_CANONICAL_BRANCH_DRIFT")
        lease = state.get("lease") if isinstance(state.get("lease"), Mapping) else {}
        target_id = str(lease.get("lease_id") or state.get("target_id") or task_id)
        target_path = str(lease.get("target_worktree") or contract_data.get("target_repo_root") or "")
        if not target_path:
            raise RuntimeError("CLOSURE_TARGET_BINDING_REQUIRED")
        verification_commands = tuple(str(command) for command in contract_data.get("verifier_commands") or ())
        preview = TargetIntegrationLifecycle.build_preview(
            task_id=task_id,
            target_id=target_id,
            candidate_commit=candidate_commit,
            acceptance=external_acceptance,
            canonical_branch=integration_branch,
            expected_canonical_head=current_head,
            verification_commands=verification_commands,
            cleanup_target_id=target_id,
            rollback="retain target and candidate ref",
        )
        dirty_baseline = hashlib.sha256(status.encode()).hexdigest()
        authorization = TargetIntegrationLifecycle.authorize(
            task_id=task_id,
            campaign_id=str((state.get("request") or {}).get("campaign_id") or task_id),
            task_card_hash=str(task_card_hash or contract_hash),
            candidate_commit=candidate_commit,
            candidate_receipt_hash=verified_receipt_hash,
            acceptance_receipt_hash=external_acceptance.receipt_hash,
            canonical_root=str(controller_root),
            canonical_branch=integration_branch,
            expected_canonical_head=current_head,
            canonical_dirty_baseline=dirty_baseline,
            preview=preview,
            cleanup_target_id=target_id,
            cleanup_target_path=target_path,
            durable_ref=str(state.get("candidate_ref") or ""),
            rollback="retain target and candidate ref",
            issued_at=str(approval.get("issued_at") or _utc_now()),
            expires_at=str(approval.get("expires_at") or "") or None,
            attempt_id=attempt_id,
            candidate_tree_sha=candidate_tree,
            candidate_state_hash=candidate_state,
            reviewer_id=external_acceptance.reviewer_id,
            verifier_artifact_hash=artifact_digest,
        )
        authorization_dict = authorization.to_dict()
        authorization_dict["authorization_hash"] = authorization.authorization_hash
        closure = {
            "schema": "nexus.candidate_integration_closure.v1",
            "task_id": task_id,
            "attempt_id": attempt_id,
            "candidate_commit_sha": candidate_commit,
            "candidate_tree_sha": candidate_tree,
            "candidate_state_hash": candidate_state,
            "verified_receipt_hash": verified_receipt_hash,
            "acceptance_receipt_hash": external_acceptance.receipt_hash,
            "canonical_head": current_head,
            "expected_canonical_head": expected_canonical_head,
            "canonical_branch": integration_branch,
            "runtime_identity": dict(runtime_identity),
            "approval_id": str(approval.get("approval_id") or ""),
            "approval_issued_at": str(approval.get("issued_at") or ""),
            "approval_expires_at": str(approval.get("expires_at") or ""),
            "approval_projection": {key: approval.get(key) for key in approval_keys},
            "approval_scope": str(approval.get("approval_scope") or ""),
            "bound_action_type": LifecycleActionType.CANDIDATE_INTEGRATE.value,
            "contract_kind": contract_kind,
            "contract_hash": contract_hash,
            "task_card_hash": str(task_card_hash or ""),
            "verifier_manifest_sha256": verifier_manifest_hash,
            "preview": preview.to_dict(),
            "authorization_hash": authorization.authorization_hash,
        }
        closure_hash = hashlib.sha256(json.dumps(closure, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        closure["binding_hash"] = closure_hash
        now = _utc_now()
        duplicate = False
        expected_prior_snapshot = json.dumps(_jsonable(dict(existing)) if existing else None, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected_history_snapshot = json.dumps(_jsonable(state.get("integration_closure_history")), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected_grant_snapshot = json.dumps(_jsonable(state.get("integration_approval_grant")), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected_failure_snapshot = json.dumps(
            _jsonable(state.get("integration_execution")),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        service_contract_hash = str(state.get("contract_hash") or "")

        def mutate(current: dict[str, Any]) -> None:
            nonlocal duplicate
            expected_status = (
                "INTEGRATION_FAILED_PRE_APPLY" if failed_pre_apply else "APPROVED"
            )
            if (
                str(current.get("task_id") or "") != task_id
                or current.get("status") != expected_status
                or current.get("promotion_status") != expected_status
            ):
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            if current.get("attempt_id") != attempt_id:
                raise RuntimeError("CLOSURE_ATTEMPT_DRIFT")
            current_packet = current.get("promotion_packet") if isinstance(current.get("promotion_packet"), Mapping) else {}
            for key, expected in {
                "candidate_commit_sha": candidate_commit,
                "candidate_tree_sha": candidate_tree,
                "candidate_state_hash": candidate_state,
                "verified_receipt_hash": verified_receipt_hash,
            }.items():
                if str(current_packet.get(key) or current.get(key) or "") != str(expected):
                    raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            current_identity = resolve_contract_identity(
                current,
                expected_task_id=task_id,
                expected_head=str(current.get("controller_revision") or ""),
            )
            if (
                str(current.get("contract_hash") or "") != service_contract_hash
                or current_identity != identity
            ):
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            persisted_current_acceptance = current.get("external_acceptance")
            if not isinstance(persisted_current_acceptance, Mapping) or dict(persisted_current_acceptance) != external_acceptance.to_dict():
                if existing or persisted_current_acceptance is not None:
                    raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            if not existing and current.get("integration_approval_grant"):
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            prior = current.get("integration_closure_binding") if isinstance(current.get("integration_closure_binding"), Mapping) else None
            if json.dumps(_jsonable(dict(prior)) if prior else None, sort_keys=True, separators=(",", ":"), ensure_ascii=False) != expected_prior_snapshot:
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            if json.dumps(_jsonable(current.get("integration_closure_history")), sort_keys=True, separators=(",", ":"), ensure_ascii=False) != expected_history_snapshot:
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            if json.dumps(_jsonable(current.get("integration_approval_grant")), sort_keys=True, separators=(",", ":"), ensure_ascii=False) != expected_grant_snapshot:
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            if json.dumps(_jsonable(current.get("integration_execution")), sort_keys=True, separators=(",", ":"), ensure_ascii=False) != expected_failure_snapshot:
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            current_contract = current.get("contract") if isinstance(current.get("contract"), Mapping) else {}
            current_manifest = ControlledIntegrationManager._admitted_manifest(
                current,
                current_contract,
            )
            if list(current_manifest) != verifier_manifest_payload:
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            live_branch = manager._run_git(["branch", "--show-current"], cwd=controller_root)
            live_status = manager._run_git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=controller_root)
            if live_branch != integration_branch or live_status:
                raise RuntimeError("CLOSURE_CANONICAL_REBIND_DRIFT")
            try:
                if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != external_acceptance.receipt_hash:
                    raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_HASH_MISMATCH")
            except OSError as exc:
                raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_UNREADABLE") from exc
            if prior:
                if current.get("merge_performed") or current.get("integration_receipt") or current.get("integration_result_sha") or (current.get("integration_execution") and not failed_pre_apply) or current.get("status") in {"INTEGRATED", "INTEGRATED_AND_CLEANED", "INTEGRATED_TARGET_RETAINED", "INTEGRATION_VERIFY_FAILED_AFTER_APPLY"}:
                    raise RuntimeError("CLOSURE_REBIND_AFTER_INTEGRATION_FORBIDDEN")
                history = current.get("integration_closure_history")
                if "integration_closure_history" in current and not isinstance(history, list):
                    raise RuntimeError("CLOSURE_HISTORY_MALFORMED")
                if history is None:
                    history = []
                    current["integration_closure_history"] = history
                history.append({
                    "closure_binding": _jsonable(dict(prior)),
                    "approval_grant": _jsonable(current.get("integration_approval_grant")),
                    "preview": _jsonable(current.get("integration_preview")),
                    "authorization": _jsonable(current.get("integration_authorization")),
                    "binding_hash": prior.get("binding_hash"),
                    "superseded_at": now,
                    "superseded_by": str(approval.get("approval_id") or ""),
                    "reason": "pre_apply_rebind",
                })
            live_head = manager._run_git(["rev-parse", "HEAD"], cwd=controller_root)
            if live_head != current_head:
                raise RuntimeError("CLOSURE_CANONICAL_HEAD_DRIFT")
            consumed = dict(approval)
            consumed["consumed_at"] = now
            consumed["validation_receipt"] = approval_validated
            current["external_acceptance"] = external_acceptance.to_dict()
            current["integration_authorization"] = authorization_dict
            current["integration_preview"] = preview.to_dict()
            current["integration_approval_grant"] = consumed
            current["integration_closure_binding"] = closure
            current["integration_closure_binding_hash"] = closure_hash
            current["integration_verifier_manifest"] = verifier_manifest_payload
            if failed_pre_apply:
                failure_history = current.get("integration_failure_history")
                if "integration_failure_history" in current and not isinstance(failure_history, list):
                    raise RuntimeError("CLOSURE_FAILURE_HISTORY_MALFORMED")
                if failure_history is None:
                    failure_history = []
                    current["integration_failure_history"] = failure_history
                failure_history.append({
                    "schema": "nexus.integration_failure_history.v1",
                    "status": "INTEGRATION_FAILED_PRE_APPLY",
                    "integration_error": current.get("integration_error"),
                    "integration_status": current.get("integration_status"),
                    "integration_execution": _jsonable(current.get("integration_execution")),
                    "closure_binding_hash": prior.get("binding_hash") if prior else None,
                    "approval_id": persisted_grant.get("approval_id"),
                    "superseded_at": now,
                })
                current["status"] = "APPROVED"
                current["promotion_status"] = "APPROVED"
                current["terminal_status"] = "APPROVED"
                current["final_disposition"] = "REBIND_READY"
                current["integration_status"] = "REBIND_READY"
                current["integration_error"] = None
                current["integration_execution"] = None
                current["state_retention_status"] = "ACTIVE"
                current["archive_eligible"] = False
                current["cleanup_eligible"] = False
                status_history = current.get("status_history")
                if not isinstance(status_history, list):
                    raise RuntimeError("CLOSURE_STATUS_HISTORY_MALFORMED")
                status_history.append({
                    "at": now,
                    "status": "APPROVED",
                    "reason": "pre_apply_closure_rebind",
                })

        persisted = self._mutate_state(task_id, mutate)
        if persisted is None:
            raise KeyError(f"unknown task_id: {task_id}")
        return {**persisted, "closure_binding": closure, "duplicate": duplicate, "integration_performed": False}

    def integrate_approved(
        self,
        task_id: str,
        *,
        integration_branch: str = "nexus/integration/main",
        runtime_identity: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        request = state.get("request") or {}
        if self.ephemeral and (
            request.get("task_card_required") or request.get("lifecycle_identity_required")
        ):
            raise RuntimeError("EPHEMERAL_INTEGRATION_FORBIDDEN: rehearsal state cannot be integrated")
        if state.get("status") in {"INTEGRATED", "INTEGRATED_AND_CLEANED", "INTEGRATED_TARGET_RETAINED"} and state.get("promotion_status") == "INTEGRATED":
            return state
        promotion_status = state.get("promotion_status") or state.get("status")
        if state.get("merge_performed") or state.get("status") == "INTEGRATION_VERIFY_FAILED_AFTER_APPLY":
            raise RuntimeError("INTEGRATION_ALREADY_APPLIED_RETRY_FORBIDDEN")
        if state.get("status") not in {"APPROVED", "INTEGRATING"} and promotion_status not in {"APPROVED", "INTEGRATING"}:
            raise RuntimeError(
                "exact approved binding is required before integration; "
                f"task status must be APPROVED or INTEGRATING to integrate, got {state.get('status')}"
            )

        if runtime_identity is not None:
            approved = state.get("approved_binding") if isinstance(state.get("approved_binding"), Mapping) else {}
            integration_grant = state.get("integration_approval_grant") if isinstance(state.get("integration_approval_grant"), Mapping) else None
            grant = integration_grant or (approved.get("approval_grant") if isinstance(approved.get("approval_grant"), Mapping) else None)
            if not grant or not grant.get("consumed_at"):
                raise RuntimeError("APPROVAL_REVALIDATION_REQUIRED: persisted approval grant is missing consume evidence")
            identity = resolve_contract_identity(
                state,
                expected_task_id=task_id,
                expected_head=str(state.get("controller_revision") or ""),
            )
            for key in ("contract_kind", "contract_hash", "task_card_hash", "owner_inline_contract"):
                if key in runtime_identity and runtime_identity[key] != identity[key]:
                    raise RuntimeError("APPROVAL_RUNTIME_IDENTITY_MISMATCH")
            contract_kind = identity["contract_kind"]
            contract_hash = identity["contract_hash"]
            task_card_hash = identity["task_card_hash"]
            owner_inline_contract = identity["owner_inline_contract"]
            if integration_grant:
                validate_approval_grant(
                    integration_grant,
                    task_id=task_id,
                    attempt_id=str(state.get("attempt_id") or ""),
                    action_type=LifecycleActionType.CANDIDATE_INTEGRATE.value,
                    task_card_hash=task_card_hash,
                    contract_kind=contract_kind,
                    contract_hash=contract_hash,
                    owner_inline_contract=owner_inline_contract,
                    tool_manifest_hash=str(runtime_identity.get("tool_manifest_hash") or ""),
                    full_tool_schema_hash=str(runtime_identity.get("full_tool_schema_hash") or ""),
                    permission_policy_hash=str(runtime_identity.get("permission_policy_hash") or ""),
                    lifecycle_revision=str(runtime_identity.get("lifecycle_revision") or ""),
                    server_instance_id=str(runtime_identity.get("server_instance_id") or ""),
                    allow_consumed=True,
                )
            expected_identity = {
                "contract_kind": contract_kind,
                "contract_hash": contract_hash,
                "task_card_hash": task_card_hash,
                "tool_manifest_hash": runtime_identity.get("tool_manifest_hash"),
                "full_tool_schema_hash": runtime_identity.get("full_tool_schema_hash"),
                "permission_policy_hash": runtime_identity.get("permission_policy_hash"),
                "lifecycle_revision": runtime_identity.get("lifecycle_revision"),
                "server_instance_id": runtime_identity.get("server_instance_id"),
            }
            drift = {
                key: {"expected": value, "received": grant.get(key)}
                for key, value in expected_identity.items()
                if str(grant.get(key)) != str(value)
            }
            if drift:
                code = "APPROVAL_BINDING_MISMATCH" if set(drift) & {"contract_kind", "contract_hash", "task_card_hash"} else "APPROVAL_DEFINITION_DRIFT"
                raise RuntimeError(f"{code}: {json.dumps(drift, sort_keys=True)}")
            packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
            binding_fields = ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")
            if any(approved.get(field) != packet.get(field) for field in binding_fields):
                raise RuntimeError("APPROVAL_CANDIDATE_BINDING_DRIFT")

        approved = state.get("approved_binding") if isinstance(state.get("approved_binding"), Mapping) else {}
        raw_acceptance = state.get("external_acceptance") or approved.get("external_acceptance")
        raw_authorization = state.get("integration_authorization") or approved.get("integration_authorization")
        if raw_acceptance is None:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_REQUIRED: persisted acceptance receipt is missing")
        if raw_authorization is None:
            raise RuntimeError("OWNER_AUTHORIZATION_REQUIRED: persisted integration authorization is missing")
        acceptance_obj = raw_acceptance if isinstance(raw_acceptance, ExternalAcceptanceReceipt) else ExternalAcceptanceReceipt(**dict(raw_acceptance))
        authorization_obj = raw_authorization if isinstance(raw_authorization, IntegrationAuthorizationEnvelope) else IntegrationAuthorizationEnvelope(**{key: value for key, value in dict(raw_authorization).items() if key != "authorization_hash"})
        if acceptance_obj.task_id != task_id or acceptance_obj.candidate_commit != str((state.get("promotion_packet") or {}).get("candidate_commit_sha") or ""):
            raise RuntimeError("EXTERNAL_ACCEPTANCE_BINDING_MISMATCH")
        if authorization_obj.task_id != task_id or authorization_obj.attempt_id not in {"", str(state.get("attempt_id") or "")}:
            raise RuntimeError("INTEGRATION_AUTHORIZATION_BINDING_MISMATCH")
        if authorization_obj.candidate_commit != acceptance_obj.candidate_commit or authorization_obj.acceptance_receipt_hash != acceptance_obj.receipt_hash:
            raise RuntimeError("INTEGRATION_AUTHORIZATION_ACCEPTANCE_MISMATCH")
        if authorization_obj.canonical_branch != integration_branch:
            raise RuntimeError("INTEGRATION_AUTHORIZATION_BRANCH_DRIFT")
        if "INTEGRATION_STAGING" not in authorization_obj.action_set or "APPLY_VERIFIED_INTEGRATION" not in authorization_obj.action_set:
            raise RuntimeError("INTEGRATION_AUTHORIZATION_ACTION_SET_INCOMPLETE")
        grant = (state.get("integration_approval_grant") if isinstance(state.get("integration_approval_grant"), Mapping) else None) or (approved.get("approval_grant") if isinstance(approved.get("approval_grant"), Mapping) else None)
        if not grant or not grant.get("consumed_at"):
            raise RuntimeError("APPROVAL_REVALIDATION_REQUIRED: one-shot approval grant is not consumed")
        if grant.get("consumed_at") and grant.get("approval_scope") != "ALLOW_ACTION_ONCE":
            raise RuntimeError("APPROVAL_SCOPE_UNSUPPORTED")

        boundary_identity = resolve_contract_identity(
            state,
            expected_task_id=task_id,
            expected_head=str(state.get("controller_revision") or ""),
        )

        c_dict = state.get("contract") or {}
        request_dict = state.get("request") or {
            "what": c_dict.get("objective", "integration task"),
            "why": c_dict.get("objective", "integration task"),
            "allowed_files": c_dict.get("allowed_files", ["bounded.txt"]),
            "controller_repo_root": c_dict.get("controller_repo_root", str(Path.cwd())),
            "target_repo_root": c_dict.get("target_repo_root", str(Path.cwd() / "target")),
            "target_worktree_root": c_dict.get("target_worktree_root", str(Path.cwd())),
            "controller_revision": c_dict.get("controller_revision", "a" * 40),
            "target_base_revision": c_dict.get("target_base_revision", "a" * 40),
        }
        contract = self.build_contract(request_dict)
        protected_binding_fields = (
            "task_id",
            "attempt_id",
            "request",
            "contract",
            "promotion_packet",
            "verified_receipt",
            "approved_binding",
            "external_acceptance",
            "integration_authorization",
            "integration_approval_grant",
            "integration_closure_binding",
            "integration_closure_binding_hash",
            "integration_verifier_manifest",
            "controller_revision",
            "contract_kind",
            "contract_hash",
            "task_card_hash",
            "owner_inline_contract",
        )

        def binding_hash(bound_state: Mapping[str, Any]) -> str:
            payload = {
                key: _jsonable(bound_state.get(key)) for key in protected_binding_fields
            }
            return hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()

        def repository_recheck(
            bound_state: Mapping[str, Any],
            bound_contract: ArchitectTaskContract,
        ) -> Any:
            packet = bound_state.get("promotion_packet") if isinstance(
                bound_state.get("promotion_packet"), Mapping
            ) else {}
            verified_receipt = bound_state.get("verified_receipt") if isinstance(
                bound_state.get("verified_receipt"), Mapping
            ) else {}
            expected_policy_revision_hash = str(
                verified_receipt.get("repository_contract_policy_revision_hash") or ""
            )
            if verified_receipt.get("repository_contract_gate_passed") is not True:
                raise RuntimeError(
                    "REPOSITORY_CONTRACT_RECHECK_REQUIRED: verified gate proof is missing"
                )
            if not re.fullmatch(r"[0-9a-f]{64}", expected_policy_revision_hash):
                raise RuntimeError(
                    "REPOSITORY_CONTRACT_RECHECK_REQUIRED: policy revision hash is missing"
                )
            result = RepositoryContractGate(
                WorktreeManager(bound_contract.target_worktree_root)
            ).evaluate_committed_candidate(
                contract=bound_contract,
                candidate_commit=str(packet.get("candidate_commit_sha") or ""),
                candidate_tree_sha=str(packet.get("candidate_tree_sha") or ""),
                expected_policy_revision_hash=expected_policy_revision_hash,
                architecture_approval=(bound_state.get("approved_binding") or {}).get("architecture_approval") if isinstance(bound_state.get("approved_binding"), Mapping) else None,
                task_id=str(bound_state.get("task_id") or task_id),
                attempt_id=str(bound_state.get("attempt_id") or ""),
            )
            if not result.passed:
                raise RuntimeError(
                    "REPOSITORY_CONTRACT_RECHECK_FAILED: "
                    + json.dumps(
                        list(result.blocking_reasons),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            return result

        approved_binding_hash = binding_hash(state)
        integration_recheck = repository_recheck(state, contract)

        self._checkpoint(
            task_id,
            "INTEGRATING",
            {
                "integration_branch": integration_branch,
                "push_performed": False,
                "repository_contract_integration_recheck": _jsonable(
                    integration_recheck
                ),
            },
            attempt_id=state.get("attempt_id"),
        )
        try:
            # Hold the lifecycle state lock across the final exact-tree recheck
            # and apply call so no formal state writer can change the approved
            # packet between proof and mutation.
            with self._state_lock():
                integrating = self._load_state_path(self._state_path(task_id), task_id)
                if integrating is None:
                    raise RuntimeError("INTEGRATION_STATE_MISSING_AT_APPLY_BOUNDARY")
                if binding_hash(integrating) != approved_binding_hash:
                    raise RuntimeError("INTEGRATION_BINDING_DRIFT_AT_APPLY_BOUNDARY")
                final_identity = resolve_contract_identity(
                    integrating,
                    expected_task_id=task_id,
                    expected_head=str(integrating.get("controller_revision") or ""),
                )
                if final_identity != boundary_identity:
                    raise RuntimeError("INTEGRATION_BINDING_DRIFT_AT_APPLY_BOUNDARY")
                final_request = integrating.get("request") or request_dict
                final_contract = self.build_contract(final_request)
                final_recheck = repository_recheck(integrating, final_contract)
                integrating["repository_contract_integration_recheck"] = _jsonable(
                    final_recheck
                )
                receipt = ControlledIntegrationManager(
                    integration_root=final_contract.controller_repo_root
                ).integrate_authorized_task_state(
                    integrating,
                    integration_branch=integration_branch,
                    staging_root=str(
                        integrating.get("integration_staging_root")
                        or (
                            Path(final_contract.target_worktree_root).parent
                            / ".nexus-integration-staging"
                        )
                    ),
                    apply=True,
                    post_apply_commands=tuple(
                        tuple(command)
                        for command in integrating.get("post_apply_commands") or ()
                    ),
                )
        except IntegrationExecutionError as exc:
            failed_status = (
                "INTEGRATION_VERIFY_FAILED_AFTER_APPLY"
                if exc.merge_performed
                else "INTEGRATION_FAILED_PRE_APPLY"
            )
            integration_status = "APPLIED_NOT_VERIFIED" if exc.merge_performed else "NOT_APPLIED"
            self._checkpoint(
                task_id,
                failed_status,
                {
                    "status": failed_status,
                    "promotion_status": failed_status,
                    "integration_branch": integration_branch,
                    "integration_error": str(exc),
                    "integration_status": integration_status,
                    "integration_execution": {
                        "stage": exc.stage,
                        "branch_head_before": exc.branch_head_before,
                        "branch_head_after": exc.branch_head_after,
                        "staging_commit_sha": exc.staging_commit_sha,
                        "candidate_commit_sha": exc.candidate_commit_sha,
                        "candidate_is_ancestor": exc.merge_performed,
                        "merge_performed": exc.merge_performed,
                        "post_apply_verified": exc.post_apply_verified,
                        "failure_reason": exc.failure_reason,
                    },
                    "integration_result_sha": exc.integration_result_sha,
                    "terminal_status": failed_status,
                    "final_disposition": failed_status,
                    "state_retention_status": "ACTIONABLE",
                    "archive_eligible": False,
                    "cleanup_eligible": False,
                    "merge_performed": exc.merge_performed,
                    "push_performed": False,
                },
                attempt_id=state.get("attempt_id"),
            )
            raise
        except Exception as exc:
            self._checkpoint(
                task_id,
                "INTEGRATION_FAILED_PRE_APPLY",
                {
                    "status": "INTEGRATION_FAILED_PRE_APPLY",
                    "promotion_status": "INTEGRATION_FAILED_PRE_APPLY",
                    "integration_branch": integration_branch,
                    "integration_error": str(exc),
                    "integration_status": "NOT_APPLIED",
                    "terminal_status": "INTEGRATION_FAILED_PRE_APPLY",
                    "final_disposition": "INTEGRATION_FAILED_PRE_APPLY",
                    "state_retention_status": "ACTIONABLE",
                    "archive_eligible": False,
                    "cleanup_eligible": False,
                    "merge_performed": False,
                    "push_performed": False,
                },
                attempt_id=state.get("attempt_id"),
            )
            raise
        return self._record_integration(receipt, task_id=task_id)

    def retry_integration(self, task_id: str, *, integration_branch: Optional[str] = None) -> dict[str, Any]:
        """Retry only the integration phase after a non-merge integration failure."""
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("merge_performed") or state.get("status") == "INTEGRATION_VERIFY_FAILED_AFTER_APPLY":
            raise RuntimeError("INTEGRATION_ALREADY_APPLIED_RETRY_FORBIDDEN")
        if state.get("status") not in {"INTEGRATION_FAILED", "INTEGRATION_FAILED_PRE_APPLY"} or not state.get("approved_binding"):
            raise RuntimeError("integration retry requires the original approved binding")
        branch = integration_branch or state.get("integration_branch") or "nexus/integration/main"
        self._checkpoint(
            task_id,
            "INTEGRATING",
            {"integration_branch": branch, "integration_retry": True, "push_performed": False},
            attempt_id=state.get("attempt_id"),
        )
        return self.integrate_approved(task_id, integration_branch=str(branch))

    def _record_integration(
        self,
        receipt: Any,
        *,
        task_id: Optional[str] = None,
    ) -> dict[str, Any]:
        from nexus.orchestrator.governed_integration import IntegrationReceipt
        if not isinstance(receipt, IntegrationReceipt):
            raise TypeError("receipt must be an IntegrationReceipt instance")
        rec_task_id = getattr(receipt, "task_id", None) or task_id
        if not rec_task_id:
            raise KeyError("unknown task_id")
        task_id = rec_task_id
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("status") not in {"APPROVED", "INTEGRATING"}:
            raise RuntimeError("task status must be APPROVED or INTEGRATING to record integration")
        if not receipt.verifier_passed:
            raise RuntimeError("integration receipt verifier_passed must be True")
        if not receipt.merge_performed:
            raise RuntimeError("integration receipt merge_performed must be True")
        if receipt.push_performed:
            raise RuntimeError("integration receipt push_performed must be False")
        if not getattr(receipt, "post_apply_verified", False):
            raise RuntimeError("post-apply verification is required before integration recording")
        if getattr(receipt, "staging_commit_sha", None) != receipt.integration_commit_sha:
            raise RuntimeError("integration result must equal the verified staging commit")
        acceptance_state = state.get("external_acceptance") if isinstance(state.get("external_acceptance"), Mapping) else {}
        authorization_state = state.get("integration_authorization") if isinstance(state.get("integration_authorization"), Mapping) else {}
        if acceptance_state or authorization_state:
            if getattr(receipt, "acceptance_receipt_hash", None) != acceptance_state.get("receipt_hash"):
                raise RuntimeError("integration receipt acceptance binding mismatch")
            if getattr(receipt, "authorization_hash", None) != authorization_state.get("authorization_hash"):
                raise RuntimeError("integration receipt authorization binding mismatch")

        packet = state.get("promotion_packet") or {"candidate_commit_sha": receipt.integration_commit_sha}
        binding = state.get("approved_binding") or packet
        if not binding or not packet:
            raise RuntimeError("exact approved binding is required for integration recording")
        binding_fields = ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")
        if state.get("approved_binding") and any(binding.get(f) != packet.get(f) for f in binding_fields):
            raise RuntimeError("approved binding mismatch")
        rcpt_cand_sha = getattr(receipt, "candidate_commit_sha", None)
        if rcpt_cand_sha and rcpt_cand_sha != binding.get("candidate_commit_sha"):
            raise RuntimeError("receipt candidate_commit_sha does not match approved binding")

        c_dict = state.get("contract") or {}
        req_dict = state.get("request") or {
            "what": c_dict.get("objective", "integration task"),
            "why": c_dict.get("objective", "integration task"),
            "allowed_files": c_dict.get("allowed_files", ["bounded.txt"]),
            "controller_repo_root": c_dict.get("controller_repo_root", str(Path.cwd())),
            "target_repo_root": c_dict.get("target_repo_root", str(Path.cwd() / "target")),
            "target_worktree_root": c_dict.get("target_worktree_root", str(Path.cwd())),
            "controller_revision": c_dict.get("controller_revision", "a" * 40),
            "target_base_revision": c_dict.get("target_base_revision", "a" * 40),
        }
        contract = self.build_contract(req_dict)
        controller_root = Path(contract.controller_repo_root).resolve()
        manager = WorktreeManager(root_dir=contract.target_worktree_root)

        try:
            actual = manager._run_git(["rev-parse", "--verify", f"{receipt.integration_commit_sha}^{{commit}}"], cwd=controller_root)
            if actual != receipt.integration_commit_sha:
                raise RuntimeError("integration result sha not present in controller")
            candidate_sha = binding.get("candidate_commit_sha")
            if candidate_sha:
                res = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", candidate_sha, receipt.integration_commit_sha],
                    cwd=controller_root,
                    capture_output=True,
                    text=True,
                )
                if res.returncode != 0:
                    raise RuntimeError("integration result commit does not contain candidate commit")
        except Exception as exc:
            if not self.ephemeral:
                raise RuntimeError(f"integration result SHA verification failed: {exc}")

        updates = {
            "candidate_commit_sha": binding.get("candidate_commit_sha"),
            "candidate_tree_sha": binding.get("candidate_tree_sha"),
            "candidate_state_hash": binding.get("candidate_state_hash"),
            "verified_receipt_hash": binding.get("verified_receipt_hash"),
            "candidate_ref": state.get("candidate_ref") or f"refs/heads/nexus/task/{task_id}",
            "approved_binding": binding,
            "integration_branch": receipt.integration_branch,
            "integration_base_sha": receipt.integration_base_sha,
            "integration_result_sha": receipt.integration_commit_sha,
            "integration_receipt": asdict(receipt),
            "candidate_status": "INTEGRATED",
            "promotion_status": "INTEGRATED",
            "terminal_status": "INTEGRATED",
            "final_disposition": "INTEGRATED",
            "status": "INTEGRATED",
            "merge_performed": True,
            "push_performed": False,
            "state_retention_status": "TERMINAL",
            "archive_eligible": True,
        }
        res = self._checkpoint(task_id, "INTEGRATED", updates, attempt_id=state.get("attempt_id"))
        return res or self._read_state(task_id) or state
