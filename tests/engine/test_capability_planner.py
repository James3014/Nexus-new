from __future__ import annotations

from nexus.engine.capability_planner import CapabilityPlanner, default_capability_nodes
from nexus.engine.learning_policy_loader import (
    load_learning_policy_budget,
    load_route_cost_policy_budget,
    load_route_cost_policy_budget_from_env,
    load_s2t_policy_draft_budget,
    merge_runtime_s2t_policy_draft,
    route_cost_controls_for_task,
)


def test_capability_planner_builds_constrained_composition_trace():
    plan = CapabilityPlanner().plan(
        task_desc="Use research to fix cross-module websocket timeout race with split worker validation.",
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


def test_capability_nodes_include_runtime_callable_search_and_swarm_pause():
    nodes = default_capability_nodes()

    assert nodes["semantic_searcher"].dependencies == ("lancedb",)
    assert "semantic_refs" in nodes["semantic_searcher"].evidence_outputs
    assert nodes["swarm_quiet_moment"].dependencies == ("swarm",)
    assert "rollback" in nodes["swarm_quiet_moment"].evidence_outputs


def test_capability_nodes_include_semantic_research_runtime_capabilities():
    nodes = default_capability_nodes()

    expected = {
        "judge_panel",
        "llm_judge_panel",
        "asi_constraint_extractor",
        "architecture_scout",
        "external_doc_scout",
        "formal_report",
    }
    assert expected <= set(nodes)
    assert nodes["judge_panel"].dependencies == ("artifact_gate", "claim_gate")
    assert nodes["llm_judge_panel"].maturity == "legacy_alias"
    assert "panel_votes" in nodes["judge_panel"].evidence_outputs
    assert nodes["asi_constraint_extractor"].dependencies == ("mempalace_gate",)
    assert "extracted_constraints" in nodes["asi_constraint_extractor"].evidence_outputs
    assert nodes["architecture_scout"].dependencies == ("codeintel",)
    assert "blast_radius" in nodes["architecture_scout"].evidence_outputs
    assert nodes["external_doc_scout"].dependencies == ("research",)
    assert "citations" in nodes["external_doc_scout"].evidence_outputs
    assert nodes["formal_report"].dependencies == ("delivery_gate", "claim_gate")
    assert "formal_report_path" in nodes["formal_report"].evidence_outputs


def test_capability_planner_selects_runtime_callable_search_and_swarm_pause():
    plan = CapabilityPlanner().plan(
        task_desc="Cross-module swarm repair with semantic retrieval evidence",
        task_type="cross_module_refactor_swarm",
        route={
            "route_features": {
                "risk_score": 75,
                "is_cross_module_task": True,
                "candidate_count": 2,
            },
        },
        pillars={"lancedb": {"hits": 2}},
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"semantic_searcher", "swarm", "swarm_quiet_moment"} <= selected


def test_capability_planner_selects_semantic_research_runtime_capabilities():
    plan = CapabilityPlanner().plan(
        task_desc="Produce formal public report for repeated timeout plateau with external API uncertainty",
        task_type="public_report_bug_repair",
        route={
            "should_research": True,
            "route_features": {
                "adjusted_root_cause_confidence": 0.45,
                "candidate_count": 3,
                "claim_uncertainty": True,
                "doc_scout_hits": 2,
                "blocked_assumptions_count": 2,
                "plateau_detected": True,
                "benchmark_required": True,
            },
            "research_context": {"role": "architecture_scout"},
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {
        "judge_panel",
        "asi_constraint_extractor",
        "architecture_scout",
        "external_doc_scout",
        "formal_report",
    } <= selected


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
    assert trace["ddtree"]["cost_tier"] == "low"
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


def test_capability_planner_selects_memory_for_context_contract_tasks():
    plan = CapabilityPlanner().plan(
        task_desc="Sync code and docs after a renamed public contract field",
        task_type="public_docs_code_sync",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {"risk_score": 35, "candidate_count": 1, "memory_hits": 0, "findings_hits": 0},
            "capability_stack": {"selected_capabilities": ["hyper_sprint"]},
        },
    ).to_dict()

    assert "memory" in plan["selected_capabilities"]
    assert any(
        item["capability"] == "memory" and "context_contract_memory_needed" in item["reasons"]
        for item in plan["decision_trace"]
    )


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
    assert {"codeintel", "ultra_review", "mempalace_gate", "artifact_gate", "claim_gate"} <= selected
    assert "research" not in selected


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
            "route_features": {
                "risk_score": 10,
                "candidate_count": 2,
                "candidate_factory_readiness_estimate": {
                    "ready": True,
                    "status": "READY",
                    "estimated_candidates": 2,
                },
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        pillars={"lancedb": {"hits": 0}},
    ).to_dict()

    assert "repair_loop" in set(repair_plan["selected_capabilities"])
    assert "autoreason" not in set(repair_plan["selected_capabilities"])
    assert "ddtree" not in set(repair_plan["selected_capabilities"])
    assert "autoreason" in set(trust_plan["selected_capabilities"])


def test_capability_planner_blocks_repair_ranking_when_factory_skipped():
    uncertain_plan = CapabilityPlanner().plan(
        task_desc=(
            "Repair hidden verifier timeout where root cause is uncertain. "
            "Nexus wearing contract requires evidence, claim, and governance checks."
        ),
        task_type="public_test_repair",
        route={
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 10,
                "candidate_count": 1,
                "adjusted_root_cause_confidence": 0.5,
                "candidate_factory_readiness_estimate": {
                    "ready": False,
                    "status": "SKIPPED",
                    "estimated_candidates": 1,
                },
                "claim_uncertainty": True,
                "blocked_assumptions_count": 1,
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        pillars={"lancedb": {"hits": 0}},
    ).to_dict()

    assert "repair_loop" in set(uncertain_plan["selected_capabilities"])
    assert "autoreason" not in set(uncertain_plan["selected_capabilities"])
    assert "judge_panel" not in set(uncertain_plan["selected_capabilities"])


def test_capability_planner_ignores_benchmark_contract_only_learning_and_claim_noise():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Repair merge helper behavior without changing default values in normal path."
            "\n\nNexus wearing contract:"
            "\n- Artifact/Claim: treat completion claims as valid only when backed by checks."
            "\n- Governance: keep the solution inside scope."
        ),
        task_type="public_test_repair",
        route={
            "recommended_flow": "baseline",
            "should_research": False,
            "route_features": {
                "risk_score": 20,
                "candidate_count": 1,
                "adjusted_root_cause_confidence": 0.9,
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        pillars={"lancedb": {"hits": 0}},
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert "research" not in selected
    assert "external_doc_scout" not in selected
    assert "learn_mode" not in selected
    assert "learn_phase_slo" not in selected
    assert "acceptance_check" not in selected
    assert "ultra_review" not in selected
    assert "pregate" not in selected
    assert "plan_quality_gate" not in selected


def test_capability_planner_keeps_simple_public_repair_out_of_external_review_stack():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Repair a flaky-looking timeout calculation without deleting assertions; "
            "success requires preserving the behavioral contract and validating the actual failing branch."
        ),
        task_type="public_test_repair",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": False,
            "route_features": {
                "risk_score": 55,
                "candidate_count": 1,
                "adjusted_root_cause_confidence": 0.9,
                "has_hard_signal": True,
            },
            "capability_stack": {"selected_capabilities": ["hyper_sprint"]},
        },
        pillars={"lancedb": {"hits": 0}},
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert "repair_loop" in selected
    assert "research" not in selected
    assert "external_doc_scout" not in selected
    assert "ultra_review" not in selected
    assert "sandbox" not in selected


def test_capability_planner_keeps_autoreason_for_candidate_ready_repair():
    evidence_plan = CapabilityPlanner().plan(
        task_desc="Repair test evidence and public claim verification.",
        task_type="public_test_repair",
        route={
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 10,
                "candidate_count": 2,
                "candidate_factory_readiness_estimate": {
                    "ready": True,
                    "status": "READY",
                    "estimated_candidates": 2,
                },
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        pillars={"lancedb": {"hits": 0}},
    ).to_dict()

    assert {"autoreason", "judge_panel", "repair_loop"} <= set(evidence_plan["selected_capabilities"])


def test_capability_planner_uses_candidate_factory_readiness_for_ranking_layers():
    plan = CapabilityPlanner().plan(
        task_desc="Repair competing timeout candidates after A/B alternatives are available.",
        task_type="public_test_repair",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 40,
                "candidate_count": 3,
                "candidate_factory_readiness_estimate": {
                    "ready": True,
                    "status": "READY",
                    "estimated_candidates": 3,
                },
            },
            "capability_stack": {"selected_capabilities": ["hyper_sprint"]},
        },
        pillars={"lancedb": {"hits": 0}},
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"autoreason", "judge_panel", "ddtree", "repair_loop"} <= selected


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


def test_capability_planner_selects_belief_for_explicit_budget_tasks():
    plan = CapabilityPlanner().plan(
        task_desc="Fix repair budget selection so uncertain confidence and elevated risk require evidence.",
        task_type="public_bugfix",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {"risk_score": 45, "candidate_count": 3},
            "capability_stack": {"selected_capabilities": ["hyper_sprint", "autoreason"]},
        },
    ).to_dict()

    assert "belief" in set(plan["selected_capabilities"])


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


