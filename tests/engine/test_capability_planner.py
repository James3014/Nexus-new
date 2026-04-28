from __future__ import annotations

from nexus.engine.capability_planner import CapabilityPlanner, default_capability_nodes


def test_capability_planner_builds_constrained_composition_trace():
    plan = CapabilityPlanner().plan(
        task_desc="Fix cross-module websocket timeout race with split worker validation",
        task_type="bug",
        route={
            "should_research": True,
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 86,
                "adjusted_root_cause_confidence": 0.42,
                "candidate_count": 4,
                "memory_hits": 1,
                "findings_hits": 1,
                "is_cross_module_task": True,
                "has_hard_signal": True,
            },
            "capability_stack": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "acceleration_layers": ["ddtree"],
                "governance_layers": ["ultra_review"],
            },
        },
        pillars={"lancedb": {"hits": 0}},
        codeintel={"impact_report_present": True},
        phase_trace={"P": "route_built"},
    ).to_dict()

    assert plan["schema_version"] == "nexus_capability_plan_v1"
    assert plan["planner_mode"] == "dry_run"
    assert {"mempalace_gate", "artifact_gate", "claim_gate"} <= set(plan["required_capabilities"])
    assert {"codeintel", "research", "hyper", "autoreason", "ddtree", "ultra_review", "swarm", "drone"} <= set(
        plan["conditional_capabilities"]
    )
    assert "claim_fail_closed" in plan["constraints"]
    assert any(item["capability"] == "ultra_review" and item["state"] == "conditional" for item in plan["decision_trace"])
    assert any(item["phase"] == "A" and "claim_and_artifact_fail_closed" in item["replan_reasons"] for item in plan["replan_trace"])


def test_capability_planner_downgrades_optional_cost_but_keeps_gates():
    plan = CapabilityPlanner().plan(
        task_desc="Fix long cross-module timeout",
        task_type="bug",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 95,
                "adjusted_root_cause_confidence": 0.4,
                "candidate_count": 4,
                "is_cross_module_task": True,
                "has_hard_signal": True,
            },
            "capability_stack": {"selected_capabilities": ["hyper_sprint", "autoreason"], "governance_layers": ["ultra_review"]},
        },
        budget={"max_cost": 12},
    ).to_dict()

    assert {"mempalace_gate", "artifact_gate", "claim_gate"} <= set(plan["selected_capabilities"])
    assert plan["forbidden_capabilities"]
    assert not {"mempalace_gate", "artifact_gate", "claim_gate"} & set(plan["forbidden_capabilities"])


def test_default_capability_nodes_cover_core_space():
    nodes = default_capability_nodes()
    for name in (
        "codeintel",
        "research",
        "hyper",
        "nightshift",
        "swarm",
        "drone",
        "ultra_review",
        "autoreason",
        "ddtree",
    ):
        assert name in nodes
        assert nodes[name].phase_hooks
