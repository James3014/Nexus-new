"""Execution readiness convergence evaluator for issue #807 (G1 gate).

Typed callers may gather plane observations, but compatibility observations are
not authority.  The evaluator rebinds planes that have canonical durable owners
before it can produce ``READY_TO_EXECUTE``:

- source identity is bound to the physical repository remote plus commit/tree;
- governance health is proved by the canonical standing-grant inspector;
- material authority is re-evaluated through the #515 durable standing grant;
- material replay state is re-read from the durable task service;
- material Workforce PASS requires Planner/Admission/provider evidence hashes;
- optional Completion compatibility uses the request's required capabilities.

The gate never repairs, reloads, selects routes/workers, grants authority, or
asserts post-execution truth.  A compatibility env/default PASS may trigger a
canonical observation, but can never itself be readiness evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from nexus.contracts.autonomy_goal import AutonomyActionClass, RepositoryIdentity
from nexus.contracts.execution_readiness import (
    COMPLETION_AUTHORITY_KIND,
    OUTCOME_EVIDENCE_MAX_IDENTITIES,
    CanonicalNextAction,
    ExecutionReadinessBlocker,
    ExecutionReadinessBlockerCode,
    ExecutionReadinessOutcome,
    ExecutionReadinessPlane,
    ExecutionReadinessPlaneResult,
    ExecutionReadinessRequest,
    ExecutionReadinessResult,
    ExecutionReadinessStatus,
    blocker_plane,
)

GATEWAY_OBSERVATION_SCHEMA = "nexus.gateway.execution_readiness_observation.v1"
COMPLETION_INTERFACE_REVISION = "nexus-core.completion.v1"
COMPLETION_REPOSITORY = "James3014/nexus-core"
# Compatibility export for the current Gateway completion observation helper.
# This tuple is not used to decide request compatibility; the request's own
# required_capabilities is the authority for that comparison.
_COMPLETION_REQUIRED_CAPABILITIES = (
    "COMPLETION_VERDICT",
    "EVIDENCE_VERIFY",
    "RECEIPT_BIND",
)

_BLOCKER_NEXT_ACTION: dict[ExecutionReadinessBlockerCode, CanonicalNextAction] = {
    ExecutionReadinessBlockerCode.GOVERNANCE_PLANE_RECOVERY_REQUIRED: (
        CanonicalNextAction.ROUTE_TO_ISSUE_806_BREAK_GLASS_RECOVERY
    ),
    ExecutionReadinessBlockerCode.SOURCE_BINDING_REQUIRED: (
        CanonicalNextAction.BIND_EXACT_DESIRED_SOURCE_IDENTITY
    ),
    ExecutionReadinessBlockerCode.SOURCE_REALM_MISMATCH: (
        CanonicalNextAction.BIND_EXACT_DESIRED_SOURCE_IDENTITY
    ),
    ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED: (
        CanonicalNextAction.ROUTE_TO_ISSUE_526_GATEWAY_REBIND_RELOAD
    ),
    ExecutionReadinessBlockerCode.HOST_ACTION_BINDING_GAP: (
        CanonicalNextAction.RECONNECT_BOUND_HOST_CONNECTOR
    ),
    ExecutionReadinessBlockerCode.ACTION_SCHEMA_OR_REVIEW_STALE: (
        CanonicalNextAction.REFRESH_SCHEMA_AND_PERMISSION_SURFACE
    ),
    ExecutionReadinessBlockerCode.PERMISSION_SURFACE_STALE: (
        CanonicalNextAction.REFRESH_SCHEMA_AND_PERMISSION_SURFACE
    ),
    ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED: (
        CanonicalNextAction.BIND_COMPLETION_CONTRACT_IDENTITY
    ),
    ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING: (
        CanonicalNextAction.OBTAIN_NORMAL_TASK_AUTHORITY
    ),
    ExecutionReadinessBlockerCode.AUTHORITY_OUT_OF_SCOPE: (
        CanonicalNextAction.OBTAIN_NORMAL_TASK_AUTHORITY
    ),
    ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE: (
        CanonicalNextAction.RECONCILE_SAME_REQUEST_FENCE
    ),
    ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY: (
        CanonicalNextAction.RUN_PLANNER_AND_WORKFORCE_ADMISSION
    ),
}

_BLOCKER_MESSAGE: dict[ExecutionReadinessBlockerCode, str] = {
    ExecutionReadinessBlockerCode.GOVERNANCE_PLANE_RECOVERY_REQUIRED: (
        "governance plane requires owner-authorized issue #806 break-glass recovery; "
        "this gate never triggers recovery"
    ),
    ExecutionReadinessBlockerCode.SOURCE_BINDING_REQUIRED: (
        "bind the exact desired source commit/tree (or explicit deployment identity) "
        "before execution"
    ),
    ExecutionReadinessBlockerCode.SOURCE_REALM_MISMATCH: (
        "observed source realm identity does not match the intended source identity"
    ),
    ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED: (
        "route gateway rebinding to the issue #526 canonical rebind/reload primitive; "
        "this gate never reloads the gateway"
    ),
    ExecutionReadinessBlockerCode.HOST_ACTION_BINDING_GAP: (
        "reconnect and rebind the exact connector/host tool mapping"
    ),
    ExecutionReadinessBlockerCode.ACTION_SCHEMA_OR_REVIEW_STALE: (
        "action surface schema or review fingerprint is stale relative to the desired "
        "source; refresh via the issue #526 rebind/reload path"
    ),
    ExecutionReadinessBlockerCode.PERMISSION_SURFACE_STALE: (
        "permission surface fingerprint is stale relative to the desired source; refresh "
        "via the issue #526 rebind/reload path"
    ),
    ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED: (
        "bind the exact canonical completion authority identity required by the "
        "intended execution contract"
    ),
    ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING: (
        "obtain the normal task/goal/standing-grant authority before execution"
    ),
    ExecutionReadinessBlockerCode.AUTHORITY_OUT_OF_SCOPE: (
        "intended action family is outside the granted authority scope"
    ),
    ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE: (
        "reconcile the same request/fence identity; blind retry is prohibited"
    ),
    ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY: (
        "run CapabilityPlanner routing and Workforce Admission/provider preflight"
    ),
}

_UNTRUSTED_COMPATIBILITY_PASSES: dict[ExecutionReadinessPlane, frozenset[str]] = {
    ExecutionReadinessPlane.GOVERNANCE: frozenset({
        "governance_plane:default_no_open_recovery",
        "NEXUS_READINESS_GOVERNANCE_STATUS=PASSED",
    }),
    ExecutionReadinessPlane.AUTHORITY: frozenset({
        "authority_plane:in_process_caller_context",
        "NEXUS_READINESS_AUTHORITY_STATUS=PASSED",
    }),
    ExecutionReadinessPlane.REPLAY_FENCE: frozenset({
        "replay_fence_plane:in_process_first_observation",
        "NEXUS_READINESS_REPLAY_FENCE_STATUS=PASSED",
    }),
    ExecutionReadinessPlane.WORKFORCE: frozenset({"NEXUS_READINESS_WORKFORCE_STATUS=PASSED"}),
}

_AUTHORITY_ACTION_FAMILY: dict[str, AutonomyActionClass] = {
    "MUTATE_BOUNDED": AutonomyActionClass.TASK_SUBMIT,
    "TASK_SUBMIT": AutonomyActionClass.TASK_SUBMIT,
    "TASK_RETRY": AutonomyActionClass.TASK_RETRY,
    "CANDIDATE_VERIFY": AutonomyActionClass.CANDIDATE_VERIFY,
    "CANDIDATE_APPROVE": AutonomyActionClass.CANDIDATE_APPROVE,
    "CANDIDATE_INTEGRATE": AutonomyActionClass.CANDIDATE_INTEGRATE,
    "REPOSITORY_PUSH": AutonomyActionClass.REPOSITORY_PUSH,
    "GITHUB_MERGE": AutonomyActionClass.GITHUB_MERGE,
    "RUNTIME_ACTIVATE": AutonomyActionClass.RUNTIME_ACTIVATE,
    "PRODUCTION_RELEASE": AutonomyActionClass.PRODUCTION_RELEASE,
}


@dataclass(frozen=True)
class PlaneObservation:
    """Typed evidence for one plane, gathered by a caller."""

    plane: ExecutionReadinessPlane
    status: ExecutionReadinessStatus
    blocker_code: ExecutionReadinessBlockerCode | None = None
    evidence_identities: tuple[str, ...] = ()
    # Material Workforce callers must provide the canonical Planner output,
    # demands, and admission receipt as typed data.  Hash strings alone are
    # deliberately insufficient evidence.
    workforce_dispatch_binding: Mapping[str, Any] | None = None

    def to_plane_result(self) -> ExecutionReadinessPlaneResult:
        return ExecutionReadinessPlaneResult(
            plane=self.plane,
            status=self.status,
            blocker_code=self.blocker_code,
            evidence_identities=self.evidence_identities,
        )


@dataclass(frozen=True)
class GatewayReadinessObservation:
    """In-process Gateway observation mirroring ``nexus_gateway_status``."""

    gateway_instance_id: str
    observed_repo_head: str
    observed_repo_tree: str
    observed_runtime_sha256: str
    runtime_sha256_at_start: str
    tool_manifest_revision: str
    full_tool_schema_hash: str
    permission_policy_hash: str
    reload_required: bool

    def to_observation_payload(self) -> dict[str, str]:
        return {
            "schema": GATEWAY_OBSERVATION_SCHEMA,
            "gateway_instance_id": self.gateway_instance_id,
            "observed_repo_head": self.observed_repo_head,
            "observed_repo_tree": self.observed_repo_tree,
            "observed_runtime_sha256": self.observed_runtime_sha256,
            "runtime_sha256_at_start": self.runtime_sha256_at_start,
            "tool_manifest_revision": self.tool_manifest_revision,
            "full_tool_schema_hash": self.full_tool_schema_hash,
            "permission_policy_hash": self.permission_policy_hash,
            "reload_required": str(self.reload_required).lower(),
        }


def _physical_repository_id() -> str:
    """Derive owner/name from the canonical checkout's physical origin remote."""

    root = Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    remote = result.stdout.strip()
    match = re.search(r"github\.com(?::|/)([^/\s]+)/([^/\s]+)$", remote)
    if match is None:
        return ""
    owner, repository = match.groups()
    if repository.endswith(".git"):
        repository = repository[:-4]
    return f"{owner}/{repository}" if owner and repository else ""


