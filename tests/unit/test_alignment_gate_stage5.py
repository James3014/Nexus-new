import pytest
from nexus.engine.alignment_gate import AlignmentGate, ApprovalScope, ApprovalStatus

def test_alignment_gate_design_required():
    gate = AlignmentGate()
    context = {"approval_receipts": []}
    ready, reason = gate.check_readiness(context, ApprovalScope.DESIGN)
    assert ready is False
    assert "DESIGN_APPROVAL_REQUIRED" in reason

def test_alignment_gate_rejected():
    gate = AlignmentGate()
    context = {
        "approval_receipts": [
            {"scope": "design", "status": "rejected", "comment": "Too complex"}
        ]
    }
    ready, reason = gate.check_readiness(context, ApprovalScope.DESIGN)
    assert ready is False
    assert "REVIEW_REJECTED" in reason
    assert "Too complex" in reason

def test_alignment_gate_approved():
    gate = AlignmentGate()
    context = {
        "approval_receipts": [
            {"scope": "design", "status": "approved"}
        ]
    }
    ready, reason = gate.check_readiness(context, ApprovalScope.DESIGN)
    assert ready is True

def test_handoff_summary_generation():
    gate = AlignmentGate()
    context = {
        "instance_id": "nexus-1",
        "approval_receipts": [{"scope": "design", "status": "approved"}],
        "budget_status": "medium_pressure"
    }
    summary = gate.generate_handoff_summary(context)
    assert summary["design_sealed"] is True
    assert summary["outline_sealed"] is False
    assert summary["budget_status"] == "medium_pressure"
