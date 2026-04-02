from pathlib import Path
import pytest
from nexus.core.state_contracts import NexusState
from nexus.core.swarm_orchestrator import TypedHandoffAdapter
from nexus.executors.protocol import ExecutorOutput, ExecutorStatusEnum

def test_handoff_valid_phase():
    """驗證標準 Phase 是否能正確手接成功"""
    adapter = TypedHandoffAdapter()
    state = NexusState(task_id="test-task", aos_score=100.0)
    
    output = ExecutorOutput(
        executor_name="research_bot",
        phase="R",
        status=ExecutorStatusEnum.SUCCESS,
        patch_generated=False,
        evidence_present=True,
        summary="Found 3 patterns",
        raw_exit_code=0
    )
    
    updated_state = adapter.sync_output_to_state(state, output)
    assert len(updated_state.steps_history) == 1
    assert updated_state.steps_history[0].phase == "R"
    assert updated_state.current_phase == "R"

def test_handoff_research_mapping_success():
    """驗證研究長名稱 (RESEARCH) 能正確對接至 R"""
    adapter = TypedHandoffAdapter()
    state = NexusState(task_id="test-research", aos_score=100.0)
    
    output = ExecutorOutput(
        executor_name="felo-cli",
        phase="RESEARCH", 
        status=ExecutorStatusEnum.SUCCESS,
        patch_generated=False,
        evidence_present=True,
        summary="Research completed",
        raw_exit_code=0
    )
    
    updated_state = adapter.sync_output_to_state(state, output)
    assert updated_state.current_phase == "R"
    assert updated_state.steps_history[0].phase == "R"

def test_handoff_case_insensitivity():
    """驗證大小寫自動修正"""
    adapter = TypedHandoffAdapter()
    state = NexusState(task_id="test-lowercase", aos_score=100.0)
    
    output = ExecutorOutput(
        executor_name="research_bot",
        phase="r", # 小寫
        status=ExecutorStatusEnum.SUCCESS,
        patch_generated=False,
        evidence_present=True,
        summary="Lowercase phase test",
        raw_exit_code=0
    )
    
    updated_state = adapter.sync_output_to_state(state, output)
    assert updated_state.current_phase == "R"
