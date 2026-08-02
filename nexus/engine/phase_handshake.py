from __future__ import annotations

from typing import Any
import hashlib
import json


PHASE_RECEIPT_REQUIRED_FIELDS = (
    "task_id",
    "attempt_id",
    "action_id",
    "phase",
    "phase_attempt",
    "input_hash",
    "output_hash",
    "authority_revision",
    "status",
    "transition",
    "evidence_refs",
    "verifier_refs",
    "timeout_telemetry",
    "block_class",
    "next_action",
)


def required_artifacts(phase: Any) -> tuple[str, ...]:
    provider = getattr(phase, "required_artifacts", None)
    if not callable(provider):
        return ()
    return tuple(str(item) for item in (provider() or ()) if str(item).strip())


def provided_artifacts(phase: Any) -> tuple[str, ...]:
    provider = getattr(phase, "provided_artifacts", None)
    if not callable(provider):
        return ()
    return tuple(str(item) for item in (provider() or ()) if str(item).strip())


def validate_required_artifacts(*, phase: Any, blackboard: Any) -> None:
    missing = [key for key in required_artifacts(phase) if not blackboard.has(key)]
    if missing:
        phase_name = str(getattr(phase, "name", "unknown"))
        raise RuntimeError(f"SEMANTIC_HANDSHAKE_MISSING_ARTIFACT:{phase_name}:{','.join(missing)}")


def record_phase_artifacts(*, phase: Any, result: Any, blackboard: Any) -> None:
    phase_name = str(getattr(phase, "name", "unknown"))
    mutations = getattr(result, "mutations", {}) or {}
    if isinstance(mutations, dict):
        for key, value in mutations.items():
            if str(key).strip():
                blackboard.append(phase_name, str(key), value)
    for key in provided_artifacts(phase):
        if isinstance(mutations, dict) and key in mutations:
            continue
        blackboard.append(phase_name, key, {"provided": True})


def stable_payload_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_phase_receipt(
    *,
    task_id: str,
    attempt_id: str,
    action_id: str,
    phase: str,
    phase_attempt: int,
    input_payload: Any,
    output_payload: Any,
    authority_revision: str,
    status: str,
    transition: str,
    evidence_refs: tuple[str, ...] | list[str] = (),
    verifier_refs: tuple[str, ...] | list[str] = (),
    timeout_telemetry: dict[str, Any] | None = None,
    block_class: str = "",
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "task_id": str(task_id),
        "attempt_id": str(attempt_id),
        "action_id": str(action_id),
        "phase": str(phase),
        "phase_attempt": int(phase_attempt),
        "input_hash": stable_payload_hash(input_payload),
        "output_hash": stable_payload_hash(output_payload),
        "authority_revision": str(authority_revision),
        "status": str(status).upper(),
        "transition": str(transition),
        "evidence_refs": list(evidence_refs),
        "verifier_refs": list(verifier_refs),
        "timeout_telemetry": dict(timeout_telemetry or {}),
        "block_class": str(block_class),
        "next_action": str(next_action),
    }


def validate_phase_receipt(receipt: dict[str, Any]) -> None:
    missing = [field for field in PHASE_RECEIPT_REQUIRED_FIELDS if field not in receipt]
    if missing:
        raise RuntimeError(f"PHASE_RECEIPT_INCOMPLETE:{','.join(missing)}")
    for field in ("task_id", "attempt_id", "action_id", "phase", "input_hash", "output_hash", "authority_revision", "status", "transition"):
        if not str(receipt[field]).strip():
            raise RuntimeError(f"PHASE_RECEIPT_INCOMPLETE:{field}")
    for field in ("evidence_refs", "verifier_refs"):
        if not isinstance(receipt[field], list):
            raise RuntimeError(f"PHASE_RECEIPT_INCOMPLETE:{field}")
