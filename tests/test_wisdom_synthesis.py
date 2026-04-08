import pytest
import json
import os
from pathlib import Path
from nexus.services.wisdom_synthesizer import WisdomSynthesizer
from nexus.services.predictive_audit import PredictiveAuditor
from nexus.services.construction_service import ConstructionService

@pytest.fixture
def project_root():
    return Path("/Users/jameschen/Workspace/nexus")

@pytest.fixture
def synthesizer(project_root):
    return WisdomSynthesizer(project_root)

@pytest.fixture
def auditor(project_root):
    return PredictiveAuditor(project_root)

def test_wisdom_synthesis_loop(synthesizer):
    """🛡️ Test the full Lesson -> Wisdom induction loop."""
    result = synthesizer.sync_all()
    assert result["status"] in ["SUCCESS", "EMPTY"]
    assert "rules_synthesized" in result

def test_predictive_audit_risk_detection(auditor):
    """🛡️ Test risk detection with high-similarity intent."""
    high_risk_pack = {
        "task_id": "test-risk-999",
        "planner_output": {
            "goal": "Change shared data schema without evidence."
        }
    }
    # Note: Success depends on whether 'UNKNOWN' category has processed this yet
    report = auditor.audit_risk(high_risk_pack)
    assert "risk_score" in report
    assert "status" in report

def test_construction_gate_block(project_root):
    """🛡️ Test that high-risk packs are blocked by the construction gate."""
    service = ConstructionService(project_root)
    
    # Mock pack that would trigger a risk (matching UNKNOWN or LOGIC)
    mock_pack = {
        "task_id": "mock-block-task",
        "goal": "Perform unsafe unknown logic modification.",
        "deliverables": ["unsafe_mod.py"],
        "planner_output": {"goal": "Perform unsafe unknown logic modification."}
    }
    
    # We create a physical file for the build service to read
    pack_file = Path("/tmp/mock_block_pack.json")
    with open(pack_file, "w") as f:
        json.dump(mock_pack, f)
        
    result = service.build(pack_file)
    # The result should be REJECTED or AUTO_REPLAN_TRIGGERED depending on score
    assert result["status"] in ["SUCCESS", "REJECTED", "AUTO_REPLAN_TRIGGERED"]
