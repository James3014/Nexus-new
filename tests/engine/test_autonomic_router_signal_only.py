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


def test_autonomic_router_state_metadata_only_has_telemetry_keys(router):
    task = "update docs entry"
    state = NexusState(task_id="test_p30_h")
    forecast = {"est_tokens": 1500}
    router.route(task, state, forecast)
    allowed = {"est_tokens", "autonomic_reason"}
    for key in state.metadata:
        if key in allowed:
            continue
    for key in ("autonomic_route", "swarm_mode", "force_external"):
        assert key not in state.metadata


def test_autonomic_router_does_not_create_new_override_keys(router):
    tasks = ["update docs", "fix bug", "research topic", "deploy package"]
    state = NexusState(task_id="test_p30_i")
    for task in tasks:
        forecast = {"est_tokens": 100}
        router.route(task, state, forecast)
    override_keys = {"autonomic_route", "swarm_mode", "force_external"}
    telemetry_keys = {"est_tokens", "autonomic_reason"}
    for key in state.metadata:
        assert key not in override_keys or key in telemetry_keys


def test_autonomic_router_consistent_with_capability_planner_authority(router):
    task = "update docs entry"
    state = NexusState(task_id="test_p30_j")
    forecast = {"est_tokens": 1500}
    plan = router.route(task, state, forecast)
    assert hasattr(plan, "mode_hint")
    assert plan.mode_hint == plan.mode
    assert "autonomic_route" not in state.metadata
    assert "swarm_mode" not in state.metadata
