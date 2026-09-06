"""Typed contracts for Owner break-glass governance-plane recovery.

This module is deliberately independent of Nexus Gateway, Task Cards, lifecycle
state, Workforce Admission, and the normal standing-grant store. It validates
an externally materialized Owner activation and the immutable evidence carried
through one recovery attempt. It performs no mutation, network, merge, runtime,
or release effect.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ALLOWED_REPOSITORY = "James3014/Nexus-new"
_ALLOWED_ISSUE = 806
_ALLOWED_OWNER = "James3014"


class BreakGlassContractError(ValueError):
    """Fail-closed contract validation error."""


class BreakGlassEffectClass(str, Enum):
    SOURCE_REPAIR = "SOURCE_REPAIR"
    EMERGENCY_INTEGRATION = "EMERGENCY_INTEGRATION"
    RUNTIME_RECOVERY = "RUNTIME_RECOVERY"


class BreakGlassPhase(str, Enum):
    PREPARED = "PREPARED"
    APPLIED = "APPLIED"
    VERIFIED = "VERIFIED"
    CONSUMED = "CONSUMED"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_json_bytes(value: Any) -> bytes:
    """Canonical UTF-8 JSON used for every break-glass content hash."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)


def _safe_relpath(value: str) -> str:
    if value != value.strip() or not value or "\\" in value:
        raise ValueError("PATH_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("PATH_INVALID")
    return path.as_posix()


class BreakGlassActivationPayload(_FrozenModel):
    """Canonical Owner-issued recovery authority for exactly one attempt."""

    schema: Literal["nexus.break_glass_owner_activation.v1"] = (
        "nexus.break_glass_owner_activation.v1"
    )
    repository: Literal[_ALLOWED_REPOSITORY]
    issue: Literal[_ALLOWED_ISSUE]
    owner_login: Literal[_ALLOWED_OWNER]
    recovery_id: StrictStr
    attempt_id: StrictStr
    failure_class: Literal["GOVERNANCE_PLANE_RECOVERY_REQUIRED"]
    failure_evidence_sha256: StrictStr
    effect_class: BreakGlassEffectClass
    base_sha: StrictStr
    base_tree: StrictStr
    allowed_paths: tuple[StrictStr, ...]
    forbidden_paths: tuple[StrictStr, ...]
    verifier_commands: tuple[StrictStr, ...]
    issued_at: datetime
    expires_at: datetime
    claim_ceiling: Literal["break_glass_source_candidate_only"]

    @field_validator("recovery_id", "attempt_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SAFE_ID.fullmatch(value) or value != value.strip():
            raise ValueError("RECOVERY_IDENTITY_INVALID")
        return value

    @field_validator("failure_evidence_sha256")
    @classmethod
    def validate_sha64(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("SHA256_INVALID")
        return value

    @field_validator("base_sha", "base_tree")
    @classmethod
    def validate_sha40(cls, value: str) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError("GIT_SHA_INVALID")
        return value

    @field_validator("allowed_paths", "forbidden_paths")
    @classmethod
    def validate_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("PATH_SET_EMPTY")
        normalized = tuple(_safe_relpath(item) for item in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("PATH_SET_DUPLICATE")
        return normalized

    @field_validator("verifier_commands")
    @classmethod
    def validate_verifiers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not item.strip() or item != item.strip() for item in value):
            raise ValueError("VERIFIER_SET_INVALID")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> "BreakGlassActivationPayload":
        issued = _utc(self.issued_at)
        expires = _utc(self.expires_at)
        if expires <= issued:
            raise ValueError("ACTIVATION_WINDOW_INVALID")
        if self.effect_class is not BreakGlassEffectClass.SOURCE_REPAIR:
            # #806 G1 activates source repair only. Other effect classes require
            # separately issued Owner authority and separate consumers.
            raise ValueError("SOURCE_REPAIR_AUTHORITY_REQUIRED")
        allowed = set(self.allowed_paths)
        forbidden = set(self.forbidden_paths)
        if allowed & forbidden:
            raise ValueError("ALLOWED_FORBIDDEN_OVERLAP")
        return self

    @property
    def payload_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))

    def assert_current(self, *, now: datetime) -> None:
        instant = _utc(now)
        if instant < _utc(self.issued_at):
            raise BreakGlassContractError("ACTIVATION_NOT_YET_VALID")
        if instant >= _utc(self.expires_at):
            raise BreakGlassContractError("ACTIVATION_EXPIRED")

    def assert_paths_authorized(self, changed_paths: tuple[str, ...]) -> None:
        normalized = tuple(_safe_relpath(item) for item in changed_paths)
        allowed = set(self.allowed_paths)
        forbidden = set(self.forbidden_paths)
        if any(path in forbidden for path in normalized):
            raise BreakGlassContractError("FORBIDDEN_PATH_CHANGED")
        if any(path not in allowed for path in normalized):
            raise BreakGlassContractError("OUT_OF_SCOPE_PATH_CHANGED")


class OwnerActivationEnvelope(_FrozenModel):
    """Externally fetched GitHub comment evidence carrying the Owner payload.

    The fetcher/controller is responsible for obtaining the exact public GitHub
    comment. This model refuses caller booleans and binds the immutable comment
    identity, author, canonical payload hash and exact recovery payload.
    """

    schema: Literal["nexus.break_glass_owner_comment_envelope.v1"] = (
        "nexus.break_glass_owner_comment_envelope.v1"
    )
    repository: Literal[_ALLOWED_REPOSITORY]
    issue: Literal[_ALLOWED_ISSUE]
    comment_id: int
    comment_url: StrictStr
    author_login: Literal[_ALLOWED_OWNER]
    comment_body_sha256: StrictStr
    payload_sha256: StrictStr
    payload: BreakGlassActivationPayload

    @field_validator("comment_id")
    @classmethod
    def validate_comment_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("COMMENT_ID_INVALID")
        return value

    @field_validator("comment_body_sha256", "payload_sha256")
    @classmethod
    def validate_payload_hash_format(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("PAYLOAD_HASH_INVALID")
        return value

    @field_validator("comment_url")
    @classmethod
    def validate_comment_url(cls, value: str) -> str:
        prefix = "https://github.com/James3014/Nexus-new/issues/806#issuecomment-"
        if not value.startswith(prefix) or not value[len(prefix) :].isdigit():
            raise ValueError("COMMENT_URL_INVALID")
        return value

    @model_validator(mode="after")
    def validate_envelope(self) -> "OwnerActivationEnvelope":
        if self.payload.owner_login != self.author_login:
            raise ValueError("OWNER_IDENTITY_MISMATCH")
        if self.payload.repository != self.repository or self.payload.issue != self.issue:
            raise ValueError("OWNER_PROVENANCE_SCOPE_MISMATCH")
        if self.payload.payload_sha256 != self.payload_sha256:
            raise ValueError("PAYLOAD_HASH_MISMATCH")
        expected_suffix = str(self.comment_id)
        if not self.comment_url.endswith(expected_suffix):
            raise ValueError("COMMENT_ID_URL_MISMATCH")
        return self


def owner_envelope_from_github_comment(comment: Mapping[str, Any]) -> OwnerActivationEnvelope:
    """Parse and validate one raw GitHub Issue-comment API object.

    This function is pure: the operator CLI owns the fixed HTTPS fetch. The raw
    response must itself identify the immutable #806 comment and Owner, and its
    body must contain exactly one canonical activation JSON block plus the
    matching declared SHA-256 marker.
    """

    try:
        comment_id = int(comment["id"])
        comment_url = str(comment["html_url"])
        issue_url = str(comment["issue_url"])
        author_login = str(comment["user"]["login"])
        body = str(comment["body"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BreakGlassContractError("GITHUB_COMMENT_MALFORMED") from exc

    if issue_url != "https://api.github.com/repos/James3014/Nexus-new/issues/806":
        raise BreakGlassContractError("GITHUB_COMMENT_ISSUE_MISMATCH")
    if author_login != _ALLOWED_OWNER:
        raise BreakGlassContractError("GITHUB_COMMENT_OWNER_MISMATCH")

    hash_matches = re.findall(r"Canonical activation payload SHA-256:\s*`([0-9a-f]{64})`", body)
    json_matches = re.findall(r"```json\s*\n(.*?)\n```", body, flags=re.DOTALL)
    if len(hash_matches) != 1 or len(json_matches) != 1:
        raise BreakGlassContractError("GITHUB_COMMENT_ACTIVATION_BLOCK_INVALID")
    try:
        payload_data = json.loads(json_matches[0])
    except json.JSONDecodeError as exc:
        raise BreakGlassContractError("GITHUB_COMMENT_ACTIVATION_JSON_INVALID") from exc
    if not isinstance(payload_data, dict):
        raise BreakGlassContractError("GITHUB_COMMENT_ACTIVATION_JSON_INVALID")
    declared_hash = hash_matches[0]
    if canonical_sha256(payload_data) != declared_hash:
        raise BreakGlassContractError("GITHUB_COMMENT_PAYLOAD_HASH_MISMATCH")

    return OwnerActivationEnvelope.model_validate({
        "repository": _ALLOWED_REPOSITORY,
        "issue": _ALLOWED_ISSUE,
        "comment_id": comment_id,
        "comment_url": comment_url,
        "author_login": author_login,
        "comment_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "payload_sha256": declared_hash,
        "payload": payload_data,
    })


class BreakGlassCheckEvidence(_FrozenModel):
    schema: Literal["nexus.break_glass_check_evidence.v1"] = "nexus.break_glass_check_evidence.v1"
    name: StrictStr
    run_id: int
    head_sha: StrictStr
    conclusion: Literal["success"]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("CHECK_NAME_INVALID")
        return value

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("CHECK_RUN_ID_INVALID")
        return value

    @field_validator("head_sha")
    @classmethod
    def validate_head_sha(cls, value: str) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError("GIT_SHA_INVALID")
        return value


class BreakGlassOwnerVerificationPayload(_FrozenModel):
    schema: Literal["nexus.break_glass_owner_verification.v1"] = (
        "nexus.break_glass_owner_verification.v1"
    )
    repository: Literal[_ALLOWED_REPOSITORY]
    issue: Literal[_ALLOWED_ISSUE]
    owner_login: Literal[_ALLOWED_OWNER]
    recovery_id: StrictStr
    source_attempt_id: StrictStr
    source_activation_payload_sha256: StrictStr
    verified_commit_sha: StrictStr
    verified_tree_sha: StrictStr
    verified_diff_sha256: StrictStr
    verifier_id: StrictStr
    checks: tuple[BreakGlassCheckEvidence, ...]
    issued_at: datetime
    expires_at: datetime
    claim_ceiling: Literal["source_repair_verification_only"]

    @field_validator("recovery_id", "source_attempt_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SAFE_ID.fullmatch(value) or value != value.strip():
            raise ValueError("RECOVERY_IDENTITY_INVALID")
        return value

    @field_validator("source_activation_payload_sha256", "verified_diff_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("SHA256_INVALID")
        return value

    @field_validator("verified_commit_sha", "verified_tree_sha")
    @classmethod
    def validate_git_sha(cls, value: str) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError("GIT_SHA_INVALID")
        return value

    @field_validator("verifier_id")
    @classmethod
    def validate_verifier(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("VERIFIER_ID_INVALID")
        return value

    @field_validator("checks")
    @classmethod
    def validate_checks(
        cls, value: tuple[BreakGlassCheckEvidence, ...]
    ) -> tuple[BreakGlassCheckEvidence, ...]:
        if not value:
            raise ValueError("CHECK_SET_EMPTY")
        names = [item.name for item in value]
        run_ids = [item.run_id for item in value]
        if len(set(names)) != len(names) or len(set(run_ids)) != len(run_ids):
            raise ValueError("CHECK_SET_DUPLICATE")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> "BreakGlassOwnerVerificationPayload":
        if _utc(self.expires_at) <= _utc(self.issued_at):
            raise ValueError("VERIFICATION_WINDOW_INVALID")
        if any(item.head_sha != self.verified_commit_sha for item in self.checks):
            raise ValueError("CHECK_SUBJECT_MISMATCH")
        return self

    @property
    def payload_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))

    def assert_current(self, *, now: datetime) -> None:
        instant = _utc(now)
        if instant < _utc(self.issued_at):
            raise BreakGlassContractError("VERIFICATION_NOT_YET_VALID")
        if instant >= _utc(self.expires_at):
            raise BreakGlassContractError("VERIFICATION_EXPIRED")


class BreakGlassOwnerIntegrationPayload(_FrozenModel):
    schema: Literal["nexus.break_glass_owner_integration.v1"] = (
        "nexus.break_glass_owner_integration.v1"
    )
    repository: Literal[_ALLOWED_REPOSITORY]
    issue: Literal[_ALLOWED_ISSUE]
    owner_login: Literal[_ALLOWED_OWNER]
    recovery_id: StrictStr
    integration_attempt_id: StrictStr
    source_attempt_id: StrictStr
    source_activation_payload_sha256: StrictStr
    verification_payload_sha256: StrictStr
    effect_class: Literal["EMERGENCY_INTEGRATION"]
    pr_number: int
    accepted_head_sha: StrictStr
    accepted_tree_sha: StrictStr
    accepted_diff_sha256: StrictStr
    expected_base_sha: StrictStr
    merge_method: Literal["merge"]
    checks: tuple[BreakGlassCheckEvidence, ...]
    issued_at: datetime
    expires_at: datetime
    claim_ceiling: Literal["emergency_integration_only"]

    @field_validator("recovery_id", "integration_attempt_id", "source_attempt_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SAFE_ID.fullmatch(value) or value != value.strip():
            raise ValueError("RECOVERY_IDENTITY_INVALID")
        return value

    @field_validator(
        "source_activation_payload_sha256",
        "verification_payload_sha256",
        "accepted_diff_sha256",
    )
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("SHA256_INVALID")
        return value

    @field_validator("accepted_head_sha", "accepted_tree_sha", "expected_base_sha")
    @classmethod
    def validate_git_sha(cls, value: str) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError("GIT_SHA_INVALID")
        return value

    @field_validator("pr_number")
    @classmethod
    def validate_pr_number(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("PR_NUMBER_INVALID")
        return value

    @field_validator("checks")
    @classmethod
    def validate_checks(
        cls, value: tuple[BreakGlassCheckEvidence, ...]
    ) -> tuple[BreakGlassCheckEvidence, ...]:
        if not value:
            raise ValueError("CHECK_SET_EMPTY")
        names = [item.name for item in value]
        run_ids = [item.run_id for item in value]
        if len(set(names)) != len(names) or len(set(run_ids)) != len(run_ids):
            raise ValueError("CHECK_SET_DUPLICATE")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> "BreakGlassOwnerIntegrationPayload":
        if _utc(self.expires_at) <= _utc(self.issued_at):
            raise ValueError("INTEGRATION_WINDOW_INVALID")
        if any(item.head_sha != self.accepted_head_sha for item in self.checks):
            raise ValueError("CHECK_SUBJECT_MISMATCH")
        return self

    @property
    def payload_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))

    def assert_current(self, *, now: datetime) -> None:
        instant = _utc(now)
        if instant < _utc(self.issued_at):
            raise BreakGlassContractError("INTEGRATION_NOT_YET_VALID")
        if instant >= _utc(self.expires_at):
            raise BreakGlassContractError("INTEGRATION_EXPIRED")


class BreakGlassOwnerCanaryPayload(_FrozenModel):
    schema: Literal["nexus.break_glass_owner_canary.v1"] = (
        "nexus.break_glass_owner_canary.v1"
    )
    repository: Literal[_ALLOWED_REPOSITORY]
    issue: Literal[_ALLOWED_ISSUE]
    owner_login: Literal[_ALLOWED_OWNER]
    recovery_id: StrictStr
    source_attempt_id: StrictStr
    source_activation_payload_sha256: StrictStr
    integrated_main_sha: StrictStr
    source_runtime_identity_sha256: StrictStr
    action_binding_sha256: StrictStr
    normal_authority_readback_sha256: StrictStr
    governance_operation_receipt_sha256: StrictStr
    verifier_receipt_sha256: StrictStr
    observed_at: datetime
    normal_governance_restored: Literal[True]
    issued_at: datetime
    claim_ceiling: Literal["post_recovery_canary_only"]

    @field_validator("recovery_id", "source_attempt_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SAFE_ID.fullmatch(value) or value != value.strip():
            raise ValueError("RECOVERY_IDENTITY_INVALID")
        return value

    @field_validator(
        "source_activation_payload_sha256",
        "source_runtime_identity_sha256",
        "action_binding_sha256",
        "normal_authority_readback_sha256",
        "governance_operation_receipt_sha256",
        "verifier_receipt_sha256",
    )
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("SHA256_INVALID")
        return value

    @field_validator("integrated_main_sha")
    @classmethod
    def validate_main_sha(cls, value: str) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError("GIT_SHA_INVALID")
        return value

    @field_validator("observed_at", "issued_at")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("TIMEZONE_REQUIRED")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> "BreakGlassOwnerCanaryPayload":
        if _utc(self.issued_at) < _utc(self.observed_at):
            raise ValueError("CANARY_ISSUED_BEFORE_OBSERVED")
        return self

    @property
    def payload_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))


class _OwnerEvidenceEnvelope(_FrozenModel):
    repository: Literal[_ALLOWED_REPOSITORY]
    issue: Literal[_ALLOWED_ISSUE]
    comment_id: int
    comment_url: StrictStr
    author_login: Literal[_ALLOWED_OWNER]
    comment_body_sha256: StrictStr
    payload_sha256: StrictStr

    @field_validator("comment_id")
    @classmethod
    def validate_comment_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("COMMENT_ID_INVALID")
        return value

    @field_validator("comment_body_sha256", "payload_sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("PAYLOAD_HASH_INVALID")
        return value

    @field_validator("comment_url")
    @classmethod
    def validate_comment_url(cls, value: str) -> str:
        prefix = "https://github.com/James3014/Nexus-new/issues/806#issuecomment-"
        if not value.startswith(prefix) or not value[len(prefix) :].isdigit():
            raise ValueError("COMMENT_URL_INVALID")
        return value


class OwnerVerificationEnvelope(_OwnerEvidenceEnvelope):
    schema: Literal["nexus.break_glass_owner_verification_envelope.v1"] = (
        "nexus.break_glass_owner_verification_envelope.v1"
    )
    payload: BreakGlassOwnerVerificationPayload

    @model_validator(mode="after")
    def validate_envelope(self) -> "OwnerVerificationEnvelope":
        if self.payload.owner_login != self.author_login:
            raise ValueError("OWNER_IDENTITY_MISMATCH")
        if self.payload.repository != self.repository or self.payload.issue != self.issue:
            raise ValueError("OWNER_PROVENANCE_SCOPE_MISMATCH")
        if self.payload.payload_sha256 != self.payload_sha256:
            raise ValueError("PAYLOAD_HASH_MISMATCH")
        if not self.comment_url.endswith(str(self.comment_id)):
            raise ValueError("COMMENT_ID_URL_MISMATCH")
        return self


class OwnerIntegrationEnvelope(_OwnerEvidenceEnvelope):
    schema: Literal["nexus.break_glass_owner_integration_envelope.v1"] = (
        "nexus.break_glass_owner_integration_envelope.v1"
    )
    payload: BreakGlassOwnerIntegrationPayload

    @model_validator(mode="after")
    def validate_envelope(self) -> "OwnerIntegrationEnvelope":
        if self.payload.owner_login != self.author_login:
            raise ValueError("OWNER_IDENTITY_MISMATCH")
        if self.payload.repository != self.repository or self.payload.issue != self.issue:
            raise ValueError("OWNER_PROVENANCE_SCOPE_MISMATCH")
        if self.payload.payload_sha256 != self.payload_sha256:
            raise ValueError("PAYLOAD_HASH_MISMATCH")
        if not self.comment_url.endswith(str(self.comment_id)):
            raise ValueError("COMMENT_ID_URL_MISMATCH")
        return self


class OwnerCanaryEnvelope(_OwnerEvidenceEnvelope):
    schema: Literal["nexus.break_glass_owner_canary_envelope.v1"] = (
        "nexus.break_glass_owner_canary_envelope.v1"
    )
    payload: BreakGlassOwnerCanaryPayload

    @model_validator(mode="after")
    def validate_envelope(self) -> "OwnerCanaryEnvelope":
        if self.payload.owner_login != self.author_login:
            raise ValueError("OWNER_IDENTITY_MISMATCH")
        if self.payload.repository != self.repository or self.payload.issue != self.issue:
            raise ValueError("OWNER_PROVENANCE_SCOPE_MISMATCH")
        if self.payload.payload_sha256 != self.payload_sha256:
            raise ValueError("PAYLOAD_HASH_MISMATCH")
        if not self.comment_url.endswith(str(self.comment_id)):
            raise ValueError("COMMENT_ID_URL_MISMATCH")
        return self


class BreakGlassOwnerTerminalPayload(_FrozenModel):
    schema: Literal["nexus.break_glass_owner_terminal.v1"] = "nexus.break_glass_owner_terminal.v1"
    repository: Literal[_ALLOWED_REPOSITORY]
    issue: Literal[_ALLOWED_ISSUE]
    owner_login: Literal[_ALLOWED_OWNER]
    recovery_id: StrictStr
    source_attempt_id: StrictStr
    source_activation_payload_sha256: StrictStr
    terminal_state: Literal["CONSUMED", "REVOKED"]
    reason: StrictStr
    integrated_main_sha: StrictStr | None = None
    canary_evidence_sha256: StrictStr | None = None
    integration_payload_sha256: StrictStr | None = None
    issued_at: datetime

    @field_validator("recovery_id", "source_attempt_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SAFE_ID.fullmatch(value) or value != value.strip():
            raise ValueError("RECOVERY_IDENTITY_INVALID")
        return value

    @field_validator("source_activation_payload_sha256")
    @classmethod
    def validate_source_hash(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("SHA256_INVALID")
        return value

    @field_validator("canary_evidence_sha256", "integration_payload_sha256")
    @classmethod
    def validate_optional_sha256(cls, value: str | None) -> str | None:
        if value is not None and not _SHA64.fullmatch(value):
            raise ValueError("SHA256_INVALID")
        return value

    @field_validator("integrated_main_sha")
    @classmethod
    def validate_optional_git_sha(cls, value: str | None) -> str | None:
        if value is not None and not _SHA40.fullmatch(value):
            raise ValueError("GIT_SHA_INVALID")
        return value

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("TERMINAL_REASON_INVALID")
        return value

    @field_validator("issued_at")
    @classmethod
    def validate_issued_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("TIMEZONE_REQUIRED")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> "BreakGlassOwnerTerminalPayload":
        if self.terminal_state == "CONSUMED" and (
            self.integrated_main_sha is None or self.canary_evidence_sha256 is None
        ):
            raise ValueError("CONSUMED_TERMINAL_EVIDENCE_REQUIRED")
        return self

    @property
    def payload_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))


class OwnerTerminalEnvelope(_OwnerEvidenceEnvelope):
    schema: Literal["nexus.break_glass_owner_terminal_envelope.v1"] = (
        "nexus.break_glass_owner_terminal_envelope.v1"
    )
    payload: BreakGlassOwnerTerminalPayload

    @model_validator(mode="after")
    def validate_envelope(self) -> "OwnerTerminalEnvelope":
        if self.payload.owner_login != self.author_login:
            raise ValueError("OWNER_IDENTITY_MISMATCH")
        if self.payload.repository != self.repository or self.payload.issue != self.issue:
            raise ValueError("OWNER_PROVENANCE_SCOPE_MISMATCH")
        if self.payload.payload_sha256 != self.payload_sha256:
            raise ValueError("PAYLOAD_HASH_MISMATCH")
        if not self.comment_url.endswith(str(self.comment_id)):
            raise ValueError("COMMENT_ID_URL_MISMATCH")
        return self


def _owner_evidence_from_github_comment(
    comment: Mapping[str, Any],
    *,
    marker: str,
    payload_model: type[BreakGlassOwnerVerificationPayload]
    | type[BreakGlassOwnerIntegrationPayload]
    | type[BreakGlassOwnerCanaryPayload]
    | type[BreakGlassOwnerTerminalPayload],
    envelope_model: type[OwnerVerificationEnvelope]
    | type[OwnerIntegrationEnvelope]
    | type[OwnerCanaryEnvelope]
    | type[OwnerTerminalEnvelope],
) -> (
    OwnerVerificationEnvelope
    | OwnerIntegrationEnvelope
    | OwnerCanaryEnvelope
    | OwnerTerminalEnvelope
):
    try:
        comment_id = int(comment["id"])
        comment_url = str(comment["html_url"])
        issue_url = str(comment["issue_url"])
        author_login = str(comment["user"]["login"])
        body = str(comment["body"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BreakGlassContractError("GITHUB_COMMENT_MALFORMED") from exc
    if issue_url != "https://api.github.com/repos/James3014/Nexus-new/issues/806":
        raise BreakGlassContractError("GITHUB_COMMENT_ISSUE_MISMATCH")
    if author_login != _ALLOWED_OWNER:
        raise BreakGlassContractError("GITHUB_COMMENT_OWNER_MISMATCH")
    hash_matches = re.findall(rf"{re.escape(marker)}:\s*`([0-9a-f]{{64}})`", body)
    json_matches = re.findall(r"```json\s*\n(.*?)\n```", body, flags=re.DOTALL)
    if len(hash_matches) != 1 or len(json_matches) != 1:
        raise BreakGlassContractError("GITHUB_COMMENT_EVIDENCE_BLOCK_INVALID")
    try:
        payload_data = json.loads(json_matches[0])
    except json.JSONDecodeError as exc:
        raise BreakGlassContractError("GITHUB_COMMENT_EVIDENCE_JSON_INVALID") from exc
    if not isinstance(payload_data, dict):
        raise BreakGlassContractError("GITHUB_COMMENT_EVIDENCE_JSON_INVALID")
    declared_hash = hash_matches[0]
    if canonical_sha256(payload_data) != declared_hash:
        raise BreakGlassContractError("GITHUB_COMMENT_PAYLOAD_HASH_MISMATCH")
    payload = payload_model.model_validate(payload_data)
    return envelope_model.model_validate({
        "repository": _ALLOWED_REPOSITORY,
        "issue": _ALLOWED_ISSUE,
        "comment_id": comment_id,
        "comment_url": comment_url,
        "author_login": author_login,
        "comment_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "payload_sha256": declared_hash,
        "payload": payload,
    })


def owner_verification_from_github_comment(
    comment: Mapping[str, Any],
) -> OwnerVerificationEnvelope:
    envelope = _owner_evidence_from_github_comment(
        comment,
        marker="Canonical verification payload SHA-256",
        payload_model=BreakGlassOwnerVerificationPayload,
        envelope_model=OwnerVerificationEnvelope,
    )
    if not isinstance(envelope, OwnerVerificationEnvelope):
        raise BreakGlassContractError("VERIFICATION_ENVELOPE_INVALID")
    return envelope


def owner_integration_from_github_comment(
    comment: Mapping[str, Any],
) -> OwnerIntegrationEnvelope:
    envelope = _owner_evidence_from_github_comment(
        comment,
        marker="Canonical integration payload SHA-256",
        payload_model=BreakGlassOwnerIntegrationPayload,
        envelope_model=OwnerIntegrationEnvelope,
    )
    if not isinstance(envelope, OwnerIntegrationEnvelope):
        raise BreakGlassContractError("INTEGRATION_ENVELOPE_INVALID")
    return envelope


def owner_canary_from_github_comment(
    comment: Mapping[str, Any],
) -> OwnerCanaryEnvelope:
    envelope = _owner_evidence_from_github_comment(
        comment,
        marker="Canonical canary payload SHA-256",
        payload_model=BreakGlassOwnerCanaryPayload,
        envelope_model=OwnerCanaryEnvelope,
    )
    if not isinstance(envelope, OwnerCanaryEnvelope):
        raise BreakGlassContractError("CANARY_ENVELOPE_INVALID")
    return envelope


def owner_terminal_from_github_comment(
    comment: Mapping[str, Any],
) -> OwnerTerminalEnvelope:
    envelope = _owner_evidence_from_github_comment(
        comment,
        marker="Canonical terminal payload SHA-256",
        payload_model=BreakGlassOwnerTerminalPayload,
        envelope_model=OwnerTerminalEnvelope,
    )
    if not isinstance(envelope, OwnerTerminalEnvelope):
        raise BreakGlassContractError("TERMINAL_ENVELOPE_INVALID")
    return envelope


def owner_terminals_from_github_comments(
    comments: tuple[Mapping[str, Any], ...],
) -> tuple[OwnerTerminalEnvelope, ...]:
    terminals: list[OwnerTerminalEnvelope] = []
    marker = "Canonical terminal payload SHA-256:"
    schema = "nexus.break_glass_owner_terminal.v1"
    for comment in comments:
        user = comment.get("user")
        body = comment.get("body")
        if not isinstance(user, Mapping) or user.get("login") != _ALLOWED_OWNER:
            continue
        if not isinstance(body, str) or marker not in body or schema not in body:
            continue
        terminals.append(owner_terminal_from_github_comment(comment))
    return tuple(terminals)


def integration_readback_from_github(
    integration: BreakGlassOwnerIntegrationPayload,
    pull_request: Mapping[str, Any],
    main_branch: Mapping[str, Any],
) -> tuple[str, str, int]:
    try:
        pr_number = int(pull_request["number"])
        state = str(pull_request["state"])
        merged = pull_request["merged"] is True
        merge_commit_sha = str(pull_request["merge_commit_sha"])
        head_sha = str(pull_request["head"]["sha"])
        base_ref = str(pull_request["base"]["ref"])
        observed_main_sha = str(main_branch["commit"]["sha"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BreakGlassContractError("GITHUB_INTEGRATION_READBACK_MALFORMED") from exc
    if pr_number != integration.pr_number:
        raise BreakGlassContractError("INTEGRATION_PR_MISMATCH")
    if state != "closed" or not merged:
        raise BreakGlassContractError("GITHUB_PR_NOT_MERGED")
    if base_ref != "main":
        raise BreakGlassContractError("INTEGRATION_BASE_REF_MISMATCH")
    if head_sha != integration.accepted_head_sha:
        raise BreakGlassContractError("INTEGRATION_HEAD_READBACK_MISMATCH")
    if not _SHA40.fullmatch(merge_commit_sha) or not _SHA40.fullmatch(observed_main_sha):
        raise BreakGlassContractError("GIT_SHA_INVALID")
    if merge_commit_sha != observed_main_sha:
        raise BreakGlassContractError("INTEGRATION_READBACK_MISMATCH")
    return merge_commit_sha, observed_main_sha, pr_number


class BreakGlassGovernanceCanaryEvidence(_FrozenModel):
    schema: Literal["nexus.break_glass_governance_canary.v1"] = (
        "nexus.break_glass_governance_canary.v1"
    )
    recovery_id: StrictStr
    source_attempt_id: StrictStr
    integrated_main_sha: StrictStr
    source_runtime_identity_sha256: StrictStr
    action_binding_sha256: StrictStr
    normal_authority_readback_sha256: StrictStr
    governance_operation_receipt_sha256: StrictStr
    verifier_receipt_sha256: StrictStr
    observed_at: datetime
    normal_governance_restored: Literal[True]

    @field_validator("recovery_id", "source_attempt_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SAFE_ID.fullmatch(value) or value != value.strip():
            raise ValueError("RECOVERY_IDENTITY_INVALID")
        return value

    @field_validator("integrated_main_sha")
    @classmethod
    def validate_main_sha(cls, value: str) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError("GIT_SHA_INVALID")
        return value

    @field_validator(
        "source_runtime_identity_sha256",
        "action_binding_sha256",
        "normal_authority_readback_sha256",
        "governance_operation_receipt_sha256",
        "verifier_receipt_sha256",
    )
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("SHA256_INVALID")
        return value

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _utc(value)

    @property
    def evidence_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))


class BreakGlassAppliedEvidence(_FrozenModel):
    schema: Literal["nexus.break_glass_applied_evidence.v1"] = (
        "nexus.break_glass_applied_evidence.v1"
    )
    repair_commit_sha: StrictStr
    repair_tree_sha: StrictStr
    full_diff_sha256: StrictStr
    changed_paths: tuple[StrictStr, ...]
    implementer_id: StrictStr

    @field_validator("repair_commit_sha", "repair_tree_sha")
    @classmethod
    def validate_git_sha(cls, value: str) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError("GIT_SHA_INVALID")
        return value

    @field_validator("full_diff_sha256")
    @classmethod
    def validate_diff_hash(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("DIFF_HASH_INVALID")
        return value

    @field_validator("changed_paths")
    @classmethod
    def validate_changed_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("CHANGED_PATHS_EMPTY")
        normalized = tuple(_safe_relpath(item) for item in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("CHANGED_PATHS_DUPLICATE")
        return normalized

    @field_validator("implementer_id")
    @classmethod
    def validate_implementer(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("IMPLEMENTER_ID_INVALID")
        return value

    @property
    def evidence_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))


class BreakGlassVerificationEvidence(_FrozenModel):
    schema: Literal["nexus.break_glass_verification_evidence.v1"] = (
        "nexus.break_glass_verification_evidence.v1"
    )
    verifier_id: StrictStr
    verifier_evidence_sha256: StrictStr
    verified_commit_sha: StrictStr
    verified_tree_sha: StrictStr
    verified_diff_sha256: StrictStr

    @field_validator("verifier_evidence_sha256", "verified_diff_sha256")
    @classmethod
    def validate_sha64(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("SHA256_INVALID")
        return value

    @field_validator("verified_commit_sha", "verified_tree_sha")
    @classmethod
    def validate_sha40(cls, value: str) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError("GIT_SHA_INVALID")
        return value

    @field_validator("verifier_id")
    @classmethod
    def validate_verifier(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("VERIFIER_ID_INVALID")
        return value

    @property
    def evidence_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))
