"""Closed, receipt-gated control seam for Learning policy effects."""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from nexus.contracts.autonomy_goal import AutonomyActionClass
from nexus.contracts.learning_experience import (
    LEARNING_POLICY_ADOPTION_SCHEMA,
    LEARNING_POLICY_ROLLBACK_SCHEMA,
    build_learning_policy_adoption,
    validate_learning_policy_adoption,
    validate_learning_policy_rollback,
)
from nexus.engine.learning_policy_loader import (
    DEFAULT_GOVERNED_ADOPTION_PATH,
    DEFAULT_GOVERNED_ROLLBACK_PATH,
)
from nexus.infrastructure.state_json_store import StateJsonStore

_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_ADOPT = AutonomyActionClass.LEARNING_POLICY_ADOPT
_ROLLBACK = AutonomyActionClass.LEARNING_POLICY_ROLLBACK
CONTROL_OPERATION_PATH = (
    Path(".nexus") / "policy" / "governed_learning_policy_control_operations.json"
)


class LearningPolicyControlError(ValueError):
    """A malformed, stale, mismatched, or denied policy effect."""


def _canonical_contract_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _store_digest(payload: Mapping[str, Any]) -> str:
    return StateJsonStore.content_digest(dict(payload))


def _strict_read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink():
        raise LearningPolicyControlError("LEARNING_POLICY_TARGET_SYMLINK")
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(
                handle, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise LearningPolicyControlError(f"LEARNING_POLICY_STRICT_READ_FAILED:{path.name}") from exc
    if not isinstance(value, dict):
        raise LearningPolicyControlError(f"LEARNING_POLICY_STRICT_OBJECT_REQUIRED:{path.name}")
    return value


@contextmanager
def _policy_transaction_lock(policy_dir: Path) -> Iterator[None]:
    policy_dir.mkdir(parents=True, exist_ok=True)
    lock_path = policy_dir / ".governed_learning_policy.transaction.lock"
    if lock_path.is_symlink():
        raise LearningPolicyControlError("LEARNING_POLICY_LOCK_SYMLINK")
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _target_paths(project_root: Path, action: AutonomyActionClass) -> tuple[Path, Path, Path]:
    root = Path(project_root)
    if root.is_symlink():
        raise LearningPolicyControlError("LEARNING_POLICY_ROOT_SYMLINK")
    policy_dir = root / ".nexus" / "policy"
    for component in (root / ".nexus", policy_dir):
        if component.exists() and component.is_symlink():
            raise LearningPolicyControlError("LEARNING_POLICY_DIRECTORY_SYMLINK")
    target = root / (
        DEFAULT_GOVERNED_ADOPTION_PATH if action is _ADOPT else DEFAULT_GOVERNED_ROLLBACK_PATH
    )
    journal = root / CONTROL_OPERATION_PATH
    if target.parent != policy_dir or journal.parent != policy_dir:
        raise LearningPolicyControlError("LEARNING_POLICY_TARGET_INVALID")
    return policy_dir, target, journal


def _validate_digest(value: Any, field: str) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not _SHA64.fullmatch(text):
        raise LearningPolicyControlError(f"{field.upper()}_INVALID")
    return text


def _validate_adoption_provenance(
    payload: Mapping[str, Any],
    recommendation: Mapping[str, Any] | None,
    validation: Mapping[str, Any] | None,
) -> None:
    if not isinstance(recommendation, Mapping) or not isinstance(validation, Mapping):
        raise LearningPolicyControlError("LEARNING_POLICY_PROVENANCE_REQUIRED")
    try:
        rebuilt = build_learning_policy_adoption(
            owner_authority_reference=str(payload["owner_authority_reference"]),
            recommendation=dict(recommendation),
            validation=dict(validation),
            source_revision=str(payload["source_revision"]),
            adopted_scope=dict(payload["adopted_scope"]),
            target_policy_delta=dict(payload["target_policy_delta"]),
            previous_policy=dict(payload["previous_policy"]),
            rollback_target=dict(payload["rollback_target"]),
            effective_candidate_generation=str(payload["effective_candidate_generation"]),
        )
    except Exception as exc:
        raise LearningPolicyControlError(f"LEARNING_POLICY_PROVENANCE_INVALID:{exc}") from exc
    if rebuilt != dict(payload):
        raise LearningPolicyControlError("LEARNING_POLICY_PROVENANCE_MISMATCH")


def _validate_rollback_pair(rollback: Mapping[str, Any], adoption: Mapping[str, Any]) -> None:
    if rollback.get("adoption_id") != adoption.get("adoption_id") or rollback.get(
        "adoption_hash"
    ) != adoption.get("adoption_hash"):
        raise LearningPolicyControlError("LEARNING_POLICY_ROLLBACK_ADOPTION_BINDING_MISMATCH")
    if rollback.get("recommendation_id") != adoption.get("recommendation_id") or rollback.get(
        "recommendation_hash"
    ) != adoption.get("recommendation_hash"):
        raise LearningPolicyControlError("LEARNING_POLICY_ROLLBACK_RECOMMENDATION_BINDING_MISMATCH")
    if rollback.get("previous_policy_hash") != adoption.get("target_policy_hash"):
        raise LearningPolicyControlError("LEARNING_POLICY_ROLLBACK_POLICY_BINDING_MISMATCH")
    target = (
        adoption.get("rollback_target", {}).get("target_state")
        if isinstance(adoption.get("rollback_target"), Mapping)
        else None
    )
    if rollback.get("rolled_back_policy") != target or rollback.get(
        "rolled_back_policy_hash"
    ) != _canonical_contract_hash(target or {}):
        raise LearningPolicyControlError("LEARNING_POLICY_ROLLBACK_STATE_BINDING_MISMATCH")


def apply_learning_policy_effect(
    *,
    action: AutonomyActionClass,
    project_root: Path,
    artifact: Mapping[str, Any],
    expected_current_digest: str | None,
    operation_id: str,
    idempotency_key: str,
    source_revision: str,
    task_family: str,
    model_name: str,
    runtime_identity: str,
    recommendation: Mapping[str, Any] | None = None,
    validation: Mapping[str, Any] | None = None,
    previous_adoption_id: str | None = None,
    previous_adoption_hash: str | None = None,
    previous_adoption: Mapping[str, Any] | None = None,
    store: StateJsonStore | None = None,
) -> dict[str, Any]:
    """Apply one exact action while holding the common policy-directory lock."""
    if action not in {_ADOPT, _ROLLBACK}:
        raise LearningPolicyControlError("LEARNING_POLICY_ACTION_INVALID")
    if not operation_id or not idempotency_key or not source_revision:
        raise LearningPolicyControlError("LEARNING_POLICY_OPERATION_ID_REQUIRED")
    expected = _validate_digest(expected_current_digest, "expected_current_digest")
    if not isinstance(artifact, Mapping):
        raise LearningPolicyControlError("LEARNING_POLICY_ARTIFACT_INVALID")
    payload = dict(artifact)
    policy_store = store or StateJsonStore()
    policy_dir, target, journal_path = _target_paths(project_root, action)
    artifact_digest = _store_digest(payload)
    request_identity = {
        "action": action.value,
        "idempotency_key": idempotency_key,
        "artifact_digest": artifact_digest,
        "target": str(target),
        "expected_current_digest": expected,
        "source_revision": source_revision,
        "task_family": task_family,
        "model_name": model_name,
        "runtime_identity": runtime_identity,
        "recommendation_input_hash": (
            _canonical_contract_hash(recommendation)
            if isinstance(recommendation, Mapping)
            else None
        ),
        "validation_input_hash": (
            _canonical_contract_hash(validation) if isinstance(validation, Mapping) else None
        ),
        "previous_adoption_input_hash": (
            _canonical_contract_hash(previous_adoption)
            if isinstance(previous_adoption, Mapping)
            else None
        ),
        "previous_adoption_id": previous_adoption_id,
        "previous_adoption_hash": previous_adoption_hash,
    }

    if action is _ADOPT:
        if payload.get("schema") != LEARNING_POLICY_ADOPTION_SCHEMA:
            raise LearningPolicyControlError("LEARNING_POLICY_ADOPTION_SCHEMA_INVALID")
        try:
            validate_learning_policy_adoption(payload)
        except Exception as exc:
            raise LearningPolicyControlError(f"LEARNING_POLICY_ADOPTION_INVALID:{exc}") from exc
        _validate_adoption_provenance(payload, recommendation, validation)
        scope = payload.get("adopted_scope")
        if not isinstance(scope, Mapping) or any(
            str(scope.get(k) or "") != v
            for k, v in {
                "task_family": task_family,
                "model_name": model_name,
                "runtime_identity": runtime_identity,
            }.items()
        ):
            raise LearningPolicyControlError("LEARNING_POLICY_TARGET_MISMATCH")
        if str(payload.get("source_revision") or "") != source_revision:
            raise LearningPolicyControlError("LEARNING_POLICY_SOURCE_REVISION_MISMATCH")
    else:
        if payload.get("schema") != LEARNING_POLICY_ROLLBACK_SCHEMA:
            raise LearningPolicyControlError("LEARNING_POLICY_ROLLBACK_SCHEMA_INVALID")
        try:
            validate_learning_policy_rollback(payload)
        except Exception as exc:
            raise LearningPolicyControlError(f"LEARNING_POLICY_ROLLBACK_INVALID:{exc}") from exc
        if (
            not isinstance(previous_adoption, Mapping)
            or previous_adoption_id != previous_adoption.get("adoption_id")
            or previous_adoption_hash != previous_adoption.get("adoption_hash")
        ):
            raise LearningPolicyControlError("LEARNING_POLICY_ROLLBACK_ADOPTION_BINDING_REQUIRED")

    with _policy_transaction_lock(policy_dir):
        root = Path(project_root)
        adoption_path = root / DEFAULT_GOVERNED_ADOPTION_PATH
        rollback_path = root / DEFAULT_GOVERNED_ROLLBACK_PATH
        persisted_adoption = _strict_read(adoption_path)
        persisted_rollback = _strict_read(rollback_path)
        journal = _strict_read(journal_path)
        journal_exists = journal is not None
        journal = journal if journal is not None else {}
        for existing_operation_id, existing_record in journal.items():
            if (
                existing_operation_id != operation_id
                and isinstance(existing_record, Mapping)
                and existing_record.get("idempotency_key") == idempotency_key
            ):
                raise LearningPolicyControlError("LEARNING_POLICY_IDEMPOTENCY_KEY_REUSE")
        record = journal.get(operation_id)
        if record is not None:
            completed_record = {**request_identity, "status": "COMPLETED"}
            pending_record = {**request_identity, "status": "PENDING"}
            if record not in (completed_record, pending_record):
                raise LearningPolicyControlError("LEARNING_POLICY_OPERATION_REPLAY_MISMATCH")
            current = _strict_read(target)
            if current == payload:
                if record == pending_record:
                    completed = {**journal, operation_id: completed_record}
                    if not policy_store.compare_and_swap_dict(
                        journal_path, _store_digest(journal), completed
                    ):
                        raise LearningPolicyControlError(
                            "LEARNING_POLICY_OPERATION_JOURNAL_READBACK_CONFLICT"
                        )
                    status = "RECONCILED_AFTER_UNKNOWN_EFFECT"
                else:
                    status = "RECONCILED_DUPLICATE"
                return {
                    "schema": "nexus.learning_policy_control_result.v1",
                    "operation_id": operation_id,
                    "idempotency_key": idempotency_key,
                    "action": action.value,
                    "status": status,
                    "artifact_digest": artifact_digest,
                    "readback_digest": _store_digest(current),
                    "atomicity": "COMMON_POLICY_LOCK_SINGLE_FILE_CAS",
                }
            if record == completed_record:
                raise LearningPolicyControlError(
                    "LEARNING_POLICY_OPERATION_RECONCILIATION_REQUIRED"
                )
        if action is _ADOPT:
            if persisted_rollback is not None:
                raise LearningPolicyControlError("LEARNING_POLICY_INCOMPATIBLE_ROLLBACK_PRESENT")
        else:
            if persisted_adoption is None:
                raise LearningPolicyControlError("LEARNING_POLICY_PERSISTED_ADOPTION_MISSING")
            if dict(previous_adoption) != persisted_adoption:
                raise LearningPolicyControlError("LEARNING_POLICY_PERSISTED_ADOPTION_MISMATCH")
            _validate_rollback_pair(payload, persisted_adoption)
            persisted_scope = persisted_adoption.get("adopted_scope")
            if (
                str(persisted_adoption.get("source_revision") or "") != source_revision
                or not isinstance(persisted_scope, Mapping)
                or any(
                    str(persisted_scope.get(k) or "") != v
                    for k, v in {
                        "task_family": task_family,
                        "model_name": model_name,
                        "runtime_identity": runtime_identity,
                    }.items()
                )
            ):
                raise LearningPolicyControlError("LEARNING_POLICY_ROLLBACK_TARGET_MISMATCH")
        current = _strict_read(target)
        current_digest = _store_digest(current) if current is not None else None
        if expected is None:
            if current is not None:
                raise LearningPolicyControlError("LEARNING_POLICY_EXPECTED_ABSENT_MISMATCH")
        elif current_digest != expected:
            raise LearningPolicyControlError("LEARNING_POLICY_EXPECTED_DIGEST_MISMATCH")
        pending = {**journal, operation_id: {**request_identity, "status": "PENDING"}}
        journal_expected = _store_digest(journal) if journal_exists else None
        if not policy_store.compare_and_swap_dict(journal_path, journal_expected, pending):
            raise LearningPolicyControlError("LEARNING_POLICY_OPERATION_JOURNAL_CAS_CONFLICT")
        unknown_effect = False
        try:
            written = policy_store.compare_and_swap_dict(target, expected, payload)
        except Exception:
            after = _strict_read(target)
            if after != payload:
                raise
            unknown_effect = True
            written = True
        if not written and _strict_read(target) != payload:
            raise LearningPolicyControlError("LEARNING_POLICY_CAS_CONFLICT")
        after = _strict_read(target)
        if after != payload or _store_digest(after) != artifact_digest:
            raise LearningPolicyControlError("LEARNING_POLICY_READBACK_MISMATCH")
        completed = {**journal, operation_id: {**request_identity, "status": "COMPLETED"}}
        if not policy_store.compare_and_swap_dict(journal_path, _store_digest(pending), completed):
            raise LearningPolicyControlError("LEARNING_POLICY_OPERATION_JOURNAL_READBACK_CONFLICT")
        return {
            "schema": "nexus.learning_policy_control_result.v1",
            "operation_id": operation_id,
            "idempotency_key": idempotency_key,
            "action": action.value,
            "status": ("RECONCILED_AFTER_UNKNOWN_EFFECT" if unknown_effect else "APPLIED"),
            "artifact_digest": artifact_digest,
            "readback_digest": _store_digest(after),
            "atomicity": "COMMON_POLICY_LOCK_SINGLE_FILE_CAS",
        }
