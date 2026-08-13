"""Privacy-bounded, immutable operator outcome receipts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

SCHEMA = "nexus.operator_outcome_receipt.v1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_GIT_HASH = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_PROVENANCE_FIELDS = frozenset({
    "observed_outcome",
    "observation_basis",
    "reason_code",
    "observed_at",
    "source_revision",
    "runtime_receipt_hash",
})
_BASIS_PROVENANCE = {
    "OPERATOR_REPORT": "operator",
    "SYSTEM_OBSERVATION": "system",
    "NOT_OBSERVED": "operator",
}
_OUTCOME_REASON_CODES = {
    "SUCCESS": {
        "OPERATOR_REPORT": "OPERATOR_CONFIRMED",
        "SYSTEM_OBSERVATION": "SYSTEM_RECORDED",
    },
    "FAILURE": {
        "OPERATOR_REPORT": "OPERATOR_CONFIRMED",
        "SYSTEM_OBSERVATION": "SYSTEM_RECORDED",
    },
    "PARTIAL": {
        "OPERATOR_REPORT": "REWORK_REQUIRED",
        "SYSTEM_OBSERVATION": "SYSTEM_RECORDED",
    },
    "UNKNOWN": {
        "OPERATOR_REPORT": "OUTCOME_UNKNOWN",
        "SYSTEM_OBSERVATION": "OUTCOME_UNKNOWN",
    },
    "NOT_OBSERVED": {"NOT_OBSERVED": "NOT_PROVIDED"},
}


def _hash_payload(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def canonical_payload_hash(value: Mapping[str, Any]) -> str:
    """Return the canonical receipt ID for a payload excluding its ID."""
    return _hash_payload({key: value[key] for key in value if key != "receipt_id"})


class FieldProvenance(BaseModel):
    """Bounded provenance without operator identity or free text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance: Literal["system", "operator", "derived"]
    source_ref: StrictStr | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"
    )
    source_hash: StrictStr | None = None

    @field_validator("source_hash")
    @classmethod
    def _source_hash(cls, value: str | None) -> str | None:
        if value is not None and not _HEX64.fullmatch(value):
            raise ValueError("OPERATOR_OUTCOME_PROVENANCE_SOURCE_HASH_INVALID")
        return value

    @model_validator(mode="after")
    def _source(self) -> "FieldProvenance":
        if self.source_ref is None and self.source_hash is None:
            raise ValueError("OPERATOR_OUTCOME_PROVENANCE_SOURCE_REQUIRED")
        return self


