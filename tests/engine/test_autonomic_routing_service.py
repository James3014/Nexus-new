from pathlib import Path
from unittest.mock import MagicMock, patch

from nexus.core.state_contracts import NexusState
from nexus.engine.autonomic_routing_service import AutonomicRoutingService


def test_autonomic_routing_service_direct_mode_skips_context_hub():
    context_hub = MagicMock()
    service = AutonomicRoutingService(
        project_root=Path("/tmp/nexus_test"),
        memory_service=MagicMock(),
        context_hub=context_hub,
    )
    state = NexusState(task_id="direct-1")
    state.metadata["direct_mode"] = True
    state.metadata["direct_mode_reason"] = "explicit_user_repair_spec"

    out = service.apply(
        state=state,
        task_id="direct-1",
        task_desc="fix regression",
        task_type="bug",
        forecast={"est_tokens": 123},
    )

    assert out["mode"] == "direct_mode"
    assert state.metadata["autonomic_route"] == "direct_mode"
    assert state.metadata["autonomic_reason"] == "explicit_user_repair_spec"
    assert state.metadata["est_tokens"] == 123
    context_hub.make_pre_routing_decision.assert_not_called()


def test_autonomic_routing_service_swarm_route_records_signal_without_executor_flag():
    context_hub = MagicMock()
    context_hub.make_pre_routing_decision.return_value = {"priority": "high"}
    service = AutonomicRoutingService(
        project_root=Path("/tmp/nexus_test"),
        memory_service=MagicMock(),
        context_hub=context_hub,
    )
    state = NexusState(task_id="route-1")

    exec_plan = MagicMock()
    exec_plan.mode = "swarm"
    exec_plan.reason = "high_risk"
    exec_plan.skill_id = ""
    exec_plan.signals = {"swarm_candidate": True, "policy_match_count": 16}
    exec_plan.matched_policies = ["POLICY-1"]

    with patch("nexus.engine.autonomic_router.AutonomicRouter") as router_cls:
        router_cls.return_value.route.return_value = exec_plan
        out = service.apply(
            state=state,
            task_id="route-1",
            task_desc="fix race condition",
            task_type="bug",
            forecast={"est_tokens": 77},
        )

    assert out["mode"] == "swarm"
    assert state.metadata["autonomic_route"] == "swarm"
    assert state.metadata["autonomic_reason"] == "high_risk"
    assert state.metadata["autonomic_route_source"] == "signal_provider"
    assert state.metadata["autonomic_signals"]["swarm_candidate"] is True
    assert state.metadata["autonomic_matched_policies"] == ["POLICY-1"]
    assert "swarm_mode" not in state.metadata
    assert state.metadata["est_tokens"] == 77
    context_hub.make_pre_routing_decision.assert_called_once()


def test_autonomic_routing_service_external_skill_signal_does_not_inject_instructions(tmp_path: Path):
    context_hub = MagicMock()
    context_hub.make_pre_routing_decision.return_value = {}
    service = AutonomicRoutingService(
        project_root=tmp_path,
        memory_service=MagicMock(),
        context_hub=context_hub,
    )
    state = NexusState(task_id="route-2")
    state.metadata["task_description"] = "fix bug"

    skill_md = tmp_path / "skills" / "external" / "SKILL.md"
    skill_md.parent.mkdir(parents=True, exist_ok=True)
    skill_md.write_text("# External Skill\nUse strict verifier.", encoding="utf-8")

    exec_plan = MagicMock()
    exec_plan.mode = "external_skill"
    exec_plan.reason = "matched"
    exec_plan.skill_id = "external-skill-1"
    exec_plan.signals = {"external_skill_candidate": True}
    exec_plan.matched_policies = []

    with patch("nexus.engine.autonomic_router.AutonomicRouter") as router_cls, patch(
        "nexus.core.unified_registry.UnifiedRegistry"
    ) as registry_cls:
        router_cls.return_value.route.return_value = exec_plan
        registry = registry_cls.return_value
        registry.registry.get_by_task_id.return_value = {
            "name": "external-skill",
            "external_path": str(skill_md),
        }
        out = service.apply(
            state=state,
            task_id="route-2",
            task_desc="fix bug",
            task_type="bug",
            forecast={"est_tokens": 21},
        )

    assert out["mode"] == "external_skill"
    assert out["signals"]["external_skill_candidate"] is True
    assert "active_external_skill" not in state.metadata
    assert state.metadata["task_description"] == "fix bug"


def test_autonomic_routing_service_research_signal_does_not_force_external():
    context_hub = MagicMock()
    context_hub.make_pre_routing_decision.return_value = {}
    service = AutonomicRoutingService(
        project_root=Path("/tmp/nexus_test"),
        memory_service=MagicMock(),
        context_hub=context_hub,
    )
    state = NexusState(task_id="route-3")

    exec_plan = MagicMock()
    exec_plan.mode = "research_first"
    exec_plan.reason = "research requested"
    exec_plan.skill_id = ""
    exec_plan.signals = {"research_requested": True}
    exec_plan.matched_policies = []

    with patch("nexus.engine.autonomic_router.AutonomicRouter") as router_cls:
        router_cls.return_value.route.return_value = exec_plan
        out = service.apply(
            state=state,
            task_id="route-3",
            task_desc="research regression",
            task_type="bug",
            forecast={"est_tokens": 42},
        )

    assert out["mode"] == "research_first"
    assert state.metadata["autonomic_signals"]["research_requested"] is True
    assert "force_external" not in state.metadata
