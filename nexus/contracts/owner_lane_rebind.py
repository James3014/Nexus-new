"""Owner-authorized execution-lane rebind contract for protected PR merge preflight."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Literal, Mapping

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
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TASK_PATH = re.compile(r"^tasks/[A-Za-z0-9._/-]+\.md$")
_DIRECT_LANES = {"DIRECT_CANONICAL", "DIRECT_DELEGATED"}


def canonical_lane_rebind_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=lambda value: (
                value.isoformat().replace("+00:00", "Z")
                if isinstance(value, datetime)
                else str(value)
            ),
        ).encode("utf-8")
    ).hexdigest()


class OwnerLaneRebind(BaseModel):
    """Durable Owner decision that supersedes one exact GOVERNED attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema: Literal["nexus.owner_execution_lane_rebind.v1"] = "nexus.owner_execution_lane_rebind.v1"
    repository: StrictStr
    issue_number: StrictInt = Field(gt=0)
    task_id: StrictStr
    attempt_id: StrictStr
    task_card_path: StrictStr
    task_card_sha256: StrictStr
    pull_request_number: StrictInt = Field(gt=0)
    expected_pr_head_sha: StrictStr
    from_lane: Literal["GOVERNED"] = "GOVERNED"
    to_lane: Literal["DIRECT_CANONICAL", "DIRECT_DELEGATED"]
    owner_id: StrictStr
    owner_confirmation: StrictBool
    decided_at: AwareDatetime
    record_hash: StrictStr

    @field_validator("repository", "owner_id")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        if value != value.strip() or not value:
            raise ValueError("NONEMPTY_EXACT_TEXT_REQUIRED")
        return value

    @field_validator("task_id", "attempt_id")
    @classmethod
    def _safe_id(cls, value: str) -> str:
        if not _SAFE_ID.fullmatch(value):
            raise ValueError("SAFE_ID_REQUIRED")
        return value

    @field_validator("task_card_path")
    @classmethod
    def _task_path(cls, value: str) -> str:
        if not _TASK_PATH.fullmatch(value) or ".." in value.split("/"):
            raise ValueError("TASK_CARD_PATH_INVALID")
        return value

    @field_validator("task_card_sha256", "record_hash")
    @classmethod
    def _sha64(cls, value: str) -> str:
        if not _SHA64.fullmatch(value):
            raise ValueError("SHA256_INVALID")
        return value

    @field_validator("expected_pr_head_sha")
    @classmethod
    def _sha40(cls, value: str) -> str:
        if not _SHA40.fullmatch(value):
            raise ValueError("PR_HEAD_SHA_INVALID")
        return value

    @model_validator(mode="after")
    def _validate_owner_and_hash(self) -> "OwnerLaneRebind":
        if self.owner_confirmation is not True:
            raise ValueError("OWNER_CONFIRMATION_REQUIRED")
        payload = self.model_dump(mode="json", exclude={"record_hash"})
        if canonical_lane_rebind_hash(payload) != self.record_hash:
            raise ValueError("RECORD_HASH_INVALID")
        return self

    @classmethod
    def issue(cls, **kwargs: Any) -> "OwnerLaneRebind":
        payload = {"schema": "nexus.owner_execution_lane_rebind.v1", **kwargs}
        payload["record_hash"] = canonical_lane_rebind_hash(payload)
        return cls.model_validate(payload)


class DirectMergeLaneDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema: Literal["nexus.direct_merge_lane_preflight.v1"] = "nexus.direct_merge_lane_preflight.v1"
    allowed: StrictBool
    effective_lane: Literal["DIRECT_CANONICAL", "DIRECT_DELEGATED"] | None
    reason: StrictStr
    lane_rebind_hash: StrictStr | None = None


def _task_card_metadata(task_card_bytes: bytes) -> tuple[str | None, str | None]:
    try:
        text = task_card_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None, None
    task_match = re.search(r"(?m)^task_id:\s*\x60?([^\s\x60]+)\x60?\s*$", text)
    lane_match = re.search(r"(?m)^execution_lane:\s*\x60?([A-Z_]+)\x60?\s*$", text)
    return (
        task_match.group(1) if task_match else None,
        lane_match.group(1) if lane_match else None,
    )


