import pytest
from nexus.core.capability_gate import CapabilityGate, Phase
from nexus.core.planner_executor import Planner, Executor
from nexus.core.ci_healer import CIHealer
from nexus.core.state_contracts import NexusState
from nexus.core.state_io import StateIO

# 🎭 P0: JIT Tool Injection
def test_jit_tool_reduction():
    gate = CapabilityGate()
    tools = gate.managed_toolsets("P") # Planning phase
    assert len(tools) <= 10
    assert "nexus:lookup-skill" in tools
    assert "edit_file" not in tools # Decoupled!

# 🧠 P1: Planner/Executor
def test_planner_executor_decoupling():
    state = NexusState(task_id="dec-test")
    state.current_phase = "P"
    
    planner = Planner(state)
    plan = planner.generate_plan("Fix bug")
    assert "steps" in plan
    
    executor = Executor(state)
    res = executor.execute_plan(plan)
    assert res["status"] == "SUCCESS"

# 🩹 P2: CI Healer
def test_ci_healer_trigger():
    healer = CIHealer(".")
    log = "Traceback: AttributeError: 'NoneType' object has no attribute 'get'"
    res = healer.on_ci_fail(log)
    assert res["status"] == "SELF_HEAL_TRIGGERED"
    assert "AttributeError" in res["detected_error"]

# 🔄 P4: Stateful Backtracking
def test_state_backtracking_trigger(tmp_path):
    state_file = tmp_path / ".musestate"
    io = StateIO(str(tmp_path), state_file=str(state_file))
    
    state = NexusState(task_id="back-test")
    state.metadata["phase_failures"] = 3
    
    # Trigger load_checkpoint which has the backtracking logic
    io.load_checkpoint(state)
    
    # Should have reset failure count
    assert state.metadata["phase_failures"] == 0
