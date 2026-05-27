import pytest
from pathlib import Path
from nexus.core.belief_contracts import CapabilityReceipt as CoreReceipt
from nexus.engine.capability_contracts import CapabilityReceipt as EngineReceipt

def test_capability_receipt_p2_fields():
    """
    TDD Phase (RED/GREEN partial): Verify CapabilityReceipt structures are upgraded with semantic fields.
    """
    # 1. Test CoreReceipt
    core_rcpt = CoreReceipt(
        capability_name="test_cap",
        selected=True,
        invoked=True,
        evidence_id="ev_001",
        gate_passed=True,
        semantic_hash="hash_value_123",
        evidence_alignment=True
    )
    assert core_rcpt.semantic_hash == "hash_value_123"
    assert core_rcpt.evidence_alignment is True

    # 2. Test EngineReceipt
    engine_rcpt = EngineReceipt(
        name="test_cap",
        selected=True,
        invoked=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        semantic_hash="hash_value_456",
        evidence_alignment=False
    )
    assert engine_rcpt.semantic_hash == "hash_value_456"
    assert engine_rcpt.evidence_alignment is False
    assert engine_rcpt.to_dict()["semantic_hash"] == "hash_value_456"
    assert engine_rcpt.to_dict()["evidence_alignment"] is False

def test_dual_gate_verifier_and_drift_detector():
    """
    TDD Phase (RED): Verify DualGateVerifier and PolicyDriftDetector correctly audit physical
    existence, semantic logic consistency, and MUSE_PROTO.md policy drift.
    """
    from nexus.core.policy_drift import DualGateVerifier, PolicyDriftDetector
    
    # 1. Test DualGateVerifier (mocked file existence)
    verifier = DualGateVerifier()
    
    # Empty artifact should fail physical gate (Gate 1)
    res_empty = verifier.verify_receipt(
        evidence_path=None,
        intent="ensure AST optimization is active"
    )
    assert res_empty["physical_gate_passed"] is False
    assert res_empty["semantic_gate_passed"] is False
    
    # 2. Test PolicyDriftDetector
    detector = PolicyDriftDetector(proto_path="MUSE_PROTO.md")
    
    # If active execution path deviates from protocol, assert drift detected
    deviated_path = ["packages/unauthorized_pkg/lib.py", "scripts/engine/breakout.py"]
    drift_res = detector.detect_drift(deviated_path)
    assert drift_res["drift_detected"] is True
    assert any("packages" in v or "scripts/engine" in v for v in drift_res["violations"])
