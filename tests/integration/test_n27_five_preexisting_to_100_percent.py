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


def _assert_fail_closed(
    name: str,
    error: str,
    *,
    status: str | None = "BLOCKED",
    invoked: bool = True,
) -> None:
    # Stub success was removed on purpose (99c8295ba, 13df4578d, 7ae787b81; #1850 archive):
    # the executor now fails closed and reports the specific reason below.
    fn = EXECUTOR_REGISTRY.get(name)
    assert fn is not None, f"{name} not in registry"
    plan = _plan()
    r = fn(plan, "test task")
    assert r.invoked is invoked, f"{name}: invoked={r.invoked}"
    assert r.gate_passed is False, f"{name}: gate_passed={r.gate_passed}"
    assert r.outcome.get("semantic_status") == status, f"{name}: {r.outcome}"
    assert r.outcome.get("error") == error, f"{name}: {r.outcome}"


def _assert_retired(name: str) -> None:
    # Executor-only key with no planner node, archived 2026-10-13 (ARCHIVED_2026-10-13.md, #1906):
    # the historical node id is kept and now asserts the key is unreachable.
    assert name not in EXECUTOR_REGISTRY, f"{name} must not be registered"


def test_exec_aos_oracle_invoked_true() -> None:
    _assert_retired("aos_oracle")


def test_exec_autonomic_router_invoked_true() -> None:
    _test_executor("autonomic_router")


def test_exec_claim_gate_invoked_true() -> None:
    _assert_fail_closed("claim_gate", "missing_real_claim_context", status=None, invoked=False)


def test_exec_reflex_loop_invoked_true() -> None:
    _assert_retired("reflex_loop")


def test_exec_zero_trust_v2_behavior_invoked_true() -> None:
    _assert_retired("zero_trust_v2_behavior")


def test_all_36_executors_real_execution_100_percent() -> None:
    # Executors that are not invoked now fail closed with a specific archived/missing-context
    # reason instead of a stub success (99c8295ba, 13df4578d, #1850 archive). Every other
    # registered executor is invoked.
    plan = _plan()
    not_invoked = {}
    for name in sorted(EXECUTOR_REGISTRY):
        r = EXECUTOR_REGISTRY[name](plan, "test task")
        if not r.invoked:
            not_invoked[name] = r.outcome.get("error")
    assert not_invoked == {
        "benchmark": "archived_fake_benchmark_2026-10-12",
        "claim_gate": "missing_real_claim_context",
        "federation": "archived_federation_2026-10-12",
        "integration_manager": "archived_retired_integration_manager_2026-10-13",
        "learning_closure": "archived_hollow_learning_closure_2026-10-12",
        "llm_judge_panel": "archived_alias_llm_judge_panel_2026-10-13",
        "oracle_shadow": "archived_oracle_shadow_2026-10-12",
        "stress_test": "archived_hollow_stress_test_2026-10-12",
        "swarm_quiet_moment": "archived_echo_swarm_quiet_moment_2026-10-13",
        "ui_validator": "archived_ui_validator_2026-10-12",
    }