def evaluate_source_binding(
    request: ExecutionReadinessRequest,
    observation: GatewayReadinessObservation,
) -> PlaneObservation:
    """Bind request repository + source to the physical canonical checkout."""

    observed_repository = _physical_repository_id()
    requested_repository = f"{request.repository_owner}/{request.repository_name}"
    observed_commit = observation.observed_repo_head.strip().lower()
    observed_tree = observation.observed_repo_tree.strip().lower()
    observed_valid = (
        len(observed_commit) == 40
        and len(observed_tree) == 40
        and all(char in "0123456789abcdef" for char in observed_commit)
        and all(char in "0123456789abcdef" for char in observed_tree)
    )
    evidence = (
        f"source_requested_repository={requested_repository}",
        f"source_observed_repository={observed_repository or '<missing>'}",
        f"source_desired_commit={request.intended_source_commit}",
        f"source_desired_tree={request.intended_source_tree}",
        f"source_observed_commit={observed_commit or '<missing>'}",
        f"source_observed_tree={observed_tree or '<missing>'}",
    )
    if not observed_repository or not observed_valid:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.SOURCE,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.SOURCE_BINDING_REQUIRED,
            evidence_identities=evidence,
        )
    if requested_repository != observed_repository:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.SOURCE,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.SOURCE_REALM_MISMATCH,
            evidence_identities=evidence,
        )
    if (
        request.intended_source_commit != observed_commit
        or request.intended_source_tree != observed_tree
    ):
        return PlaneObservation(
            plane=ExecutionReadinessPlane.SOURCE,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.SOURCE_REALM_MISMATCH,
            evidence_identities=evidence,
        )
    return PlaneObservation(
        plane=ExecutionReadinessPlane.SOURCE,
        status=ExecutionReadinessStatus.PASSED,
        evidence_identities=evidence,
    )


