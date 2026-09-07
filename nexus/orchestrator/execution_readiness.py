"""Execution readiness convergence evaluator for issue #807 (G1 gate).

Pure, in-process evaluator over typed plane observations.  It consumes
evidence gathered by callers (the gateway host or a direct in-process
preflight) and produces the one typed result defined by
``nexus.contracts.execution_readiness``:

- every material plane compatible -> ``READY_TO_EXECUTE``;
- otherwise -> ``BLOCKED`` with exactly one primary blocker, the
  highest-precedence failing plane, plus one canonical next action routing to
  the existing authority owner (#806 recovery, #526 rebind/reload, exact
  source binding, normal authority gates, replay-fence reconciliation,
  Planner/Workforce Admission preflight).

This module is a convergence gate only.  It never performs repair, never
triggers Gateway reload, never selects routes or workers, never grants
authority, and never asserts post-execution truth.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

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


@dataclass(frozen=True)
class PlaneObservation:
    """Typed evidence for one plane, gathered by the caller (never by this gate).

    ``status`` is the caller's observed verdict for this plane:
    ``PASSED`` (compatible, with evidence identities), ``BLOCKED`` (failing,
    with the frozen blocker code), or ``UNPROVEN`` (no evidence gathered).
    Lower-precedence planes stay ``UNPROVEN`` while a higher plane fails.
    """

    plane: ExecutionReadinessPlane
    status: ExecutionReadinessStatus
    blocker_code: ExecutionReadinessBlockerCode | None = None
    evidence_identities: tuple[str, ...] = ()

    def to_plane_result(self) -> ExecutionReadinessPlaneResult:
        return ExecutionReadinessPlaneResult(
            plane=self.plane,
            status=self.status,
            blocker_code=self.blocker_code,
            evidence_identities=self.evidence_identities,
        )


@dataclass(frozen=True)
class GatewayReadinessObservation:
    """In-process gateway-plane observation mirroring ``nexus_gateway_status``.

    ``observed_runtime_sha256`` must be computed with the same
    ``_hash_source_paths(RUNTIME_SOURCE_PATHS)`` primitive that
    ``nexus_gateway_status`` uses, and ``observed_repo_head`` with
    ``git rev-parse HEAD``.  ``reload_required`` mirrors the gateway's own
    freshness semantics so the readiness gate and the status tool can never
    disagree about the running instance.
    """

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


def evaluate_source_binding(
    request: ExecutionReadinessRequest,
    observation: GatewayReadinessObservation,
) -> PlaneObservation:
    """Bind the requested source identity to the physically observed Git identity.

    The desired commit/tree come only from the typed request.  The observed
    commit/tree come only from the canonical checkout.  Missing or malformed
    observed identity fails closed; any exact mismatch is a source-realm
    blocker rather than a gateway-freshness result.
    """

    observed_commit = observation.observed_repo_head.strip().lower()
    observed_tree = observation.observed_repo_tree.strip().lower()
    observed_valid = (
        len(observed_commit) == 40
        and len(observed_tree) == 40
        and all(char in "0123456789abcdef" for char in observed_commit)
        and all(char in "0123456789abcdef" for char in observed_tree)
    )
    evidence = (
        f"source_desired_commit={request.intended_source_commit}",
        f"source_desired_tree={request.intended_source_tree}",
        f"source_observed_commit={observed_commit or '<missing>'}",
        f"source_observed_tree={observed_tree or '<missing>'}",
    )
    if not observed_valid:
        return PlaneObservation(
            plane=ExecutionReadinessPlane.SOURCE,
            status=ExecutionReadinessStatus.BLOCKED,
            blocker_code=ExecutionReadinessBlockerCode.SOURCE_BINDING_REQUIRED,
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
    """Observed completion-authority identity (material-only plane 5 input).

    Callers gather this only when the request carries
    ``required_completion_contract``.  ``artifact_or_source_identity`` must be
    the actually installed/available artifact identity — never a GitHub ``main``
    ref substituted for the runtime artifact.
    """

    observed_authority_kind: str
    observed_repository: str
    observed_artifact_identity: str
    observed_interface_revision: str
    observed_capabilities: tuple[str, ...] = ()

    def to_observation_payload(self) -> dict[str, str | tuple[str, ...]]:
        """Bounded identity-fact surface; carries no authority verbs."""
        return {
            "completion_observed_authority_kind": self.observed_authority_kind,
            "completion_observed_repository": self.observed_repository,
            "completion_observed_artifact_identity": self.observed_artifact_identity,
            "completion_observed_interface_revision": self.observed_interface_revision,
            "completion_observed_capabilities": tuple(self.observed_capabilities),
        }

    def identity_digest(self) -> str:
        """Canonical sha256 over the observed identity facts, for tamper checks."""
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
    """Compare the required completion contract to the observed identity.

    Fail-closed: stale, substituted, unavailable, or incompatible identities
    block with ``COMPLETION_CONTRACT_BINDING_REQUIRED`` (plane 5 subtype).
    """

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
    if not set(_COMPLETION_REQUIRED_CAPABILITIES).issubset(set(observation.observed_capabilities)):
        return False, ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED, evidence
    return True, None, evidence


class ReadinessEvidenceError(ValueError):
    """Raised when caller-supplied evidence cannot produce a decisive result.

    This gate never fabricates a verdict: incomplete or indisciplined evidence
    is an error, not a ``READY`` and not a synthetic blocker.
    """

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
        else:
            if observation.blocker_code is not None:
                raise ReadinessEvidenceError("NON_BLOCKED_OBSERVATION_MUST_NOT_CARRY_CODE", plane)
        if observation.status is ExecutionReadinessStatus.UNPROVEN and observation.evidence_identities:
            raise ReadinessEvidenceError("UNPROVEN_OBSERVATION_MUST_NOT_CARRY_EVIDENCE", plane)
    blocked = next(
        (observation for observation in observations if observation.status is ExecutionReadinessStatus.BLOCKED),
        None,
    )
    if blocked is not None:
        return (
            ExecutionReadinessStatus.BLOCKED,
            blocked.blocker_code,
            _merge_evidence(*(observation.evidence_identities for observation in observations)),
        )
    if any(observation.status is ExecutionReadinessStatus.UNPROVEN for observation in observations):
        return ExecutionReadinessStatus.UNPROVEN, None, ()
    return (
        ExecutionReadinessStatus.PASSED,
        None,
        _merge_evidence(*(observation.evidence_identities for observation in observations)),
    )


def evaluate_execution_readiness(
    request: ExecutionReadinessRequest,
    plane_observations: Mapping[ExecutionReadinessPlane, Sequence[PlaneObservation]],
    *,
    completion_observation: CompletionAuthorityObservation | None = None,
    evaluated_at: datetime | None = None,
) -> ExecutionReadinessResult:
    """Aggregate typed plane evidence into the one typed readiness result.

    Deterministic G0 precedence: the primary blocker is always the failing
    plane with the lowest precedence rank (1 = highest).  Every plane that is
    not the primary blocker and not higher-precedence-passed is ``UNPROVEN``.

    ``completion_observation`` is material only when the request carries
    ``required_completion_contract``; it is then compared fail-closed and its
    verdict folds into the plane-5 (ACTION_SURFACE) result.
    """

    moment = evaluated_at or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ReadinessEvidenceError("EVALUATED_AT_MUST_BE_TIMEZONE_AWARE")

    aggregated: dict[
        ExecutionReadinessPlane,
        tuple[ExecutionReadinessStatus, ExecutionReadinessBlockerCode | None, tuple[str, ...]],
    ] = {}
    for plane in ExecutionReadinessPlane:
        aggregated[plane] = _aggregate_plane(plane, plane_observations.get(plane, ()))

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

    blocked = [result for result in results if result.status is ExecutionReadinessStatus.BLOCKED]
    if blocked:
        # G0 determinism: the primary blocker is the highest-precedence
        # failing plane.  Every plane ranked after it collapses to UNPROVEN
        # (never READY, never a second blocker, evidence dropped per the
        # plane-result contract) so post-repair re-preflight re-evaluates it.
        primary = min(blocked, key=lambda result: result.plane.precedence)
        primary_rank = primary.plane.precedence
        results = [
            (
                result
                if result.plane.precedence <= primary_rank
                else ExecutionReadinessPlaneResult(
                    plane=result.plane, status=ExecutionReadinessStatus.UNPROVEN
                )
            )
            for result in results
        ]
        blocked = [result for result in results if result.status is ExecutionReadinessStatus.BLOCKED]
        primary = min(blocked, key=lambda result: result.plane.precedence)
        # Deterministic capacity bound: keep the first plane evidence
        # identities so the blocker always fits the outcome evidence cap with
        # the request hash and precedence rank appended last.
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
                result.plane
                for result in results
                if result.status is ExecutionReadinessStatus.PASSED
            ),
            plane_results=tuple(results),
            primary_blocker=blocker,
        )

    unproven = [result for result in results if result.status is ExecutionReadinessStatus.UNPROVEN]
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
