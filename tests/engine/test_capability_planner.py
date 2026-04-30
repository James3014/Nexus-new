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
    assert {"swarm", "drone"} <= set(plan["pending_capabilities"])
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


def test_capability_planner_default_scoring_matches_legacy_formula():
    plan = CapabilityPlanner().plan(
        task_desc="Repair a candidate-heavy bug with DDTree pruning",
        task_type="public_test_repair",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {"risk_score": 60, "candidate_count": 4},
            "capability_stack": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "acceleration_layers": ["ddtree"],
            },
        },
    ).to_dict()

    trace = {item["capability"]: item for item in plan["decision_trace"]}
    assert trace["ddtree"]["score_delta"] == 3
    assert trace["ddtree"]["score_components"] == {
        "benefit": 3.0,
        "risk_reduction": 1.0,
        "cost_penalty": 1.0,
    }
    assert trace["ddtree"]["scoring_weights"] == {
        "benefit_weight": 1.0,
        "risk_weight": 1.0,
        "cost_weight": 1.0,
    }


def test_capability_planner_accepts_cost_risk_scoring_weights():
    plan = CapabilityPlanner().plan(
        task_desc="Repair a candidate-heavy bug with DDTree pruning",
        task_type="public_test_repair",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {"risk_score": 60, "candidate_count": 4},
            "capability_stack": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "acceleration_layers": ["ddtree"],
            },
        },
        budget={"scoring": {"benefit_weight": 1.0, "risk_weight": 2.0, "cost_weight": 3.0}},
    ).to_dict()

    trace = {item["capability"]: item for item in plan["decision_trace"]}
    assert trace["ddtree"]["score_delta"] == 2
    assert trace["ddtree"]["score_components"] == {
        "benefit": 3.0,
        "risk_reduction": 2.0,
        "cost_penalty": 3.0,
    }
    assert trace["ddtree"]["scoring_weights"] == {
        "benefit_weight": 1.0,
        "risk_weight": 2.0,
        "cost_weight": 3.0,
    }


def test_capability_planner_ignores_invalid_scoring_weights():
    plan = CapabilityPlanner().plan(
        task_desc="Repair a candidate-heavy bug with DDTree pruning",
        task_type="public_test_repair",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {"risk_score": 60, "candidate_count": 4},
            "capability_stack": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "acceleration_layers": ["ddtree"],
            },
        },
        budget={"scoring": {"benefit_weight": "bad", "risk_weight": None, "cost_weight": {}}},
    ).to_dict()

    trace = {item["capability"]: item for item in plan["decision_trace"]}
    assert trace["ddtree"]["score_delta"] == 3
    assert trace["ddtree"]["scoring_weights"] == {
        "benefit_weight": 1.0,
        "risk_weight": 1.0,
        "cost_weight": 1.0,
    }


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


def test_default_capability_nodes_cover_full_nexus_capability_registry():
    nodes = default_capability_nodes()
    expected = {
        "direct_mode",
        "memory",
        "lancedb",
        "belief",
        "learn_mode",
        "learn_scheduler",
        "learn_phase_slo",
        "research_route",
        "research_control_plane",
        "mempalace_gate",
        "artifact_gate",
        "claim_gate",
        "delivery_gate",
        "acceptance_check",
        "sandbox",
        "benchmark",
        "meta_opt",
        "autonomic_router",
        "pregate",
        "forecast_gate",
        "plan_quality_gate",
        "xray",
        "repair_loop",
        "multi_agent",
        "file_lock",
        "integration_manager",
        "ui_validator",
        "stress_test",
        "registry_sync",
        "metabolism",
        "oracle_shadow",
        "federation",
    }

    assert expected <= set(nodes)
    assert nodes["delivery_gate"].default_state == "required"
    assert nodes["memory"].category == "memory"
    assert nodes["autonomic_router"].maturity == "prototype"
    assert nodes["oracle_shadow"].maturity == "experimental"
    assert "gate_verdict" in nodes["delivery_gate"].evidence_outputs
    assert "policy_verdict" in nodes["mempalace_gate"].evidence_outputs


