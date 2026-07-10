from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
from nexus.core.belief_contracts import CapabilityExecutionPlan


def _plan() -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(plan_id="test-n27", task_id="n27")


def _test_executor(name: str) -> None:
    fn = EXECUTOR_REGISTRY.get(name)
    assert fn is not None, f"{name} not in registry"
    plan = _plan()
    r = fn(plan, "test task")
    assert r.invoked, f"{name}: invoked={r.invoked}"
    assert r.gate_passed, f"{name}: gate_passed={r.gate_passed}"
    assert r.telemetries["wall_time_ms"] > 0, f"{name}: wall_time_ms=0"


def test_exec_aos_oracle_invoked_true() -> None:
    _test_executor("aos_oracle")


def test_exec_autonomic_router_invoked_true() -> None:
    _test_executor("autonomic_router")


def test_exec_claim_gate_invoked_true() -> None:
    _test_executor("claim_gate")


def test_exec_reflex_loop_invoked_true() -> None:
    _test_executor("reflex_loop")


def test_exec_zero_trust_v2_behavior_invoked_true() -> None:
    _test_executor("zero_trust_v2_behavior")


def test_all_36_executors_real_execution_100_percent() -> None:
    plan = _plan()
    failed = []
    for name in sorted(EXECUTOR_REGISTRY):
        fn = EXECUTOR_REGISTRY[name]
        r = fn(plan, "test task")
        if not r.invoked:
            failed.append(f"{name}: {r.outcome.get('error', 'unknown')[:80]}")
    assert not failed, f"  {'; '.join(failed)}"