def validate_direct_merge_lane(
    *,
    repository: str,
    issue_number: int,
    task_id: str,
    attempt_id: str,
    task_card_path: str | None,
    task_card_bytes: bytes | None,
    pull_request_number: int,
    current_pr_head_sha: str,
    requested_lane: str,
    expected_owner_id: str,
    lane_rebind: OwnerLaneRebind | Mapping[str, Any] | None = None,
    carrier_author_id: str | None = None,
    carrier_created_at: datetime | None = None,
    merge_observed_at: datetime | None = None,
) -> DirectMergeLaneDecision:
    """Fail closed when a GOVERNED task is sent to a direct merge sink without exact Owner rebind."""

    if requested_lane not in _DIRECT_LANES:
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="DIRECT_LANE_REQUIRED"
        )
    if not _SHA40.fullmatch(current_pr_head_sha):
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="PR_HEAD_SHA_INVALID"
        )

    if task_card_path is None and task_card_bytes is None:
        return DirectMergeLaneDecision(
            allowed=True, effective_lane=requested_lane, reason="GENUINE_DIRECT_ATTEMPT"
        )
    if task_card_path is None or task_card_bytes is None:
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="TASK_CARD_BINDING_INCOMPLETE"
        )

    card_task_id, card_lane = _task_card_metadata(task_card_bytes)
    if card_task_id != task_id or card_lane is None:
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="TASK_CARD_IDENTITY_INVALID"
        )
    if card_lane in _DIRECT_LANES:
        if card_lane != requested_lane:
            return DirectMergeLaneDecision(
                allowed=False, effective_lane=None, reason="DIRECT_LANE_MISMATCH"
            )
        return DirectMergeLaneDecision(
            allowed=True, effective_lane=requested_lane, reason="TASK_CARD_ALREADY_DIRECT"
        )
    if card_lane != "GOVERNED":
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="TASK_CARD_LANE_UNSUPPORTED"
        )
    if lane_rebind is None:
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="OWNER_LANE_REBIND_REQUIRED"
        )

    try:
        record = (
            lane_rebind
            if isinstance(lane_rebind, OwnerLaneRebind)
            else OwnerLaneRebind.model_validate(lane_rebind)
        )
    except Exception:
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="OWNER_LANE_REBIND_INVALID"
        )

    expected_card_hash = hashlib.sha256(task_card_bytes).hexdigest()
    exact = (
        record.repository == repository
        and record.issue_number == issue_number
        and record.task_id == task_id
        and record.attempt_id == attempt_id
        and record.task_card_path == task_card_path
        and record.task_card_sha256 == expected_card_hash
        and record.pull_request_number == pull_request_number
        and record.expected_pr_head_sha == current_pr_head_sha
        and record.from_lane == "GOVERNED"
        and record.to_lane == requested_lane
    )
    if not exact:
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="OWNER_LANE_REBIND_SUBJECT_MISMATCH"
        )
    if not expected_owner_id or record.owner_id != expected_owner_id:
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="OWNER_LANE_REBIND_OWNER_MISMATCH"
        )
    if carrier_author_id != expected_owner_id:
        return DirectMergeLaneDecision(
            allowed=False,
            effective_lane=None,
            reason="OWNER_LANE_REBIND_CARRIER_AUTHOR_MISMATCH",
        )
    if carrier_created_at is None:
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="DURABLE_REBIND_CARRIER_REQUIRED"
        )
    if carrier_created_at.tzinfo is None:
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="CARRIER_TIMEZONE_REQUIRED"
        )
    if carrier_created_at < record.decided_at:
        return DirectMergeLaneDecision(
            allowed=False, effective_lane=None, reason="REBIND_CARRIER_PRECEDES_DECISION"
        )
    if merge_observed_at is not None:
        if merge_observed_at.tzinfo is None:
            return DirectMergeLaneDecision(
                allowed=False, effective_lane=None, reason="MERGE_TIMEZONE_REQUIRED"
            )
        if record.decided_at > merge_observed_at or carrier_created_at > merge_observed_at:
            return DirectMergeLaneDecision(
                allowed=False, effective_lane=None, reason="POST_MERGE_LANE_REBIND_FORBIDDEN"
            )
    return DirectMergeLaneDecision(
        allowed=True,
        effective_lane=requested_lane,
        reason="OWNER_LANE_REBIND_VALID",
        lane_rebind_hash=record.record_hash,
    )