def test_capability_planner_consumes_provider_signals_without_executor_side_effects():
    plan = CapabilityPlanner().plan(
        task_desc="Investigate policy-dense route signal with MSA code evidence.",
        task_type="bug",
        route={
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 65,
                "adjusted_root_cause_confidence": 0.7,
                "candidate_count": 1,
            },
            "autonomic_signals": {
                "suggested_mode": "research_first",
                "research_requested": True,
                "swarm_candidate": True,
                "policy_match_count": 12,
            },
            "msa_routing": {
                "candidate_count": 1,
                "top_score": 0.86,
                "rerank_reasons": ["source:lancedb", "sot:code"],
            },
        },
        skills=[{"skill_id": "as-code-review-and-quality", "score": 0.91}],
    )

    payload = plan.to_dict()
    selected = set(payload["selected_capabilities"])
    assert {"research", "pregate", "plan_quality_gate", "swarm", "lancedb", "registry_sync"} <= selected
    assert payload["signal_snapshot"]["autonomic_suggested_mode"] == "research_first"
    assert payload["signal_snapshot"]["msa_rerank_reasons"] == ("source:lancedb", "sot:code")


def test_capability_planner_applies_promoted_learning_policy_only_when_opt_in():
    baseline = CapabilityPlanner().plan(
        task_desc="Simple typo repair with no research need.",
        task_type="docs_fix",
        route={
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 5, "candidate_count": 1},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
    ).to_dict()
    learned = CapabilityPlanner().plan(
        task_desc="Simple typo repair with no research need.",
        task_type="docs_fix",
        route={
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 5, "candidate_count": 1},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        budget={
            "learning_policy": {
                "source_experiences": ["exp:task-1"],
                "promoted_capabilities": ["autoreason"],
                "penalized_capabilities": ["swarm"],
            }
        },
    ).to_dict()

    assert "autoreason" not in baseline["selected_capabilities"]
    assert "autoreason" in learned["selected_capabilities"]
    assert learned["signal_snapshot"]["learning_policy"]["influenced"] is True
    trace = {item["capability"]: item for item in learned["decision_trace"]}
    assert "learning_policy_promoted" in trace["autoreason"]["reasons"]
    assert "learning_policy_penalized" in trace["swarm"]["reasons"]


