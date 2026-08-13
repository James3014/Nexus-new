"""Immutable authority contract for goal-scoped autonomy shadow evaluation.

This module defines policy evidence only.  It grants no lifecycle mutation,
approval, integration, push, merge, activation, or release authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal, Mapping

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PositiveInt = Annotated[StrictInt, Field(gt=0)]
_REPOSITORY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")


def canonical_autonomy_hash(value: Mapping[str, Any]) -> str:
    """Return the canonical UTF-8 SHA-256 hash of a JSON-safe mapping."""
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AutonomyActionClass(str, Enum):
    TASK_SUBMIT = "TASK_SUBMIT"
    TASK_RETRY = "TASK_RETRY"
    CANDIDATE_VERIFY = "CANDIDATE_VERIFY"
    CANDIDATE_APPROVE = "CANDIDATE_APPROVE"
    CANDIDATE_INTEGRATE = "CANDIDATE_INTEGRATE"
    REPOSITORY_PUSH = "REPOSITORY_PUSH"
    GITHUB_MERGE = "GITHUB_MERGE"
    RUNTIME_ACTIVATE = "RUNTIME_ACTIVATE"
    PRODUCTION_RELEASE = "PRODUCTION_RELEASE"


class AutonomyRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SensitiveScope(str, Enum):
    AUTHORITY = "AUTHORITY"
    SECURITY = "SECURITY"
    MIGRATION = "MIGRATION"
    PRODUCTION = "PRODUCTION"


class MergeAuthorizationPolicy(str, Enum):
    NEVER = "NEVER"
    OWNER_ONLY = "OWNER_ONLY"


class RuntimeActivationPolicy(str, Enum):
    NEVER = "NEVER"
    OWNER_ONLY = "OWNER_ONLY"


def _safe_id(value: str, field: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"{field.upper()}_INVALID")
    return value


def _repo_path(value: str, field: str) -> str:
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"{field.upper()}_INVALID")
    path = PurePosixPath(value)
    if ".." in path.parts or ".git" in path.parts or path.as_posix() != value:
        raise ValueError(f"{field.upper()}_INVALID")
    return value


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StandingGrantContext(_FrozenModel):
    """Immutable evidence binding for a coordinator standing grant."""

    schema: Literal["nexus.standing_grant_context.v1"] = "nexus.standing_grant_context.v1"
    owner_id: StrictStr
    coordinator_id: StrictStr
    repository: RepositoryIdentity
    thread_id: StrictStr
    goal_id: StrictStr
    allowed_actions: tuple[AutonomyActionClass, ...]
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None = None
    revocation_reason: StrictStr | None = None
    context_hash: StrictStr

    @field_validator("owner_id", "coordinator_id", "thread_id", "goal_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator("allowed_actions")
    @classmethod
    def canonicalize_actions(cls, values: tuple[AutonomyActionClass, ...]) -> tuple[AutonomyActionClass, ...]:
        if not values:
            raise ValueError("STANDING_GRANT_ACTIONS_REQUIRED")
        return tuple(sorted(set(values), key=lambda item: item.value))

    @field_validator("revocation_reason")
    @classmethod
    def validate_revocation_reason(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value.strip() != value):
            raise ValueError("REVOCATION_REASON_INVALID")
        return value

    @field_validator("context_hash")
    @classmethod
    def validate_context_hash_format(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("CONTEXT_HASH_INVALID")
        return value

    @model_validator(mode="after")
    def validate_context(self) -> "StandingGrantContext":
        if self.expires_at <= self.issued_at:
            raise ValueError("STANDING_GRANT_EXPIRY_INVALID")
        if (self.revoked_at is None) != (self.revocation_reason is None):
            raise ValueError("REVOCATION_BINDING_INVALID")
        payload = self.model_dump(mode="json", exclude={"context_hash"})
        if self.context_hash != canonical_autonomy_hash(payload):
            raise ValueError("CONTEXT_HASH_INVALID")
        return self

    @classmethod
    def issue(cls, **values: Any) -> "StandingGrantContext":
        values.setdefault("schema", "nexus.standing_grant_context.v1")
        payload = dict(values)
        payload.pop("context_hash", None)
        payload = cls.model_construct(**payload).model_dump(mode="json")
        return cls.model_validate({**payload, "context_hash": canonical_autonomy_hash(payload)})


class RepositoryIdentity(_FrozenModel):
    repository_id: StrictStr
    canonical_remote: StrictStr

    @field_validator("repository_id")
    @classmethod
    def validate_repository_id(cls, value: str) -> str:
        if not _REPOSITORY_ID.fullmatch(value) or any(
            segment in {".", ".."} for segment in value.split("/")
        ):
            raise ValueError("REPOSITORY_ID_INVALID")
        return value

    @field_validator("canonical_remote")
    @classmethod
    def validate_canonical_remote(cls, value: str) -> str:
        if (
            value.strip() != value
            or any(ord(char) < 33 or ord(char) == 127 for char in value)
            or not value.startswith(("https://", "ssh://", "git@"))
        ):
            raise ValueError("CANONICAL_REMOTE_INVALID")
        return value


class CollaborationBaseIdentity(_FrozenModel):
    branch: StrictStr
    head_sha: StrictStr

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        normalized = value.strip()
        invalid = (
            not normalized
            or normalized != value
            or value.startswith(("-", "/", "."))
            or value.endswith(("/", ".", ".lock"))
            or ".." in value
            or "@{" in value
            or "//" in value
            or any(char in value for char in " ~^:?*[\\")
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        )
        if invalid:
            raise ValueError("COLLABORATION_BRANCH_INVALID")
        return value

    @field_validator("head_sha")
    @classmethod
    def validate_head(cls, value: str) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError("COLLABORATION_HEAD_INVALID")
        return value


class AutonomyPathPolicy(_FrozenModel):
    allowed_paths: tuple[StrictStr, ...]
    forbidden_paths: tuple[StrictStr, ...] = ()

    @field_validator("allowed_paths", "forbidden_paths")
    @classmethod
    def validate_paths(cls, values: tuple[str, ...], info) -> tuple[str, ...]:
        normalized = tuple(sorted({_repo_path(value, info.field_name) for value in values}))
        if info.field_name == "allowed_paths" and not normalized:
            raise ValueError("ALLOWED_PATHS_REQUIRED")
        return normalized

    @model_validator(mode="after")
    def validate_disjoint_paths(self) -> "AutonomyPathPolicy":
        if set(self.allowed_paths) & set(self.forbidden_paths):
            raise ValueError("PATH_POLICY_CONFLICT")
        return self

    def allows(self, value: str) -> bool:
        """Return whether one normalized repository path is in this scope."""
        path = _repo_path(value, "requested_path")
        within_allowed = any(
            path == parent or path.startswith(parent.rstrip("/") + "/")
            for parent in self.allowed_paths
        )
        overlaps_forbidden = any(
            path == denied
            or path.startswith(denied.rstrip("/") + "/")
            or denied.startswith(path.rstrip("/") + "/")
            for denied in self.forbidden_paths
        )
        return within_allowed and not overlaps_forbidden


class AutonomyGoalGrantSpec(_FrozenModel):
    schema: Literal["nexus.autonomy_goal_grant.v1"]
    goal_id: StrictStr
    issued_by: StrictStr
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    repository: RepositoryIdentity
    collaboration_base: CollaborationBaseIdentity
    objective: StrictStr
    allowed_actions: tuple[AutonomyActionClass, ...]
    forbidden_actions: tuple[AutonomyActionClass, ...]
    risk_ceiling: AutonomyRiskLevel
    path_policy: AutonomyPathPolicy
    maximum_tasks: PositiveInt
    maximum_attempts_per_task: PositiveInt
    maximum_provider_calls: PositiveInt
    maximum_wall_time_seconds: PositiveInt
    maximum_changed_files: PositiveInt
    maximum_concurrent_targets: PositiveInt
    independent_acceptance_required: StrictBool
    admitted_sensitive_scopes: tuple[SensitiveScope, ...] = ()
    merge_authorization_policy: MergeAuthorizationPolicy
    runtime_activation_authorization_policy: RuntimeActivationPolicy
    production_release_authorized: StrictBool = False

    @field_validator("goal_id", "issued_by")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator("objective")
    @classmethod
    def validate_objective(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or normalized != value:
            raise ValueError("OBJECTIVE_INVALID")
        return value

    @field_validator("allowed_actions", "forbidden_actions")
    @classmethod
    def canonicalize_actions(
        cls,
        values: tuple[AutonomyActionClass, ...],
        info,
    ) -> tuple[AutonomyActionClass, ...]:
        normalized = tuple(sorted(set(values), key=lambda item: item.value))
        if info.field_name == "allowed_actions" and not normalized:
            raise ValueError("ALLOWED_ACTIONS_REQUIRED")
        return normalized

    @field_validator("admitted_sensitive_scopes")
    @classmethod
    def canonicalize_scopes(
        cls,
        values: tuple[SensitiveScope, ...],
    ) -> tuple[SensitiveScope, ...]:
        return tuple(sorted(set(values), key=lambda item: item.value))

    @model_validator(mode="after")
    def validate_authority(self) -> "AutonomyGoalGrantSpec":
        if self.expires_at <= self.issued_at:
            raise ValueError("GRANT_EXPIRY_INVALID")
        if set(self.allowed_actions) & set(self.forbidden_actions):
            raise ValueError("ACTION_POLICY_CONFLICT")
        if self.production_release_authorized is not False:
            raise ValueError("PRODUCTION_RELEASE_AUTHORIZATION_FORBIDDEN_IN_V1")
        return self


class AutonomyGoalGrant(AutonomyGoalGrantSpec):
    grant_hash: StrictStr

    @field_validator("grant_hash")
    @classmethod
    def validate_grant_hash_format(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("GRANT_HASH_INVALID")
        return value

    @model_validator(mode="after")
    def validate_grant_hash(self) -> "AutonomyGoalGrant":
        payload = self.model_dump(mode="json", exclude={"grant_hash"})
        if self.grant_hash != canonical_autonomy_hash(payload):
            raise ValueError("GRANT_HASH_INVALID")
        return self

    @classmethod
    def issue(cls, **values: Any) -> "AutonomyGoalGrant":
        """Validate policy fields and bind their canonical hash."""
        values.setdefault("schema", "nexus.autonomy_goal_grant.v1")
        spec = AutonomyGoalGrantSpec.model_validate(values)
        payload = spec.model_dump(mode="json")
        return cls.model_validate({**payload, "grant_hash": canonical_autonomy_hash(payload)})
