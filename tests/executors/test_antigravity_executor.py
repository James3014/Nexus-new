import pytest
from nexus.executors.antigravity import AntigravityExecutor
from nexus.executors.protocol import ExecutorInput, ContextPackSchema, ExecutorStatusEnum

def test_antigravity_executor_basic():
    """驗證 AntigravityExecutor (Stub) 是否符合協議規範。"""
    executor = AntigravityExecutor(model_name="antigravity-v2")
    ctx = ContextPackSchema(files={})
    inp = ExecutorInput(task_id="T2", phase="test", workspace_root="/tmp", context_pack=ctx)
    
    out = executor.execute(inp)
    
    assert out.status == ExecutorStatusEnum.SUCCESS
    assert out.executor_name == "antigravity_stub"
    assert out.meta["model_name"] == "antigravity-v2"