def test_learning_policy_loader_feeds_planner_without_default_pollution(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_learning_policy.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        """
{
  "schema_version": "nexus_promoted_learning_policy.v1",
  "source_experiences": ["exp:task-1"],
  "promoted_capabilities": ["autoreason"],
  "penalized_capabilities": ["swarm"],
  "escalation_recommendations": []
}
""",
        encoding="utf-8",
    )

    budget = load_learning_policy_budget(artifact)
    plan = CapabilityPlanner().plan(
        task_desc="Simple typo repair with no research need.",
        task_type="docs_fix",
        route={
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 5, "candidate_count": 1},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        budget=budget,
    ).to_dict()

    assert budget["learning_policy"]["enforce_penalties"] is False
    assert "autoreason" in plan["selected_capabilities"]
    assert "learning_policy" in plan["signal_snapshot"]


def test_capability_planner_enforces_runtime_penalty_candidates_for_high_cost_capabilities(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_learning_policy.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema_version": "nexus_promoted_learning_policy.v1",
  "source_experiences": ["exp:1", "exp:2"],
  "promoted_capabilities": [],
  "penalized_capabilities": ["research", "external_doc_scout"],
  "escalation_recommendations": [],
  "capability_roi": {
    "research": {"selected": 2, "invoked": 0, "evidence": 0, "outcome": 0, "gate_passed": 0},
    "external_doc_scout": {"selected": 2, "invoked": 0, "evidence": 0, "outcome": 0, "gate_passed": 0}
  },
  "penalty_candidates": ["research", "external_doc_scout"],
  "enforce_penalties": true
}""",
        encoding="utf-8",
    )

    budget = load_learning_policy_budget(artifact)
    plan = CapabilityPlanner().plan(
        task_desc="Verify SDK API timeout parameter before editing call site.",
        task_type="bug",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": True,
            "route_features": {
                "risk_score": 70,
                "candidate_count": 1,
                "adjusted_root_cause_confidence": 0.6,
                "claim_uncertainty": True,
                "doc_scout_hits": 2,
            },
            "research_context": {"role": "claim_scout"},
            "capability_stack": {"selected_capabilities": ["hyper_sprint"]},
        },
        budget=budget,
    ).to_dict()

    assert budget["learning_policy"]["enforce_penalties"] is True
    assert "research" not in plan["selected_capabilities"]
    assert "external_doc_scout" not in plan["selected_capabilities"]


def test_route_cost_policy_loader_exposes_task_controls(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "candidate_cap_overrides": {"nexus-value-evidence-001": 1},
  "lite_route_tasks": ["nexus-value-trust-001"],
  "hold_tasks": ["nexus-value-repair-001"]
}""",
        encoding="utf-8",
    )

    budget = load_route_cost_policy_budget(artifact)
    evidence_controls = route_cost_controls_for_task(tmp_path, "nexus-value-evidence-001", budget)
    trust_controls = route_cost_controls_for_task(tmp_path, "nexus-value-trust-001", budget)
    repair_controls = route_cost_controls_for_task(tmp_path, "nexus-value-repair-001", budget)

    assert evidence_controls["candidate_cap"] == 1
    assert trust_controls["lite_route"] is True
    assert repair_controls["hold"] is True


