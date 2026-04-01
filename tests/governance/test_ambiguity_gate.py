import pytest
from nexus.engine.phases.planner import PlannerPhaseHandler
from nexus.core.state_contracts import NexusState

def test_ambiguity_high_score():
    planner = PlannerPhaseHandler(".", "/tmp")
    # 模糊指令：無路徑、短、含模糊詞
    score = planner.calculate_ambiguity_score("請修一下功能")
    assert score > 0.7

def test_ambiguity_low_score():
    planner = PlannerPhaseHandler(".", "/tmp")
    # 明確指令：全路徑、長度足夠
    score = planner.calculate_ambiguity_score("修正 nexus/core/orchestrator.py 中的併發死鎖問題")
    assert score < 0.5

def test_clarification_gate_interception():
    planner = PlannerPhaseHandler(".", "/tmp")
    state = NexusState("TASK_001")
    context = {"task": "優化一下"}
    
    # 模擬執行 run
    result, msg = planner._guard_intent(context["task"])
    assert result is False
    assert "🛑 [ClarificationGate]" in msg