@dataclass(frozen=True)
class CompletionAuthorityObservation:
    """Observed completion-authority identity (material-only plane-5 input)."""

    observed_authority_kind: str
    observed_repository: str
    observed_artifact_identity: str
    observed_interface_revision: str
    observed_capabilities: tuple[str, ...] = ()

    def to_observation_payload(self) -> dict[str, str | tuple[str, ...]]:
        return {
            "completion_observed_authority_kind": self.observed_authority_kind,
            "completion_observed_repository": self.observed_repository,
            "completion_observed_artifact_identity": self.observed_artifact_identity,
            "completion_observed_interface_revision": self.observed_interface_revision,
            "completion_observed_capabilities": tuple(self.observed_capabilities),
        }

    def identity_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_observation_payload(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


def evaluate_completion_contract(
    required: object,
    observation: CompletionAuthorityObservation | None,
) -> tuple[bool, ExecutionReadinessBlockerCode | None, tuple[str, ...]]:
    """Compare the exact required Completion contract to observed identity."""

    evidence = (
        "completion_contract:required",
        f"completion_contract:required_repository={required.repository}",
        f"completion_contract:required_interface={required.interface_revision}",
        "completion_contract:authority_kind=NEXUS_CORE_COMPLETION",
    )
    if observation is None:
        return (
            False,
            ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED,
            evidence + ("completion_contract:observation_unavailable",),
        )
    evidence = evidence + (
        f"completion_contract:observed_artifact={observation.observed_artifact_identity}",
        f"completion_contract:observed_interface={observation.observed_interface_revision}",
    )
    if observation.observed_authority_kind != COMPLETION_AUTHORITY_KIND:
        return False, ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED, evidence
    if observation.observed_repository != required.repository:
        return False, ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED, evidence
    if observation.observed_artifact_identity != required.artifact_or_source_identity:
        return False, ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED, evidence
    if observation.observed_interface_revision != required.interface_revision:
        return False, ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED, evidence
    required_capabilities = set(required.required_capabilities)
    if not required_capabilities.issubset(set(observation.observed_capabilities)):
        return False, ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED, evidence
    return True, None, evidence


class ReadinessEvidenceError(ValueError):
    """Raised when caller evidence cannot produce a decisive safe result."""

    def __init__(self, reason: str, plane: ExecutionReadinessPlane | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.plane = plane


def _merge_evidence(*chunks: Sequence[str]) -> tuple[str, ...]:
    merged: list[str] = []
    for chunk in chunks:
        for identity in chunk:
            if identity not in merged:
                merged.append(identity)
    return tuple(merged)


def _canonical_governance_observation(moment: datetime) -> PlaneObservation:
    """Prove the normal authority observer is operational; do not infer grant validity."""

    try:
        from nexus.orchestrator.standing_grant_store import inspect_standing_grant_receipt

        snapshot = inspect_standing_grant_receipt(now=moment)
        schema = str(snapshot.get("schema") or "")
        status = str(snapshot.get("status") or "")
        if not schema or not status:
            raise ValueError("standing grant inspection returned no schema/status")
    except Exception as exc:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.GOVERNANCE,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.GOVERNANCE_PLANE_RECOVERY_REQUIRED,
            evidence_identities=(
                "governance_observer=standing_grant_store.inspect_standing_grant_receipt",
                f"governance_observer_error={exc.__class__.__name__}",
            ),
        )
    return PlaneObservation(
        plane=ExecutionReadinessPlane.GOVERNANCE,
        status=ExecutionReadinessStatus.PASSED,
        evidence_identities=(
            "governance_observer=standing_grant_store.inspect_standing_grant_receipt",
            f"governance_snapshot_schema={schema}",
            f"governance_authority_snapshot_status={status}",
        ),
    )


def _authority_action(request: ExecutionReadinessRequest) -> AutonomyActionClass | None:
    raw = request.required_action_family.strip().upper()
    try:
        return AutonomyActionClass(raw)
    except ValueError:
        return _AUTHORITY_ACTION_FAMILY.get(raw)


def _canonical_authority_observation(
    request: ExecutionReadinessRequest,
    moment: datetime,
) -> PlaneObservation:
    """Re-evaluate a material Goal/action through the canonical #515 grant."""

    goal_id = request.task_campaign_goal_identity
    if not goal_id:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.AUTHORITY,
            status=ExecutionReadinessStatus.PASSED,
            evidence_identities=(
                "authority_plane:non_material:no_task_campaign_goal_identity",
                f"authority_action_family={request.required_action_family}",
            ),
        )
    action = _authority_action(request)
    if action is None:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.AUTHORITY,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.AUTHORITY_OUT_OF_SCOPE,
            evidence_identities=(
                f"authority_goal_id={goal_id}",
                f"authority_action_family_unmapped={request.required_action_family}",
            ),
        )
    try:
        from nexus.orchestrator.standing_grant_store import (
            evaluate_rehydrated_durable_standing_grant,
            inspect_standing_grant_receipt,
        )

        snapshot = inspect_standing_grant_receipt(now=moment)
    except Exception as exc:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.AUTHORITY,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING,
            evidence_identities=(
                f"authority_goal_id={goal_id}",
                f"authority_action={action.value}",
                f"authority_observer_error={exc.__class__.__name__}",
            ),
        )
    snapshot_status = str(snapshot.get("status") or "UNKNOWN")
    evidence = (
        f"authority_receipt_status={snapshot_status}",
        f"authority_receipt_hash={snapshot.get('receipt_hash') or '<missing>'}",
        f"authority_owner_id={snapshot.get('owner_id') or '<missing>'}",
        f"authority_coordinator_id={snapshot.get('coordinator_id') or '<missing>'}",
        f"authority_repository_id={snapshot.get('repository_id') or '<missing>'}",
        f"authority_goal_id={goal_id}",
        f"authority_action={action.value}",
        f"authority_expires_at={snapshot.get('expires_at') or '<missing>'}",
    )
    if snapshot_status != "VALID":
        return PlaneObservation(
            plane=ExecutionReadinessPlane.AUTHORITY,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING,
            evidence_identities=evidence,
        )
    try:
        canonical_remote = str(snapshot.get("canonical_remote") or "").strip()
        decision = evaluate_rehydrated_durable_standing_grant(
            requested_owner_id=str(snapshot.get("owner_id") or ""),
            requested_coordinator_id=str(snapshot.get("coordinator_id") or ""),
            repository=RepositoryIdentity(
                repository_id=f"{request.repository_owner}/{request.repository_name}",
                canonical_remote=canonical_remote,
            ),
            goal_id=goal_id,
            action=action,
            requested_at=moment,
        )
    except Exception as exc:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.AUTHORITY,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING,
            evidence_identities=evidence + (f"authority_evaluator_error={exc.__class__.__name__}",),
        )
    outcome = getattr(decision.outcome, "value", str(decision.outcome))
    decision_evidence = evidence + (
        f"authority_context_hash={decision.context_hash}",
        f"authority_decision_hash={decision.decision_hash}",
        f"authority_outcome={outcome}",
    )
    if outcome == "GRANT_MATCH" and decision.mutation_authorized is True:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.AUTHORITY,
            status=ExecutionReadinessStatus.PASSED,
            evidence_identities=decision_evidence,
        )
    code = (
        ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING
        if outcome == "INVALID"
        else ExecutionReadinessBlockerCode.AUTHORITY_OUT_OF_SCOPE
    )
    return PlaneObservation(
        plane=ExecutionReadinessPlane.AUTHORITY,
        status=ExecutionReadinessStatus.BLOCKED,
        blocker_code=code,
        evidence_identities=decision_evidence,
    )


