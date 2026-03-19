import pytest
from nexus.engine.phases.planner import PlannerPhaseHandler
from nexus.core.state_contracts import NexusState

def test_intent_gate_fuzzy_input():
    """驗證 Intent Gate 排除模糊輸入 (RED CASE)"""
    planner = PlannerPhaseHandler(".", "/tmp/nexus_run")
    state = NexusState(task_id="test-fuzzy")
    
    # 模糊指令
    context = {"task": "幫我改代碼"}
    
    result = planner.run(state, context)
    # 預期 result 中應包含 intent_pass=False 或引發特定異常
    assert result.get("intent_pass") == False
    assert "簡短" in result.get("refusal_reason", "")

def test_intent_gate_clear_input():
    """驗證清晰指令通過 (GREEN CASE)"""
    planner = PlannerPhaseHandler(".", "/tmp/nexus_run")
    state = NexusState(task_id="test-clear")
    
    # 清晰指令
    context = {"task": "在 nexus/core/state_contracts.py 中新增一個 TraumaRecord 類別"}
    
    result = planner.run(state, context)
    assert result.get("intent_pass") == True