def test_route_cost_policy_loader_can_disable_repo_policy_for_clean_bench(tmp_path, monkeypatch):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/stale",
  "hold_tasks": ["nexus-value-context-001"]
}""",
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_DISABLE_PROMOTED_ROUTE_COST_POLICY", "1")

    controls = route_cost_controls_for_task(tmp_path, "nexus-value-context-001")

    assert controls == {}


def test_route_cost_policy_loader_reads_task_specific_env_controls(monkeypatch):
    monkeypatch.setenv(
        "NEXUS_ROUTE_COST_CONTROLS",
        '{"lite_route": true, "candidate_cap": 1, "policy_source": ".nexus/policy/promoted_route_cost_policy.json"}',
    )

    budget = load_route_cost_policy_budget_from_env()

    assert budget["route_cost_policy"]["current_lite_route"] is True
    assert budget["route_cost_policy"]["current_candidate_cap"] == 1


def test_s2t_policy_draft_loader_feeds_shadow_scoring_without_runtime_promotion(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_s2t_policy_draft.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema": "nexus_promoted_s2t_policy_draft_v1",
  "status": "DRAFT_SHADOW_ONLY",
  "source_schema": "nexus_s2t_shadow_report_v1",
  "trace_event_schema": "nexus_s2t_trace_event_v1",
  "task_rules": {
    "task-a": {
      "selector_profile": "standard",
      "recommended_action": "try_standard_with_cost_cap"
    }
  }
}""",
        encoding="utf-8",
    )

    budget = load_s2t_policy_draft_budget(artifact)
    merged = merge_runtime_s2t_policy_draft(tmp_path)
    plan = CapabilityPlanner().plan(
        task_desc="Fix a public API claim with external research evidence.",
        task_type="public_feature",
        route={
            "task_id": "task-a",
            "recommended_flow": "hyper_sprint",
            "should_research": True,
            "route_features": {"risk_score": 75, "candidate_count": 3, "claim_uncertainty": True},
            "research_context": {"role": "claim_scout"},
        },
        budget=merged,
    ).to_dict()

    assert budget["s2t_policy_draft"]["status"] == "DRAFT_SHADOW_ONLY"
    assert merged["s2t_policy_draft"]["task_rules"]["task-a"]["recommended_action"] == "try_standard_with_cost_cap"
    assert plan["signal_snapshot"]["s2t_policy_draft"]["matched_task_rule"] is True
    assert plan["signal_snapshot"]["s2t_policy_draft"]["mode"] == "shadow_only_no_runtime_decision_change"