def _replay_is_material(request: ExecutionReadinessRequest) -> bool:
    return (
        bool(request.task_campaign_goal_identity)
        and "TASK" in request.execution_contract_kind.upper()
    )


def _canonical_replay_observation(request: ExecutionReadinessRequest) -> PlaneObservation:
    """Read durable task/reconcile state when the execution contract binds a task."""

    if not _replay_is_material(request):
        return PlaneObservation(
            plane=ExecutionReadinessPlane.REPLAY_FENCE,
            status=ExecutionReadinessStatus.PASSED,
            evidence_identities=("replay_fence_plane:non_material:no_tracked_task_binding",),
        )
    task_id = str(request.task_campaign_goal_identity)
    try:
        from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

        snapshot = SelfHostedTaskService().get_task_snapshot(task_id, include_details=True)
    except Exception as exc:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.REPLAY_FENCE,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE,
            evidence_identities=(
                f"replay_task_id={task_id}",
                f"replay_observer_error={exc.__class__.__name__}",
            ),
        )
    if not isinstance(snapshot, Mapping):
        return PlaneObservation(
            plane=ExecutionReadinessPlane.REPLAY_FENCE,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE,
            evidence_identities=(f"replay_task_id={task_id}", "replay_snapshot=missing"),
        )
    task_action = snapshot.get("task_action")
    action = task_action if isinstance(task_action, Mapping) else {}
    status = str(snapshot.get("status") or "UNKNOWN")
    next_action = str(action.get("next_action") or snapshot.get("next_action") or "")
    evidence = (
        f"replay_task_id={task_id}",
        f"replay_attempt_id={snapshot.get('attempt_id') or '<missing>'}",
        f"replay_status={status}",
        f"replay_next_action={next_action or '<none>'}",
        f"replay_action_id={snapshot.get('action_id') or '<missing>'}",
        f"replay_request_hash={snapshot.get('request_hash') or '<missing>'}",
    )
    reconciliation_required = bool(
        snapshot.get("reconciliation_required")
        or snapshot.get("uncertain_mutation")
        or next_action == "nexus_task_reconcile"
        or status == "UNKNOWN_REQUIRES_RECONCILE"
    )
    if reconciliation_required:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.REPLAY_FENCE,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE,
            evidence_identities=evidence,
        )
    return PlaneObservation(
        plane=ExecutionReadinessPlane.REPLAY_FENCE,
        status=ExecutionReadinessStatus.PASSED,
        evidence_identities=evidence,
    )


