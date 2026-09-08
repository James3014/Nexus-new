"""Closed source-owned contracts for the writer transition boundary."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

SHA64 = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
_ROLES = frozenset({"task_state", "runtime_receipt", "event_log", "effect_journal"})
_MAX_TEXT = 512


class TransitionValidationError(ValueError):
    pass


class Operation(str, Enum):
    PREFLIGHT = "PREFLIGHT"
    APPLY = "APPLY"
    RECONCILE = "RECONCILE"


class ReceiptState(str, Enum):
    PREFLIGHT_READY = "PREFLIGHT_READY"
    DENIED = "DENIED"
    INTENT_RECORDED = "INTENT_RECORDED"
    GENERATION_ADVANCED = "GENERATION_ADVANCED"
    PREPARED = "PREPARED"
    COMMITTED = "COMMITTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED = "RECONCILED"


def _text(value: Any, name: str, *, max_len: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise TransitionValidationError(f"{name}_INVALID")
    if any(ord(char) < 0x20 for char in value):
        raise TransitionValidationError(f"{name}_INVALID")
    return value


def _sha(value: Any, name: str, *, git: bool = False) -> str:
    pattern = SHA40 if git else SHA64
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise TransitionValidationError(f"{name}_INVALID")
    return value


def _relative_path(value: Any, name: str) -> str:
    value = _text(value, name)
    path = value.replace("\\", "/")
    parts = path.split("/")
    if path.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise TransitionValidationError(f"{name}_INVALID")
    return path


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class TransitionSelection:
    entry_id: str
    role: str
    relative_path: str
    expected_sha256: str
    size: int

    def __post_init__(self) -> None:
        _text(self.entry_id, "entry_id")
        _text(self.role, "role")
        if self.role not in _ROLES:
            raise TransitionValidationError("role_INVALID")
        _relative_path(self.relative_path, "relative_path")
        _sha(self.expected_sha256, "expected_sha256")
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise TransitionValidationError("size_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "role": self.role,
            "relative_path": self.relative_path,
            "expected_sha256": self.expected_sha256,
            "size": self.size,
        }


REQUEST_FIELDS = frozenset(
    "schema operation request_id transaction_id idempotency_key task_id card_path card_sha256 expected_source_head expected_source_tree accepted_source_receipt root_id expected_root_identity expected_owner_id expected_generation expected_writer_id expected_manifest_sha256 next_generation next_writer_id selections authority_receipt_id authority_receipt_hash drain_receipt_id drain_receipt_hash snapshot_receipt_id snapshot_receipt_hash rollback_receipt_id rollback_receipt_hash loaded_writer_plan_id loaded_writer_plan_hash".split()
)
_OPTIONAL_REQUEST_FIELDS = frozenset({"accepted_source_receipt_hash"})


@dataclass(frozen=True, slots=True)
class WriterTransitionRequest:
    operation: Operation
    request_id: str
    transaction_id: str
    idempotency_key: str
    task_id: str
    card_path: str
    card_sha256: str
    expected_source_head: str
    expected_source_tree: str
    accepted_source_receipt: str
    root_id: str
    expected_root_identity: str
    expected_owner_id: str
    expected_generation: int | None
    expected_writer_id: str
    expected_manifest_sha256: str | None
    next_generation: int
    next_writer_id: str
    selections: tuple[TransitionSelection, ...]
    authority_receipt_id: str
    authority_receipt_hash: str
    drain_receipt_id: str
    drain_receipt_hash: str
    snapshot_receipt_id: str
    snapshot_receipt_hash: str
    rollback_receipt_id: str
    rollback_receipt_hash: str
    loaded_writer_plan_id: str
    loaded_writer_plan_hash: str
    schema: str = "nexus.state_owner_transition_request.v1"
    accepted_source_receipt_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema != "nexus.state_owner_transition_request.v1":
            raise TransitionValidationError("SCHEMA_INVALID")
        if not isinstance(self.operation, Operation):
            raise TransitionValidationError("operation_INVALID")
        for name in (
            "request_id",
            "transaction_id",
            "idempotency_key",
            "task_id",
            "root_id",
            "expected_owner_id",
            "expected_writer_id",
            "next_writer_id",
            "authority_receipt_id",
            "drain_receipt_id",
            "snapshot_receipt_id",
            "rollback_receipt_id",
            "loaded_writer_plan_id",
        ):
            _text(getattr(self, name), name)
        _relative_path(self.card_path, "card_path")
        _text(self.accepted_source_receipt, "accepted_source_receipt")
        if self.accepted_source_receipt_hash:
            _sha(self.accepted_source_receipt_hash, "accepted_source_receipt_hash")
        _sha(self.card_sha256, "card_sha256")
        _sha(self.expected_root_identity, "expected_root_identity")
        _sha(self.expected_source_head, "expected_source_head", git=True)
        _sha(self.expected_source_tree, "expected_source_tree", git=True)
        for name in (
            "authority_receipt_hash",
            "drain_receipt_hash",
            "snapshot_receipt_hash",
            "rollback_receipt_hash",
            "loaded_writer_plan_hash",
        ):
            _sha(getattr(self, name), name)
        if self.expected_manifest_sha256 is not None:
            _sha(self.expected_manifest_sha256, "expected_manifest_sha256")
        if (
            isinstance(self.next_generation, bool)
            or not isinstance(self.next_generation, int)
            or self.next_generation < 1
        ):
            raise TransitionValidationError("next_generation_INVALID")
        if self.expected_generation is not None and (
            isinstance(self.expected_generation, bool)
            or not isinstance(self.expected_generation, int)
            or self.expected_generation < 1
        ):
            raise TransitionValidationError("expected_generation_INVALID")
        if not isinstance(self.selections, tuple) or not self.selections:
            raise TransitionValidationError("SELECTIONS_INVALID")
        if any(not isinstance(item, TransitionSelection) for item in self.selections):
            raise TransitionValidationError("SELECTIONS_INVALID")
        if len({item.entry_id for item in self.selections}) != len(self.selections):
            raise TransitionValidationError("SELECTIONS_INVALID")
        if len({item.relative_path for item in self.selections}) != len(self.selections):
            raise TransitionValidationError("SELECTIONS_INVALID")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "WriterTransitionRequest":
        if not isinstance(raw, Mapping):
            raise TransitionValidationError("REQUEST_FIELDS_INVALID")
        keys = set(raw)
        if keys - REQUEST_FIELDS - _OPTIONAL_REQUEST_FIELDS or not REQUEST_FIELDS <= keys:
            raise TransitionValidationError("REQUEST_FIELDS_INVALID")
        if raw.get("schema") != "nexus.state_owner_transition_request.v1":
            raise TransitionValidationError("SCHEMA_INVALID")
        selections = raw.get("selections")
        if not isinstance(selections, list) or not selections:
            raise TransitionValidationError("SELECTIONS_INVALID")
        try:
            parsed = tuple(TransitionSelection(**item) for item in selections)
            operation = Operation(raw["operation"])
        except (TypeError, ValueError) as exc:
            raise TransitionValidationError("REQUEST_VALUE_INVALID") from exc
        values = dict(raw)
        values["operation"] = operation
        values["selections"] = parsed
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        fields = {
            name: getattr(self, name)
            for name in REQUEST_FIELDS
            if name not in {"schema", "operation", "selections"}
        }
        if self.accepted_source_receipt_hash:
            fields["accepted_source_receipt_hash"] = self.accepted_source_receipt_hash
        fields.update(
            schema=self.schema,
            operation=self.operation.value,
            selections=[item.to_dict() for item in self.selections],
        )
        return fields

    @property
    def request_digest(self) -> str:
        return _digest(self.to_dict())

    @property
    def authorization_intent_digest(self) -> str:
        payload = self.to_dict()
        payload.pop("authority_receipt_id", None)
        payload.pop("authority_receipt_hash", None)
        return _digest(payload)


@dataclass(frozen=True, slots=True)
class TransitionReceipt:
    request_digest: str
    transaction_id: str
    state: ReceiptState
    writes_observed: bool
    effects_started: bool
    replayed: bool
    reconcile_required: bool
    error: str = ""
    task_id: str = ""
    card_path: str = ""
    card_sha256: str = ""
    source_head: str = ""
    source_tree: str = ""
    accepted_source_receipt: str = ""
    accepted_source_receipt_hash: str = ""
    authority_receipt_id: str = ""
    authority_receipt_hash: str = ""
    authorization_intent_digest: str = ""
    grant_id: str = ""
    grant_hash: str = ""
    effect_hash: str = ""
    root_id: str = ""
    expected_root_identity: str = ""
    expected_owner_id: str = ""
    expected_generation: int | None = None
    expected_writer_id: str = ""
    next_generation: int | None = None
    next_writer_id: str = ""
    selection_digest: str = ""
    expected_manifest_sha256: str | None = None
    observed_before_manifest_sha256: str | None = None
    observed_after_manifest_sha256: str = ""
    before_manifest_present: bool = True
    drain_receipt_id: str = ""
    drain_receipt_hash: str = ""
    snapshot_receipt_id: str = ""
    snapshot_receipt_hash: str = ""
    rollback_receipt_id: str = ""
    rollback_receipt_hash: str = ""
    loaded_writer_plan_id: str = ""
    loaded_writer_plan_hash: str = ""
    observations: tuple[Mapping[str, Any], ...] = ()
    errors: tuple[str, ...] = ()
    receipt_digest: str = ""
    schema: str = "nexus.state_owner_transition_receipt.v1"

    def __post_init__(self) -> None:
        if self.schema != "nexus.state_owner_transition_receipt.v1" or not isinstance(
            self.state, ReceiptState
        ):
            raise TransitionValidationError("RECEIPT_SCHEMA_INVALID")
        _sha(self.request_digest, "request_digest")
        _text(self.transaction_id, "transaction_id")
        for name in ("writes_observed", "effects_started", "replayed", "reconcile_required"):
            if not isinstance(getattr(self, name), bool):
                raise TransitionValidationError(f"{name}_INVALID")
        if not isinstance(self.before_manifest_present, bool):
            raise TransitionValidationError("before_manifest_present_INVALID")
        if not self.before_manifest_present and (
            self.expected_generation is not None
            or self.expected_manifest_sha256 is not None
            or self.observed_before_manifest_sha256 is not None
        ):
            raise TransitionValidationError("INITIAL_MANIFEST_FIELDS_INVALID")
        if not isinstance(self.observations, tuple) or any(
            not isinstance(v, Mapping) for v in self.observations
        ):
            raise TransitionValidationError("observations_INVALID")
        if not isinstance(self.errors, tuple) or any(not isinstance(v, str) for v in self.errors):
            raise TransitionValidationError("errors_INVALID")

    def to_dict(self) -> dict[str, Any]:
        value = {
            "schema": self.schema,
            "request_digest": self.request_digest,
            "transaction_id": self.transaction_id,
            "state": self.state.value,
            "task_id": self.task_id,
            "card_path": self.card_path,
            "card_sha256": self.card_sha256,
            "source_head": self.source_head,
            "source_tree": self.source_tree,
            "accepted_source_receipt": self.accepted_source_receipt,
            "accepted_source_receipt_hash": self.accepted_source_receipt_hash,
            "authority_receipt_id": self.authority_receipt_id,
            "authority_receipt_hash": self.authority_receipt_hash,
            "authorization_intent_digest": self.authorization_intent_digest,
            "grant_id": self.grant_id,
            "grant_hash": self.grant_hash,
            "effect_hash": self.effect_hash,
            "root_id": self.root_id,
            "expected_root_identity": self.expected_root_identity,
            "expected_owner_id": self.expected_owner_id,
            "expected_generation": self.expected_generation,
            "expected_writer_id": self.expected_writer_id,
            "next_generation": self.next_generation,
            "next_writer_id": self.next_writer_id,
            "selection_digest": self.selection_digest,
            "expected_manifest_sha256": self.expected_manifest_sha256,
            "observed_before_manifest_sha256": self.observed_before_manifest_sha256,
            "observed_after_manifest_sha256": self.observed_after_manifest_sha256,
            "before_manifest_present": self.before_manifest_present,
            "drain_receipt_id": self.drain_receipt_id,
            "drain_receipt_hash": self.drain_receipt_hash,
            "snapshot_receipt_id": self.snapshot_receipt_id,
            "snapshot_receipt_hash": self.snapshot_receipt_hash,
            "rollback_receipt_id": self.rollback_receipt_id,
            "rollback_receipt_hash": self.rollback_receipt_hash,
            "loaded_writer_plan_id": self.loaded_writer_plan_id,
            "loaded_writer_plan_hash": self.loaded_writer_plan_hash,
            "observations": list(self.observations),
            "errors": list(self.errors),
            "effects_started": self.effects_started,
            "writes_observed": self.writes_observed,
            "replayed": self.replayed,
            "reconcile_required": self.reconcile_required,
            "error": self.error,
        }
        value["receipt_digest"] = _digest(value)
        return value

    def require_claim_fields(self) -> dict[str, Any]:
        """Validate complete evidence before a committed claim is emitted."""
        if self.state not in {ReceiptState.COMMITTED, ReceiptState.RECONCILED}:
            raise TransitionValidationError("RECEIPT_NOT_CLAIMABLE")
        required = (
            "task_id",
            "card_path",
            "card_sha256",
            "source_head",
            "source_tree",
            "accepted_source_receipt",
            "accepted_source_receipt_hash",
            "authority_receipt_id",
            "authority_receipt_hash",
            "authorization_intent_digest",
            "grant_id",
            "grant_hash",
            "effect_hash",
            "root_id",
            "expected_root_identity",
            "expected_owner_id",
            "expected_writer_id",
            "next_writer_id",
            "selection_digest",
            "observed_after_manifest_sha256",
            "drain_receipt_id",
            "drain_receipt_hash",
            "snapshot_receipt_id",
            "snapshot_receipt_hash",
            "rollback_receipt_id",
            "rollback_receipt_hash",
            "loaded_writer_plan_id",
            "loaded_writer_plan_hash",
        )
        if any(not getattr(self, field) for field in required):
            raise TransitionValidationError("RECEIPT_FIELDS_INCOMPLETE")
        if self.before_manifest_present:
            if not self.expected_manifest_sha256 or not self.observed_before_manifest_sha256:
                raise TransitionValidationError("RECEIPT_FIELDS_INCOMPLETE")
        elif (
            self.expected_generation is not None
            or self.expected_manifest_sha256 is not None
            or self.observed_before_manifest_sha256 is not None
        ):
            raise TransitionValidationError("INITIAL_MANIFEST_FIELDS_INVALID")
        if self.expected_generation is not None and (
            self.next_generation is None or self.next_generation <= self.expected_generation
        ):
            raise TransitionValidationError("GENERATION_NOT_MONOTONIC")
        if (
            self.before_manifest_present
            and self.observed_before_manifest_sha256 == self.observed_after_manifest_sha256
        ):
            raise TransitionValidationError("MANIFEST_SNAPSHOT_UNCHANGED")
        for field in (
            "request_digest",
            "card_sha256",
            "source_tree",
            "expected_root_identity",
            "authority_receipt_hash",
            "accepted_source_receipt_hash",
            "grant_hash",
            "effect_hash",
            "selection_digest",
            "observed_after_manifest_sha256",
            "drain_receipt_hash",
            "snapshot_receipt_hash",
            "rollback_receipt_hash",
            "loaded_writer_plan_hash",
            "authorization_intent_digest",
        ):
            _sha(getattr(self, field), field, git=field == "source_tree")
        _sha(self.source_head, "source_head", git=True)
        if self.before_manifest_present:
            _sha(self.expected_manifest_sha256, "expected_manifest_sha256")
            _sha(self.observed_before_manifest_sha256, "observed_before_manifest_sha256")
        return self.to_dict()
