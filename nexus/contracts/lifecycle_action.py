"""Typed identity and idempotency contract for Gateway lifecycle actions."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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
    CANDIDATE_ADOPT_EXTERNAL = "CANDIDATE_ADOPT_EXTERNAL"
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


@dataclass(frozen=True)
class HistoricalEpbTaskCardProjection:
    """The bounded, non-authoritative projection consumed by Candidate adoption."""

    allowed_repository_paths: tuple[str, ...]
    forbidden_scope: tuple[str, ...]
    exact_verification_commands: tuple[str, ...]
    auto_chain: Literal[False] = False
    forbidden_repository_paths: tuple[str, ...] = ()
    forbidden_repository_patterns: tuple[str, ...] = ()
    allow_deletions: bool = False


_HISTORICAL_CARD_SECTIONS = (
    "Allowed repository paths",
    "Forbidden scope",
    "Exact verification commands",
)


def _unresolvable_card() -> ValueError:
    return ValueError("ADOPTION_CARD_CONTRACT_UNRESOLVABLE")


def _historical_card_section(lines: list[str], title: str) -> list[str]:
    heading = f"## {title}"
    starts = [index for index, line in enumerate(lines) if line == heading]
    if len(starts) != 1:
        raise _unresolvable_card()
    start = starts[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    section = lines[start:end]
    if any(line.startswith("#") for line in section):
        raise _unresolvable_card()
    return section


def parse_historical_epb_task_card(card_bytes: bytes) -> HistoricalEpbTaskCardProjection:
    """Parse only the frozen EPB card contract fields, without inference."""
    if not isinstance(card_bytes, bytes) or not card_bytes:
        raise _unresolvable_card()
    try:
        text = card_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _unresolvable_card() from exc
    if "\r" in text:
        raise _unresolvable_card()
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if sum(line == "`AUTO_CHAIN=false`" for line in lines) != 1:
        raise _unresolvable_card()
    if any(line == "`AUTO_CHAIN=true`" for line in lines):
        raise _unresolvable_card()
    sections = {title: _historical_card_section(lines, title) for title in _HISTORICAL_CARD_SECTIONS}

    def code_bullets(section: list[str]) -> tuple[str, ...]:
        values = tuple(
            match.group(1)
            for line in section
            if (match := re.fullmatch(r"- `([^`]+)`", line))
        )
        nonempty_bullets = tuple(line for line in section if line.startswith("- "))
        if not values or len(values) != len(nonempty_bullets):
            raise _unresolvable_card()
        return values

    def exact_bullets(section: list[str]) -> tuple[str, ...]:
        values: list[str] = []
        for line in section:
            if not line.strip():
                continue
            match = re.fullmatch(r"- (.+\S)", line)
            if not match:
                raise _unresolvable_card()
            value = match.group(1)
            if value.startswith("`") or value.endswith("`"):
                if not (value.startswith("`") and value.endswith("`") and len(value) > 2):
                    raise _unresolvable_card()
                value = value[1:-1]
            values.append(value)
        if not values:
            raise _unresolvable_card()
        return tuple(values)

    allowed = code_bullets(sections["Allowed repository paths"])
    try:
        for path in allowed:
            _repo_path(path, "allowed_repository_paths")
    except ValueError as exc:
        raise _unresolvable_card() from exc

    forbidden_lines = tuple(line[2:].replace("`", "") for line in sections["Forbidden scope"] if line.startswith("- "))
    if not forbidden_lines or len(forbidden_lines) != sum(bool(line.strip()) for line in sections["Forbidden scope"]):
        raise _unresolvable_card()
    forbidden_paths: list[str] = []
    forbidden_patterns: list[str] = []
    for line in sections["Forbidden scope"]:
        for token in re.findall(r"`([^`]+)`", line):
            if "/" not in token:
                continue
            if token.endswith("/**") or token.endswith("/*"):
                prefix = token[:-3] if token.endswith("/**") else token[:-2]
                try:
                    _repo_path(prefix, "forbidden_repository_patterns")
                except ValueError as exc:
                    raise _unresolvable_card() from exc
                if "*" in prefix or token in forbidden_patterns:
                    raise _unresolvable_card()
                forbidden_patterns.append(token)
                continue
            if "*" in token:
                raise _unresolvable_card()
            try:
                _repo_path(token, "forbidden_repository_paths")
            except ValueError as exc:
                raise _unresolvable_card() from exc
            if token in forbidden_paths:
                raise _unresolvable_card()
            forbidden_paths.append(token)
    commands = exact_bullets(sections["Exact verification commands"])
    return HistoricalEpbTaskCardProjection(
        allowed,
        forbidden_lines,
        commands,
        False,
        tuple(forbidden_paths),
        tuple(forbidden_patterns),
    )


def parse_external_adoption_task_card(card_bytes: bytes) -> HistoricalEpbTaskCardProjection:
    """Parse either the historical EPB card or the current EIA Task Card shape.

    The return type stays the existing adoption projection so lifecycle authority
    does not change; this only removes a formatting-generation mismatch between
    External Intelligence and external Candidate adoption.
    """
    try:
        return parse_historical_epb_task_card(card_bytes)
    except ValueError:
        pass
    if not isinstance(card_bytes, bytes) or not card_bytes:
        raise _unresolvable_card()
    try:
        text = card_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _unresolvable_card() from exc
    if "\r" in text:
        raise _unresolvable_card()
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    false_markers = [
        line
        for line in lines
        if re.fullmatch(r"\s*-\s*AUTO_CHAIN:\s*false\s*", line, re.IGNORECASE)
    ]
    if len(false_markers) != 1 or any(
        re.fullmatch(r"\s*-\s*AUTO_CHAIN:\s*true\s*", line, re.IGNORECASE)
        for line in lines
    ):
        raise _unresolvable_card()
    deletion_markers = [
        match.group(1).lower()
        for line in lines
        if (match := re.fullmatch(
            r"\s*-\s*allow_deletions:\s*(true|false)\s*", line, re.IGNORECASE
        ))
    ]
    if len(deletion_markers) > 1:
        raise _unresolvable_card()
    allow_deletions = bool(deletion_markers and deletion_markers[0] == "true")

    def section(title: str) -> list[str]:
        heading = f"## {title}".lower()
        starts = [index for index, line in enumerate(lines) if line.strip().lower() == heading]
        if len(starts) != 1:
            raise _unresolvable_card()
        start = starts[0] + 1
        end = len(lines)
        for index in range(start, len(lines)):
            if lines[index].startswith("## "):
                end = index
                break
        return lines[start:end]

    allowed_section = section("Allowed files")
    allowed: list[str] = []
    for raw in allowed_section:
        line = raw.strip()
        if not line:
            continue
        match = re.fullmatch(r"[-*]\s*`([^`]+)`", line)
        if not match:
            raise _unresolvable_card()
        try:
            allowed.append(_repo_path(match.group(1), "allowed_repository_paths"))
        except ValueError as exc:
            raise _unresolvable_card() from exc
    if not allowed or len(allowed) != len(set(allowed)):
        raise _unresolvable_card()

    forbidden_section = section("Forbidden scope")
    if not any(line.strip() for line in forbidden_section):
        raise _unresolvable_card()
    forbidden_scope = tuple(line.strip() for line in forbidden_section if line.strip())
    forbidden_paths: list[str] = []
    forbidden_patterns: list[str] = []
    for raw in forbidden_section:
        for token in re.findall(r"`([^`]+)`", raw):
            if "/" not in token:
                continue
            if token.endswith("/**") or token.endswith("/*"):
                prefix = token[:-3] if token.endswith("/**") else token[:-2]
                try:
                    _repo_path(prefix, "forbidden_repository_patterns")
                except ValueError as exc:
                    raise _unresolvable_card() from exc
                if "*" in prefix:
                    raise _unresolvable_card()
                if token not in forbidden_patterns:
                    forbidden_patterns.append(token)
                continue
            if "*" in token:
                raise _unresolvable_card()
            try:
                normalized = _repo_path(token, "forbidden_repository_paths")
            except ValueError as exc:
                raise _unresolvable_card() from exc
            if normalized not in forbidden_paths:
                forbidden_paths.append(normalized)

    verifier_section = section("Verification commands")
    commands: list[str] = []
    in_fence = False
    for raw in verifier_section:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("```"):
            language = line[3:].strip().lower()
            if not in_fence:
                if language not in ("", "bash", "sh", "shell", "zsh"):
                    raise _unresolvable_card()
                in_fence = True
            else:
                in_fence = False
            continue
        if in_fence:
            if line.startswith("#"):
                continue
            commands.append(line)
            continue
        match = re.fullmatch(r"[-*]\s*`([^`]+)`", line)
        if match:
            commands.append(match.group(1).strip())
            continue
        raise _unresolvable_card()
    if in_fence or not commands or len(commands) != len(set(commands)):
        raise _unresolvable_card()

    return HistoricalEpbTaskCardProjection(
        tuple(allowed),
        forbidden_scope,
        tuple(commands),
        False,
        tuple(forbidden_paths),
        tuple(forbidden_patterns),
        allow_deletions,
    )


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


class ExternalCandidateAdoptionRequest(BaseModel):
    """Closed, one-shot assertion envelope for physical Candidate adoption."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema: Literal["nexus.external_candidate_adoption_request.v1"] = "nexus.external_candidate_adoption_request.v1"  # pyright: ignore[reportIncompatibleMethodOverride]
    repository: str
    task_id: str
    attempt_id: str
    action_id: str
    idempotency_key: str
    task_card_path: str
    task_card_hash: str
    controller_revision: str
    tool_manifest_hash: str
    full_tool_schema_hash: str
    permission_policy_hash: str
    lifecycle_revision: str
    server_instance_id: str
    target_base_revision: str
    candidate_commit_sha: str
    candidate_tree_sha: str
    candidate_diff_sha256: str
    validation_receipt_sha256: str
    acceptance_receipt_sha256: str
    validation_receipt_b64: str
    acceptance_receipt_b64: str
    allowed_files: tuple[str, ...]
    forbidden_files: tuple[str, ...] = ()
    authorized_deletions: tuple[str, ...] = ()
    verifier_commands: tuple[str, ...]
    protected_contracts: tuple[str, ...] = ()
    action: LifecycleActionEnvelope

    @staticmethod
    def semantic_hash_for(value: Mapping[str, Any]) -> str:
        payload = dict(value)
        payload.pop("action", None)
        return canonical_request_hash(payload)

    def semantic_hash(self) -> str:
        return self.semantic_hash_for(self.model_dump(mode="json", exclude={"action"}))

    @field_validator("task_id", "attempt_id", "action_id")
    @classmethod
    def validate_adoption_ids(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator("idempotency_key")
    @classmethod
    def validate_adoption_idempotency_key(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError("idempotency_key must be non-empty and <=256 characters")
        return value.strip()

    @field_validator("task_card_path")
    @classmethod
    def validate_adoption_card_path(cls, value: str) -> str:
        return _repo_path(value, "task_card_path")

    @field_validator("repository")
    @classmethod
    def validate_adoption_repository(cls, value: str) -> str:
        if value == "LOCAL_TEST":
            return value
        if not isinstance(value, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value,
        ):
            raise ValueError("repository must be a canonical owner/name identity")
        return value

    @field_validator(
        "controller_revision",
        "target_base_revision",
        "candidate_commit_sha",
        "candidate_tree_sha",
    )
    @classmethod
    def validate_adoption_git_sha(cls, value: str, info) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError(f"{info.field_name} must be a lowercase 40-character Git SHA")
        return value

    @field_validator("tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash")
    @classmethod
    def validate_runtime_sha256(cls, value: str, info) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError(f"{info.field_name} must be a lowercase SHA-256 digest")
        return value

    @field_validator("lifecycle_revision", "server_instance_id")
    @classmethod
    def validate_runtime_identity(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator(
        "task_card_hash",
        "candidate_diff_sha256",
        "validation_receipt_sha256",
        "acceptance_receipt_sha256",
    )
    @classmethod
    def validate_adoption_sha256(cls, value: str, info) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError(f"{info.field_name} must be a lowercase SHA-256 digest")
        return value

    @field_validator("validation_receipt_b64", "acceptance_receipt_b64")
    @classmethod
    def validate_adoption_artifact(cls, value: str, info) -> str:
        if not isinstance(value, str) or not value or len(value) > 2 * 1024 * 1024:
            raise ValueError(f"{info.field_name} must be bounded non-empty base64")
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{info.field_name} must be valid base64") from exc
        if not decoded or len(decoded) > 1024 * 1024:
            raise ValueError(f"{info.field_name} decoded artifact must be 1..1048576 bytes")
        return value

    @field_validator("allowed_files", "forbidden_files", "authorized_deletions")
    @classmethod
    def validate_adoption_paths(cls, values: tuple[str, ...], info) -> tuple[str, ...]:
        normalized = tuple(_repo_path(value, info.field_name) for value in values)
        if info.field_name == "allowed_files" and not normalized:
            raise ValueError("allowed_files must be non-empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{info.field_name} must not contain duplicates")
        return normalized

    @field_validator("verifier_commands")
    @classmethod
    def validate_adoption_verifiers(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("verifier_commands must be non-empty")
        return tuple(value.strip() for value in values)

    @model_validator(mode="after")
    def validate_adoption_action(self) -> "ExternalCandidateAdoptionRequest":
        validation_bytes = base64.b64decode(self.validation_receipt_b64, validate=True)
        acceptance_bytes = base64.b64decode(self.acceptance_receipt_b64, validate=True)
        if sha256(validation_bytes).hexdigest() != self.validation_receipt_sha256:
            raise ValueError("validation receipt content hash mismatch")
        if sha256(acceptance_bytes).hexdigest() != self.acceptance_receipt_sha256:
            raise ValueError("acceptance receipt content hash mismatch")
        def overlaps(left: str, right: str) -> bool:
            return left == right or left.startswith(right + "/") or right.startswith(left + "/")
        if any(overlaps(allowed, forbidden) for allowed in self.allowed_files for forbidden in self.forbidden_files):
            raise ValueError("allowed_files and forbidden_files must not overlap")
        if not set(self.authorized_deletions).issubset(set(self.allowed_files)):
            raise ValueError("authorized_deletions must be a subset of allowed_files")
        action = self.action
        if (
            action.action_type is not LifecycleActionType.CANDIDATE_ADOPT_EXTERNAL
            or action.task_id != self.task_id
            or action.attempt_id != self.attempt_id
            or action.action_id != self.action_id
            or action.idempotency_key != self.idempotency_key
            or action.task_card_path != self.task_card_path
            or action.task_card_hash != self.task_card_hash
            or action.contract_kind is not ContractKind.TRACKED_TASK_CARD
            or action.expected_head != self.controller_revision
            or action.permission_profile is not PermissionProfile.CANDIDATE
            or action.approval_scope is not ApprovalScope.ALLOW_ACTION_ONCE
            or action.mutation_domain is not MutationDomain.CANDIDATE_REF
            or action.mutation is not True
            or action.allowed_paths != self.allowed_files
            or action.tool_manifest_hash != self.tool_manifest_hash
        ):
            raise ValueError("external adoption action identity mismatch")
        if not action.verify_request({"adoption_request_hash": self.semantic_hash()}):
            raise ValueError("external adoption request hash mismatch")
        return self


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
