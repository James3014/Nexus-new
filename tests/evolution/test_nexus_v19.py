import pytest
import os
from pathlib import Path
from nexus.engine.planner_graph import TacticalGraphPlanner
from nexus.core.hardened_validator import NexusHardenedValidator
from nexus.core.neural_aggregator import NexusNeuralAggregator
from nexus.learning.vector_cache import VectorCache

def test_swarm_dag_planning(tmp_path):
    """驗證 DAG 任務調度與依賴感知。"""
    planner = TacticalGraphPlanner(tmp_path)
    planner.add_task("A", "Task A")
    planner.add_task("B", "Task B", deps=["A"])
    
    # Init: 只有 A 是 Ready
    ready = planner.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].id == "A"
    
    # A 完成後，B 應該 Ready
    ready[0].status = "completed"
    ready_b = planner.get_ready_tasks()
    assert len(ready_b) == 1
    assert ready_b[0].id == "B"

def test_ast_security_interception():
    """驗證 AST 物理硬化驗證器是否能攔截危險調用。"""
    validator = NexusHardenedValidator()
    
    # 安全代碼
    safe_code = "print('hello world')"
    assert validator.validate_code(safe_code)["passed"] is True
    
    # 危險代碼 (os.system)
    dangerous_code = "import os; os.system('rm -rf /')"
    result = validator.validate_code(dangerous_code)
    assert result["passed"] is False
    assert any("DANGEROUS_CALL_DETECTED" in e for e in result["errors"])
    
    # 危險代碼 (eval)
    eval_code = "eval('1+1')"
    assert validator.validate_code(eval_code)["passed"] is False

def test_neural_aggregator_compression():
    """驗證 Triage 壓縮邏輯是否有效排除雜訊。"""
    aggregator = NexusNeuralAggregator()
    events = [
        {"kind": "heartbeat", "message": "ping"},
        {"kind": "heartbeat", "message": "ping"},
        {"kind": "error", "message": "Physical fault in sector 7"},
        {"kind": "completed", "message": "Mission success"}
    ]
    
    snapshot = aggregator.triage_summarize(events)
    # 驗證包含關鍵詞
    assert "CRITICAL" in snapshot
    assert "sector 7" in snapshot
    assert "RESULT" in snapshot
    # 驗證雜訊被抑制
    assert "Heartbeat updates: 2" in snapshot
    assert "ping" not in snapshot