def test_route_cost_controls_for_task_applies_current_env_controls(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "NEXUS_ROUTE_COST_CONTROLS",
        '{"lite_route": true, "candidate_cap": 1, "hold": true, "policy_source": "env:test"}',
    )

    controls = route_cost_controls_for_task(tmp_path, "rlm-harder-v2-governance-001")

    assert controls["candidate_cap"] == 1
    assert controls["lite_route"] is True
    assert controls["hold"] is True
    assert controls["policy_source"] == "env:test"


def test_capability_planner_lite_route_downgrades_high_cost_conditionals():
    plan = CapabilityPlanner().plan(
        task_desc="Refactor a credential scrubber while preserving governance boundaries and evidence claims",
        task_type="public_refactor",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {"risk_score": 80, "has_governance_signal": True, "candidate_count": 1},
            "route_decision": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "governance_layers": ["ultra_review"],
            },
        },
        budget={"route_cost_policy": {"current_lite_route": True, "source": "test"}},
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"} <= selected
    assert "ultra_review" not in selected
    assert "sandbox" not in selected
    assert "research" not in selected
    assert "autoreason" not in selected


def test_capability_planner_scores_s2t_policy_draft_without_changing_selection():
    baseline = CapabilityPlanner().plan(
        task_desc="Fix a risky public feature with a high-cost research route.",
        task_type="public_feature",
        route={
            "task_id": "task-a",
            "recommended_flow": "hyper_sprint",
            "should_research": True,
            "route_features": {
                "risk_score": 75,
                "candidate_count": 3,
                "claim_uncertainty": True,
            },
            "research_context": {"role": "claim_scout"},
            "route_decision": {"selected_capabilities": ["hyper_sprint", "research"]},
        },
    ).to_dict()
    shadow = CapabilityPlanner().plan(
        task_desc="Fix a risky public feature with a high-cost research route.",
        task_type="public_feature",
        route={
            "task_id": "task-a",
            "recommended_flow": "hyper_sprint",
            "should_research": True,
            "route_features": {
                "risk_score": 75,
                "candidate_count": 3,
                "claim_uncertainty": True,
            },
            "research_context": {"role": "claim_scout"},
            "route_decision": {"selected_capabilities": ["hyper_sprint", "research"]},
        },
        budget={
            "s2t_policy_draft": {
                "schema": "nexus_promoted_s2t_policy_draft_v1",
                "status": "DRAFT_SHADOW_ONLY",
                "task_rules": {
                    "task-a": {
                        "selector_profile": "standard",
                        "recommended_action": "try_standard_with_cost_cap",
                    }
                },
            }
        },
    ).to_dict()

    assert shadow["selected_capabilities"] == baseline["selected_capabilities"]
    assert shadow["signal_snapshot"]["s2t_policy_draft"]["mode"] == "shadow_only_no_runtime_decision_change"
    assert shadow["signal_snapshot"]["s2t_policy_draft"]["matched_task_rule"] is True
    trace = {item["capability"]: item for item in shadow["decision_trace"]}
    assert trace["research"]["s2t_shadow_policy"]["would_downgrade"] is True
    assert trace["research"]["s2t_shadow_policy"]["reason"] == "s2t_shadow_cost_candidate"


