"""Typed Execution Readiness contract for issue #807 (G1 convergence gate).

One typed request evaluates to exactly one typed result:

- ``READY_TO_EXECUTE`` with per-plane evidence identities, or
- ``BLOCKED`` carrying exactly one primary blocker (the highest-precedence
  failing plane), its supporting evidence identities, and one canonical next
  action.  Remaining lower-precedence planes are reported ``UNPROVEN`` (never
  ``READY``) so post-repair re-preflight re-evaluates them.

Frozen blocker precedence (issue #807 G0 freeze, comment 5558229416):

1. GOVERNANCE_PLANE_RECOVERY_REQUIRED -> issue #806 (owner-authorized only)
2. SOURCE_BINDING_REQUIRED / SOURCE_REALM_MISMATCH -> bind exact desired source
3. GATEWAY_REBIND_REQUIRED -> issue #526 canonical rebind/reload primitive
4. HOST_ACTION_BINDING_GAP -> exact connector/host reconnect-rebind
5. ACTION_SCHEMA_OR_REVIEW_STALE / PERMISSION_SURFACE_STALE /
   COMPLETION_CONTRACT_BINDING_REQUIRED -> desired-derived surface comparison
6. TASK_AUTHORITY_MISSING / AUTHORITY_OUT_OF_SCOPE -> normal authority gate
7. SEMANTIC_REPLAY_FENCE -> reconcile the same request/fence (never blind retry)
8. WORKFORCE_NOT_READY -> Planner / Workforce Admission / provider preflight

Boundaries (G0 + contract delta comment 5558296357): this gate proves
pre-execution readiness only.  It never selects routes, admits workers,
grants authority, reloads Gateways, approves candidates, merges/releases, and
it can never certify post-execution ``VERIFIED`` / ``CERTIFIED`` /
``COMPLETE`` truth: those belong to the canonical post-execution authorities.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

EXECUTION_READINESS_SCHEMA = "nexus.execution_readiness.v1"
EXECUTION_READINESS_PLANE_RESULTS_SCHEMA = "nexus.execution_readiness_plane_results.v1"
EXECUTION_READINESS_BLOCKER_SCHEMA = "nexus.execution_readiness_blocker.v1"
COMPLETION_AUTHORITY_KIND = "NEXUS_CORE_COMPLETION"
COMPLETION_CONTRACT_BLOCKER = "COMPLETION_CONTRACT_BINDING_REQUIRED"
HOST_GATEWAY_SERVICE_LABEL = "com.nexus.mcp.gateway.direct"
PLANE_EVIDENCE_MAX_IDENTITIES = 16
OUTCOME_EVIDENCE_MAX_IDENTITIES = 16
WORKER_CONSTRAINT_MAX_ENTRIES = 8
WORKER_CONSTRAINT_MAX_LENGTH = 256

READY_ONLY_VOCABULARY = ("READY_TO_EXECUTE",)
# Post-execution certification vocabulary must never appear in a readiness
# result.  Kept as a module literal so tampering with the tuple below is
# detectable by tests that compare against this constant.
_FORBIDDEN_CERTIFICATION_VOCABULARY = ("VERIFIED", "CERTIFIED", "COMPLETE")
assert not set(_FORBIDDEN_CERTIFICATION_VOCABULARY) & set(READY_ONLY_VOCABULARY)


def canonical_hash(value: Any) -> str:
    """Deterministic content hash used for cross-realm identity comparison.

    Key-order independent so the same completion identity always hashes to the
    same digest regardless of mapping construction order.
    """

    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("COMPLETION_IDENTITY_NOT_CANONICALLY_SERIALIZABLE") from exc
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ExecutionReadinessPlane(str, Enum):
    """Convergence planes in frozen G0 precedence order (1 = highest)."""

    GOVERNANCE = "GOVERNANCE_PLANE"
    SOURCE = "SOURCE_PLANE"
    GATEWAY = "GATEWAY_PLANE"
    HOST_BINDING = "HOST_BINDING_PLANE"
    ACTION_SURFACE = "ACTION_SURFACE_PLANE"
    AUTHORITY = "AUTHORITY_PLANE"
    REPLAY_FENCE = "REPLAY_FENCE_PLANE"
    WORKFORCE = "WORKFORCE_PLANE"

    @property
    def precedence(self) -> int:
        return _PLANE_PRECEDENCE[self]


_PLANE_PRECEDENCE: dict["ExecutionReadinessPlane", int] = {
    ExecutionReadinessPlane.GOVERNANCE: 1,
    ExecutionReadinessPlane.SOURCE: 2,
    ExecutionReadinessPlane.GATEWAY: 3,
    ExecutionReadinessPlane.HOST_BINDING: 4,
    ExecutionReadinessPlane.ACTION_SURFACE: 5,
    ExecutionReadinessPlane.AUTHORITY: 6,
    ExecutionReadinessPlane.REPLAY_FENCE: 7,
    ExecutionReadinessPlane.WORKFORCE: 8,
}


class ExecutionReadinessStatus(str, Enum):
    """Plane-level status; only ``PASSED`` means the plane agreed."""

    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    UNPROVEN = "UNPROVEN"


class ExecutionReadinessOutcome(str, Enum):
    """Whole-gate outcome vocabulary; deliberately contains exactly one ready value."""

    READY_TO_EXECUTE = "READY_TO_EXECUTE"
    BLOCKED = "BLOCKED"


class CanonicalNextAction(str, Enum):
    """Canonical next actions; each routes to the existing authority owner."""

    ROUTE_TO_ISSUE_806_BREAK_GLASS_RECOVERY = "ROUTE_TO_ISSUE_806_BREAK_GLASS_RECOVERY"
    BIND_EXACT_DESIRED_SOURCE_IDENTITY = "BIND_EXACT_DESIRED_SOURCE_IDENTITY"
    ROUTE_TO_ISSUE_526_GATEWAY_REBIND_RELOAD = "ROUTE_TO_ISSUE_526_GATEWAY_REBIND_RELOAD"
    RECONNECT_BOUND_HOST_CONNECTOR = "RECONNECT_BOUND_HOST_CONNECTOR"
    REFRESH_SCHEMA_AND_PERMISSION_SURFACE = "REFRESH_SCHEMA_AND_PERMISSION_SURFACE"
    BIND_COMPLETION_CONTRACT_IDENTITY = "BIND_COMPLETION_CONTRACT_IDENTITY"
    OBTAIN_NORMAL_TASK_AUTHORITY = "OBTAIN_NORMAL_TASK_AUTHORITY"
    RECONCILE_SAME_REQUEST_FENCE = "RECONCILE_SAME_REQUEST_FENCE"
    RUN_PLANNER_AND_WORKFORCE_ADMISSION = "RUN_PLANNER_AND_WORKFORCE_ADMISSION"


class ExecutionReadinessBlockerCode(str, Enum):
    """Frozen blocker codes; each belongs to exactly one plane."""

    GOVERNANCE_PLANE_RECOVERY_REQUIRED = "GOVERNANCE_PLANE_RECOVERY_REQUIRED"
    SOURCE_BINDING_REQUIRED = "SOURCE_BINDING_REQUIRED"
    SOURCE_REALM_MISMATCH = "SOURCE_REALM_MISMATCH"
    GATEWAY_REBIND_REQUIRED = "GATEWAY_REBIND_REQUIRED"
    HOST_ACTION_BINDING_GAP = "HOST_ACTION_BINDING_GAP"
    ACTION_SCHEMA_OR_REVIEW_STALE = "ACTION_SCHEMA_OR_REVIEW_STALE"
    PERMISSION_SURFACE_STALE = "PERMISSION_SURFACE_STALE"
    COMPLETION_CONTRACT_BINDING_REQUIRED = COMPLETION_CONTRACT_BLOCKER
    TASK_AUTHORITY_MISSING = "TASK_AUTHORITY_MISSING"
    AUTHORITY_OUT_OF_SCOPE = "AUTHORITY_OUT_OF_SCOPE"
    SEMANTIC_REPLAY_FENCE = "SEMANTIC_REPLAY_FENCE"
    WORKFORCE_NOT_READY = "WORKFORCE_NOT_READY"


_BLOCKER_PLANE: dict[str, ExecutionReadinessPlane] = {
    ExecutionReadinessBlockerCode.GOVERNANCE_PLANE_RECOVERY_REQUIRED.value: (
        ExecutionReadinessPlane.GOVERNANCE
    ),
    ExecutionReadinessBlockerCode.SOURCE_BINDING_REQUIRED.value: ExecutionReadinessPlane.SOURCE,
    ExecutionReadinessBlockerCode.SOURCE_REALM_MISMATCH.value: ExecutionReadinessPlane.SOURCE,
    ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED.value: ExecutionReadinessPlane.GATEWAY,
    ExecutionReadinessBlockerCode.HOST_ACTION_BINDING_GAP.value: (
        ExecutionReadinessPlane.HOST_BINDING
    ),
    ExecutionReadinessBlockerCode.ACTION_SCHEMA_OR_REVIEW_STALE.value: (
        ExecutionReadinessPlane.ACTION_SURFACE
    ),
    ExecutionReadinessBlockerCode.PERMISSION_SURFACE_STALE.value: (
        ExecutionReadinessPlane.ACTION_SURFACE
    ),
    ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED.value: (
        ExecutionReadinessPlane.ACTION_SURFACE
    ),
    ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING.value: ExecutionReadinessPlane.AUTHORITY,
    ExecutionReadinessBlockerCode.AUTHORITY_OUT_OF_SCOPE.value: (ExecutionReadinessPlane.AUTHORITY),
    ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE.value: (
        ExecutionReadinessPlane.REPLAY_FENCE
    ),
    ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY.value: ExecutionReadinessPlane.WORKFORCE,
}


def blocker_precedence(code: str | ExecutionReadinessBlockerCode) -> int:
    """Return the frozen G0 precedence rank (1 = highest) for a blocker code."""

    value = code.value if isinstance(code, ExecutionReadinessBlockerCode) else str(code)
    plane = _BLOCKER_PLANE.get(value)
    if plane is None:
        raise ValueError(f"UNKNOWN_BLOCKER_CODE: {value}")
    return plane.precedence


def blocker_plane(code: str | ExecutionReadinessBlockerCode) -> ExecutionReadinessPlane:
    """Return the plane that owns a blocker code."""

    value = code.value if isinstance(code, ExecutionReadinessBlockerCode) else str(code)
    plane = _BLOCKER_PLANE.get(value)
    if plane is None:
        raise ValueError(f"UNKNOWN_BLOCKER_CODE: {value}")
    return plane


class RequiredCompletionContract(BaseModel):
    """Optional material-only completion binding (contract delta rule 1).

    Present only when the intended execution contract explicitly requires a
    formal post-execution Completion/Evidence authority.  Ordinary tasks never
    carry this field and must never be blocked by its absence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    authority_kind: StrictStr
    repository: StrictStr
    artifact_or_source_identity: StrictStr
    interface_revision: StrictStr
    required_capabilities: tuple[StrictStr, ...] = ()

    @field_validator("repository")
    @classmethod
    def _repository_shape(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
            raise ValueError("COMPLETION_REPOSITORY_MALFORMED")
        return value

    @field_validator("artifact_or_source_identity")
    @classmethod
    def _artifact_identity_shape(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("COMPLETION_ARTIFACT_IDENTITY_EMPTY")
        segments = normalized.replace(":", "/").replace("@", "/").split("/")
        if any(
            segment in {"main", "master", "head", "heads", "origin", "refs"} for segment in segments
        ):
            raise ValueError("COMPLETION_ARTIFACT_IDENTITY_NOT_AN_INSTALLED_ARTIFACT")
        return value

    @field_validator("required_capabilities")
    @classmethod
    def _capabilities_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) > WORKER_CONSTRAINT_MAX_ENTRIES:
            raise ValueError("COMPLETION_CAPABILITIES_TOO_MANY")
        for item in value:
            if not item or len(item) > WORKER_CONSTRAINT_MAX_LENGTH:
                raise ValueError("COMPLETION_CAPABILITY_MALFORMED")
        return value


class ExecutionReadinessRequest(BaseModel):
    """Typed one-request/one-result readiness request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: str = EXECUTION_READINESS_SCHEMA
    repository_owner: StrictStr
    repository_name: StrictStr
    intended_source_commit: StrictStr
    intended_source_tree: StrictStr
    execution_realm: StrictStr
    required_action_family: StrictStr
    execution_contract_kind: StrictStr
    task_campaign_goal_identity: StrictStr | None = None
    desired_deployment_identity: StrictStr | None = None
    worker_constraints: tuple[StrictStr, ...] = ()
    required_completion_contract: RequiredCompletionContract | None = None

    @field_validator("intended_source_commit")
    @classmethod
    def _commit_shape(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("INTENDED_SOURCE_COMMIT_MALFORMED")
        return value

    @field_validator("intended_source_tree")
    @classmethod
    def _tree_shape(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("INTENDED_SOURCE_TREE_MALFORMED")
        return value

    @field_validator("worker_constraints")
    @classmethod
    def _worker_constraints_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) > WORKER_CONSTRAINT_MAX_ENTRIES:
            raise ValueError("WORKER_CONSTRAINTS_TOO_MANY")
        for item in value:
            if not item or len(item) > WORKER_CONSTRAINT_MAX_LENGTH:
                raise ValueError("WORKER_CONSTRAINT_MALFORMED")
        return value

    @model_validator(mode="after")
    def _material_consistency(self) -> "ExecutionReadinessRequest":
        if not self.execution_realm.strip() or len(self.execution_realm) > 128:
            raise ValueError("EXECUTION_REALM_MALFORMED")
        if not self.required_action_family.strip() or len(self.required_action_family) > 128:
            raise ValueError("REQUIRED_ACTION_FAMILY_MALFORMED")
        if not self.execution_contract_kind.strip() or len(self.execution_contract_kind) > 128:
            raise ValueError("EXECUTION_CONTRACT_KIND_MALFORMED")
        if (
            self.task_campaign_goal_identity is not None
            and not self.task_campaign_goal_identity.strip()
        ):
            raise ValueError("TASK_CAMPAIGN_GOAL_IDENTITY_EMPTY")
        if (
            self.desired_deployment_identity is not None
            and not self.desired_deployment_identity.strip()
        ):
            raise ValueError("DESIRED_DEPLOYMENT_IDENTITY_EMPTY")
        if self.required_completion_contract is not None:
            if self.required_completion_contract.authority_kind != COMPLETION_AUTHORITY_KIND:
                raise ValueError("COMPLETION_CONTRACT_AUTHORITY_KIND_UNSUPPORTED")
            if self.execution_contract_kind != "FORMAL_COMPLETION_CERTIFICATION":
                raise ValueError("COMPLETION_CONTRACT_NOT_MATERIAL_FOR_CONTRACT_KIND")
        return self

    def request_hash(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ExecutionReadinessPlaneResult(BaseModel):
    """Per-plane verdict: PASSED, BLOCKED (one code), or UNPROVEN."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: str = EXECUTION_READINESS_PLANE_RESULTS_SCHEMA
    plane: ExecutionReadinessPlane
    status: ExecutionReadinessStatus
    blocker_code: ExecutionReadinessBlockerCode | None = None
    evidence_identities: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def _internal_consistency(self) -> "ExecutionReadinessPlaneResult":
        if len(self.evidence_identities) > PLANE_EVIDENCE_MAX_IDENTITIES:
            raise ValueError("PLANE_EVIDENCE_TOO_MANY_IDENTITIES")
        if any(not item.strip() for item in self.evidence_identities):
            raise ValueError("PLANE_EVIDENCE_IDENTITY_EMPTY")
        if self.status is ExecutionReadinessStatus.BLOCKED:
            if self.blocker_code is None:
                raise ValueError("BLOCKED_PLANE_REQUIRES_BLOCKER_CODE")
            if blocker_plane(self.blocker_code) is not self.plane:
                raise ValueError("BLOCKER_CODE_DOES_NOT_BELONG_TO_PLANE")
        elif self.blocker_code is not None:
            raise ValueError("NON_BLOCKED_PLANE_MUST_NOT_CARRY_BLOCKER_CODE")
        if self.status is ExecutionReadinessStatus.UNPROVEN and self.evidence_identities:
            raise ValueError("UNPROVEN_PLANE_MUST_NOT_CARRY_EVIDENCE")
        return self


class ExecutionReadinessBlocker(BaseModel):
    """The single primary blocker of a BLOCKED result (G0 one-of rule)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: str = EXECUTION_READINESS_BLOCKER_SCHEMA
    code: ExecutionReadinessBlockerCode
    plane: ExecutionReadinessPlane
    precedence_rank: int
    message: StrictStr
    evidence_identities: tuple[StrictStr, ...] = ()
    next_action: CanonicalNextAction

    @model_validator(mode="after")
    def _internal_consistency(self) -> "ExecutionReadinessBlocker":
        if blocker_plane(self.code) is not self.plane:
            raise ValueError("BLOCKER_PLANE_MISMATCH")
        if self.precedence_rank != self.plane.precedence:
            raise ValueError("BLOCKER_PRECEDENCE_RANK_MISMATCH")
        if len(self.evidence_identities) > OUTCOME_EVIDENCE_MAX_IDENTITIES:
            raise ValueError("BLOCKER_EVIDENCE_TOO_MANY_IDENTITIES")
        if any(not item.strip() for item in self.evidence_identities):
            raise ValueError("BLOCKER_EVIDENCE_IDENTITY_EMPTY")
        return self


class ExecutionReadinessResult(BaseModel):
    """Typed gate result: READY_TO_EXECUTE or BLOCKED with one primary blocker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: str = EXECUTION_READINESS_SCHEMA
    outcome: ExecutionReadinessOutcome
    request_hash: StrictStr
    evaluated_at: datetime
    ready_planes: tuple[ExecutionReadinessPlane, ...] = ()
    plane_results: tuple[ExecutionReadinessPlaneResult, ...] = ()
    primary_blocker: ExecutionReadinessBlocker | None = None

    @model_validator(mode="after")
    def _internal_consistency(self) -> "ExecutionReadinessResult":
        if self.evaluated_at.tzinfo is None:
            raise ValueError("EVALUATED_AT_MUST_BE_TIMEZONE_AWARE")
        if self.outcome is ExecutionReadinessOutcome.READY_TO_EXECUTE:
            if self.primary_blocker is not None:
                raise ValueError("READY_RESULT_MUST_NOT_CARRY_BLOCKER")
            if len(self.ready_planes) != len(_PLANE_PRECEDENCE):
                raise ValueError("READY_RESULT_MUST_COVER_ALL_PLANES")
            if len(set(self.ready_planes)) != len(self.ready_planes):
                raise ValueError("READY_PLANES_MUST_BE_UNIQUE")
            if any(
                result.status is not ExecutionReadinessStatus.PASSED
                for result in self.plane_results
            ):
                raise ValueError("READY_RESULT_ALL_PLANES_MUST_BE_PASSED")
            if not self.request_satisfies_certification_fence():
                raise ValueError("READY_RESULT_MUST_NOT_IMPLY_CERTIFICATION")
        else:
            if self.primary_blocker is None:
                raise ValueError("BLOCKED_RESULT_REQUIRES_PRIMARY_BLOCKER")
            primary = self.primary_blocker.plane
            primary_rank = primary.precedence
            if primary.precedence != _min_blocked_precedence(self.plane_results):
                raise ValueError("PRIMARY_BLOCKER_NOT_HIGHEST_PRECEDENCE")
            for result in self.plane_results:
                if result.plane.precedence < primary_rank:
                    if result.status is not ExecutionReadinessStatus.PASSED:
                        raise ValueError("HIGHER_PRECEDENCE_PLANE_MUST_BE_PASSED_OR_PRIMARY")
                elif result.plane is primary:
                    if result.status is not ExecutionReadinessStatus.BLOCKED:
                        raise ValueError("PRIMARY_PLANE_MUST_BE_BLOCKED")
                else:
                    if result.status is not ExecutionReadinessStatus.UNPROVEN:
                        raise ValueError("LOWER_PRECEDENCE_PLANE_MUST_BE_UNPROVEN")
        if len(self.plane_results) != len(_PLANE_PRECEDENCE):
            raise ValueError("RESULT_MUST_COVER_ALL_PLANES")
        if len({result.plane for result in self.plane_results}) != len(self.plane_results):
            raise ValueError("PLANE_RESULTS_MUST_BE_UNIQUE")
        return self

    def request_satisfies_certification_fence(self) -> bool:
        """True when no certification vocabulary leaks into this result.

        Deliberately excludes ``primary_blocker.message``: free-text operator
        guidance may reference forbidden words; machine vocabulary may not.
        """

        machine_vocabulary = [self.outcome.value] + [
            result.status.value for result in self.plane_results
        ]
        machine_vocabulary.extend(result.plane.value for result in self.plane_results)
        for result in self.plane_results:
            if result.blocker_code is not None:
                machine_vocabulary.append(result.blocker_code.value)
        if self.primary_blocker is not None:
            machine_vocabulary.append(self.primary_blocker.code.value)
            machine_vocabulary.append(self.primary_blocker.plane.value)
            machine_vocabulary.append(self.primary_blocker.next_action.value)
        joined = " ".join(machine_vocabulary)
        return not any(word in joined for word in _FORBIDDEN_CERTIFICATION_VOCABULARY)

    def result_hash(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _min_blocked_precedence(
    plane_results: tuple[ExecutionReadinessPlaneResult, ...],
) -> int | None:
    blocked = [
        result for result in plane_results if result.status is ExecutionReadinessStatus.BLOCKED
    ]
    if not blocked:
        return None
    return min(result.plane.precedence for result in blocked)
