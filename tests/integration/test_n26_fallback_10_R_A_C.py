from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
from nexus.core.belief_contracts import CapabilityExecutionPlan


def _plan() -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(plan_id="test-n26", task_id="n26", phases=["R"])


def _test_executor(name: str) -> None:
    fn = EXECUTOR_REGISTRY.get(name)
    assert fn is not None, f"{name} not in registry"
    plan = _plan()
    r = fn(plan, "test task")
    assert r.invoked, f"{name}: invoked={r.invoked}"
    assert r.gate_passed, f"{name}: gate_passed={r.gate_passed}"
    assert r.telemetries["wall_time_ms"] > 0, f"{name}: wall_time_ms=0"


def test_exec_nightshift_runs() -> None:
    _test_executor("nightshift")


def test_exec_battle_swarm_runs() -> None:
    _test_executor("battle_swarm")


def test_exec_sandbox_runner_runs() -> None:
    _test_executor("sandbox_runner")


def test_exec_dual_loop_runs() -> None:
    _test_executor("dual_loop")


def test_exec_ultra_review_runs() -> None:
    _test_executor("ultra_review")


def test_exec_learning_closure_runs() -> None:
    _test_executor("learning_closure")


def test_exec_metabolism_resume_runs() -> None:
    _test_executor("metabolism_resume")


def test_exec_promotion_engine_runs() -> None:
    _test_executor("promotion_engine")


def test_exec_subagent_outcome_service_runs() -> None:
    _test_executor("subagent_outcome_service")


def test_exec_attempt_settlement_service_runs() -> None:
    _test_executor("attempt_settlement_service")