def test_candidate_factory_ready_alone_does_not_select_research():
    plan = CapabilityPlanner().plan(
        task_desc="Fix claim verification so only fully supported successful claims are accepted.",
        task_type="public_feature",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": False,
            "route_features": {
                "risk_score": 55,
                "adjusted_root_cause_confidence": 0.55,
                "candidate_count": 3,
                "candidate_factory_readiness_estimate": {
                    "ready": True,
                    "status": "READY",
                    "estimated_candidates": 3,
                },
                "claim_uncertainty": False,
                "is_cross_module_task": False,
                "memory_hits": 0,
                "findings_hits": 0,
            },
            "capability_stack": {"selected_capabilities": ["hyper_sprint"]},
        },
    ).to_dict()

    assert "research" not in plan["selected_capabilities"]


def test_learning_policy_promoted_research_still_requires_evidence_demand():
    plan = CapabilityPlanner().plan(
        task_desc="Fix relevance selection so broad same-type history cannot pollute the current task.",
        task_type="public_bugfix",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": False,
            "route_features": {
                "risk_score": 55,
                "adjusted_root_cause_confidence": 0.55,
                "candidate_count": 3,
                "candidate_factory_readiness_estimate": {
                    "ready": True,
                    "status": "READY",
                    "estimated_candidates": 3,
                },
                "claim_uncertainty": False,
                "is_cross_module_task": False,
            },
            "capability_stack": {"selected_capabilities": ["hyper_sprint"]},
        },
        budget={"learning_policy": {"promoted_capabilities": ["research"]}},
    ).to_dict()

    assert "research" not in plan["selected_capabilities"]
    trace = {item["capability"]: item for item in plan["decision_trace"]}
    assert "research_no_substantive_evidence_demand_cost_control" in trace["research"]["reasons"]


def test_route_seeded_research_still_requires_substantive_evidence_demand():
    plan = CapabilityPlanner().plan(
        task_desc="Tighten an action filter so unsafe operations are rejected while ordinary read-only work remains allowed.",
        task_type="public_ops_research",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": False,
            "route_features": {
                "risk_score": 55,
                "adjusted_root_cause_confidence": 0.55,
                "candidate_count": 3,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
            },
            "route_decision": {"selected_capabilities": ["hyper_sprint", "research"]},
        },
    ).to_dict()

    assert "research" not in plan["selected_capabilities"]


def test_should_research_without_claim_or_role_does_not_force_research():
    plan = CapabilityPlanner().plan(
        task_desc="Tighten an action filter so unsafe operations are rejected while ordinary read-only work remains allowed.",
        task_type="public_ops_research",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": True,
            "route_features": {
                "risk_score": 55,
                "adjusted_root_cause_confidence": 0.55,
                "candidate_count": 3,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
            },
            "route_decision": {"selected_capabilities": ["hyper_sprint", "research"]},
        },
    ).to_dict()

    assert "research" not in plan["selected_capabilities"]


def test_replay_evidence_contract_keeps_research_context():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Fix receipt acceptance so verified claims require a replay command and a clean replay exit code. "
            "Nexus replay evidence rule: trust receipts only when the claim, replay command, and execution result all agree. "
            "Nexus replay receipt contract: accept only claim='verified' with a non-empty replay_command and exit_code == 0."
        ),
        task_type="public_feature",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": True,
            "route_features": {
                "risk_score": 55,
                "adjusted_root_cause_confidence": 1.0,
                "candidate_count": 3,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
            },
            "route_decision": {"selected_capabilities": ["hyper_sprint", "research"]},
        },
        budget={"learning_policy": {"promoted_capabilities": ["research"]}},
    ).to_dict()

    assert "research" in plan["selected_capabilities"]


