from __future__ import annotations

from nexus.contracts.evidence_sealing import seal_evidence, verify_evidence_seal


def test_evidence_seal_verifies_stable_payload_hash() -> None:
    seal = seal_evidence({"b": 2, "a": 1}, evidence_id="row-1")
    verification = verify_evidence_seal(seal)

    assert seal["schema"] == "nexus.evidence_seal.v1"
    assert seal["status"] == "PASS"
    assert seal["evidence_seal_status"] == "PASS"
    assert seal["evidence_hash_status"] == "PASS"
    assert len(seal["sha256"]) == 64
    assert verification["status"] == "PASS"
    assert verification["expected_sha256"] == verification["actual_sha256"]


def test_evidence_seal_verification_returns_on_tamper() -> None:
    seal = seal_evidence({"a": 1}, evidence_id="row-1")
    seal["sealed_payload"]["a"] = 2

    verification = verify_evidence_seal(seal)

    assert verification["status"] == "RETURN"
    assert verification["evidence_seal_status"] == "RETURN"
    assert verification["evidence_hash_status"] == "RETURN"
    assert verification["blockers"] == ["evidence_hash_mismatch"]