def test_capability_planner_maps_public_governance_task_to_review_and_reasoning():
    plan = CapabilityPlanner().plan(
        task_desc="Refactor a credential scrubber while preserving the governance boundary: never weaken secret redaction.",
        task_type="public_refactor",
        route={
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10, "candidate_count": 1},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        pillars={"lancedb": {"hits": 0}},
        codeintel={"impact_report_present": True},
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"codeintel", "research", "ultra_review", "mempalace_gate", "artifact_gate", "claim_gate"} <= selected


def test_capability_planner_maps_repair_and_trust_tasks_to_dynamic_controls():
    repair_plan = CapabilityPlanner().plan(
        task_desc="Repair a flaky-looking timeout calculation without deleting assertions.",
        task_type="public_test_repair",
        route={
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10, "candidate_count": 1},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        pillars={"lancedb": {"hits": 0}},
    ).to_dict()
    trust_plan = CapabilityPlanner().plan(
        task_desc="Fix an incident classifier that over-trusts a passing smoke test without semantic evidence.",
        task_type="public_ops_research",
        route={
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10, "candidate_count": 1},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        pillars={"lancedb": {"hits": 0}},
    ).to_dict()

    assert {"autoreason", "ddtree", "repair_loop"} <= set(repair_plan["selected_capabilities"])
    assert "autoreason" in set(trust_plan["selected_capabilities"])


def test_capability_planner_selects_memory_belief_and_preflight_governance():
    plan = CapabilityPlanner().plan(
        task_desc="Fix a trust-sensitive regression with prior evidence and low confidence.",
        task_type="bug",
        route={
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 45,
                "adjusted_root_cause_confidence": 0.52,
                "candidate_count": 1,
                "memory_hits": 2,
                "findings_hits": 1,
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        pillars={"lancedb": {"hits": 3}},
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"memory", "lancedb", "belief", "pregate", "plan_quality_gate", "delivery_gate"} <= selected
    assert "sandbox" not in selected


def test_capability_planner_selects_sandbox_for_high_risk_governance():
    plan = CapabilityPlanner().plan(
        task_desc="Refactor credential scrubber without weakening secret redaction governance.",
        task_type="bug",
        route={
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 80, "candidate_count": 1},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"ultra_review", "sandbox", "pregate", "plan_quality_gate", "forecast_gate"} <= selected


def test_capability_planner_selects_second_wave_platform_capabilities():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Run a baseline direct repair that must learn citation SLOs, coordinate multi-agent owner "
            "file lock worktree integration, update registry skills, distill a resume checkpoint, "
            "and produce a benchmark public report with oracle shadow stress coverage."
        ),
        task_type="platform_integration",
        route={
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 65,
                "adjusted_root_cause_confidence": 0.7,
                "candidate_count": 1,
                "is_cross_module_task": True,
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {
        "direct_mode",
        "learn_mode",
        "learn_phase_slo",
        "research_route",
        "multi_agent",
        "file_lock",
        "integration_manager",
        "registry_sync",
        "metabolism",
        "benchmark",
        "oracle_shadow",
        "stress_test",
    } <= selected


def test_capability_planner_selects_acceptance_xray_forecast_and_research_control_gap_capabilities():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Run research:auto-flow experiment with rollback and semantic status, "
            "then produce an acceptance closeout public claim after xray deep scan "
            "of dependency graph blast radius and forecast preflight risk."
        ),
        task_type="platform_route_diagnostic",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 82,
                "adjusted_root_cause_confidence": 0.55,
                "candidate_count": 2,
                "is_cross_module_task": True,
            },
            "capability_stack": {"selected_capabilities": ["hyper_sprint"]},
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"acceptance_check", "forecast_gate", "xray", "research_control_plane"} <= selected


def test_capability_planner_selects_msa_capabilities_from_explicit_task_type_words():
    plan = CapabilityPlanner().plan(
        task_desc="Cross-module refactor: align swarm ownership, drone handoff, and NightShift fallback.",
        task_type="cross_module_refactor_swarm_drone_nightshift",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 45,
                "adjusted_root_cause_confidence": 0.72,
                "candidate_count": 1,
                "is_cross_module_task": True,
            },
            "capability_stack": {"selected_capabilities": ["hyper_sprint"]},
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"swarm", "drone", "nightshift"} <= selected
