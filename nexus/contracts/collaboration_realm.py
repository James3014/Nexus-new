"""Typed, immutable bindings for a collaboration execution realm."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator

from nexus.contracts.autonomy_goal import (
    CollaborationBaseIdentity,
    RepositoryIdentity,
    canonical_autonomy_hash,
)

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SCHEMA = "nexus.collaboration_execution_realm.v1"


def _safe_id(value: str, field: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"{field.upper()}_INVALID")
    return value


def _absolute_path(value: str, field: str) -> str:
    if (
        not value
        or value.strip() != value
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"{field.upper()}_INVALID")
    candidate = Path(value)
    if not candidate.is_absolute():
        raise ValueError(f"{field.upper()}_INVALID")
    return candidate.resolve(strict=False).as_posix()


def _overlaps(left: str, right: str) -> bool:
    left_path = Path(left)
    right_path = Path(right)
    return (
        left_path == right_path
        or left_path in right_path.parents
        or right_path in left_path.parents
    )


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ControlPlaneRepoBinding(_FrozenModel):
    repo_root: StrictStr
    revision: StrictStr

    @field_validator("repo_root")
    @classmethod
    def validate_repo_root(cls, value: str) -> str:
        return _absolute_path(value, "repo_root")

    @field_validator("revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError("REVISION_INVALID")
        return value


class CollaborationRepoBinding(_FrozenModel):
    repository: RepositoryIdentity
    base: CollaborationBaseIdentity
    repo_root: StrictStr
    remote_name: StrictStr = "origin"

    @field_validator("repo_root")
    @classmethod
    def validate_repo_root(cls, value: str) -> str:
        return _absolute_path(value, "repo_root")

    @field_validator("remote_name")
    @classmethod
    def validate_remote_name(cls, value: str) -> str:
        return _safe_id(value, "remote_name")


class RuntimeActivationBinding(_FrozenModel):
    realm_id: StrictStr
    activation_authorized: Literal[False] = False

    @field_validator("realm_id")
    @classmethod
    def validate_realm_id(cls, value: str) -> str:
        return _safe_id(value, "realm_id")


class CollaborationExecutionRealmSpec(_FrozenModel):
    schema: Literal[_SCHEMA] = _SCHEMA
    control_plane: ControlPlaneRepoBinding
    collaboration: CollaborationRepoBinding
    runtime_activation: RuntimeActivationBinding
    execution_root: StrictStr

    @field_validator("execution_root")
    @classmethod
    def validate_execution_root(cls, value: str) -> str:
        return _absolute_path(value, "execution_root")

    @model_validator(mode="after")
    def validate_boundaries(self) -> "CollaborationExecutionRealmSpec":
        roots = (
            self.control_plane.repo_root,
            self.collaboration.repo_root,
            self.execution_root,
        )
        if any(
            _overlaps(left, right)
            for index, left in enumerate(roots)
            for right in roots[index + 1 :]
        ):
            raise ValueError("ROOT_BOUNDARY_CONFLICT")
        if self.runtime_activation.activation_authorized is not False:
            raise ValueError("ACTIVATION_UNAUTHORIZED")
        return self


class CollaborationExecutionRealm(CollaborationExecutionRealmSpec):
    binding_hash: StrictStr

    @field_validator("binding_hash")
    @classmethod
    def validate_binding_hash(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("BINDING_HASH_INVALID")
        return value

    @model_validator(mode="after")
    def validate_canonical_binding_hash(self) -> "CollaborationExecutionRealm":
        payload = self.model_dump(mode="json", exclude={"binding_hash"})
        expected = canonical_autonomy_hash(payload)
        if expected != self.binding_hash:
            raise ValueError("BINDING_HASH_MISMATCH")
        return self

    @classmethod
    def issue(cls, **values: Any) -> "CollaborationExecutionRealm":
        spec = CollaborationExecutionRealmSpec.model_validate(values)
        payload: Mapping[str, Any] = spec.model_dump(mode="json")
        return cls.model_validate({**payload, "binding_hash": canonical_autonomy_hash(payload)})


__all__ = [
    "CollaborationBaseIdentity",
    "CollaborationExecutionRealm",
    "CollaborationExecutionRealmSpec",
    "CollaborationRepoBinding",
    "ControlPlaneRepoBinding",
    "RepositoryIdentity",
    "RuntimeActivationBinding",
]
