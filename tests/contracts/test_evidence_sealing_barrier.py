from __future__ import annotations

import pytest

from nexus.contracts.evidence_sealing import seal_evidence
from nexus.contracts.evidence_sealing_barrier import (
    EVIDENCE_SEALING_BARRIER_SCHEMA,
    UnsealedEvidenceError,
    build_evidence_sealing_barrier_receipt,
    read_sealed_evidence_payload,
    require_sealed_evidence,
)


def test_barrier_allows_valid_seal_for_claim_read() -> None:
    seal = seal_evidence({"delivery_status": "PASS"}, evidence_id="row-1")

    receipt = build_evidence_sealing_barrier_receipt(seal)

    assert receipt["schema"] == EVIDENCE_SEALING_BARRIER_SCHEMA
    assert receipt["status"] == "PASS"
    assert receipt["claim_read_allowed"] is True
    assert receipt["runtime_update_allowed"] is False
    assert receipt["public_benchmark_allowed"] is False
    assert receipt["blockers"] == []


def test_barrier_blocks_missing_seal() -> None:
    receipt = build_evidence_sealing_barrier_receipt(None, evidence_id="row-1")

    assert receipt["status"] == "RETURN"
    assert receipt["claim_read_allowed"] is False
    assert receipt["blockers"] == ["missing_evidence_seal"]


def test_barrier_raises_unsealed_error_for_tampered_payload() -> None:
    seal = seal_evidence({"a": 1}, evidence_id="row-1")
    seal["sealed_payload"]["a"] = 2

    with pytest.raises(UnsealedEvidenceError) as exc:
        require_sealed_evidence(seal)

    assert exc.value.receipt["status"] == "RETURN"
    assert exc.value.receipt["blockers"] == ["evidence_hash_mismatch"]


def test_barrier_blocks_partial_telemetry_and_dirty_write() -> None:
    seal = seal_evidence({"a": 1}, evidence_id="row-1")

    receipt = build_evidence_sealing_barrier_receipt(
        seal,
        partial_telemetry_detected=True,
        dirty_write_detected=True,
    )

    assert receipt["status"] == "RETURN"
    assert receipt["blockers"] == [
        "dirty_evidence_write_detected",
        "partial_telemetry_detected",
    ]


def test_read_sealed_payload_returns_copy_after_barrier() -> None:
    seal = seal_evidence({"a": {"nested": True}}, evidence_id="row-1")

    payload = read_sealed_evidence_payload(seal)
    payload["a"] = "changed"

    assert seal["sealed_payload"]["a"] == {"nested": True}
