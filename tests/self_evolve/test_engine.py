import pytest
from nexus.core.self_evolve_engine import SelfEvolveEngine
from nexus.core.state_contracts import NexusState

def test_self_evolve_engine_init():
    state = NexusState(task_id="test-engine")
    engine = SelfEvolveEngine(state, workspace=".")
    assert engine.workspace == "."
    assert engine.state.task_id == "test-engine"

def test_self_evolve_full_cycle():
    state = NexusState(task_id="test-cycle")
    state.metadata["aos_score"] = 108
    engine = SelfEvolveEngine(state, workspace=".")
    
    res = engine.run_evolution_cycle(target_aos=120, features=["k8s_swarm", "acl"])
    assert res["status"] == "EVOLVE_COMPLETE"
    assert res["new_aos"] == 120
    assert state.metadata["aos_score"] == 120

def test_self_evolve_failure_simulation():
    # 測試執行失敗時的返回值
    state = NexusState(task_id="test-fail")
    engine = SelfEvolveEngine(state, workspace=".")
    
    # 這裡可以透過 mock Executor.execute_plan 來測試 Healer 觸發
    # 暫時核驗邏輯路徑
    from unittest.mock import MagicMock
    engine.executor.execute_plan = MagicMock(return_value={"status": "FAILED"})
    
    res = engine.run_evolution_cycle(target_aos=120, features=["fail_test"])
    assert res["status"] == "HEAL_REQUIRED"
    assert res["details"]["status"] == "SELF_HEAL_TRIGGERED"
