import pytest
from nexus.core.crystal_analyzer import TraumaEngine
from nexus.core.state_contracts import NexusState, StepRecord
from datetime import datetime

def test_trauma_capture_on_audit_failure():
    """驗證 TraumaEngine 能捕捉 A 階段的失敗 (Phase 4 RED)"""
    state = NexusState(task_id="test-trauma-1")
    
    # 模擬 A 階段失敗
    state.steps_history.append(StepRecord(
        phase="A", step_id="A-1", status="rejected",
        started_at=datetime.now(),
        metadata={"error_type": "SecurityViolation"}
    ))
    
    # 觸發引擎
    TraumaEngine.process_failures(state)
    
    # 驗證
    assert len(state.autonomic_weights.trauma_records) == 1
    record = state.autonomic_weights.trauma_records[0]
    assert record.failure_signature == "SecurityViolation"
    assert record.penalty < 0
    assert state.learning_velocity < 1.0
