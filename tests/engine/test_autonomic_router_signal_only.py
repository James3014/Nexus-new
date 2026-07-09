import pytest
from nexus.engine.autonomic_router import AutonomicRouter, ExecutionPlan
from nexus.core.state_contracts import NexusState


@pytest.fixture
def router(tmp_path):
    knowledge_dir = tmp_path / "nexus" / "knowledge"
    knowledge_dir.mkdir(parents=True)
    policy_file = knowledge_dir / "policy_memory.jsonl"
    policy_file.write_text("")
    return AutonomicRouter(project_root=str(tmp_path))


def test_autonomic_router_no_writes_autonomic_route(router):
    task = "update docs entry"
    state = NexusState(task_id="test_p30_a")
    forecast = {"est_tokens": 1500}
    router.route(task, state, forecast)
    assert "autonomic_route" not in state.metadata


def test_autonomic_router_no_writes_swarm_mode(router):
    task = "update docs entry"
    state = NexusState(task_id="test_p30_b")
    forecast = {"est_tokens": 1500}
    router.route(task, state, forecast)
    assert "swarm_mode" not in state.metadata


def test_autonomic_router_no_writes_force_external(router):
    task = "update docs entry"
    state = NexusState(task_id="test_p30_c")
    forecast = {"est_tokens": 1500}
    router.route(task, state, forecast)
    assert "force_external" not in state.metadata


def test_autonomic_router_still_writes_est_tokens(router):
    task = "update docs entry"
    state = NexusState(task_id="test_p30_d")
    forecast = {"est_tokens": 2500}
    router.route(task, state, forecast)
    assert state.metadata.get("est_tokens") == 2500


def test_autonomic_router_still_writes_autonomic_reason(router):
    task = "update docs entry"
    state = NexusState(task_id="test_p30_e")
    forecast = {"est_tokens": 1500}
    router.route(task, state, forecast)
    assert "autonomic_reason" in state.metadata
    assert isinstance(state.metadata["autonomic_reason"], str)
    assert len(state.metadata["autonomic_reason"]) > 0


def test_execution_plan_has_mode_hint_field():
    plan = ExecutionPlan(mode="standard", reason="test", confidence=1.0)
    assert hasattr(plan, "mode_hint")
    assert plan.mode_hint == ""


def test_autonomic_router_route_returns_mode_hint(router):
    task = "update docs entry"
    state = NexusState(task_id="test_p30_g")
    forecast = {"est_tokens": 1500}
    plan = router.route(task, state, forecast)
    assert plan.mode_hint == plan.mode