def _evidence_map(observation: PlaneObservation) -> dict[str, str]:
    values: dict[str, str] = {}
    for identity in observation.evidence_identities:
        if "=" not in identity:
            continue
        key, value = identity.split("=", 1)
        values[key] = value
    return values


def _canonical_workforce_observation(
    request: ExecutionReadinessRequest,
    supplied: Sequence[PlaneObservation],
) -> PlaneObservation:
    """Revalidate the canonical Planner -> Admission binding for material work."""

    if not request.worker_constraints:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.WORKFORCE,
            status=ExecutionReadinessStatus.PASSED,
            evidence_identities=("workforce_plane:non_material:no_worker_constraints",),
        )
    for observation in supplied:
        if observation.status is not ExecutionReadinessStatus.PASSED:
            continue
        binding = observation.workforce_dispatch_binding
        if not isinstance(binding, Mapping):
            continue
        required_binding_fields = (
            "canonical_dispatch_envelope",
            "task_id",
            "attempt_id",
            "task_card_path",
            "task_card_hash",
        )
        if any(not binding.get(field) for field in required_binding_fields):
            continue
        demands = binding.get("workforce_demands")
        admission = binding.get("workforce_admission")
        planner = binding.get("planner_output")
        if not isinstance(demands, Mapping) or not isinstance(admission, Mapping):
            continue
        # The admission validator is the sole policy authority.  The planner
        # snapshot is checked only for lineage, never recomputed here.
        if not isinstance(planner, Mapping):
            continue
        planned_demands = (
            planner.get("plan_payload", {}).get("signal_snapshot", {}).get("workforce_demands")
            if isinstance(planner.get("plan_payload"), Mapping)
            else None
        )
        if planned_demands != demands:
            continue
        try:
            from nexus.orchestrator.self_hosted_task_service import (
                validate_workforce_dispatch_binding,
            )

            validated = validate_workforce_dispatch_binding(
                {
                    "planner_output": planner,
                    "workforce_demands": demands,
                    "workforce_admission": admission,
                    "canonical_dispatch_envelope": binding.get("canonical_dispatch_envelope"),
                    "task_id": binding.get("task_id", ""),
                    "attempt_id": binding.get("attempt_id", ""),
                    "task_card_path": binding.get("task_card_path", ""),
                    "task_card_hash": binding.get("task_card_hash", ""),
                },
                require_binding=True,
            )
        except Exception:
            continue
        if not isinstance(validated, Mapping):
            continue
        identity = {
            "worker": str(validated.get("worker_id") or "").strip().lower(),
            "worker_id": str(validated.get("worker_id") or "").strip().lower(),
            "provider": str(validated.get("provider") or "").strip().lower(),
            "model": str(validated.get("model") or "").strip().lower(),
        }
        for raw_constraint in request.worker_constraints:
            key, separator, value = str(raw_constraint).partition("=")
            key, value = key.strip().lower(), value.strip().lower()
            if separator and key in identity and identity[key] != value:
                break
        else:
            evidence = tuple(
                item
                for item in observation.evidence_identities
                if item not in _UNTRUSTED_COMPATIBILITY_PASSES[ExecutionReadinessPlane.WORKFORCE]
            ) + tuple(
                f"workforce_{key}={validated[key]}"
                for key in (
                    "worker_id",
                    "provider",
                    "model",
                    "policy_hash",
                    "binding_hash",
                    "aggregate_binding_hash",
                )
                if isinstance(validated.get(key), str) and validated[key]
            )
            return PlaneObservation(
                plane=ExecutionReadinessPlane.WORKFORCE,
                status=ExecutionReadinessStatus.PASSED,
                evidence_identities=evidence,
                workforce_dispatch_binding=binding,
            )
    return PlaneObservation(
        plane=ExecutionReadinessPlane.WORKFORCE,
        status=ExecutionReadinessStatus.BLOCKED,
        blocker_code=ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY,
        evidence_identities=(
            "workforce_plane:canonical_planner_admission_provider_evidence_required",
            *tuple(f"workforce_constraint={item}" for item in request.worker_constraints[:4]),
        ),
    )


