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


def test_autonomic_routing_service_swarm_route_sets_metadata():
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
    assert state.metadata["swarm_mode"] is True
    assert state.metadata["est_tokens"] == 77
    context_hub.make_pre_routing_decision.assert_called_once()


def test_autonomic_routing_service_external_skill_injects_instructions(tmp_path: Path):
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
    assert state.metadata["active_external_skill"] == "external-skill"
    assert "[EXTERNAL SKILL INSTRUCTIONS: external-skill]" in state.metadata["task_description"]
