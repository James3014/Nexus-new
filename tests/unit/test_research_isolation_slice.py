import pytest
from nexus.research.isolation_contracts import ResearchIsolationLevel
from nexus.research.contamination_guard import build_research_receipt

def test_research_receipt_l2_fail_closed_contamination():
    # Arrange
    # 研究產物中包含 "fix" 關鍵字 (Contamination)
    facts_payload = {
        "observed_components": ["TacticalDrone"],
        "execution_flows": ["timeout logic"],
        "findings": "We should fix the timeout by adding a signal handler."
    }
    
    # Act
    receipt = build_research_receipt(
        policy_level=ResearchIsolationLevel.L2,
        brief_masked=True,
        facts_payload=facts_payload
    )
    
    # Assert
    assert receipt.policy_level == "L2"
    assert receipt.contamination_detected is True
    assert receipt.gate_passed is False
    assert "fix" in receipt.design_terms_detected

def test_research_receipt_l2_fail_closed_missing_masked_brief():
    # Arrange
    facts_payload = {"observed_components": ["TacticalDrone"]}
    
    # Act
    receipt = build_research_receipt(
        policy_level=ResearchIsolationLevel.L2,
        brief_masked=False, # Missing masked brief
        facts_payload=facts_payload
    )
    
    # Assert
    assert receipt.gate_passed is False

def test_research_receipt_l2_pass():
    # Arrange
    # 純事實產物 (Facts Only)
    facts_payload = {
        "observed_components": ["TacticalDrone"],
        "constraints": ["inactivity timeout is 30s"]
    }
    
    # Act
    receipt = build_research_receipt(
        policy_level=ResearchIsolationLevel.L2,
        brief_masked=True,
        facts_payload=facts_payload
    )
    
    # Assert
    assert receipt.gate_passed is True
    assert receipt.contamination_detected is False

def test_research_receipt_l1_pass_with_minimal_facts():
    facts_payload = {"observed_components": ["TacticalDrone"]}
    receipt = build_research_receipt(
        policy_level=ResearchIsolationLevel.L1,
        brief_masked=True,
        facts_payload=facts_payload
    )
    assert receipt.gate_passed is True