def _has_explicit_block(observations: Sequence[PlaneObservation]) -> bool:
    return any(item.status is ExecutionReadinessStatus.BLOCKED for item in observations)


def _normalize_canonical_planes(
    request: ExecutionReadinessRequest,
    plane_observations: Mapping[ExecutionReadinessPlane, Sequence[PlaneObservation]],
    moment: datetime,
) -> dict[ExecutionReadinessPlane, tuple[PlaneObservation, ...]]:
    """Replace compatibility PASS observations with canonical/typed evidence."""

    normalized = {plane: tuple(values) for plane, values in plane_observations.items()}
    for plane in (
        ExecutionReadinessPlane.GOVERNANCE,
        ExecutionReadinessPlane.AUTHORITY,
        ExecutionReadinessPlane.REPLAY_FENCE,
        ExecutionReadinessPlane.WORKFORCE,
    ):
        supplied = tuple(normalized.get(plane, ()))
        if not supplied or _has_explicit_block(supplied):
            continue
        if not any(item.status is ExecutionReadinessStatus.PASSED for item in supplied):
            continue
        if plane is ExecutionReadinessPlane.GOVERNANCE:
            normalized[plane] = (_canonical_governance_observation(moment),)
        elif plane is ExecutionReadinessPlane.AUTHORITY:
            normalized[plane] = (_canonical_authority_observation(request, moment),)
        elif plane is ExecutionReadinessPlane.REPLAY_FENCE:
            normalized[plane] = (_canonical_replay_observation(request),)
        else:
            normalized[plane] = (_canonical_workforce_observation(request, supplied),)
    return normalized


