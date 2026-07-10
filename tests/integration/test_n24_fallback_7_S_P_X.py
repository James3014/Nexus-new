from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
from nexus.core.belief_contracts import CapabilityExecutionPlan


def _plan() -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(plan_id="test-n24", task_id="n24", phases=["S"])


def _test_executor(name: str) -> None:
    fn = EXECUTOR_REGISTRY.get(name)
    assert fn is not None, f"{name} not in registry"
    plan = _plan()
    r = fn(plan, "test task")
    assert r.invoked, f"{name}: invoked={r.invoked}"
    assert r.gate_passed, f"{name}: gate_passed={r.gate_passed}"
    assert r.telemetries["wall_time_ms"] > 0, f"{name}: wall_time_ms=0"


def test_exec_policy_capability_gate_runs() -> None:
    _test_executor("policy_capability_gate")


def test_exec_nightshift_runner_service_runs() -> None:
    _test_executor("nightshift_runner_service")


def test_exec_decision_formula_engine_runs() -> None:
    _test_executor("decision_formula_engine")


def test_exec_codeintel_runs() -> None:
    _test_executor("codeintel")


def test_exec_lancedb_runs() -> None:
    _test_executor("lancedb")


def test_exec_research_runs() -> None:
    _test_executor("research")


def test_exec_research_and_source_discipline_runs() -> None:
    _test_executor("research_and_source_discipline")
