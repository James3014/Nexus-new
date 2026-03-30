import pytest
from nexus.executors.protocol import (
    ExecutorInput, ExecutorOutput, ExecutorStatusEnum, 
    ContextPackSchema, ProviderErrorType, TaskInstruction
)

def test_executor_input_instantiation():
    """驗證 ExecutorInput 是否能正確封裝上下文。"""
    ctx = ContextPackSchema(files={"app.py": "content"})
    instr = TaskInstruction(task_id="T1", objective="fix it")
    inp = ExecutorInput(
        task_id="T1",
        phase="repair",
        workspace_root="/tmp/ws",
        context_pack=ctx,
        instruction=instr
    )
    assert inp.task_id == "T1"
    assert inp.context_pack.files["app.py"] == "content"
    assert inp.instruction.objective == "fix it"

def test_executor_output_instantiation():
    """驗證 ExecutorOutput 是否能正確回傳狀態。"""
    out = ExecutorOutput(
        executor_name="MockExecutor",
        phase="repair",
        status=ExecutorStatusEnum.SUCCESS,
        patch_generated=True,
        evidence_present=True,
        raw_exit_code=0,
        summary="Done"
    )
    assert out.status == ExecutorStatusEnum.SUCCESS
    assert out.patch_generated is True
    assert out.evidence_present is True

def test_provider_error_enum():
    """驗證 Provider 錯誤類型的 Enum 值。"""
    assert ProviderErrorType.QUOTA_LIMIT.value == "QUOTA_LIMIT"
    assert ProviderErrorType.SCHEMA_VIOLATION.value == "SCHEMA_VIOLATION"
