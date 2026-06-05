import pytest
from nexus.core.state_contracts import NexusState, NexusDerivation, AuditResult

def test_empty_invariants():
    derivation = NexusDerivation(
        task_id="edge-001",
        goal="Empty Invariants Test",
        invariants=[]
    )
    assert derivation.invariants == []
    print("Empty invariants test passed.")

def test_failed_proof():
    audit = AuditResult(
        audit_id="aud-edge-001",
        reasoning_mode="FORMAL",
        formal_gate_passed=False,
        repair_status="FAIL",
        smoke_status="FAIL",
        summary="Proof failed due to contradiction"
    )
    assert audit.formal_gate_passed is False
    print("Failed proof test passed.")

if __name__ == "__main__":
    test_empty_invariants()
    test_failed_proof()