class OperatorOutcomeReceipt(BaseModel):
    """Strict observational receipt; it contains no authority or free text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema: StrictStr = SCHEMA
    receipt_id: StrictStr = Field(min_length=64, max_length=64)
    idempotency_key: StrictStr = Field(min_length=1, max_length=256)
    task_id: StrictStr = Field(min_length=1, max_length=256)
    attempt_id: StrictStr = Field(min_length=1, max_length=256)
    action_id: StrictStr | None = Field(default=None, min_length=1, max_length=256)
    lifecycle_revision: StrictStr = Field(min_length=1, max_length=256)
    observed_outcome: Literal["SUCCESS", "FAILURE", "PARTIAL", "UNKNOWN", "NOT_OBSERVED"]
    observation_basis: Literal["OPERATOR_REPORT", "SYSTEM_OBSERVATION", "NOT_OBSERVED"]
    reason_code: StrictStr = Field(min_length=1, max_length=64)
    observed_at: datetime
    recorded_at: datetime
    source_revision: StrictStr | None = None
    runtime_receipt_hash: StrictStr | None = None
    supersedes_receipt_id: StrictStr | None = None
    field_provenance: dict[StrictStr, FieldProvenance]

    @field_validator("schema")
    @classmethod
    def _schema(cls, value: str) -> str:
        if value != SCHEMA:
            raise ValueError("OPERATOR_OUTCOME_SCHEMA_INVALID")
        return value

    @field_validator("source_revision")
    @classmethod
    def _source_revision(cls, value: str | None) -> str | None:
        if value is not None and not _GIT_HASH.fullmatch(value):
            raise ValueError("OPERATOR_OUTCOME_SOURCE_REVISION_NOT_HASH")
        return value

    @field_validator("receipt_id", "runtime_receipt_hash", "supersedes_receipt_id")
    @classmethod
    def _hash(cls, value: str | None) -> str | None:
        if value is not None and not _HEX64.fullmatch(value):
            raise ValueError("OPERATOR_OUTCOME_HASH_INVALID")
        return value

    @field_validator("observed_at", "recorded_at")
    @classmethod
    def _timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("OPERATOR_OUTCOME_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value.astimezone(timezone.utc)

    @field_validator("reason_code")
    @classmethod
    def _reason_code(cls, value: str) -> str:
        if not _REASON_CODE.fullmatch(value):
            raise ValueError("OPERATOR_OUTCOME_REASON_CODE_INVALID")
        return value

    @field_validator("field_provenance")
    @classmethod
    def _provenance(cls, value: dict[str, FieldProvenance]) -> dict[str, FieldProvenance]:
        if "observed_outcome" not in value or not set(value).issubset(_PROVENANCE_FIELDS):
            raise ValueError("OPERATOR_OUTCOME_FIELD_PROVENANCE_INVALID")
        return value

    @model_validator(mode="after")
    def _digest(self) -> "OperatorOutcomeReceipt":
        expected_reason = _OUTCOME_REASON_CODES.get(self.observed_outcome, {}).get(
            self.observation_basis
        )
        if expected_reason is None or self.reason_code != expected_reason:
            raise ValueError("OPERATOR_OUTCOME_SEMANTICS_INVALID")
        required_provenance = {
            "observed_outcome",
            "observation_basis",
            "reason_code",
            "observed_at",
        }
        if self.source_revision is not None:
            required_provenance.add("source_revision")
        if self.runtime_receipt_hash is not None:
            required_provenance.add("runtime_receipt_hash")
        if not required_provenance.issubset(self.field_provenance):
            raise ValueError("OPERATOR_OUTCOME_FIELD_PROVENANCE_INCOMPLETE")
        expected_provenance = _BASIS_PROVENANCE[self.observation_basis]
        for field in ("observed_outcome", "observation_basis", "reason_code"):
            if self.field_provenance[field].provenance != expected_provenance:
                raise ValueError("OPERATOR_OUTCOME_SEMANTICS_INVALID")
        if self.recorded_at < self.observed_at:
            raise ValueError("OPERATOR_OUTCOME_RECORDED_BEFORE_OBSERVED")
        payload = self.model_dump(mode="json", exclude={"receipt_id"})
        if self.receipt_id != _hash_payload(payload):
            raise ValueError("OPERATOR_OUTCOME_PAYLOAD_HASH_MISMATCH")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def build_operator_outcome_receipt(
    *,
    task_id: str,
    attempt_id: str,
    lifecycle_revision: str,
    observed_outcome: str,
    observation_basis: str,
    reason_code: str,
    idempotency_key: str,
    field_provenance: Mapping[str, Mapping[str, Any] | FieldProvenance],
    action_id: str | None = None,
    observed_at: datetime | None = None,
    recorded_at: datetime | None = None,
    source_revision: str | None = None,
    runtime_receipt_hash: str | None = None,
    supersedes_receipt_id: str | None = None,
) -> OperatorOutcomeReceipt:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "idempotency_key": idempotency_key,
        "task_id": task_id,
        "attempt_id": attempt_id,
        "action_id": action_id,
        "lifecycle_revision": lifecycle_revision,
        "observed_outcome": observed_outcome,
        "observation_basis": observation_basis,
        "reason_code": reason_code,
        "observed_at": (observed_at or now)
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "recorded_at": (recorded_at or now)
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "source_revision": source_revision,
        "runtime_receipt_hash": runtime_receipt_hash,
        "supersedes_receipt_id": supersedes_receipt_id,
        "field_provenance": {
            key: (
                value
                if isinstance(value, FieldProvenance)
                else FieldProvenance.model_validate(value)
            ).model_dump(mode="json")
            for key, value in field_provenance.items()
        },
    }
    payload["receipt_id"] = _hash_payload(payload)
    return OperatorOutcomeReceipt.model_validate(payload)


def validate_operator_outcome_receipt(
    receipt: OperatorOutcomeReceipt | Mapping[str, Any],
    *,
    task_id: str | None = None,
    attempt_id: str | None = None,
    action_id: str | None = None,
    lifecycle_revision: str | None = None,
    source_revision: str | None = None,
    runtime_receipt_hash: str | None = None,
    now: datetime | None = None,
    max_age_seconds: float = 300.0,
    check_freshness: bool = True,
) -> OperatorOutcomeReceipt:
    result = (
        receipt
        if isinstance(receipt, OperatorOutcomeReceipt)
        else OperatorOutcomeReceipt.model_validate(receipt)
    )
    expected = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "action_id": action_id,
        "lifecycle_revision": lifecycle_revision,
        "source_revision": source_revision,
        "runtime_receipt_hash": runtime_receipt_hash,
    }
    for field, value in expected.items():
        if value is not None and getattr(result, field) != value:
            raise ValueError(f"OPERATOR_OUTCOME_{field.upper()}_MISMATCH")
    if check_freshness:
        reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        observed_age = (reference - result.observed_at).total_seconds()
        recorded_age = (reference - result.recorded_at).total_seconds()
        if (
            observed_age < 0
            or observed_age > max_age_seconds
            or recorded_age < 0
            or recorded_age > max_age_seconds
        ):
            raise ValueError("OPERATOR_OUTCOME_RECEIPT_STALE")
    return result
