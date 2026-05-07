from __future__ import annotations

from nexus.engine.capability_planner import CapabilityPlanner, default_capability_nodes
from nexus.engine.learning_policy_loader import load_learning_policy_budget


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
