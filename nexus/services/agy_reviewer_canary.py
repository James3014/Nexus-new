"""Durable canary state for the physical RDC -> Agy packet-review path.

The canary observes one already-authorized reviewer operation across controller
process boundaries. It does not own reviewer routing, retry, acceptance, merge,
release, or production authority.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from nexus.services.agy_reviewer_runtime import atomic_private_json, sha256_json

CANARY_SCHEMA = "nexus.agy_review_canary.v1"
CANARY_RECEIPT_SCHEMA = "nexus.agy_review_canary_receipt.v1"
CANARY_CLAIM_CEILING = "BOUNDED_RDC_AGY_REVIEWER_CANARY_ONLY"


class AgyReviewCanaryError(RuntimeError):
    """Canary state, continuity, or terminal evidence is invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canary_id_for_effect(review_effect_id: str) -> str:
    value = str(review_effect_id or "").strip()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise AgyReviewCanaryError("CANARY_REVIEW_EFFECT_ID_INVALID")
    return "agyreviewcanary_" + value[:32]


def _state_path(root: Path, canary_id: str) -> Path:
    return root / f"{canary_id}.json"


def _receipt_path(root: Path, canary_id: str) -> Path:
    return root / f"{canary_id}.receipt.json"


def _load_json(path: Path, *, error: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgyReviewCanaryError(error) from exc
    if not isinstance(value, dict):
        raise AgyReviewCanaryError(error)
    return value


def _validate_operation_binding(
    *,
    state: Mapping[str, Any],
    operation: Mapping[str, Any],
) -> None:
    if operation.get("operation_id") != state.get("operation_id"):
        raise AgyReviewCanaryError("CANARY_OPERATION_ID_MISMATCH")
    if operation.get("review_effect_id") != state.get("review_effect_id"):
        raise AgyReviewCanaryError("CANARY_REVIEW_EFFECT_ID_MISMATCH")


def _operation_effect_count(operation_root: Path, review_effect_id: str) -> int:
    count = 0
    if not operation_root.is_dir():
        return 0
    for path in operation_root.glob("operations/*/operation.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(row, dict) and row.get("review_effect_id") == review_effect_id:
            count += 1
    return count


def create_canary(
    *,
    start_result: Mapping[str, Any],
    canary_root: str | os.PathLike[str],
    operation_root: str | os.PathLike[str],
    lease_root: str | os.PathLike[str],
    expected_runtime_revision: str,
    review_cli_sha256: str,
) -> dict[str, Any]:
    if start_result.get("action") != "DISPATCHED":
        raise AgyReviewCanaryError("CANARY_REQUIRES_FRESH_DISPATCH")
    operation = start_result.get("operation")
    if not isinstance(operation, Mapping):
        raise AgyReviewCanaryError("CANARY_START_OPERATION_MISSING")
    effect_id = str(operation.get("review_effect_id") or "")
    canary_id = canary_id_for_effect(effect_id)
    operation_id = str(operation.get("operation_id") or "")
    if not operation_id:
        raise AgyReviewCanaryError("CANARY_OPERATION_ID_MISSING")
    runtime_revision = str(expected_runtime_revision or "").strip()
    if len(runtime_revision) != 40:
        raise AgyReviewCanaryError("CANARY_EXPECTED_RUNTIME_REVISION_INVALID")
    cli_sha = str(review_cli_sha256 or "").strip()
    if len(cli_sha) != 64 or any(ch not in "0123456789abcdef" for ch in cli_sha):
        raise AgyReviewCanaryError("CANARY_REVIEW_CLI_SHA256_INVALID")

    root = Path(canary_root).expanduser().resolve()
    path = _state_path(root, canary_id)
    if path.exists():
        raise AgyReviewCanaryError("CANARY_ALREADY_EXISTS")

    state: dict[str, Any] = {
        "schema": CANARY_SCHEMA,
        "claim_ceiling": CANARY_CLAIM_CEILING,
        "canary_id": canary_id,
        "phase": "INTERRUPTIBLE",
        "review_effect_id": effect_id,
        "operation_id": operation_id,
        "operation_root": str(Path(operation_root).expanduser().resolve()),
        "lease_root": str(Path(lease_root).expanduser().resolve()),
        "expected_runtime_revision": runtime_revision,
        "review_cli_sha256": cli_sha,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "resume_observations": 0,
        "initial_action": "DISPATCHED",
        "initial_attempt_id": operation.get("attempt_id"),
        "initial_pid": operation.get("pid"),
        "initial_model": operation.get("model"),
        "initial_review_profile_id": operation.get("review_launch_profile_id"),
    }
    state["state_sha256"] = sha256_json(state)
    atomic_private_json(path, state)
    return state


def load_canary(
    canary_id: str,
    *,
    canary_root: str | os.PathLike[str],
) -> dict[str, Any]:
    root = Path(canary_root).expanduser().resolve()
    state = _load_json(_state_path(root, canary_id), error="CANARY_STATE_READ_FAILED")
    digest = state.get("state_sha256")
    if not isinstance(digest, str):
        raise AgyReviewCanaryError("CANARY_STATE_HASH_MISSING")
    body = dict(state)
    body.pop("state_sha256", None)
    if sha256_json(body) != digest:
        raise AgyReviewCanaryError("CANARY_STATE_HASH_MISMATCH")
    if state.get("schema") != CANARY_SCHEMA:
        raise AgyReviewCanaryError("CANARY_STATE_SCHEMA_INVALID")
    return state


def _write_state(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    state = dict(state)
    state["updated_at"] = utc_now()
    state.pop("state_sha256", None)
    state["state_sha256"] = sha256_json(state)
    atomic_private_json(_state_path(root, str(state["canary_id"])), state)
    return state


def _lease_cleanup_evidence(
    *,
    operation: Mapping[str, Any],
    lease_root: Path,
) -> dict[str, Any]:
    alias_hash = operation.get("account_alias_hash")
    lease_id_hash = operation.get("lease_id_hash")
    if not isinstance(alias_hash, str) or not alias_hash:
        raise AgyReviewCanaryError("CANARY_ACCOUNT_ALIAS_HASH_MISSING")
    if not isinstance(lease_id_hash, str) or not lease_id_hash:
        raise AgyReviewCanaryError("CANARY_LEASE_ID_HASH_MISSING")
    receipt = lease_root / f"{alias_hash}.receipt.json"
    return {
        "account_alias_hash": alias_hash,
        "lease_id_hash": lease_id_hash,
        "lease_receipt_path_sha256": hashlib.sha256(str(receipt).encode("utf-8")).hexdigest(),
        "lease_receipt_absent": not receipt.exists(),
    }


def observe_canary(
    *,
    canary_id: str,
    canary_root: str | os.PathLike[str],
    review_status: Mapping[str, Any],
    current_review_cli_sha256: str,
) -> dict[str, Any]:
    root = Path(canary_root).expanduser().resolve()
    state = load_canary(canary_id, canary_root=root)
    if current_review_cli_sha256 != state.get("review_cli_sha256"):
        raise AgyReviewCanaryError("CANARY_REVIEW_CLI_DRIFT")
    operation = review_status.get("operation")
    if not isinstance(operation, Mapping):
        raise AgyReviewCanaryError("CANARY_STATUS_OPERATION_MISSING")
    _validate_operation_binding(state=state, operation=operation)

    state["resume_observations"] = int(state.get("resume_observations") or 0) + 1
    status = str(operation.get("status") or "")
    state["last_operation_status"] = status
    state["last_status_action"] = review_status.get("action")

    if status in {"QUEUED", "RUNNING", "WAITING_INPUT"}:
        state["phase"] = "WAITING"
        return {
            "state": _write_state(root, state),
            "receipt": None,
            "action": "WAIT",
        }

    if status == "OUTCOME_UNKNOWN":
        state["phase"] = "RECONCILE_REQUIRED"
        return {
            "state": _write_state(root, state),
            "receipt": None,
            "action": "RECONCILE",
        }

    if status in {"FAILED", "CANCELLED"}:
        state["phase"] = "TERMINAL_NON_ACCEPTING"
        return {
            "state": _write_state(root, state),
            "receipt": None,
            "action": "TERMINAL_NON_ACCEPTING",
        }

    if status != "COMPLETED":
        raise AgyReviewCanaryError(f"CANARY_OPERATION_STATUS_INVALID:{status}")

    review_receipt = review_status.get("receipt")
    if not isinstance(review_receipt, Mapping):
        raise AgyReviewCanaryError("CANARY_REVIEW_RECEIPT_MISSING")
    if review_receipt.get("review_effect_id") != state["review_effect_id"]:
        raise AgyReviewCanaryError("CANARY_RECEIPT_EFFECT_MISMATCH")
    if review_receipt.get("review_applicable") is not True:
        raise AgyReviewCanaryError("CANARY_REVIEW_NOT_APPLICABLE")
    if review_receipt.get("subject_stable") is not True:
        raise AgyReviewCanaryError("CANARY_SUBJECT_NOT_STABLE")
    provider_session_id = operation.get("provider_session_id")
    if not isinstance(provider_session_id, str) or not provider_session_id:
        raise AgyReviewCanaryError("CANARY_PROVIDER_SESSION_MISSING")
    runtime_revision = operation.get("runtime_revision")
    if runtime_revision != state["expected_runtime_revision"]:
        raise AgyReviewCanaryError("CANARY_RUNTIME_REVISION_MISMATCH")
    if int(state["resume_observations"]) < 1:
        raise AgyReviewCanaryError("CANARY_RESUME_OBSERVATION_MISSING")

    operation_root = Path(str(state["operation_root"]))
    effect_count = _operation_effect_count(operation_root, str(state["review_effect_id"]))
    if effect_count != 1:
        raise AgyReviewCanaryError(f"CANARY_SEMANTIC_OPERATION_COUNT_INVALID:{effect_count}")
    lease = _lease_cleanup_evidence(
        operation=operation,
        lease_root=Path(str(state["lease_root"])),
    )
    if lease["lease_receipt_absent"] is not True:
        raise AgyReviewCanaryError("CANARY_LEASE_NOT_CLEANED")

    receipt: dict[str, Any] = {
        "schema": CANARY_RECEIPT_SCHEMA,
        "claim_ceiling": CANARY_CLAIM_CEILING,
        "canary_id": state["canary_id"],
        "review_effect_id": state["review_effect_id"],
        "operation_id": state["operation_id"],
        "expected_runtime_revision": state["expected_runtime_revision"],
        "observed_runtime_revision": runtime_revision,
        "review_receipt_sha256": review_receipt.get("receipt_sha256"),
        "review_verdict": review_receipt.get("verdict"),
        "subject_stable": True,
        "review_applicable": True,
        "resume_observations": state["resume_observations"],
        "semantic_operation_count": effect_count,
        "provider_session_id": provider_session_id,
        "lease_cleanup": lease,
        "completed_at": utc_now(),
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    atomic_private_json(_receipt_path(root, canary_id), receipt)
    state["phase"] = "PASSED"
    state["receipt_sha256"] = receipt["receipt_sha256"]
    return {
        "state": _write_state(root, state),
        "receipt": receipt,
        "action": "PASSED",
    }


def load_canary_receipt(
    canary_id: str,
    *,
    canary_root: str | os.PathLike[str],
) -> dict[str, Any]:
    root = Path(canary_root).expanduser().resolve()
    receipt = _load_json(
        _receipt_path(root, canary_id),
        error="CANARY_RECEIPT_READ_FAILED",
    )
    digest = receipt.get("receipt_sha256")
    if not isinstance(digest, str):
        raise AgyReviewCanaryError("CANARY_RECEIPT_HASH_MISSING")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if sha256_json(body) != digest:
        raise AgyReviewCanaryError("CANARY_RECEIPT_HASH_MISMATCH")
    if receipt.get("schema") != CANARY_RECEIPT_SCHEMA:
        raise AgyReviewCanaryError("CANARY_RECEIPT_SCHEMA_INVALID")
    return receipt
