from __future__ import annotations

import pytest
from nexus.services.local_heal.claim_delivery_gate import (
    ClaimDeliveryGate,
    validate_context_claim_delivery,
)


def _valid_payload(**overrides):
    base = {
        "verifier_status": "pass",
        "verifier_artifact": "verification_report.txt",
        "source_hash": "abc123",
        "patch_applied": True,
        "artifact_refs": ["patch.diff"],
    }
    base.update(overrides)
    return base


def test_claim_delivery_gate_hash_mismatch_blocks_claim():
    """P2-C: candidate_hash_matches_applied=False → claim_gate_passed=False."""
    gate = ClaimDeliveryGate()
    decision = gate.validate(_valid_payload(candidate_hash_matches_applied=False))
    assert decision.claim_gate_passed is False
    assert "candidate_hash_mismatch" in decision.reasons


def test_claim_delivery_gate_hash_match_no_blocker():
    """P2-C: candidate_hash_matches_applied=True → no blocker."""
    gate = ClaimDeliveryGate()
    decision = gate.validate(_valid_payload(
        candidate_hash_matches_applied=True,
        candidate_target_file="foo.py",
    ))
    assert decision.claim_gate_passed is True
    assert "candidate_hash_mismatch" not in decision.reasons


def test_claim_delivery_gate_hash_absent_default_true():
    """P2-C: No candidate_hash_matches_applied in payload → backward compat."""
    gate = ClaimDeliveryGate()
    decision = gate.validate(_valid_payload(candidate_target_file="foo.py"))
    assert decision.claim_gate_passed is True
    assert "candidate_hash_mismatch" not in decision.reasons


def test_claim_delivery_gate_hash_mismatch_with_missing_source_hash():
    """P2-C: Both hash mismatch AND missing source_hash → both reasons present."""
    gate = ClaimDeliveryGate()
    decision = gate.validate(_valid_payload(
        candidate_hash_matches_applied=False,
        source_hash="",
    ))
    assert decision.claim_gate_passed is False
    assert "candidate_hash_mismatch" in decision.reasons
    assert "missing_source_hash" in decision.reasons


def test_validate_context_claim_delivery_reads_hash_match_from_op():
    """P2-C: validate_context reads selected_candidate_hash_matches_applied from op."""
    class FakeOp:
        solve_eligible = True
        evaluation_report = "pass"
        source_hash = "abc123"
        final_patch = "patch"
        selected_candidate_hash_matches_applied = False

    class FakeCtx:
        op = FakeOp()

    gate = ClaimDeliveryGate()
    out = validate_context_claim_delivery(FakeCtx(), gate=gate)
    assert out["claim_gate_passed"] is False
    assert "candidate_hash_mismatch" in out["failure_reasons"]


def test_validate_context_explicit_param_overrides_op():
    """P2-D: Explicit candidate_hash_matches_applied param overrides op field."""
    class FakeOp:
        solve_eligible = True
        evaluation_report = "pass"
        source_hash = "abc123"
        final_patch = "patch"
        selected_candidate_hash_matches_applied = True

    class FakeCtx:
        op = FakeOp()

    gate = ClaimDeliveryGate()
    out = validate_context_claim_delivery(FakeCtx(), gate=gate, candidate_hash_matches_applied=False)
    assert out["claim_gate_passed"] is False
    assert "candidate_hash_mismatch" in out["failure_reasons"]


def test_validate_context_fallback_to_route_context():
    """P2-D: Falls back to route_context when op field absent."""
    class FakeOp:
        solve_eligible = True
        evaluation_report = "pass"
        source_hash = "abc123"
        final_patch = "patch"
        route_context = {"candidate_hash_matches_applied": False}

    class FakeCtx:
        op = FakeOp()

    gate = ClaimDeliveryGate()
    out = validate_context_claim_delivery(FakeCtx(), gate=gate)
    assert out["claim_gate_passed"] is False
    assert "candidate_hash_mismatch" in out["failure_reasons"]


def test_claim_delivery_gate_missing_target_file_blocks_claim():
    """P2-E: source_hash present but candidate_target_file empty → blocker."""
    gate = ClaimDeliveryGate()
    decision = gate.validate(_valid_payload(
        source_hash="abc123",
        candidate_target_file="",
    ))
    assert decision.claim_gate_passed is False
    assert "missing_candidate_target_file" in decision.reasons


def test_claim_delivery_gate_target_file_present_no_blocker():
    """P2-E: source_hash AND candidate_target_file set → no blocker."""
    gate = ClaimDeliveryGate()
    decision = gate.validate(_valid_payload(
        source_hash="abc123",
        candidate_target_file="foo.py",
    ))
    assert decision.claim_gate_passed is True
    assert "missing_candidate_target_file" not in decision.reasons


def test_claim_delivery_gate_target_file_absent_no_hash_ok():
    """P2-E: No source_hash and no candidate_target_file → no blocker."""
    gate = ClaimDeliveryGate()
    decision = gate.validate(_valid_payload(
        source_hash="",
        candidate_target_file="",
    ))
    assert "missing_candidate_target_file" not in decision.reasons
