"""Privacy-bounded, immutable operator outcome receipts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

SCHEMA = "nexus.operator_outcome_receipt.v1"
_HEX64 = set("0123456789abcdef")


def _hash_payload(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def canonical_payload_hash(value: Mapping[str, Any]) -> str:
    """Return the canonical digest for a receipt payload (excluding its digest)."""
    payload = {key: value[key] for key in value if key != "payload_hash"}
    return _hash_payload(payload)


class OperatorOutcomeReceipt(BaseModel):
    """Strict observational receipt; it contains no authority or free text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema: StrictStr = SCHEMA
    task_id: StrictStr = Field(min_length=1, max_length=256)
    attempt_id: StrictStr = Field(min_length=1, max_length=256)
    lifecycle_revision: StrictStr = Field(min_length=1, max_length=256)
    source_revision: StrictStr = Field(min_length=1, max_length=256)
    runtime_identity: StrictStr = Field(min_length=1, max_length=256)
    outcome: StrictStr = Field(min_length=1, max_length=64)
    observed_at: datetime
    idempotency_key: StrictStr = Field(min_length=1, max_length=256)
    payload_hash: StrictStr = Field(min_length=64, max_length=64)
    supersedes_receipt_hash: StrictStr | None = None

    @field_validator("schema")
    @classmethod
    def _schema(cls, value: str) -> str:
        if value != SCHEMA:
            raise ValueError("OPERATOR_OUTCOME_SCHEMA_INVALID")
        return value

    @field_validator("source_revision")
    @classmethod
    def _source_revision(cls, value: str) -> str:
        if len(value) not in {40, 64} or any(ch not in _HEX64 for ch in value.lower()):
            raise ValueError("OPERATOR_OUTCOME_SOURCE_REVISION_NOT_HASH")
        return value

    @field_validator("lifecycle_revision")
    @classmethod
    def _lifecycle_revision(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("OPERATOR_OUTCOME_LIFECYCLE_REVISION_REQUIRED")
        return value

    @field_validator("runtime_identity")
    @classmethod
    def _runtime_identity(cls, value: str) -> str:
        if len(value) != 64 or any(ch not in _HEX64 for ch in value.lower()):
            raise ValueError("OPERATOR_OUTCOME_RUNTIME_IDENTITY_NOT_HASH")
        return value

    @field_validator("payload_hash", "supersedes_receipt_hash")
    @classmethod
    def _hash(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 64 or any(ch not in _HEX64 for ch in value)):
            raise ValueError("OPERATOR_OUTCOME_HASH_INVALID")
        return value

    @field_validator("observed_at")
    @classmethod
    def _timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("OPERATOR_OUTCOME_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value.astimezone(timezone.utc)

    @field_validator("outcome")
    @classmethod
    def _outcome(cls, value: str) -> str:
        if value not in {"SUCCESS", "FAILURE", "BLOCKED", "CANCELLED"}:
            raise ValueError("OPERATOR_OUTCOME_VALUE_INVALID")
        return value

    @model_validator(mode="after")
    def _digest(self) -> "OperatorOutcomeReceipt":
        payload = self.model_dump(mode="json", exclude={"payload_hash"})
        if self.payload_hash != _hash_payload(payload):
            raise ValueError("OPERATOR_OUTCOME_PAYLOAD_HASH_MISMATCH")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def build_operator_outcome_receipt(
    *,
    task_id: str,
    attempt_id: str,
    lifecycle_revision: str,
    source_revision: str,
    runtime_identity: str,
    outcome: str,
    observed_at: datetime | None = None,
    idempotency_key: str,
    supersedes_receipt_hash: str | None = None,
) -> OperatorOutcomeReceipt:
    timestamp = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "task_id": task_id,
        "attempt_id": attempt_id,
        "lifecycle_revision": lifecycle_revision,
        "source_revision": source_revision,
        "runtime_identity": runtime_identity,
        "outcome": outcome,
        "observed_at": timestamp,
        "idempotency_key": idempotency_key,
        "supersedes_receipt_hash": supersedes_receipt_hash,
    }
    payload["payload_hash"] = _hash_payload(payload)
    return OperatorOutcomeReceipt.model_validate(payload)


def validate_operator_outcome_receipt(
    receipt: OperatorOutcomeReceipt | Mapping[str, Any],
    *,
    task_id: str | None = None,
    attempt_id: str | None = None,
    lifecycle_revision: str | None = None,
    source_revision: str | None = None,
    runtime_identity: str | None = None,
    now: datetime | None = None,
    max_age_seconds: float = 300.0,
) -> OperatorOutcomeReceipt:
    result = receipt if isinstance(receipt, OperatorOutcomeReceipt) else OperatorOutcomeReceipt.model_validate(receipt)
    expected = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "lifecycle_revision": lifecycle_revision,
        "source_revision": source_revision,
        "runtime_identity": runtime_identity,
    }
    for field, value in expected.items():
        if value is not None and getattr(result, field) != value:
            raise ValueError(f"OPERATOR_OUTCOME_{field.upper()}_MISMATCH")
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = (reference - result.observed_at).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise ValueError("OPERATOR_OUTCOME_RECEIPT_STALE")
    return result