def test_capability_planner_uses_micro_patch_lane_for_simple_hidden_bugfix():
    plan = CapabilityPlanner().plan(
        task_desc="Fix a small hidden bug in one local file.",
        task_type="public_bugfix",
        route={
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 10,
                "adjusted_root_cause_confidence": 0.92,
                "candidate_count": 1,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
    ).to_dict()

    assert plan["signal_snapshot"]["routing_tier"] == "L0_micro_patch"
    assert "research_route" not in plan["selected_capabilities"]
    assert "memory" not in plan["selected_capabilities"]
    assert "asi_constraint_extractor" not in plan["selected_capabilities"]
    assert "belief" not in plan["selected_capabilities"]
    assert "direct_mode" not in plan["selected_capabilities"]
    assert {"mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"} <= set(plan["selected_capabilities"])


def test_capability_planner_honors_bulleted_route_oracle_expected_receipts():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Use semantic retrieval evidence only when semantic_searcher refs are present."
            "\n\nNexus route oracle contract:"
            "\n- Expected capability receipts: semantic_searcher."
        ),
        task_type="public_docs_code_sync",
        route={"recommended_flow": "hyper_sprint", "route_features": {"risk_score": 65, "candidate_count": 3}},
    ).to_dict()

    assert "semantic_searcher" in plan["selected_capabilities"]


def test_capability_planner_keeps_route_oracle_expected_receipts_under_cost_policy():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Select retrieval hits only when semantic score and source identifiers are usable."
            "\n\nNexus route oracle contract:"
            "\n- Expected capability receipts: lancedb."
        ),
        task_type="public_docs_code_sync",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {"risk_score": 20, "candidate_count": 1},
        },
        budget={
            "learning_policy": {
                "penalized_capabilities": ["lancedb"],
                "enforce_penalties": True,
            },
            "route_cost_policy": {"current_lite_route": True, "source": "test"},
            "max_cost": 6,
        },
    ).to_dict()

    assert "lancedb" in plan["selected_capabilities"]
    assert "lancedb" in plan["required_capabilities"]
    trace = {item["capability"]: item for item in plan["decision_trace"]}
    assert "route_oracle_expected_receipt_required" in trace["lancedb"]["reasons"]


def test_capability_planner_ignores_wearing_contract_for_costly_lexical_signals():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Fix a small parser branch.\n\n"
            "Nexus wearing contract:\n"
            "- MemPalace: keep the solution inside governance constraints.\n"
            "- Artifact/Claim: treat completion claims as valid only when backed by evidence."
        ),
        task_type="public_test_repair",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 20,
                "adjusted_root_cause_confidence": 0.95,
                "candidate_count": 1,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert "asi_constraint_extractor" not in selected
    assert "learn_mode" not in selected
    assert "learn_phase_slo" not in selected
    assert "acceptance_check" not in selected


def test_capability_planner_keeps_hidden_contract_fast_path_light_under_learning_policy():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Sync code and docs after a renamed public field; the expected fix must infer "
            "the canonical field from surrounding contract text rather than only the failing assertion."
            "\n\nNexus wearing contract:\n"
            "- Artifact/Claim: treat completion claims as valid only when backed by checks."
        ),
        task_type="public_docs_code_sync",
        route={
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 20,
                "candidate_count": 3,
                "adjusted_root_cause_confidence": 1.0,
                "benchmark_hidden_contract_fast_path": True,
                "memory_hits": 1,
            },
        },
        budget={
            "learning_policy": {
                "promoted_capabilities": ["research", "autoreason", "judge_panel"],
                "enforce_penalties": False,
            }
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert "research" not in selected
    assert "autoreason" not in selected
    assert "judge_panel" not in selected
    trace = {item["capability"]: item for item in plan["decision_trace"]}
    assert (
        "simple_hidden_contract_fast_path_cost_control" in trace["research"]["reasons"]
        or "research_no_substantive_evidence_demand_cost_control" in trace["research"]["reasons"]
    )
