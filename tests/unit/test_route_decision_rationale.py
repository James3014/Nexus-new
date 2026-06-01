import pytest
from nexus.engine.route_decision_adapter import RouteDecisionReceipt, RouteDecisionRationale, RouteRationaleCode

def test_route_decision_receipt_rationale_serialization():
    # Arrange
    rationale = RouteDecisionRationale(
        primary_code=RouteRationaleCode.RESEARCH_ISOLATION_REQUIRED,
        supporting_codes=(RouteRationaleCode.HIGH_RISK_GOVERNANCE_LOCKED,),
        reason_text="Task involves public API contract changes."
    )
    
    receipt = RouteDecisionReceipt(
        task_id="astropy-14096",
        selected_route="research_isolated_patch",
        rationale=rationale
    )
    
    # Act
    data = receipt.to_dict()
    
    # Assert
    assert data["schema_version"] == "route_decision_receipt.v1"
    assert data["task_id"] == "astropy-14096"
    assert data["rationale"]["primary_code"] == "research_isolation_required"
    assert "high_risk_governance_locked" in data["rationale"]["supporting_codes"]
    assert data["gate_passed"] is True

def test_route_decision_receipt_default_none_rationale():
    receipt = RouteDecisionReceipt(task_id="simple-fix")
    data = receipt.to_dict()
    assert data["rationale"] is None
