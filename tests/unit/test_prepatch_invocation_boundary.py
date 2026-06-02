import pytest
from nexus.services.local_heal.pre_patch import (
    PatchInputClassifier, 
    PrePatchGateDecision, 
    PatchInvocationBoundaryReceipt,
    PrePatchRejectClass
)

def test_prepatch_gate_decision_refusal():
    classifier = PatchInputClassifier()
    raw_text = "I apologize, but I cannot assist."
    decision = classifier.make_decision(raw_text)
    
    assert decision.should_invoke_patch is False
    assert decision.reject_class == PrePatchRejectClass.REFUSAL_DETECTED

def test_prepatch_invocation_boundary_receipt_logic():
    # Simulate a rejected input
    decision = PrePatchGateDecision(
        should_invoke_patch=False,
        reject_class=PrePatchRejectClass.REFUSAL_DETECTED,
        reason="Model apologized"
    )
    
    # Construct the boundary receipt
    receipt = PatchInvocationBoundaryReceipt(
        task_id="probe-123",
        patch_phase_invoked=decision.should_invoke_patch,
        blocked_before_patch=not decision.should_invoke_patch,
        reject_class=decision.reject_class.value,
        input_origin="ollama:14b"
    )
    
    data = receipt.to_dict()
    assert data["patch_phase_invoked"] is False
    assert data["blocked_before_patch"] is True
    assert data["reject_class"] == "refusal_detected"

def test_prepatch_gate_decision_pass():
    classifier = PatchInputClassifier()
    raw_text = "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"
    decision = classifier.make_decision(raw_text)
    assert decision.should_invoke_patch is True