def _aggregate_plane(
    plane: ExecutionReadinessPlane,
    observations: Sequence[PlaneObservation],
) -> tuple[ExecutionReadinessStatus, ExecutionReadinessBlockerCode | None, tuple[str, ...]]:
    if not observations:
        return ExecutionReadinessStatus.UNPROVEN, None, ()
    for observation in observations:
        if observation.plane is not plane:
            raise ReadinessEvidenceError("PLANE_OBSERVATION_MISMATCH", plane)
        if observation.status is ExecutionReadinessStatus.BLOCKED:
            if observation.blocker_code is None:
                raise ReadinessEvidenceError("BLOCKED_OBSERVATION_REQUIRES_CODE", plane)
            if blocker_plane(observation.blocker_code) is not plane:
                raise ReadinessEvidenceError("OBSERVATION_CODE_PLANE_MISMATCH", plane)
        elif observation.blocker_code is not None:
            raise ReadinessEvidenceError("NON_BLOCKED_OBSERVATION_MUST_NOT_CARRY_CODE", plane)
        if (
            observation.status is ExecutionReadinessStatus.UNPROVEN
            and observation.evidence_identities
        ):
            raise ReadinessEvidenceError("UNPROVEN_OBSERVATION_MUST_NOT_CARRY_EVIDENCE", plane)
    blocked = next(
        (item for item in observations if item.status is ExecutionReadinessStatus.BLOCKED),
        None,
    )
    if blocked is not None:
        return (
            ExecutionReadinessStatus.BLOCKED,
            blocked.blocker_code,
            _merge_evidence(*(item.evidence_identities for item in observations)),
        )
    if any(item.status is ExecutionReadinessStatus.UNPROVEN for item in observations):
        return ExecutionReadinessStatus.UNPROVEN, None, ()
    return (
        ExecutionReadinessStatus.PASSED,
        None,
        _merge_evidence(*(item.evidence_identities for item in observations)),
    )


