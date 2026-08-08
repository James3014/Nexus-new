"""Typed identity and idempotency contract for Gateway lifecycle actions."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any, Mapping, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class LifecycleActionType(str, Enum):
    TASK_RUN = "TASK_RUN"
    TASK_FINISH = "TASK_FINISH"
    TASK_RECONCILE = "TASK_RECONCILE"
    TASK_RETRY = "TASK_RETRY"
    TASK_RESUME = "TASK_RESUME"
    CANDIDATE_APPROVE = "CANDIDATE_APPROVE"
    CANDIDATE_INTEGRATE = "CANDIDATE_INTEGRATE"
    CANDIDATE_DISPOSE = "CANDIDATE_DISPOSE"


class PermissionProfile(str, Enum):
    DISCOVERY = "DISCOVERY"
    OBSERVE = "OBSERVE"
    VERIFY = "VERIFY"
    MUTATE_BOUNDED = "MUTATE_BOUNDED"
    CANDIDATE = "CANDIDATE"
    INTEGRATE = "INTEGRATE"


class ApprovalScope(str, Enum):
    ALLOW_ACTION_ONCE = "ALLOW_ACTION_ONCE"
    ALLOW_TASK_ATTEMPT = "ALLOW_TASK_ATTEMPT"
    REJECT = "REJECT"


class MutationDomain(str, Enum):
    """What durable surface an action is allowed to mutate."""

    NONE = "NONE"
    REPOSITORY = "REPOSITORY"
    LIFECYCLE_STATE = "LIFECYCLE_STATE"
    TARGET = "TARGET"
    CANDIDATE_REF = "CANDIDATE_REF"
    INTEGRATION = "INTEGRATION"


class ContractKind(str, Enum):
    """Authorization source, independent from the execution lane."""

    NONE = "NONE"
    TRACKED_TASK_CARD = "TRACKED_TASK_CARD"
    OWNER_INLINE = "OWNER_INLINE"


def canonical_request_hash(payload: Mapping[str, Any]) -> str:
    """Hash the request without relying on caller key order or formatting."""
    encoded = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256(encoded).hexdigest()


def owner_inline_contract_hash(contract: Mapping[str, Any]) -> str:
    """Hash an inline contract without trusting a caller-supplied hash."""
    payload = dict(contract)
    payload.pop("contract_hash", None)
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def build_owner_inline_contract(
    *,
    task_id: str,
    objective: str,
    allowed_files: list[str] | tuple[str, ...],
    verifier_commands: list[str] | tuple[str, ...],
    expected_head: str,
    issued_at: str,
    expires_at: str,
    permission_profile: PermissionProfile = PermissionProfile.MUTATE_BOUNDED,
    worker_may_commit: bool = False,
    authority_change_candidate_confirmation: bool = False,
) -> dict[str, Any]:
    """Create the immutable bounded Owner-inline authorization contract."""
    paths = [str(path) for path in allowed_files if str(path).strip()]
    if not 1 <= len(paths) <= 4:
        raise ValueError("OWNER_INLINE_ALLOWED_FILES_LIMIT")
    for path in paths:
        _repo_path(path, "allowed_files")
    verifiers = [str(command).strip() for command in verifier_commands if str(command).strip()]
    if not verifiers:
        raise ValueError("OWNER_INLINE_VERIFIERS_REQUIRED")
    if not _SHA40.fullmatch(expected_head):
        raise ValueError("OWNER_INLINE_EXPECTED_HEAD_INVALID")
    contract: dict[str, Any] = {
        "schema": "nexus.owner_inline_contract.v1",
        "contract_kind": ContractKind.OWNER_INLINE.value,
        "task_id": _safe_id(task_id, "task_id"),
        "owner_confirmation": True,
        "objective": str(objective).strip(),
        "allowed_files": paths,
        "verifier_commands": verifiers,
        "expected_head": expected_head,
        "issued_at": str(issued_at),
        "expires_at": str(expires_at),
        "permission_profile": permission_profile.value,
        "worker_may_commit": bool(worker_may_commit),
        "worker_may_approve": False,
        "worker_may_integrate": False,
        "worker_may_push": False,
        "authorized_deletions": False,
    }
    if authority_change_candidate_confirmation:
        contract["authority_change_candidate_confirmation"] = True
    contract["contract_hash"] = owner_inline_contract_hash(contract)
    return contract


def validate_owner_inline_contract(contract: Mapping[str, Any], *, expected_task_id: Optional[str] = None, expected_head: Optional[str] = None) -> dict[str, Any]:
    """Fail closed on tampering or authority widening in an inline contract."""
    value = dict(contract)
    if value.get("schema") != "nexus.owner_inline_contract.v1" or value.get("contract_kind") != ContractKind.OWNER_INLINE.value:
        raise ValueError("OWNER_INLINE_SCHEMA_INVALID")
    if value.get("owner_confirmation") is not True:
        raise ValueError("OWNER_INLINE_CONFIRMATION_REQUIRED")
    if not isinstance(value.get("authority_change_candidate_confirmation", False), bool):
        raise ValueError("OWNER_INLINE_AUTHORITY_CONFIRMATION_INVALID")
    if expected_task_id is not None and value.get("task_id") != expected_task_id:
        raise ValueError("OWNER_INLINE_TASK_ID_MISMATCH")
    if expected_head is not None and value.get("expected_head") != expected_head:
        raise ValueError("OWNER_INLINE_HEAD_MISMATCH")
    try:
        issued = datetime.fromisoformat(str(value.get("issued_at")).replace("Z", "+00:00"))
        expires = datetime.fromisoformat(str(value.get("expires_at")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("OWNER_INLINE_EXPIRY_INVALID") from exc
    if expires <= issued or expires <= datetime.now(timezone.utc):
        raise ValueError("OWNER_INLINE_CONTRACT_EXPIRED")
    if not isinstance(value.get("allowed_files"), list) or not 1 <= len(value["allowed_files"]) <= 4:
        raise ValueError("OWNER_INLINE_ALLOWED_FILES_LIMIT")
    for path in value["allowed_files"]:
        _repo_path(path, "allowed_files")
    if not isinstance(value.get("verifier_commands"), list) or not value["verifier_commands"]:
        raise ValueError("OWNER_INLINE_VERIFIERS_REQUIRED")
    forbidden = {
        "worker_may_approve": False,
        "worker_may_integrate": False,
        "worker_may_push": False,
        "authorized_deletions": False,
    }
    if any(value.get(key) is not expected for key, expected in forbidden.items()):
        raise ValueError("OWNER_INLINE_AUTHORITY_WIDENING")
    supplied = str(value.get("contract_hash") or "")
    if not _SHA64.fullmatch(supplied) or supplied != owner_inline_contract_hash(value):
        raise ValueError("CONTRACT_HASH_MISMATCH")
    return value


def _safe_id(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError(f"{field} must be a safe lifecycle identifier")
    return value


def _repo_path(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise ValueError(f"{field} must be a repository-relative path")
    path = PurePosixPath(value)
    if ".." in path.parts or ".git" in path.parts or path.as_posix() != value:
        raise ValueError(f"{field} must be a normalized repository-relative path")
    return value


class LifecycleActionEnvelope(BaseModel):
    """The identity/precondition envelope attached to one lifecycle action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema: str = "nexus.lifecycle_action.v1"
    task_id: str
    attempt_id: str
    action_id: str
    idempotency_key: str
    action_type: LifecycleActionType
    task_card_path: Optional[str] = None
    task_card_hash: Optional[str] = None
    contract_kind: ContractKind = ContractKind.NONE
    contract_hash: Optional[str] = None
    expected_head: Optional[str] = None
    allowed_paths: tuple[str, ...] = ()
    permission_profile: PermissionProfile = PermissionProfile.OBSERVE
    approval_scope: ApprovalScope = ApprovalScope.ALLOW_ACTION_ONCE
    mutation_domain: MutationDomain = MutationDomain.NONE
    tool_manifest_hash: str
    request_hash: str
    mutation: bool = False

    @field_validator("task_id", "attempt_id", "action_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError("idempotency_key must be non-empty and <=256 characters")
        return value.strip()

    @field_validator("task_card_path")
    @classmethod
    def validate_card_path(cls, value: Optional[str]) -> Optional[str]:
        return _repo_path(value, "task_card_path") if value else value

    @field_validator("task_card_hash", "contract_hash", "tool_manifest_hash", "request_hash")
    @classmethod
    def validate_sha256(cls, value: Optional[str], info) -> Optional[str]:
        if value is None and info.field_name in {"task_card_hash", "contract_hash"}:
            return value
        if not _SHA64.fullmatch(value):
            raise ValueError(f"{info.field_name} must be a lowercase SHA-256 digest")
        return value

    @field_validator("expected_head")
    @classmethod
    def validate_head(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not _SHA40.fullmatch(value):
            raise ValueError("expected_head must be a lowercase 40-character Git SHA")
        return value

    @field_validator("allowed_paths")
    @classmethod
    def validate_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_repo_path(value, "allowed_paths") for value in values)

    @model_validator(mode="after")
    def validate_mutation_preconditions(self) -> "LifecycleActionEnvelope":
        if self.mutation:
            if self.expected_head is None:
                raise ValueError("mutation actions require expected_head")
            if self.permission_profile not in {PermissionProfile.MUTATE_BOUNDED, PermissionProfile.CANDIDATE, PermissionProfile.INTEGRATE}:
                raise ValueError("mutation actions require a mutation permission profile")
            if self.mutation_domain == MutationDomain.NONE:
                raise ValueError("mutation actions require mutation_domain")
            if self.mutation_domain in {MutationDomain.REPOSITORY, MutationDomain.INTEGRATION} and not self.allowed_paths:
                raise ValueError("repository mutation actions require allowed_paths")
        elif self.mutation_domain != MutationDomain.NONE:
            raise ValueError("non-mutation actions must use mutation_domain=NONE")
        if bool(self.task_card_path) != bool(self.task_card_hash):
            raise ValueError("task_card_path and task_card_hash must be supplied together")
        if self.contract_kind == ContractKind.OWNER_INLINE and self.contract_hash is None:
            raise ValueError("OWNER_INLINE actions require contract_hash")
        if self.contract_kind == ContractKind.TRACKED_TASK_CARD and not self.task_card_hash:
            raise ValueError("TRACKED_TASK_CARD actions require task_card_hash")
        return self

    def verify_request(self, payload: Mapping[str, Any]) -> bool:
        return canonical_request_hash(payload) == self.request_hash


def build_action_envelope(
    *,
    task_id: str,
    action_type: LifecycleActionType,
    request: Mapping[str, Any],
    tool_manifest_hash: str,
    expected_head: Optional[str],
    allowed_paths: list[str] | tuple[str, ...],
    mutation: bool,
    task_card_path: Optional[str] = None,
    task_card_hash: Optional[str] = None,
    contract_kind: ContractKind = ContractKind.NONE,
    contract_hash: Optional[str] = None,
    attempt_id: Optional[str] = None,
    action_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    permission_profile: PermissionProfile = PermissionProfile.MUTATE_BOUNDED,
    approval_scope: ApprovalScope = ApprovalScope.ALLOW_ACTION_ONCE,
    mutation_domain: Optional[MutationDomain] = None,
) -> LifecycleActionEnvelope:
    canonical = dict(request)
    return LifecycleActionEnvelope(
        task_id=task_id,
        attempt_id=attempt_id or f"attempt-{uuid4().hex}",
        action_id=action_id or f"action-{uuid4().hex}",
        idempotency_key=idempotency_key or f"{task_id}:{canonical_request_hash(canonical)}",
        action_type=action_type,
        task_card_path=task_card_path,
        task_card_hash=task_card_hash,
        contract_kind=contract_kind,
        contract_hash=contract_hash,
        expected_head=expected_head,
        allowed_paths=tuple(allowed_paths),
        permission_profile=permission_profile,
        approval_scope=approval_scope,
        mutation_domain=mutation_domain or (MutationDomain.REPOSITORY if mutation else MutationDomain.NONE),
        tool_manifest_hash=tool_manifest_hash,
        request_hash=canonical_request_hash(canonical),
        mutation=mutation,
    )
