from __future__ import annotations

from typing import Any, Mapping

from nexus.contracts.evidence_sealing import verify_evidence_seal


EVIDENCE_SEALING_BARRIER_SCHEMA = "nexus.evidence_sealing_barrier.v1"


class UnsealedEvidenceError(RuntimeError):
    def __init__(self, receipt: Mapping[str, Any]) -> None:
        self.receipt = dict(receipt)
        blockers = ",".join(str(item) for item in self.receipt.get("blockers", []))
        super().__init__(f"unsealed_evidence_blocked:{blockers}")


def build_evidence_sealing_barrier_receipt(
    seal: Mapping[str, Any] | None,
    *,
    evidence_id: str = "",
    partial_telemetry_detected: bool = False,
    dirty_write_detected: bool = False,
) -> dict[str, Any]:
    blockers: list[str] = []
    verification: dict[str, Any] = {}
    if not isinstance(seal, Mapping):
        blockers.append("missing_evidence_seal")
    else:
        verification = verify_evidence_seal(seal)
        blockers.extend(str(item) for item in verification.get("blockers", []))

    if partial_telemetry_detected:
        blockers.append("partial_telemetry_detected")
    if dirty_write_detected:
        blockers.append("dirty_evidence_write_detected")

    uniq_blockers = sorted(set(blockers))
    status = "PASS" if not uniq_blockers else "RETURN"
    resolved_evidence_id = evidence_id or str((seal or {}).get("evidence_id") or verification.get("evidence_id") or "")
    return {
        "schema": EVIDENCE_SEALING_BARRIER_SCHEMA,
        "status": status,
        "evidence_id": resolved_evidence_id,
        "claim_read_allowed": status == "PASS",
        "evidence_seal_status": "PASS" if status == "PASS" else "RETURN",
        "evidence_hash_status": "PASS" if status == "PASS" else "RETURN",
        "verification": verification,
        "partial_telemetry_detected": bool(partial_telemetry_detected),
        "dirty_write_detected": bool(dirty_write_detected),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "blockers": uniq_blockers,
        "claim_boundary": [
            "The evidence sealing barrier only gates reads of sealed evidence.",
            "It does not mutate runtime policy or unlock public benchmark claims.",
        ],
    }


def require_sealed_evidence(
    seal: Mapping[str, Any] | None,
    *,
    evidence_id: str = "",
    partial_telemetry_detected: bool = False,
    dirty_write_detected: bool = False,
) -> dict[str, Any]:
    receipt = build_evidence_sealing_barrier_receipt(
        seal,
        evidence_id=evidence_id,
        partial_telemetry_detected=partial_telemetry_detected,
        dirty_write_detected=dirty_write_detected,
    )
    if receipt["status"] != "PASS":
        raise UnsealedEvidenceError(receipt)
    return receipt


def read_sealed_evidence_payload(
    seal: Mapping[str, Any] | None,
    *,
    evidence_id: str = "",
    partial_telemetry_detected: bool = False,
    dirty_write_detected: bool = False,
) -> dict[str, Any]:
    require_sealed_evidence(
        seal,
        evidence_id=evidence_id,
        partial_telemetry_detected=partial_telemetry_detected,
        dirty_write_detected=dirty_write_detected,
    )
    payload = seal.get("sealed_payload") if isinstance(seal, Mapping) else {}
    return dict(payload) if isinstance(payload, Mapping) else {}