def evaluate_execution_readiness(
    request: ExecutionReadinessRequest,
    plane_observations: Mapping[ExecutionReadinessPlane, Sequence[PlaneObservation]],
    *,
    completion_observation: CompletionAuthorityObservation | None = None,
    evaluated_at: datetime | None = None,
) -> ExecutionReadinessResult:
    """Converge evidence after re-binding canonical planes at one watermark."""

    moment = evaluated_at or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ReadinessEvidenceError("EVALUATED_AT_MUST_BE_TIMEZONE_AWARE")

    canonical_observations = _normalize_canonical_planes(request, plane_observations, moment)
    aggregated: dict[
        ExecutionReadinessPlane,
        tuple[ExecutionReadinessStatus, ExecutionReadinessBlockerCode | None, tuple[str, ...]],
    ] = {}
    for plane in ExecutionReadinessPlane:
        aggregated[plane] = _aggregate_plane(plane, canonical_observations.get(plane, ()))

    completion_ok: bool | None = None
    completion_code: ExecutionReadinessBlockerCode | None = None
    completion_evidence: tuple[str, ...] = ()
    if request.required_completion_contract is not None:
        completion_ok, completion_code, completion_evidence = evaluate_completion_contract(
            request.required_completion_contract, completion_observation
        )

    results: list[ExecutionReadinessPlaneResult] = []
    for plane in ExecutionReadinessPlane:
        status, code, evidence = aggregated[plane]
        if plane is ExecutionReadinessPlane.ACTION_SURFACE and completion_ok is not None:
            if completion_ok and status is not ExecutionReadinessStatus.BLOCKED:
                evidence = _merge_evidence(evidence, completion_evidence)
            elif not completion_ok:
                status = ExecutionReadinessStatus.BLOCKED
                code = (
                    completion_code
                    or ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED
                )
                evidence = _merge_evidence(evidence, completion_evidence)
        results.append(
            ExecutionReadinessPlaneResult(
                plane=plane,
                status=status,
                blocker_code=code,
                evidence_identities=evidence,
            )
        )

    blocked = [item for item in results if item.status is ExecutionReadinessStatus.BLOCKED]
    if blocked:
        primary = min(blocked, key=lambda item: item.plane.precedence)
        primary_rank = primary.plane.precedence
        results = [
            (
                item
                if item.plane.precedence <= primary_rank
                else ExecutionReadinessPlaneResult(
                    plane=item.plane, status=ExecutionReadinessStatus.UNPROVEN
                )
            )
            for item in results
        ]
        blocked = [item for item in results if item.status is ExecutionReadinessStatus.BLOCKED]
        primary = min(blocked, key=lambda item: item.plane.precedence)
        plane_evidence = _merge_evidence(primary.evidence_identities)[
            : OUTCOME_EVIDENCE_MAX_IDENTITIES - 1
        ]
        evidence = plane_evidence + (f"request_hash={request.request_hash()}",)
        code = primary.blocker_code or ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING
        blocker = ExecutionReadinessBlocker(
            code=code,
            plane=primary.plane,
            precedence_rank=primary.plane.precedence,
            message=_BLOCKER_MESSAGE.get(code, "readiness blocked"),
            evidence_identities=evidence,
            next_action=_BLOCKER_NEXT_ACTION.get(
                code, CanonicalNextAction.OBTAIN_NORMAL_TASK_AUTHORITY
            ),
        )
        return ExecutionReadinessResult(
            outcome=ExecutionReadinessOutcome.BLOCKED,
            request_hash=request.request_hash(),
            evaluated_at=moment,
            ready_planes=tuple(
                item.plane for item in results if item.status is ExecutionReadinessStatus.PASSED
            ),
            plane_results=tuple(results),
            primary_blocker=blocker,
        )

    unproven = [item for item in results if item.status is ExecutionReadinessStatus.UNPROVEN]
    if unproven:
        raise ReadinessEvidenceError("NO_BLOCKER_BUT_UNPROVEN_PLANES", unproven[0].plane)

    return ExecutionReadinessResult(
        outcome=ExecutionReadinessOutcome.READY_TO_EXECUTE,
        request_hash=request.request_hash(),
        evaluated_at=moment,
        ready_planes=tuple(plane for plane in ExecutionReadinessPlane),
        plane_results=tuple(results),
        primary_blocker=None,
    )
