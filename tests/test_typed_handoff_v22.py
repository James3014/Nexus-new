import pytest
from pydantic import ValidationError
from nexus.executors.protocol import ExecutorInput, ExecutorOutput, ExecutorStatusEnum, ContextPackSchema
from nexus.core.state_contracts import NexusState, StepRecord
from nexus.core.swarm_orchestrator import TypedHandoffAdapter
from datetime import datetime

def test_handoff_executor_output_to_state():
    # 1. 模擬執行器輸出 (Dataclass)
    mock_output = ExecutorOutput(
        executor_name="FlashExecutor",
        phase="D",
        status=ExecutorStatusEnum.SUCCESS,
        patch_generated=True,
        evidence_present=True,
        raw_exit_code=0,
        summary="Diagnosis PASSED",
        files_touched=["app.py"]
    )
    
    # 2. 模擬現有 NexusState (Pydantic)
    state = NexusState(task_id="task_123")
    
    # 3. 使用 Adapter 進行 Handoff
    adapter = TypedHandoffAdapter()
    updated_state = adapter.sync_output_to_state(state, mock_output)
    
    # 4. 驗證狀態更新
    assert updated_state.current_phase == "D"
    assert len(updated_state.steps_history) > 0
    assert updated_state.steps_history[-1].phase == "D"
    assert updated_state.steps_history[-1].status == "completed"

def test_invalid_phase_validation():
    adapter = TypedHandoffAdapter()
    state = NexusState(task_id="task_123")
    
    # 模擬無效 Phase
    invalid_output = ExecutorOutput(
        executor_name="ErrExecutor",
        phase="Z", # 無效的 Phase
        status=ExecutorStatusEnum.EXECUTION_FAIL,
        patch_generated=False,
        evidence_present=False,
        raw_exit_code=1
    )
    
    with pytest.raises(ValueError, match="Invalid phase: Z"):
        adapter.sync_output_to_state(state, invalid_output)
