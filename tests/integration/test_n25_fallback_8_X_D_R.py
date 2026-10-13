from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
from nexus.core.belief_contracts import CapabilityExecutionPlan


def _plan() -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(plan_id="test-n25", task_id="n25", phases=["X"])


def _test_executor(name: str) -> None:
    fn = EXECUTOR_REGISTRY.get(name)
    assert fn is not None, f"{name} not in registry"
    plan = _plan()
    r = fn(plan, "test task")
    assert r.invoked, f"{name}: invoked={r.invoked}"
    assert r.gate_passed, f"{name}: gate_passed={r.gate_passed}"
    assert r.telemetries["wall_time_ms"] > 0, f"{name}: wall_time_ms=0"


def _assert_retired(name: str) -> None:
    # Executor-only key with no planner node, archived 2026-10-13 (ARCHIVED_2026-10-13.md, #1906):
    # the historical node id is kept and now asserts the key is unreachable.
    assert name not in EXECUTOR_REGISTRY, f"{name} must not be registered"


def test_exec_learn_refresh_service_runs() -> None:
    _assert_retired("learn_refresh_service")


def test_exec_learn_scheduler_service_runs() -> None:
    _test_executor("learn_scheduler_service")


def test_exec_belief_runs() -> None:
    _test_executor("belief")


def test_exec_autoreason_runs() -> None:
    _test_executor("autoreason")


def test_exec_repair_loop_runs() -> None:
    _test_executor("repair_loop")


def test_exec_hyper_sprint_runs() -> None:
    _test_executor("hyper_sprint")


def test_exec_swarm_multi_agent_runs() -> None:
    _test_executor("swarm_multi_agent")


def test_exec_drone_runs() -> None:
    _test_executor("drone")
