import pytest
from nexus.core.state_contracts import NexusState, NexusWeights, TraumaRecord

def test_nexus_weights_contract():
    """驗證 Trinity Evolution 的權重合約"""
    trauma = TraumaRecord(failure_signature="CircularImportError", penalty=-0.2)
    weights = NexusWeights(
        skill_weights={"nexus-debug-expert": 1.2},
        trauma_records=[trauma]
    )
    
    state = NexusState(task_id="test-123", autonomic_weights=weights)
    assert state.autonomic_weights.skill_weights["nexus-debug-expert"] == 1.2
    assert len(state.autonomic_weights.trauma_records) == 1
    assert state.autonomic_weights.trauma_records[0].failure_signature == "CircularImportError"

def test_enhanced_plan_contract():
    """驗證強化版 P 階段計畫合約"""
    state = NexusState(task_id="test-456")
    state.superpowers_plan = {
        "intent_id": "intent-001",
        "success_criteria": ["All tests pass"],
        "scope_boundary": {"include": ["src/"], "exclude": ["tests/"]}
    }
    assert state.superpowers_plan["intent_id"] == "intent-001"
