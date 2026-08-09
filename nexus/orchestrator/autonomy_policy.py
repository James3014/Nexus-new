"""Pure SHADOW evaluator for goal-scoped autonomy policy.

The evaluator is deliberately incapable of mutation.  Its positive result is
evidence about a hypothetical continuation only; it is not an approval grant.
M0 inputs remain caller-bound until later milestones wire authoritative Nexus
state, receipts, ledgers, clocks, and repository/runtime identity.  Consumers
must not use a decision with ``authority_inputs_verified=False`` as machine
authorization.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping, Optional

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    AutonomyGoalGrant,
    AutonomyRiskLevel,
    CollaborationBaseIdentity,
    RepositoryIdentity,
    SensitiveScope,
    canonical_autonomy_hash,
)

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RISK_RANK = {
    AutonomyRiskLevel.LOW: 0,
    AutonomyRiskLevel.MEDIUM: 1,
    AutonomyRiskLevel.HIGH: 2,
    AutonomyRiskLevel.CRITICAL: 3,
}
_RUNTIME_BOUND_ACTIONS = frozenset(
    {
        AutonomyActionClass.CANDIDATE_APPROVE,
        AutonomyActionClass.CANDIDATE_INTEGRATE,
        AutonomyActionClass.REPOSITORY_PUSH,
        AutonomyActionClass.GITHUB_MERGE,
        AutonomyActionClass.RUNTIME_ACTIVATE,
        AutonomyActionClass.PRODUCTION_RELEASE,
    }
)
_CANDIDATE_BOUND_ACTIONS = frozenset(
    {
        AutonomyActionClass.CANDIDATE_APPROVE,
        AutonomyActionClass.CANDIDATE_INTEGRATE,
        AutonomyActionClass.REPOSITORY_PUSH,
        AutonomyActionClass.GITHUB_MERGE,
        AutonomyActionClass.RUNTIME_ACTIVATE,
        AutonomyActionClass.PRODUCTION_RELEASE,
    }
)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _sha(value: str, field: str, *, git: bool = False) -> str:
    regex = _SHA40 if git else _SHA64
    if not regex.fullmatch(value):
        raise ValueError(f"{field.upper()}_INVALID")
    return value


def _safe_id(value: str, field: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"{field.upper()}_INVALID")
    return value


def _path(value: str) -> str:
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("REQUESTED_PATH_INVALID")
    parsed = PurePosixPath(value)
    if ".." in parsed.parts or ".git" in parsed.parts or parsed.as_posix() != value:
        raise ValueError("REQUESTED_PATH_INVALID")
    return value


class AutonomyDecisionState(str, Enum):
    WOULD_AUTO_CONTINUE = "WOULD_AUTO_CONTINUE"
    WOULD_BLOCK = "WOULD_BLOCK"


class AutonomyReasonCode(str, Enum):
    GRANT_INVALID = "GRANT_INVALID"
    GRANT_HASH_INVALID = "GRANT_HASH_INVALID"
    EVALUATOR_INPUT_INVALID = "EVALUATOR_INPUT_INVALID"
    GRANT_NOT_YET_VALID = "GRANT_NOT_YET_VALID"
    GRANT_EXPIRED = "GRANT_EXPIRED"
    EVALUATION_TIME_UNTRUSTED = "EVALUATION_TIME_UNTRUSTED"
    LEGACY_TASK_MANUAL = "LEGACY_TASK_MANUAL"
    POST_SUBMISSION_GRANT_INJECTION = "POST_SUBMISSION_GRANT_INJECTION"
    GOAL_BINDING_MISMATCH = "GOAL_BINDING_MISMATCH"
    SUBMISSION_GRANT_MISMATCH = "SUBMISSION_GRANT_MISMATCH"
    CONTRACT_HASH_MISMATCH = "CONTRACT_HASH_MISMATCH"
    ATTEMPT_BINDING_MISMATCH = "ATTEMPT_BINDING_MISMATCH"
    TASK_SCOPE_EXCEEDED = "TASK_SCOPE_EXCEEDED"
    SUBMISSION_REPOSITORY_IDENTITY_MISMATCH = "SUBMISSION_REPOSITORY_IDENTITY_MISMATCH"
    SUBMISSION_BASE_IDENTITY_MISMATCH = "SUBMISSION_BASE_IDENTITY_MISMATCH"
    REPOSITORY_IDENTITY_MISMATCH = "REPOSITORY_IDENTITY_MISMATCH"
    BASE_IDENTITY_MISMATCH = "BASE_IDENTITY_MISMATCH"
    ACTION_NOT_ALLOWED = "ACTION_NOT_ALLOWED"
    ACTION_FORBIDDEN = "ACTION_FORBIDDEN"
    PATH_SCOPE_EXCEEDED = "PATH_SCOPE_EXCEEDED"
    CHILD_SCOPE_WIDENING = "CHILD_SCOPE_WIDENING"
    CHILD_SCOPE_ACTION_MISMATCH = "CHILD_SCOPE_ACTION_MISMATCH"
    CHILD_SCOPE_PATH_MISMATCH = "CHILD_SCOPE_PATH_MISMATCH"
    CHILD_SCOPE_RISK_MISMATCH = "CHILD_SCOPE_RISK_MISMATCH"
    RISK_CEILING_EXCEEDED = "RISK_CEILING_EXCEEDED"
    TASK_BUDGET_EXHAUSTED = "TASK_BUDGET_EXHAUSTED"
    ATTEMPT_BUDGET_EXHAUSTED = "ATTEMPT_BUDGET_EXHAUSTED"
    PROVIDER_CALL_BUDGET_EXHAUSTED = "PROVIDER_CALL_BUDGET_EXHAUSTED"
    WALL_TIME_BUDGET_EXHAUSTED = "WALL_TIME_BUDGET_EXHAUSTED"
    CHANGED_FILE_BUDGET_EXHAUSTED = "CHANGED_FILE_BUDGET_EXHAUSTED"
    TARGET_CONCURRENCY_EXHAUSTED = "TARGET_CONCURRENCY_EXHAUSTED"
    SENSITIVE_SCOPE_NOT_ADMITTED = "SENSITIVE_SCOPE_NOT_ADMITTED"
    PRODUCTION_RELEASE_NOT_AUTHORIZED = "PRODUCTION_RELEASE_NOT_AUTHORIZED"
    MERGE_NOT_AUTHORIZED = "MERGE_NOT_AUTHORIZED"
    RUNTIME_ACTIVATION_NOT_AUTHORIZED = "RUNTIME_ACTIVATION_NOT_AUTHORIZED"
    CANDIDATE_IDENTITY_REQUIRED = "CANDIDATE_IDENTITY_REQUIRED"
    CANDIDATE_TASK_ATTEMPT_MISMATCH = "CANDIDATE_TASK_ATTEMPT_MISMATCH"
    CANDIDATE_IDENTITY_DRIFT = "CANDIDATE_IDENTITY_DRIFT"
    INDEPENDENT_ACCEPTANCE_REQUIRED = "INDEPENDENT_ACCEPTANCE_REQUIRED"
    IMPLEMENTER_ACCEPTANCE_FORBIDDEN = "IMPLEMENTER_ACCEPTANCE_FORBIDDEN"
    ACCEPTANCE_CANDIDATE_MISMATCH = "ACCEPTANCE_CANDIDATE_MISMATCH"
    ACCEPTANCE_RECEIPT_CANDIDATE_MISMATCH = "ACCEPTANCE_RECEIPT_CANDIDATE_MISMATCH"
    RUNTIME_IDENTITY_REQUIRED = "RUNTIME_IDENTITY_REQUIRED"
    RUNTIME_IDENTITY_DRIFT = "RUNTIME_IDENTITY_DRIFT"


class AcceptanceAuthorityKind(str, Enum):
    INDEPENDENT_REVIEWER = "INDEPENDENT_REVIEWER"
    WORKER_OUTPUT = "WORKER_OUTPUT"


class AutonomyCandidateIdentity(_FrozenModel):
    task_id: StrictStr
    attempt_id: StrictStr
    candidate_commit_sha: StrictStr
    candidate_tree_sha: StrictStr
    candidate_state_hash: StrictStr
    verified_receipt_hash: StrictStr

    @field_validator("task_id", "attempt_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator("candidate_commit_sha", "candidate_tree_sha")
    @classmethod
    def validate_git_sha(cls, value: str, info) -> str:
        return _sha(value, info.field_name, git=True)

    @field_validator("candidate_state_hash", "verified_receipt_hash")
    @classmethod
    def validate_sha256(cls, value: str, info) -> str:
        return _sha(value, info.field_name)


class AcceptanceIdentity(_FrozenModel):
    receipt_hash: StrictStr
    candidate_receipt_hash: StrictStr
    accepted_by: StrictStr
    authority_kind: AcceptanceAuthorityKind
    candidate: AutonomyCandidateIdentity

    @field_validator("receipt_hash", "candidate_receipt_hash")
    @classmethod
    def validate_receipt_hash(cls, value: str, info) -> str:
        return _sha(value, info.field_name)

    @field_validator("accepted_by")
    @classmethod
    def validate_reviewer(cls, value: str) -> str:
        return _safe_id(value, "accepted_by")


class AutonomyRuntimeIdentity(_FrozenModel):
    tool_manifest_hash: StrictStr
    full_tool_schema_hash: StrictStr
    permission_policy_hash: StrictStr
    lifecycle_revision: StrictStr
    server_instance_id: StrictStr

    @field_validator("tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash")
    @classmethod
    def validate_hashes(cls, value: str, info) -> str:
        return _sha(value, info.field_name)

    @field_validator("lifecycle_revision")
    @classmethod
    def validate_lifecycle_revision(cls, value: str) -> str:
        if len(value) > 128:
            raise ValueError("LIFECYCLE_REVISION_INVALID")
        return _safe_id(value, "lifecycle_revision")

    @field_validator("server_instance_id")
    @classmethod
    def validate_server_instance(cls, value: str) -> str:
        return _safe_id(value, "server_instance_id")


class AutonomyBudgetUsage(_FrozenModel):
    tasks: StrictInt = Field(ge=0)
    attempts_for_task: StrictInt = Field(ge=0)
    provider_calls: StrictInt = Field(ge=0)
    wall_time_seconds: StrictInt = Field(ge=0)
    changed_files: StrictInt = Field(ge=0)
    active_targets: StrictInt = Field(ge=0)


class ChildAutonomyScope(_FrozenModel):
    allowed_actions: tuple[AutonomyActionClass, ...]
    allowed_paths: tuple[StrictStr, ...]
    risk_ceiling: AutonomyRiskLevel
    maximum_attempts_per_task: StrictInt = Field(gt=0)
    maximum_provider_calls: StrictInt = Field(gt=0)
    maximum_wall_time_seconds: StrictInt = Field(gt=0)
    maximum_changed_files: StrictInt = Field(gt=0)
    maximum_concurrent_targets: StrictInt = Field(gt=0)

    @field_validator("allowed_actions")
    @classmethod
    def canonicalize_actions(
        cls,
        values: tuple[AutonomyActionClass, ...],
    ) -> tuple[AutonomyActionClass, ...]:
        if not values:
            raise ValueError("CHILD_ACTIONS_REQUIRED")
        return tuple(sorted(set(values), key=lambda item: item.value))

    @field_validator("allowed_paths")
    @classmethod
    def canonicalize_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({_path(value) for value in values}))
        if not normalized:
            raise ValueError("CHILD_PATHS_REQUIRED")
        return normalized


class AutonomySubmissionBindingSpec(_FrozenModel):
    schema: Literal["nexus.autonomy_submission_binding.v1"]
    mode: Literal["SHADOW"] = "SHADOW"
    task_id: StrictStr
    initial_attempt_id: StrictStr
    action_request_hash: StrictStr
    contract_hash: StrictStr
    controller_revision: StrictStr
    repository: RepositoryIdentity
    collaboration_base: CollaborationBaseIdentity
    allowed_paths: tuple[StrictStr, ...]
    goal_id: StrictStr
    grant_hash: StrictStr

    @field_validator("task_id", "initial_attempt_id", "goal_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator("action_request_hash", "contract_hash", "grant_hash")
    @classmethod
    def validate_hashes(cls, value: str, info) -> str:
        return _sha(value, info.field_name)

    @field_validator("controller_revision")
    @classmethod
    def validate_controller_revision(cls, value: str) -> str:
        return _sha(value, "controller_revision", git=True)

    @field_validator("allowed_paths")
    @classmethod
    def validate_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({_path(value) for value in values}))
        if not normalized:
            raise ValueError("SUBMISSION_PATHS_REQUIRED")
        return normalized


class AutonomySubmissionBinding(AutonomySubmissionBindingSpec):
    binding_hash: StrictStr

    @field_validator("binding_hash")
    @classmethod
    def validate_binding_hash_format(cls, value: str) -> str:
        return _sha(value, "binding_hash")

    @model_validator(mode="after")
    def validate_binding_hash(self) -> "AutonomySubmissionBinding":
        payload = self.model_dump(mode="json", exclude={"binding_hash"})
        if self.binding_hash != canonical_autonomy_hash(payload):
            raise ValueError("SUBMISSION_BINDING_HASH_INVALID")
        return self

    @classmethod
    def issue(cls, **values: Any) -> "AutonomySubmissionBinding":
        values.setdefault("schema", "nexus.autonomy_submission_binding.v1")
        spec = AutonomySubmissionBindingSpec.model_validate(values)
        payload = spec.model_dump(mode="json")
        return cls.model_validate({**payload, "binding_hash": canonical_autonomy_hash(payload)})


class AutonomyEvaluationInput(_FrozenModel):
    schema: Literal["nexus.autonomy_evaluation_input.v1"]
    evaluated_at: AwareDatetime
    task_id: StrictStr
    attempt_id: StrictStr
    contract_hash: StrictStr
    action: AutonomyActionClass
    repository: RepositoryIdentity
    collaboration_base: CollaborationBaseIdentity
    requested_paths: tuple[StrictStr, ...]
    risk: AutonomyRiskLevel
    sensitive_scopes: tuple[SensitiveScope, ...] = ()
    child_scope: ChildAutonomyScope
    budget_usage: AutonomyBudgetUsage
    submission_binding: Optional[AutonomySubmissionBinding]
    post_submission_grant_presented: StrictBool = False
    implementer_id: StrictStr
    candidate_at_verification: Optional[AutonomyCandidateIdentity] = None
    current_candidate: Optional[AutonomyCandidateIdentity] = None
    acceptance: Optional[AcceptanceIdentity] = None
    expected_runtime_identity: Optional[AutonomyRuntimeIdentity] = None
    current_runtime_identity: Optional[AutonomyRuntimeIdentity] = None

    @field_validator("task_id", "attempt_id", "implementer_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator("contract_hash")
    @classmethod
    def validate_contract_hash(cls, value: str) -> str:
        return _sha(value, "contract_hash")

    @field_validator("requested_paths")
    @classmethod
    def canonicalize_requested_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({_path(value) for value in values}))
        if not normalized:
            raise ValueError("REQUESTED_PATHS_REQUIRED")
        return normalized

    @field_validator("sensitive_scopes")
    @classmethod
    def canonicalize_scopes(
        cls,
        values: tuple[SensitiveScope, ...],
    ) -> tuple[SensitiveScope, ...]:
        return tuple(sorted(set(values), key=lambda item: item.value))


class AutonomyDecision(_FrozenModel):
    schema: Literal["nexus.autonomy_decision.v1"]
    evaluator_version: Literal["autonomy-shadow-m0"] = "autonomy-shadow-m0"
    state: AutonomyDecisionState
    reason_codes: tuple[AutonomyReasonCode, ...]
    input_hash: StrictStr
    decision_hash: StrictStr
    shadow_only: Literal[True] = True
    mutation_authorized: Literal[False] = False
    authority_inputs_verified: Literal[False] = False
    claim_ceiling: Literal["SHADOW_CALLER_BOUND_EVIDENCE_ONLY"] = (
        "SHADOW_CALLER_BOUND_EVIDENCE_ONLY"
    )

    @field_validator("input_hash", "decision_hash")
    @classmethod
    def validate_hashes(cls, value: str, info) -> str:
        return _sha(value, info.field_name)

    @model_validator(mode="after")
    def validate_decision_hash(self) -> "AutonomyDecision":
        payload = self.model_dump(mode="json", exclude={"decision_hash"})
        if self.decision_hash != canonical_autonomy_hash(payload):
            raise ValueError("DECISION_HASH_INVALID")
        return self


def _path_is_within(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent.rstrip("/") + "/")


def _paths_overlap(first: str, second: str) -> bool:
    return _path_is_within(first, second) or _path_is_within(second, first)


def _decision(*, reasons: list[str], input_hash: str) -> AutonomyDecision:
    reason_codes = tuple(dict.fromkeys(reasons))
    state = (
        AutonomyDecisionState.WOULD_BLOCK
        if reason_codes
        else AutonomyDecisionState.WOULD_AUTO_CONTINUE
    )
    payload = {
        "schema": "nexus.autonomy_decision.v1",
        "evaluator_version": "autonomy-shadow-m0",
        "state": state.value,
        "reason_codes": list(reason_codes),
        "input_hash": input_hash,
        "shadow_only": True,
        "mutation_authorized": False,
        "authority_inputs_verified": False,
        "claim_ceiling": "SHADOW_CALLER_BOUND_EVIDENCE_ONLY",
    }
    return AutonomyDecision.model_validate(
        {**payload, "decision_hash": canonical_autonomy_hash(payload)}
    )


def _safe_input_hash(grant: Any, evaluation: Any) -> str:
    def dump(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, Mapping):
            return dict(value)
        return {"invalid_type": type(value).__name__}

    try:
        return canonical_autonomy_hash({"grant": dump(grant), "evaluation": dump(evaluation)})
    except (TypeError, ValueError):
        return canonical_autonomy_hash({"invalid_evaluator_input": True})


def evaluate_autonomy_policy(
    grant: AutonomyGoalGrant | Mapping[str, Any],
    evaluation: AutonomyEvaluationInput | Mapping[str, Any],
) -> AutonomyDecision:
    """Evaluate an exact action without mutating or authorizing anything."""
    input_hash = _safe_input_hash(grant, evaluation)
    try:
        validated_grant = AutonomyGoalGrant.model_validate(
            grant.model_dump(mode="json") if isinstance(grant, AutonomyGoalGrant) else grant
        )
    except ValidationError as exc:
        reason = "GRANT_HASH_INVALID" if "GRANT_HASH_INVALID" in str(exc) else "GRANT_INVALID"
        return _decision(reasons=[reason], input_hash=input_hash)
    try:
        value = AutonomyEvaluationInput.model_validate(
            evaluation.model_dump(mode="json")
            if isinstance(evaluation, AutonomyEvaluationInput)
            else evaluation
        )
    except ValidationError:
        return _decision(reasons=["EVALUATOR_INPUT_INVALID"], input_hash=input_hash)

    reasons: list[str] = []
    observed_now = datetime.now(timezone.utc)
    if value.evaluated_at < validated_grant.issued_at:
        reasons.append("GRANT_NOT_YET_VALID")
    if value.evaluated_at >= validated_grant.expires_at:
        reasons.append("GRANT_EXPIRED")
    if observed_now < validated_grant.issued_at:
        reasons.append("GRANT_NOT_YET_VALID")
    if observed_now >= validated_grant.expires_at:
        reasons.append("GRANT_EXPIRED")
    if value.evaluated_at > observed_now + timedelta(
        seconds=30
    ) or observed_now - value.evaluated_at > timedelta(minutes=5):
        reasons.append("EVALUATION_TIME_UNTRUSTED")

    binding = value.submission_binding
    if binding is None:
        reasons.append(
            "POST_SUBMISSION_GRANT_INJECTION"
            if value.post_submission_grant_presented
            else "LEGACY_TASK_MANUAL"
        )
    else:
        if binding.task_id != value.task_id or binding.goal_id != validated_grant.goal_id:
            reasons.append("GOAL_BINDING_MISMATCH")
        if binding.grant_hash != validated_grant.grant_hash:
            reasons.append("SUBMISSION_GRANT_MISMATCH")
        if binding.contract_hash != value.contract_hash:
            reasons.append("CONTRACT_HASH_MISMATCH")
        if binding.initial_attempt_id != value.attempt_id:
            reasons.append("ATTEMPT_BINDING_MISMATCH")
        if (
            binding.repository != validated_grant.repository
            or binding.repository != value.repository
        ):
            reasons.append("SUBMISSION_REPOSITORY_IDENTITY_MISMATCH")
        if (
            binding.collaboration_base != validated_grant.collaboration_base
            or binding.collaboration_base != value.collaboration_base
        ):
            reasons.append("SUBMISSION_BASE_IDENTITY_MISMATCH")
        if any(
            not any(_path_is_within(path, allowed) for allowed in binding.allowed_paths)
            for path in value.requested_paths
        ):
            reasons.append("TASK_SCOPE_EXCEEDED")

    if value.repository != validated_grant.repository:
        reasons.append("REPOSITORY_IDENTITY_MISMATCH")
    if value.collaboration_base != validated_grant.collaboration_base:
        reasons.append("BASE_IDENTITY_MISMATCH")
    if value.action not in validated_grant.allowed_actions:
        reasons.append("ACTION_NOT_ALLOWED")
    if value.action in validated_grant.forbidden_actions:
        reasons.append("ACTION_FORBIDDEN")

    if any(
        not any(
            _path_is_within(path, allowed) for allowed in validated_grant.path_policy.allowed_paths
        )
        or any(
            _paths_overlap(path, forbidden)
            for forbidden in validated_grant.path_policy.forbidden_paths
        )
        for path in value.requested_paths
    ):
        reasons.append("PATH_SCOPE_EXCEEDED")

    child = value.child_scope
    child_widened = (
        not set(child.allowed_actions).issubset(validated_grant.allowed_actions)
        or any(
            not any(
                _path_is_within(path, allowed)
                for allowed in validated_grant.path_policy.allowed_paths
            )
            for path in child.allowed_paths
        )
        or _RISK_RANK[child.risk_ceiling] > _RISK_RANK[validated_grant.risk_ceiling]
        or child.maximum_attempts_per_task > validated_grant.maximum_attempts_per_task
        or child.maximum_provider_calls > validated_grant.maximum_provider_calls
        or child.maximum_wall_time_seconds > validated_grant.maximum_wall_time_seconds
        or child.maximum_changed_files > validated_grant.maximum_changed_files
        or child.maximum_concurrent_targets > validated_grant.maximum_concurrent_targets
        or (
            binding is not None
            and any(
                not any(_path_is_within(path, allowed) for allowed in binding.allowed_paths)
                for path in child.allowed_paths
            )
        )
    )
    if child_widened:
        reasons.append("CHILD_SCOPE_WIDENING")
    if value.action not in child.allowed_actions:
        reasons.append("CHILD_SCOPE_ACTION_MISMATCH")
    if any(
        not any(_path_is_within(path, allowed) for allowed in child.allowed_paths)
        for path in value.requested_paths
    ):
        reasons.append("CHILD_SCOPE_PATH_MISMATCH")
    if _RISK_RANK[value.risk] > _RISK_RANK[child.risk_ceiling]:
        reasons.append("CHILD_SCOPE_RISK_MISMATCH")
    if _RISK_RANK[value.risk] > _RISK_RANK[validated_grant.risk_ceiling]:
        reasons.append("RISK_CEILING_EXCEEDED")

    usage = value.budget_usage
    budget_checks = (
        (usage.tasks >= validated_grant.maximum_tasks, "TASK_BUDGET_EXHAUSTED"),
        (
            usage.attempts_for_task
            >= min(
                validated_grant.maximum_attempts_per_task,
                child.maximum_attempts_per_task,
            ),
            "ATTEMPT_BUDGET_EXHAUSTED",
        ),
        (
            usage.provider_calls
            >= min(
                validated_grant.maximum_provider_calls,
                child.maximum_provider_calls,
            ),
            "PROVIDER_CALL_BUDGET_EXHAUSTED",
        ),
        (
            usage.wall_time_seconds
            >= min(
                validated_grant.maximum_wall_time_seconds,
                child.maximum_wall_time_seconds,
            ),
            "WALL_TIME_BUDGET_EXHAUSTED",
        ),
        (
            usage.changed_files + len(value.requested_paths)
            > min(
                validated_grant.maximum_changed_files,
                child.maximum_changed_files,
            ),
            "CHANGED_FILE_BUDGET_EXHAUSTED",
        ),
        (
            usage.active_targets
            >= min(
                validated_grant.maximum_concurrent_targets,
                child.maximum_concurrent_targets,
            ),
            "TARGET_CONCURRENCY_EXHAUSTED",
        ),
    )
    reasons.extend(reason for exhausted, reason in budget_checks if exhausted)

    if not set(value.sensitive_scopes).issubset(validated_grant.admitted_sensitive_scopes):
        reasons.append("SENSITIVE_SCOPE_NOT_ADMITTED")
    if (
        value.action is AutonomyActionClass.PRODUCTION_RELEASE
        and not validated_grant.production_release_authorized
    ):
        reasons.append("PRODUCTION_RELEASE_NOT_AUTHORIZED")
    if value.action is AutonomyActionClass.GITHUB_MERGE:
        reasons.append("MERGE_NOT_AUTHORIZED")
    if value.action is AutonomyActionClass.RUNTIME_ACTIVATE:
        reasons.append("RUNTIME_ACTIVATION_NOT_AUTHORIZED")

    verified_candidate = value.candidate_at_verification
    current_candidate = value.current_candidate
    if value.action in _CANDIDATE_BOUND_ACTIONS and (
        verified_candidate is None or current_candidate is None
    ):
        reasons.append("CANDIDATE_IDENTITY_REQUIRED")
    if verified_candidate is not None and (
        verified_candidate.task_id != value.task_id
        or verified_candidate.attempt_id != value.attempt_id
    ):
        reasons.append("CANDIDATE_TASK_ATTEMPT_MISMATCH")
    if verified_candidate is not None and current_candidate != verified_candidate:
        reasons.append("CANDIDATE_IDENTITY_DRIFT")
    if validated_grant.independent_acceptance_required:
        if value.acceptance is None:
            reasons.append("INDEPENDENT_ACCEPTANCE_REQUIRED")
        else:
            if (
                value.acceptance.authority_kind is not AcceptanceAuthorityKind.INDEPENDENT_REVIEWER
                or value.acceptance.accepted_by == value.implementer_id
            ):
                reasons.append("IMPLEMENTER_ACCEPTANCE_FORBIDDEN")
            if verified_candidate is None or value.acceptance.candidate != verified_candidate:
                reasons.append("ACCEPTANCE_CANDIDATE_MISMATCH")
            elif (
                value.acceptance.candidate_receipt_hash != verified_candidate.verified_receipt_hash
            ):
                reasons.append("ACCEPTANCE_RECEIPT_CANDIDATE_MISMATCH")

    if value.action in _RUNTIME_BOUND_ACTIONS:
        if value.expected_runtime_identity is None or value.current_runtime_identity is None:
            reasons.append("RUNTIME_IDENTITY_REQUIRED")
        elif value.expected_runtime_identity != value.current_runtime_identity:
            reasons.append("RUNTIME_IDENTITY_DRIFT")

    return _decision(reasons=reasons, input_hash=input_hash)


def project_autonomy_submission(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return a read-only eligibility projection without backfilling state."""
    raw_binding = state.get("autonomy_submission_binding")
    if raw_binding is None:
        return {
            "schema": "nexus.autonomy_submission_projection.v1",
            "mode": "MANUAL",
            "eligible": False,
            "reason_codes": ["LEGACY_TASK_MANUAL"],
        }
    try:
        binding = AutonomySubmissionBinding.model_validate(raw_binding)
    except ValidationError:
        return {
            "schema": "nexus.autonomy_submission_projection.v1",
            "mode": "SHADOW",
            "eligible": False,
            "reason_codes": ["SUBMISSION_BINDING_INVALID"],
        }
    contract = state.get("contract") if isinstance(state.get("contract"), Mapping) else {}
    attempts = state.get("attempts") if isinstance(state.get("attempts"), list) else []
    initial_attempt = attempts[0] if attempts and isinstance(attempts[0], Mapping) else {}
    persisted_paths = tuple(
        sorted(
            str(path).rstrip("/")
            for path in contract.get("allowed_files", ())
            if str(path).rstrip("/")
        )
    )
    matching = (
        state.get("task_id") == binding.task_id
        and state.get("autonomy_goal_id") == binding.goal_id
        and state.get("autonomy_goal_grant_hash") == binding.grant_hash
        and state.get("autonomy_mode") == binding.mode
        and state.get("contract_hash") == binding.contract_hash
        and state.get("controller_revision") == binding.controller_revision
        and persisted_paths == binding.allowed_paths
        and initial_attempt.get("attempt_id") == binding.initial_attempt_id
        and initial_attempt.get("action_request_hash") == binding.action_request_hash
    )
    return {
        "schema": "nexus.autonomy_submission_projection.v1",
        "mode": "SHADOW",
        "eligible": matching,
        "goal_id": binding.goal_id,
        "grant_hash": binding.grant_hash,
        "binding_hash": binding.binding_hash,
        "reason_codes": [] if matching else ["SUBMISSION_BINDING_DRIFT"],
    }
