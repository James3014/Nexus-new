from __future__ import annotations

import json

import pytest

from nexus.engine.capability_contracts import (
    CapabilityPlan,
    ExecutionReplanAuthorization,
    apply_execution_depth_floor,
)
from nexus.engine.capability_planner import CapabilityPlanner, default_capability_nodes
from nexus.engine.learning_policy_loader import (
    audit_route_cost_policy,
    build_route_cost_policy_usage_ledger,
    load_learning_policy_budget,
    load_route_cost_policy_budget,
    load_route_cost_policy_budget_from_env,
    load_s2t_policy_draft_budget,
    merge_runtime_s2t_policy_draft,
    route_cost_controls_from_env,
    route_cost_controls_for_task,
)
from nexus.engine.planner.skill_mount_evidence import runtime_policy_overlay_skill_requests


def test_capability_planner_delegates_runtime_policy_overlay_skill_requests_to_split_module():
    budget = {
        "runtime_skill_policy_overlay": {
            "status": "PASS",
            "primary_skill_by_capability": {"repair": "repair-skill"},
        }
    }

    assert CapabilityPlanner._runtime_policy_overlay_skill_requests(
        budget=budget,
        selected_capabilities=["repair"],
    ) == runtime_policy_overlay_skill_requests(
        budget=budget,
        selected_capabilities=["repair"],
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
    assert not ({"swarm", "drone"} & set(plan["pending_capabilities"]))
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


def test_capability_planner_research_isolation_snapshot_stays_minimal():
    plan = CapabilityPlanner().plan(
        task_desc="Investigate cross-module timeout behavior with unknown ownership.",
        task_type="bugfix",
        route={
            "should_research": True,
            "route_features": {
                "risk_score": 55,
                "is_cross_module_task": True,
                "adjusted_root_cause_confidence": 0.62,
            },
        },
        codeintel={"impact_report_present": True},
    ).to_dict()

    policy = plan["signal_snapshot"]["research_isolation_policy"]
    assert policy == {
        "level": "L1",
        "goal_visibility": "masked",
        "output_mode": "facts_only",
        "confirmation_required": False,
    }


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


def test_capability_planner_budget_safety_floor_preserves_high_risk_governance():
    plan = CapabilityPlanner().plan(
        task_desc="Refactor credential scrubber without weakening governance or claim evidence.",
        task_type="bug",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 95,
                "candidate_count": 4,
                "is_cross_module_task": True,
                "has_governance_signal": True,
            },
            "capability_stack": {"selected_capabilities": ["hyper_sprint"], "governance_layers": ["ultra_review"]},
        },
        budget={"max_cost": 8},
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    forbidden = set(plan["forbidden_capabilities"])
    assert {"mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate", "ultra_review", "sandbox"} <= selected
    assert not {"ultra_review", "sandbox", "pregate", "plan_quality_gate"} & forbidden
    trace = {item["capability"]: item for item in plan["decision_trace"]}
    assert "budget_safety_floor_preserved" in trace["ultra_review"]["reasons"]


def test_capability_planner_escalates_survived_mutation_blind_spot():
    plan = CapabilityPlanner().plan(
        task_desc="Fix public claim safety after mutation assurance found a blind spot.",
        task_type="public_feature",
        route={
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 30, "candidate_count": 1},
            "mutation_assurance": {
                "required": True,
                "survived_mutants_present": True,
                "survived_mutant_ids": ["public_safe_forced_true"],
            },
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"ultra_review", "sandbox", "autoreason", "jit_validation"} <= selected
    trace = {item["capability"]: item for item in plan["decision_trace"]}
    assert "mutation_assurance_blind_spot_escalation" in trace["ultra_review"]["reasons"]


def test_capability_planner_emits_ssd_route_map_for_every_selected_capability():
    plan = CapabilityPlanner().plan(
        task_desc="Use research and codeintel to repair cross-module route evidence.",
        task_type="bug",
        route={
            "should_research": True,
            "route_features": {
                "risk_score": 76,
                "candidate_count": 3,
                "is_cross_module_task": True,
                "memory_hits": 2,
            },
        },
        pillars={"lancedb": {"hits": 2}},
    ).to_dict()

    route_map = plan["signal_snapshot"]["ssd_route_map"]
    assert route_map["schema_version"] == "nexus_ssd_route_map_v1"
    assert route_map["map_status"] == "PASS"
    assert set(plan["selected_capabilities"]) == set(route_map["capability_reasons"])
    assert route_map["leverage_points"]
    for item in plan["decision_trace"]:
        if item["state"] in {"required", "conditional"}:
            assert item["leverage_role"], item["capability"]


def test_capability_planner_emits_dream_context_slimming_for_simple_hidden_path():
    plan = CapabilityPlanner().plan(
        task_desc="Fix a simple hidden fixture assertion without external research.",
        task_type="public_bugfix",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 10,
                "adjusted_root_cause_confidence": 0.95,
                "candidate_count": 1,
                "simple_hidden_bugfix": True,
            },
        },
    ).to_dict()

    slimming = plan["signal_snapshot"]["context_slimming_policy"]
    assert slimming["schema_version"] == "nexus_context_slimming_policy_v1"
    assert slimming["mode"] == "dream_micro"
    assert slimming["max_context_items"] <= 4
    assert slimming["allow_research_context"] is False
    assert "unreferenced_codeintel_sections" in slimming["drop_by_default"]


def test_capability_planner_selects_harness_sensors_without_heavy_route_bloat():
    plan = CapabilityPlanner().plan(
        task_desc="Given-When-Then business acceptance after a hidden verifier AssertionError.",
        task_type="business_acceptance",
        route={
            "bdd_acceptance": True,
            "failure_text": "Hidden verifier failure: AssertionError expected candidate winner",
            "route_features": {
                "risk_score": 18,
                "candidate_count": 1,
                "simple_hidden_bugfix": True,
            },
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    snapshot = plan["signal_snapshot"]
    assert "harness_preflight_sensor" in selected
    assert "semantic_failure_sensor" in selected
    assert "bdd_acceptance_skill" in selected
    assert snapshot["harness_preflight_sensor"]["cost_lane"] == "lite"
    assert snapshot["harness_preflight_sensor"]["bdd_acceptance_required"] is True
    assert snapshot["semantic_failure_sensor"]["retry_policy"]["allow_blind_retry"] is False
    assert "research" not in selected


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


def test_capability_planner_selects_explicit_prompt_compression_route():
    plan = CapabilityPlanner().plan(
        task_desc="continue a long task with compressed context",
        task_type="repair",
        route={
            "recommended_flow": "hybrid",
            "prompt_compression": True,
            "route_features": {"risk_score": 10},
        },
    )

    assert "prompt_compression" in plan.selected_capabilities


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


def test_capability_planner_emits_planned_skill_mount_contract_for_curated_skill(tmp_path):
    status_report = tmp_path / "skill_status.json"
    status_report.write_text(
        json.dumps(
            {
                "schema": "nexus.skill_status.v1",
                "skills": [
                    {
                        "name": "nexus-benchmark-public-report",
                        "path": "/repo/.agents/skills/nexus-benchmark-public-report/SKILL.md",
                        "root": "nexus_repo",
                        "skill_status": "nexus_curated_candidate",
                        "test_level": "routing_plus_e2e",
                        "action": "eligible_for_capability_mount_review",
                        "capability_mount": "benchmark",
                        "reason_codes": ["repo_local_nexus_skill"],
                    },
                    {
                        "name": "candidate-skill-from-run-001",
                        "path": "/Users/jameschen/.agents/skills/candidate-skill-from-run-001/SKILL.md",
                        "root": "agents",
                        "skill_status": "candidate_quarantine",
                        "test_level": "quarantine",
                        "action": "review_before_promotion",
                        "capability_mount": None,
                        "reason_codes": ["generated_or_candidate_inbox"],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    plan = CapabilityPlanner().plan(
        task_desc="Prepare public benchmark promotion report.",
        task_type="benchmark",
        route={
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 20, "candidate_count": 1},
        },
        budget={"skill_status_report": str(status_report)},
        skills=[
            {"skill_id": "nexus-benchmark-public-report", "score": 0.91},
            {"skill_id": "candidate-skill-from-run-001", "score": 0.7},
        ],
    ).to_dict()

    snapshot = plan["signal_snapshot"]
    assert snapshot["planned_skill_mount_contracts"] == [
        {
            "skill_id": "nexus-benchmark-public-report",
            "skill_status": "nexus_curated_candidate",
            "capability_mount": "benchmark",
            "capability": "benchmark",
            "load_reason_codes": [
                "capability_planner_skill_signal",
                "catalog_status:nexus_curated_candidate",
            ],
            "evidence_refs": [
                "skill_catalog:nexus-benchmark-public-report",
                "skill_path:/repo/.agents/skills/nexus-benchmark-public-report/SKILL.md",
            ],
            "planner_selected_capability": True,
        }
    ]
    assert snapshot["skill_mount_violations"] == [
        {
            "skill_name": "candidate-skill-from-run-001",
            "path": "/Users/jameschen/.agents/skills/candidate-skill-from-run-001/SKILL.md",
            "reason": "quarantined_status:candidate_quarantine",
        }
    ]


def test_capability_planner_allows_reference_skill_only_for_ablation(tmp_path):
    status_report = tmp_path / "skill_status.json"
    status_report.write_text(
        json.dumps(
            {
                "schema": "nexus.skill_status.v1",
                "skills": [
                    {
                        "name": "hermes-debugging",
                        "path": "/Users/jameschen/Workspace/hermes-agent/skills/debugging/SKILL.md",
                        "root": "hermes",
                        "skill_status": "external_reference_candidate",
                        "test_level": "routing_reference",
                        "action": "reference_only_until_imported",
                        "capability_mount": "reference:repair_and_coding",
                        "reason_codes": ["structured_hermes_reference_catalog"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    plan = CapabilityPlanner().plan(
        task_desc="Repair code with external skill ablation.",
        task_type="benchmark",
        route={"recommended_flow": "baseline", "route_features": {"risk_score": 20, "candidate_count": 1}},
        budget={"skill_status_report": str(status_report), "allow_ablation_skill_mounts": True},
        skills=[{"skill_id": "hermes-debugging", "score": 0.7}],
    ).to_dict()

    snapshot = plan["signal_snapshot"]
    assert snapshot["skill_mount_violations"] == []
    assert snapshot["planned_skill_mount_contracts"] == [
        {
            "skill_id": "hermes-debugging",
            "skill_status": "external_reference_candidate",
            "capability_mount": "repair_and_coding",
            "capability": "repair_and_coding",
            "load_reason_codes": [
                "capability_planner_skill_signal",
                "catalog_status:external_reference_candidate",
                "benchmark_ablation_only_mount",
            ],
            "evidence_refs": [
                "skill_catalog:hermes-debugging",
                "skill_path:/Users/jameschen/Workspace/hermes-agent/skills/debugging/SKILL.md",
            ],
            "planner_selected_capability": False,
        }
    ]


def test_capability_planner_uses_sf_runtime_policy_overlay_for_selected_capability(tmp_path):
    status_report = tmp_path / "skill_status.json"
    status_report.write_text(
        json.dumps(
            {
                "schema": "nexus.skill_status.v1",
                "skills": [
                    {
                        "name": "create-plan",
                        "path": "/repo/.agents/skills/create-plan/SKILL.md",
                        "root": "nexus_repo",
                        "skill_status": "nexus_repo_local_candidate",
                        "test_level": "runtime_reviewed",
                        "action": "runtime_policy_overlay_only",
                        "capability_mount": "reference:forecast_pregate",
                        "reason_codes": ["sf_runtime_policy_overlay"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    overlay_path = tmp_path / "sf_runtime_overlay.json"
    overlay_path.write_text(
        json.dumps(
            {
                "schema": "nexus.sf_runtime_skill_policy_overlay.v1",
                "status": "PASS",
                "primary_skill_by_capability": {"forecast_pregate": "create-plan"},
                "capability_aliases": {"forecast_pregate": ["forecast_gate"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    plan = CapabilityPlanner().plan(
        task_desc="Forecast plan risk before execution.",
        task_type="planning",
        route={"recommended_flow": "baseline", "route_features": {"risk_score": 75, "candidate_count": 1}},
        budget={
            "skill_status_report": str(status_report),
            "runtime_skill_policy_overlay_path": str(overlay_path),
        },
    ).to_dict()

    snapshot = plan["signal_snapshot"]
    contracts = snapshot["planned_skill_mount_contracts"]
    assert snapshot.get("skill_mount_violations", []) == []
    assert contracts == [
        {
            "skill_id": "create-plan",
            "skill_status": "nexus_repo_local_candidate",
            "capability_mount": "forecast_pregate",
            "capability": "forecast_pregate",
            "load_reason_codes": [
                "capability_planner_skill_signal",
                "catalog_status:nexus_repo_local_candidate",
                "sf_runtime_policy_overlay",
            ],
            "evidence_refs": [
                "skill_catalog:create-plan",
                "skill_path:/repo/.agents/skills/create-plan/SKILL.md",
            ],
            "planner_selected_capability": True,
        }
    ]


def test_capability_planner_uses_sf_runtime_policy_assembly_overlay(tmp_path):
    status_report = tmp_path / "skill_status.json"
    status_report.write_text(
        json.dumps(
            {
                "schema": "nexus.skill_status.v1",
                "skills": [
                    {
                        "name": "code-scout",
                        "path": "/repo/.agents/skills/code-scout/SKILL.md",
                        "skill_status": "nexus_curated_candidate",
                        "capability_mount": "codeintel",
                    },
                    {
                        "name": "code-audit",
                        "path": "/repo/.agents/skills/code-audit/SKILL.md",
                        "skill_status": "nexus_curated_candidate",
                        "capability_mount": "codeintel",
                    },
                    {
                        "name": "solo-codeintel",
                        "path": "/repo/.agents/skills/solo-codeintel/SKILL.md",
                        "skill_status": "nexus_curated_candidate",
                        "capability_mount": "codeintel",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    overlay_path = tmp_path / "heep_runtime_overlay.json"
    overlay_path.write_text(
        json.dumps(
            {
                "schema": "nexus.heep_runtime_skill_policy_overlay.v1",
                "status": "PASS",
                "primary_skill_by_capability": {"codeintel": "solo-codeintel"},
                "skill_assembly_by_capability": {
                    "codeintel": [
                        {"role": "Scout", "skill_id": "code-scout"},
                        {"role": "Audit", "skill_id": "code-audit"},
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    plan = CapabilityPlanner().plan(
        task_desc="Scan implementation impact before editing.",
        task_type="code_change",
        route={"recommended_flow": "baseline", "route_features": {"risk_score": 40}},
        budget={
            "skill_status_report": str(status_report),
            "runtime_skill_policy_overlay_path": str(overlay_path),
        },
    ).to_dict()

    snapshot = plan["signal_snapshot"]
    contracts = snapshot["planned_skill_mount_contracts"]
    assert [contract["skill_id"] for contract in contracts] == ["code-scout", "code-audit"]
    assert all("sf_runtime_policy_overlay" in contract["load_reason_codes"] for contract in contracts)
    assert snapshot.get("skill_mount_violations", []) == []


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
  "allow_task_id_runtime_controls": true,
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


def test_route_cost_policy_loader_ignores_task_controls_by_default(tmp_path):
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
    controls = route_cost_controls_for_task(tmp_path, "nexus-value-evidence-001", budget)
    audit = audit_route_cost_policy(tmp_path, budget)

    assert controls == {}
    assert audit["passed"] is True
    assert audit["task_id_runtime_policy_count"] == 0
    assert audit["legacy_task_controls_ignored_count"] == 3


def test_route_cost_policy_loader_applies_feature_rules_without_task_id(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:bug-lite",
      "match": {"task_type": "bug", "difficulty": ["easy", "medium"], "repo_kind": "fixture"},
      "controls": {"candidate_cap": 1, "lite_route": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    controls = route_cost_controls_for_task(
        tmp_path,
        "unseen-task-id",
        route_features={"task_type": "bug", "difficulty": "medium", "repo_kind": "fixture"},
    )
    miss = route_cost_controls_for_task(
        tmp_path,
        "unseen-task-id",
        route_features={"task_type": "public_feature", "difficulty": "medium", "repo_kind": "fixture"},
    )

    assert controls["candidate_cap"] == 1
    assert controls["lite_route"] is True
    assert controls["policy_source"] == "feature:bug-lite"
    assert miss == {}


def test_route_cost_policy_usage_ledger_marks_unmatched_feature_rules_for_dehydration():
    policy = {
        "feature_rules": [
            {
                "id": "feature:public-bug",
                "match": {"task_type": "public_test_repair", "difficulty": "hard"},
                "controls": {"candidate_cap": 1},
            },
            {
                "id": "feature:fixture-only",
                "match": {"fixture_kind": "neutral_fixture"},
                "controls": {"lite_route": True},
            },
        ]
    }

    ledger = build_route_cost_policy_usage_ledger(
        policy,
        rows=[{"task_type": "public_test_repair", "difficulty": "hard"}],
    )

    assert ledger["schema_version"] == "nexus_route_cost_policy_usage_ledger.v1"
    assert ledger["active_count"] == 1
    assert ledger["dehydrate_candidate_count"] == 1
    assert ledger["rules"][1]["status"] == "dehydrate_candidate"


def test_route_cost_policy_audit_marks_fixture_only_feature_rules(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:fixture-only-lite",
      "match": {"task_type": "bug", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "lite_route": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    audit = audit_route_cost_policy(tmp_path)

    assert audit["passed"] is True
    assert audit["feature_rule_scope"]["fixture_only"] is True
    assert audit["feature_rule_scope"]["generic"] == 0


def test_route_cost_policy_loader_can_match_local_reflex_features(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:reflex-low-risk-supervised",
      "match": {"task_type": "public_test_repair", "local_reflex_risk_level": "low", "local_reflex_bare_sufficiency": "high"},
      "controls": {"candidate_cap": 1, "lite_route": true, "supervised_bare_first": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    controls = route_cost_controls_for_task(
        tmp_path,
        "unseen-task-id",
        route_features={
            "task_type": "public_test_repair",
            "local_reflex_risk_level": "low",
            "local_reflex_bare_sufficiency": "high",
        },
    )
    blocked = route_cost_controls_for_task(
        tmp_path,
        "unseen-task-id",
        route_features={
            "task_type": "public_test_repair",
            "local_reflex_risk_level": "high",
            "local_reflex_bare_sufficiency": "low",
        },
    )

    assert controls["supervised_bare_first"] is True
    assert controls["policy_source"] == "feature:reflex-low-risk-supervised"
    assert blocked == {}


def test_route_cost_policy_loader_can_match_public_bugfix_supervised_bare_first(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:public-bugfix-supervised",
      "match": {"task_type": "public_bugfix", "difficulty": "hard", "category": "bugfix", "repo_kind": "neutral_fixture", "local_reflex_risk_level": "low", "local_reflex_bare_sufficiency": "high"},
      "controls": {"candidate_cap": 1, "lite_route": true, "supervised_bare_first": true, "allow_pre_model_deterministic_rescue": true, "route_lane": "hidden_bugfix_supervised"}
    }
  ]
}""",
        encoding="utf-8",
    )

    controls = route_cost_controls_for_task(
        tmp_path,
        "nexus-value-hidden-002",
        route_features={
            "task_type": "public_bugfix",
            "difficulty": "hard",
            "category": "bugfix",
            "repo_kind": "neutral_fixture",
            "local_reflex_risk_level": "low",
            "local_reflex_bare_sufficiency": "high",
        },
    )

    assert controls["supervised_bare_first"] is True
    assert controls["allow_pre_model_deterministic_rescue"] is True
    assert controls["route_lane"] == "hidden_bugfix_supervised"
    assert controls["policy_source"] == "feature:public-bugfix-supervised"


def test_route_cost_policy_loader_matches_public_context_and_refactor_lanes(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:public-refactor-capped",
      "match": {"task_type": "public_refactor", "difficulty": "hard", "category": "refactor", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "context_mode": "compact", "disable_research": true, "max_rounds": 1, "route_lane": "governance_hardened_capped", "skip_llm_baseline": true}
    },
    {
      "id": "feature:public-docs-code-sync-capped",
      "match": {"task_type": "public_docs_code_sync", "difficulty": "hard", "category": "docs_code_sync", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "context_mode": "compact", "disable_research": true, "max_rounds": 1, "route_lane": "context_sync_capped", "skip_llm_baseline": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    refactor = route_cost_controls_for_task(
        tmp_path,
        "nexus-value-gov-002",
        route_features={
            "task_type": "public_refactor",
            "difficulty": "hard",
            "category": "refactor",
            "repo_kind": "neutral_fixture",
        },
    )
    context = route_cost_controls_for_task(
        tmp_path,
        "nexus-value-context-002",
        route_features={
            "task_type": "public_docs_code_sync",
            "difficulty": "hard",
            "category": "docs_code_sync",
            "repo_kind": "neutral_fixture",
        },
    )

    assert refactor["route_lane"] == "governance_hardened_capped"
    assert refactor["disable_research"] is True
    assert refactor["skip_llm_baseline"] is True
    assert context["route_lane"] == "context_sync_capped"
    assert context["disable_research"] is True
    assert context["skip_llm_baseline"] is True


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
        (
            '{"lite_route": true, "candidate_cap": 1, "disable_research": true, '
            '"context_mode": "compact", "max_rounds": 1, "route_lane": "hidden_lite", '
            '"allow_high_risk_supervised_bare_first": true, '
            '"policy_source": ".nexus/policy/promoted_route_cost_policy.json"}'
        ),
    )

    budget = load_route_cost_policy_budget_from_env()
    controls = route_cost_controls_from_env()

    assert budget["route_cost_policy"]["current_lite_route"] is True
    assert budget["route_cost_policy"]["current_candidate_cap"] == 1
    assert budget["route_cost_policy"]["current_disable_research"] is True
    assert budget["route_cost_policy"]["current_context_mode"] == "compact"
    assert budget["route_cost_policy"]["current_max_rounds"] == 1
    assert budget["route_cost_policy"]["current_route_lane"] == "hidden_lite"
    assert budget["route_cost_policy"]["current_allow_high_risk_supervised_bare_first"] is True
    assert controls["disable_research"] is True
    assert controls["context_mode"] == "compact"
    assert controls["allow_high_risk_supervised_bare_first"] is True


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


def test_s2t_policy_draft_promoted_runtime_requires_gate(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_s2t_policy_draft.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema": "nexus_promoted_s2t_policy_draft_v1",
  "status": "PROMOTED_RUNTIME",
  "promotion_gate": {"passed": false, "trust_mismatch_rate": 0, "sample_count": 5, "rollback_policy": "disable_s2t"},
  "task_rules": {"task-a": {"selector_profile": "lite", "recommended_action": "try_lite_with_defensive_gate"}}
}""",
        encoding="utf-8",
    )

    assert load_s2t_policy_draft_budget(artifact) == {}


def test_s2t_policy_draft_promoted_runtime_can_downgrade_costly_non_floor_caps(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_s2t_policy_draft.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema": "nexus_promoted_s2t_policy_draft_v1",
  "status": "PROMOTED_RUNTIME",
  "promotion_gate": {"passed": true, "trust_mismatch_rate": 0, "sample_count": 5, "rollback_policy": "set NEXUS_DISABLE_S2T_POLICY_DRAFT=1"},
  "task_rules": {
    "task-a": {
      "selector_profile": "lite",
      "recommended_action": "try_lite_with_defensive_gate"
    }
  }
}""",
        encoding="utf-8",
    )

    plan = CapabilityPlanner().plan(
        task_desc="Fix a public API claim with external research evidence.",
        task_type="public_feature",
        route={
            "task_id": "task-a",
            "recommended_flow": "hyper_sprint",
            "should_research": True,
            "route_features": {"risk_score": 55, "candidate_count": 3, "claim_uncertainty": True},
            "research_context": {"role": "claim_scout"},
        },
        budget=load_s2t_policy_draft_budget(artifact),
    ).to_dict()

    assert plan["signal_snapshot"]["s2t_policy_draft"]["mode"] == "promoted_runtime_candidate"
    assert "research" not in plan["selected_capabilities"]
    trace = {item["capability"]: item for item in plan["decision_trace"]}
    assert "s2t_promoted_policy_cost_downgrade" in trace["research"]["reasons"]


def test_route_cost_controls_for_task_applies_current_env_controls(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "NEXUS_ROUTE_COST_CONTROLS",
        (
            '{"lite_route": true, "candidate_cap": 1, "hold": true, '
            '"disable_research": true, "context_mode": "compact", "max_rounds": 1, '
            '"route_lane": "repair_capped", "require_llm_baseline": true, '
            '"skip_llm_baseline": true, "policy_source": "env:test"}'
        ),
    )

    controls = route_cost_controls_for_task(tmp_path, "rlm-harder-v2-governance-001")

    assert controls["candidate_cap"] == 1
    assert controls["lite_route"] is True
    assert controls["hold"] is True
    assert controls["disable_research"] is True
    assert controls["context_mode"] == "compact"
    assert controls["max_rounds"] == 1
    assert controls["route_lane"] == "repair_capped"
    assert controls["require_llm_baseline"] is True
    assert controls["skip_llm_baseline"] is True
    assert controls["policy_source"] == "env:test"


def test_route_cost_policy_loader_matches_real_benchmark_category_lane(tmp_path):
    artifact = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:governance-direct-hyper",
      "match": {"category": "ops_research", "difficulty": "hard", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "context_mode": "compact", "disable_research": true, "max_rounds": 1, "route_lane": "governance_hardened", "skip_llm_baseline": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    controls = route_cost_controls_for_task(
        tmp_path,
        "rlm-harder-v2-governance-001",
        route_features={
            "category": "ops_research",
            "difficulty": "hard",
            "repo_kind": "neutral_fixture",
            "task_type": "",
        },
    )

    assert controls["candidate_cap"] == 1
    assert controls["disable_research"] is True
    assert controls["context_mode"] == "compact"
    assert controls["max_rounds"] == 1
    assert controls["route_lane"] == "governance_hardened"
    assert controls["skip_llm_baseline"] is True


def test_route_cost_controls_enable_gate_only_receipt_lite_for_governance_lane(tmp_path):
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:governance-hard-neutral",
                    "match": {
                        "task_type": "public_ops_research",
                        "category": "ops_research",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                    },
                    "controls": {
                        "allow_pre_model_deterministic_rescue": True,
                        "candidate_cap": 1,
                        "context_mode": "compact",
                        "disable_research": True,
                        "max_rounds": 1,
                        "route_lane": "governance_hardened",
                        "skip_llm_baseline": True,
                    },
                }
            ],
        }
    }

    controls = route_cost_controls_for_task(
        tmp_path,
        "nexus-value-trust-002",
        budget=budget,
        route_features={
            "task_type": "public_ops_research",
            "category": "ops_research",
            "difficulty": "hard",
            "repo_kind": "neutral_fixture",
        },
        expected_capabilities=("claim_gate", "delivery_gate"),
    )

    assert controls["gate_only_receipt_lite"] is True
    assert controls["supervised_bare_first"] is True
    assert controls["allow_medium_risk_supervised_bare_first"] is True
    assert controls["allow_pre_model_deterministic_rescue"] is True
    assert "expected_capability_protection" not in controls


def test_route_cost_controls_enable_swarm_receipt_executor_for_swarm_lane(tmp_path):
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:governance-hard-neutral",
                    "match": {
                        "task_type": "public_ops_research",
                        "category": "ops_research",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                    },
                    "controls": {
                        "allow_pre_model_deterministic_rescue": True,
                        "candidate_cap": 1,
                        "context_mode": "compact",
                        "disable_research": True,
                        "max_rounds": 1,
                        "route_lane": "governance_hardened",
                        "skip_llm_baseline": True,
                    },
                }
            ],
        }
    }

    controls = route_cost_controls_for_task(
        tmp_path,
        "route-oracle-swarm-001",
        budget=budget,
        route_features={
            "task_type": "public_ops_research",
            "category": "ops_research",
            "difficulty": "hard",
            "repo_kind": "neutral_fixture",
        },
        expected_capabilities=("swarm",),
    )

    assert controls["swarm_receipt_executor"] is True
    assert controls["route_oracle_receipt_lite"] is True
    assert "expected_capability_protection" not in controls


def test_route_cost_controls_enable_belief_receipt_lite_for_capped_lane(tmp_path):
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:belief-capped",
                    "match": {"task_type": "public_bugfix"},
                    "controls": {
                        "candidate_cap": 1,
                        "context_mode": "compact",
                        "disable_research": True,
                        "max_rounds": 1,
                        "route_lane": "belief_budget_hardened_capped",
                        "require_llm_baseline": True,
                    },
                }
            ],
        }
    }

    controls = route_cost_controls_for_task(
        tmp_path,
        "rlm-harder-v2-belief-001",
        budget=budget,
        route_features={"task_type": "public_bugfix"},
        expected_capabilities=("belief",),
    )

    assert controls["belief_receipt_lite"] is True
    assert controls["allow_pre_model_deterministic_rescue"] is True
    assert "expected_capability_protection" not in controls


def test_route_cost_controls_enable_hyper_receipt_lite_for_repair_capped_lane(tmp_path):
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:repair-capped",
                    "match": {"task_type": "public_test_repair"},
                    "controls": {
                        "candidate_cap": 1,
                        "context_mode": "compact",
                        "disable_research": True,
                        "max_rounds": 1,
                        "route_lane": "repair_capped",
                    },
                }
            ],
        }
    }

    controls = route_cost_controls_for_task(
        tmp_path,
        "rlm-harder-v2-second-round-002",
        budget=budget,
        route_features={"task_type": "public_test_repair"},
        expected_capabilities=("hyper", "delivery_gate"),
    )

    assert controls["hyper_receipt_lite"] is True
    assert controls["allow_pre_model_deterministic_rescue"] is True
    assert "expected_capability_protection" not in controls


def test_route_cost_controls_protect_expected_capabilities_from_cost_slimming(tmp_path):
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:low-cost-lite",
                    "match": {"task_type": "public_test_repair"},
                    "controls": {
                        "candidate_cap": 1,
                        "context_mode": "compact",
                        "disable_research": True,
                        "lite_route": True,
                        "supervised_bare_first": True,
                    },
                }
            ],
        }
    }

    controls = route_cost_controls_for_task(
        tmp_path,
        "route-oracle-ddtree-ultra-001",
        budget=budget,
        route_features={"task_type": "public_test_repair"},
        expected_capabilities=("ddtree", "ultra_review"),
    )

    assert controls["candidate_cap"] == 3
    assert controls["lite_route"] is False
    assert controls["supervised_bare_first"] is False
    assert controls["ddtree_mixed_candidate_pool"] is True
    assert controls["expected_capability_protection"] == ["ddtree", "ultra_review"]


def test_route_cost_controls_allow_deterministic_route_oracle_receipt_lite(tmp_path):
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:low-cost-lite",
                    "match": {"task_type": "public_test_repair"},
                    "controls": {
                        "allow_pre_model_deterministic_rescue": True,
                        "context_mode": "compact",
                        "disable_research": True,
                        "lite_route": True,
                        "max_rounds": 1,
                        "route_lane": "governance_hardened_capped",
                        "supervised_bare_first": True,
                    },
                }
            ],
        }
    }

    controls = route_cost_controls_for_task(
        tmp_path,
        "route-oracle-semantic-failure-sensor-001",
        budget=budget,
        route_features={"task_type": "public_test_repair"},
        expected_capabilities=("semantic_failure_sensor",),
    )

    assert controls["lite_route"] is True
    assert controls["route_oracle_receipt_lite"] is True
    assert controls["allow_pre_model_deterministic_rescue"] is True
    assert "expected_capability_protection" not in controls


def test_route_cost_controls_enable_preflight_receipt_lite_for_memory_lane(tmp_path):
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:memory-contract-compact",
                    "match": {"task_type": "public_bugfix"},
                    "controls": {
                        "candidate_cap": 2,
                        "context_mode": "compact",
                        "disable_research": True,
                        "max_rounds": 2,
                        "route_lane": "memory_contract_compact",
                    },
                }
            ],
        }
    }

    controls = route_cost_controls_for_task(
        tmp_path,
        "rlm-harder-v2-memory-001",
        budget=budget,
        route_features={"task_type": "public_bugfix"},
        expected_capabilities=("memory",),
    )

    assert controls["preflight_receipt_lite"] is True
    assert controls["allow_pre_model_deterministic_rescue"] is True
    assert "expected_capability_protection" not in controls


def test_route_cost_controls_enable_gate_receipt_lite_for_feature_and_hidden_lanes(tmp_path):
    for route_lane, task_type in (
        ("feature_reflex", "public_feature"),
        ("hidden_bugfix_supervised", "public_bugfix"),
    ):
        budget = {
            "route_cost_policy": {
                "source": "test",
                "feature_rules": [
                    {
                        "id": f"feature:{route_lane}",
                        "match": {"task_type": task_type},
                        "controls": {
                            "candidate_cap": 1,
                            "context_mode": "compact",
                            "disable_research": True,
                            "max_rounds": 1,
                            "route_lane": route_lane,
                            "supervised_bare_first": True,
                        },
                    }
                ],
            }
        }

        controls = route_cost_controls_for_task(
            tmp_path,
            f"{route_lane}-gate-task",
            budget=budget,
            route_features={"task_type": task_type},
            expected_capabilities=("artifact_gate", "claim_gate", "delivery_gate"),
        )

        assert controls["gate_only_receipt_lite"] is True
        assert controls["allow_pre_model_deterministic_rescue"] is True
        assert "expected_capability_protection" not in controls


def test_route_cost_controls_allow_autoreason_mixed_candidate_pool(tmp_path):
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:autoreason-cost-cap",
                    "match": {"task_type": "public_feature"},
                    "controls": {
                        "candidate_cap": 1,
                        "context_mode": "compact",
                        "disable_research": True,
                        "route_lane": "feature_reflex",
                    },
                }
            ],
        }
    }

    controls = route_cost_controls_for_task(
        tmp_path,
        "route-oracle-autoreason-001",
        budget=budget,
        route_features={"task_type": "public_feature"},
        expected_capabilities=("autoreason",),
    )

    assert "candidate_cap" not in controls
    assert controls["autoreason_mixed_candidate_pool"] is True
    assert controls["expected_capability_protection"] == ["autoreason"]


def test_route_cost_controls_keep_model_path_for_non_receipt_lite_expected_capabilities(tmp_path):
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:research-cost-cap",
                    "match": {"task_type": "public_feature"},
                    "controls": {
                        "candidate_cap": 1,
                        "context_mode": "compact",
                        "disable_research": True,
                        "max_rounds": 1,
                        "route_lane": "feature_reflex",
                        "skip_llm_baseline": True,
                    },
                }
            ],
        }
    }

    controls = route_cost_controls_for_task(
        tmp_path,
        "commercial-reasoning-judge-panel-002",
        budget=budget,
        route_features={"task_type": "public_feature"},
        expected_capabilities=("judge_panel",),
    )

    assert controls["require_llm_baseline"] is True
    assert "skip_llm_baseline" not in controls
    assert controls["disable_research"] is True
    assert controls["expected_capability_protection"] == ["judge_panel"]


def test_context_sync_capped_can_supervise_bare_with_preflight_receipts(tmp_path):
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:docs-context-capped",
                    "match": {"task_type": "public_docs_code_sync"},
                    "controls": {
                        "context_mode": "compact",
                        "disable_research": True,
                        "max_rounds": 1,
                        "route_lane": "context_sync_capped",
                        "supervised_bare_first": True,
                    },
                }
            ],
        }
    }

    controls = route_cost_controls_for_task(
        tmp_path,
        "model-required-docs-001",
        budget=budget,
        route_features={"task_type": "public_docs_code_sync"},
        expected_capabilities=("codeintel", "memory", "delivery_gate"),
    )

    assert controls["route_lane"] == "context_sync_capped"
    assert controls["supervised_bare_first"] is True
    assert "expected_capability_protection" not in controls


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


def test_capability_planner_capped_context_lane_prunes_runtime_reopened_research_stack():
    plan = CapabilityPlanner().plan(
        task_desc="Sync public docs with fixture behavior without external research.",
        task_type="public_docs_code_sync",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": False,
            "route_features": {
                "risk_score": 70,
                "has_governance_signal": True,
                "candidate_count": 1,
                "route_lane": "context_sync_capped",
            },
            "route_decision": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "governance_layers": ["ultra_review"],
            },
        },
        budget={
            "route_cost_policy": {
                "current_disable_research": True,
                "current_context_mode": "compact",
                "current_max_rounds": 1,
                "current_route_lane": "context_sync_capped",
                "source": "test",
            }
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"} <= selected
    assert "research_route" not in selected
    assert "research" not in selected
    assert "architecture_scout" not in selected
    assert "nightshift" not in selected
    assert "swarm" not in selected
    assert "drone" not in selected
    assert "judge_panel" not in selected
    assert "formal_report" not in selected


def test_capability_planner_capped_governance_lane_preserves_governance_gate_not_swarm_stack():
    plan = CapabilityPlanner().plan(
        task_desc="Refactor governance fixture with claim evidence and scoped policy safety.",
        task_type="public_refactor",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": False,
            "route_features": {
                "risk_score": 80,
                "has_governance_signal": True,
                "candidate_count": 1,
                "route_lane": "governance_hardened_capped",
            },
            "route_decision": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "governance_layers": ["ultra_review"],
            },
        },
        budget={
            "route_cost_policy": {
                "current_disable_research": True,
                "current_context_mode": "compact",
                "current_max_rounds": 1,
                "current_route_lane": "governance_hardened_capped",
                "source": "test",
            }
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"} <= selected
    assert "ultra_review" in selected
    assert "research_route" not in selected


def test_capability_planner_hardened_governance_lane_preserves_governance_gate_not_swarm_stack():
    plan = CapabilityPlanner().plan(
        task_desc="Classify a governance incident with trust-safe public evidence.",
        task_type="public_ops_research",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": False,
            "route_features": {
                "risk_score": 85,
                "has_governance_signal": True,
                "candidate_count": 1,
                "route_lane": "governance_hardened",
            },
            "route_decision": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "governance_layers": ["ultra_review"],
            },
        },
        budget={
            "route_cost_policy": {
                "current_disable_research": True,
                "current_context_mode": "compact",
                "current_max_rounds": 1,
                "current_route_lane": "governance_hardened",
                "source": "test",
            }
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert "ultra_review" in selected
    assert "research_route" not in selected
    assert "swarm" not in selected
    assert "nightshift" not in selected
    assert "research" not in selected
    assert "architecture_scout" not in selected
    assert "nightshift" not in selected
    assert "swarm" not in selected
    assert "drone" not in selected
    assert "judge_panel" not in selected
    assert "formal_report" not in selected


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


def test_capability_planner_route_cost_policy_respects_expected_safety_floor():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Exercise governance review and candidate factory routing."
            "\n\nNexus route oracle contract:"
            "\n- Expected capability receipts: autoreason, ultra_review, research."
        ),
        task_type="public_test_repair",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {"risk_score": 35, "candidate_count": 3},
        },
        budget={
            "route_cost_policy": {
                "current_lite_route": True,
                "current_disable_research": True,
                "protected_expected_capabilities": ["autoreason", "ultra_review", "research"],
                "source": "test",
            },
        },
    ).to_dict()

    trace = {item["capability"]: item for item in plan["decision_trace"]}
    for capability in ("autoreason", "ultra_review", "research"):
        assert capability in plan["selected_capabilities"]
        assert "route_oracle_expected_receipt_required" in trace[capability]["reasons"]
        assert not any(
            str(reason).startswith("route_cost_capped_lane") or str(reason).startswith("route_cost_disable_research")
            for reason in trace[capability]["reasons"]
        )


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


def test_capability_planner_harness_lite_lane_slims_seeded_high_cost_capabilities():
    plan = CapabilityPlanner().plan(
        task_desc="Fix a simple hidden fixture assertion with supervised bare-first fallback.",
        task_type="public_bugfix",
        route={
            "recommended_flow": "baseline",
            "route_decision": {
                "selected_capabilities": ["research", "swarm", "nightshift", "ultra_review", "benchmark"],
            },
            "route_features": {
                "risk_score": 10,
                "candidate_count": 1,
                "adjusted_root_cause_confidence": 0.98,
                "simple_hidden_bugfix": True,
            },
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert {"mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate", "harness_preflight_sensor"} <= selected
    assert not {"research", "swarm", "nightshift", "ultra_review", "benchmark"} & selected
    policy = plan["signal_snapshot"]["harness_cost_lane_policy"]
    assert policy["cost_lane"] == "lite"
    assert policy["applied"] is True
    assert {"swarm", "nightshift", "ultra_review", "benchmark"} <= set(policy["downgraded"])
    trace = {item["capability"]: item for item in plan["decision_trace"]}
    assert "harness_lite_lane_cost_slimming" in trace["swarm"]["reasons"]


def test_capability_planner_harness_lite_lane_preserves_route_oracle_expected_capability():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Fix a simple hidden fixture assertion with semantic retrieval proof."
            "\n\nNexus route oracle contract:"
            "\n- Expected capability receipts: semantic_searcher."
        ),
        task_type="public_bugfix",
        route={
            "recommended_flow": "baseline",
            "route_decision": {"selected_capabilities": ["semantic_searcher", "research"]},
            "route_features": {
                "risk_score": 10,
                "candidate_count": 1,
                "adjusted_root_cause_confidence": 0.98,
                "simple_hidden_bugfix": True,
            },
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert "semantic_searcher" in selected
    assert "research" not in selected
    policy = plan["signal_snapshot"]["harness_cost_lane_policy"]
    assert "semantic_searcher" in policy["protected"]


def test_capability_planner_drops_unbacked_bdd_and_failure_sensors_for_ops_route_oracles():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Accept a swarm review only when independent roles provide evidence and consensus is explicit."
            "\n\nNexus route oracle contract:"
            "\n- Expected capability receipts: swarm."
        ),
        task_type="public_ops_research",
        route={
            "recommended_flow": "hyper_sprint",
            "route_decision": {
                "selected_capabilities": [
                    "bdd_acceptance_skill",
                    "semantic_failure_sensor",
                    "swarm",
                ],
            },
            "route_features": {"risk_score": 75},
        },
    ).to_dict()

    selected = set(plan["selected_capabilities"])
    assert "swarm" in selected
    assert "bdd_acceptance_skill" not in selected
    assert "semantic_failure_sensor" not in selected
    relevance = plan["signal_snapshot"]["harness_relevance_policy"]
    assert set(relevance["downgraded"]) == {"bdd_acceptance_skill", "semantic_failure_sensor"}


def test_lane_policy_defaults_resolution_snapshot(tmp_path):
    controls_bugfix = route_cost_controls_for_task(
        tmp_path,
        "task-1",
        budget={"route_cost_policy": {"current_route_lane": "hidden_bugfix_supervised", "source": "test"}},
    )
    assert controls_bugfix.get("allow_pre_model_deterministic_rescue") is True

    controls_gov = route_cost_controls_for_task(
        tmp_path,
        "task-2",
        budget={"route_cost_policy": {"current_route_lane": "governance_hardened", "source": "test"}},
    )
    assert controls_gov.get("skip_llm_baseline") is True

    controls_context = route_cost_controls_for_task(
        tmp_path,
        "task-3",
        budget={"route_cost_policy": {"current_route_lane": "context_sync_capped", "source": "test"}},
    )
    assert controls_context.get("supervised_bare_first") is True

    budget_override = {
        "route_cost_policy": {
            "source": "test",
            "current_route_lane": "context_sync_capped",
            "feature_rules": [
                {
                    "id": "rule-1",
                    "match": {"task_type": "public_docs_code_sync"},
                    "controls": {
                        "supervised_bare_first": False,
                    }
                }
            ]
        }
    }
    controls_override = route_cost_controls_for_task(
        tmp_path,
        "task-4",
        budget=budget_override,
        route_features={"task_type": "public_docs_code_sync"}
    )
    assert "supervised_bare_first" not in controls_override or controls_override.get("supervised_bare_first") is False


def test_capability_planner_local_executor_planning(monkeypatch):
    # 1. By default, planner does not select local_model
    monkeypatch.delenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", raising=False)
    plan = CapabilityPlanner().plan(
        task_desc="test desc",
        task_type="bug",
        route={},
    )
    assert "local_model_executor" not in plan.selected_capabilities
    assert "selected_executor" not in plan.signal_snapshot

    # 2. When env gate is enabled, planner selects local_model
    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER", "ollama")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", "qwen2.5-coder:7b")
    
    plan_with_local = CapabilityPlanner().plan(
        task_desc="test desc",
        task_type="bug",
        route={},
    )
    
    # Assert local_model_executor is selected
    assert "local_model_executor" in plan_with_local.selected_capabilities
    
    # Assert metadata snapshot exists
    snapshot = plan_with_local.signal_snapshot
    assert snapshot["selected_executor"] == "local_model"
    assert snapshot["executor_provider"] == "ollama"
    assert snapshot["executor_model"] == "qwen2.5-coder:7b"
    assert snapshot["local_executor_authority"] == "candidate_only"
    
    # Assert route_truth_source is still CapabilityPlanner
    # We can check plan_with_local properties
    
    # Assert selected_capabilities include required gates
    assert "artifact_gate" in plan_with_local.selected_capabilities
    assert "claim_gate" in plan_with_local.selected_capabilities
    assert "delivery_gate" in plan_with_local.selected_capabilities
    
    # Assert authority/readiness are not implied as true by default
    assert not snapshot.get("public_claim_allowed", False)
    assert not snapshot.get("production_ready", False)


def test_capability_planner_local_committee_topology_metadata(monkeypatch):
    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY", "local_committee_only")

    plan = CapabilityPlanner().plan(
        task_desc="Fix zeta function logic",
        task_type="bug",
        route={
            "should_research": False,
            "recommended_flow": "direct",
        },
    )
    
    snapshot = plan.signal_snapshot
    assert "local_model_executor" in plan.selected_capabilities
    assert snapshot.get("execution_topology") == "ASSISTED_CANONICAL"
    assert snapshot.get("executor_topology") == "local_committee_only"
    assert snapshot.get("committee_profile") == "qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b"
    assert snapshot.get("local_committee_enabled") is True


# ── P0-T1: execution_depth contract tests ──────────────────────────────────


def test_execution_depth_l0_micro_patch_maps_to_light():
    """L0_micro_patch routing_tier must produce LIGHT execution_depth."""
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
    assert plan["execution_depth"] == "LIGHT"
    assert plan["signal_snapshot"]["execution_depth"] == "LIGHT"
    assert plan["signal_snapshot"]["execution_depth_source"] == "CapabilityPlanner:routing_tier"


def test_execution_depth_l1_green_lane_maps_to_light():
    """L1_green_lane routing_tier must produce LIGHT execution_depth."""
    plan = CapabilityPlanner().plan(
        task_desc="Rename a variable in a single file for clarity.",
        task_type="refactor",
        route={
            "recommended_flow": "direct",
            "route_features": {
                "risk_score": 15,
                "adjusted_root_cause_confidence": 0.90,
                "candidate_count": 1,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
        },
    ).to_dict()

    assert plan["signal_snapshot"]["routing_tier"] == "L1_green_lane"
    assert plan["execution_depth"] == "LIGHT"
    assert plan["signal_snapshot"]["execution_depth"] == "LIGHT"


def test_execution_depth_l2_hardened_maps_to_standard():
    """L2_hardened routing_tier must produce STANDARD execution_depth."""
    plan = CapabilityPlanner().plan(
        task_desc="Refactor auth module with moderate risk changes.",
        task_type="refactor",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 50,
                "adjusted_root_cause_confidence": 0.60,
                "candidate_count": 2,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
        },
    ).to_dict()

    assert plan["signal_snapshot"]["routing_tier"] == "L2_hardened"
    assert plan["execution_depth"] == "STANDARD"
    assert plan["signal_snapshot"]["execution_depth"] == "STANDARD"


def test_execution_depth_l3_swarm_deep_maps_to_full():
    """L3_swarm_deep routing_tier must produce FULL execution_depth."""
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
    ).to_dict()

    assert plan["signal_snapshot"]["routing_tier"] == "L3_swarm_deep"
    assert plan["execution_depth"] == "FULL"
    assert plan["signal_snapshot"]["execution_depth"] == "FULL"


def test_execution_depth_caller_cannot_override():
    """Caller-provided route['execution_depth'] must not override planner derivation."""
    plan = CapabilityPlanner().plan(
        task_desc="Rename a variable in a single file for clarity.",
        task_type="refactor",
        route={
            "recommended_flow": "direct",
            "execution_depth": "FULL",
            "route_features": {
                "risk_score": 15,
                "adjusted_root_cause_confidence": 0.90,
                "candidate_count": 1,
                "claim_uncertainty": False,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
        },
    ).to_dict()

    assert plan["signal_snapshot"]["routing_tier"] in ("L0_micro_patch", "L1_green_lane")
    assert plan["execution_depth"] == "LIGHT"


def test_execution_depth_invalid_value_fail_closed():
    """CapabilityPlan with invalid execution_depth must raise ValueError."""
    import pytest

    with pytest.raises(ValueError, match="invalid_execution_depth"):
        CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=[],
            required_capabilities=[],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=[],
            decision_trace=[],
            replan_trace=[],
            score=0.0,
            execution_depth="MAGIC",
        )


# ── P0-T2: execution_depth safety floor tests ─────────────────────────────


def test_execution_depth_safety_escalates_multi_candidate_light_to_standard():
    """Unsafe multi-candidate LIGHT plan must escalate to STANDARD execution_depth."""
    plan = CapabilityPlanner().plan(
        task_desc="Fix minor bug with candidate count 2.",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 15,
                "adjusted_root_cause_confidence": 0.90,
                "candidate_count": 2,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
        },
    ).to_dict()

    assert plan["signal_snapshot"]["routing_tier"] == "L1_green_lane"
    assert plan["execution_depth"] == "STANDARD"
    snapshot = plan["signal_snapshot"]
    assert snapshot["execution_depth"] == "STANDARD"
    policy = snapshot["execution_depth_policy"]
    assert policy["authority"] == "CapabilityPlanner"
    assert policy["base_depth"] == "LIGHT"
    assert policy["effective_depth"] == "STANDARD"
    assert policy["safety_advisor"] == "LiteRouteOracle"
    assert "candidate_count_gt_1" in policy["safety_blockers"]
    assert policy["escalated"] is True
    assert policy["reason"] == "lite_safety_floor_escalation"


def test_execution_depth_safety_escalates_low_confidence_light_to_standard():
    """Low-confidence LIGHT plan must escalate to STANDARD execution_depth."""
    plan = CapabilityPlanner().plan(
        task_desc="Fix minor bug with low confidence.",
        task_type="public_bugfix",
        route={
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 15,
                "adjusted_root_cause_confidence": 0.80,
                "candidate_count": 1,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
        },
    ).to_dict()

    assert plan["execution_depth"] == "STANDARD"
    policy = plan["signal_snapshot"]["execution_depth_policy"]
    assert policy["base_depth"] == "LIGHT"
    assert policy["effective_depth"] == "STANDARD"
    assert "confidence_below_0_85" in policy["safety_blockers"]
    assert policy["escalated"] is True
    assert policy["reason"] == "lite_safety_floor_escalation"


def test_execution_depth_safety_keeps_safe_light():
    """Safe LIGHT plan without blockers remains LIGHT execution_depth."""
    plan = CapabilityPlanner().plan(
        task_desc="Simple variable rename in a single module.",
        task_type="public_bugfix",
        route={
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 15,
                "adjusted_root_cause_confidence": 0.90,
                "candidate_count": 1,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
        },
    ).to_dict()

    assert plan["execution_depth"] == "LIGHT"
    policy = plan["signal_snapshot"]["execution_depth_policy"]
    assert policy["base_depth"] == "LIGHT"
    assert policy["effective_depth"] == "LIGHT"
    assert policy["safety_blockers"] == []
    assert policy["escalated"] is False
    assert policy["reason"] == "base_depth_preserved"


def test_execution_depth_safety_never_downgrades_standard():
    """L2_hardened (STANDARD base depth) must never be downgraded by safe parameters or caller suggestions."""
    plan = CapabilityPlanner().plan(
        task_desc="Moderate task with L2 routing.",
        task_type="refactor",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 50,
                "adjusted_root_cause_confidence": 0.95,
                "candidate_count": 1,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
        },
    ).to_dict()

    assert plan["signal_snapshot"]["routing_tier"] == "L2_hardened"
    assert plan["execution_depth"] == "STANDARD"
    policy = plan["signal_snapshot"]["execution_depth_policy"]
    assert policy["base_depth"] == "STANDARD"
    assert policy["effective_depth"] == "STANDARD"
    assert policy["escalated"] is False
    assert policy["reason"] == "base_depth_preserved"


def test_execution_depth_safety_never_downgrades_full():
    """L3_swarm_deep (FULL base depth) must never be downgraded by safe parameters or caller suggestions."""
    plan = CapabilityPlanner().plan(
        task_desc="Complex swarm task with L3 routing.",
        task_type="bug",
        route={
            "execution_depth": "LIGHT",
            "should_research": True,
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 86,
                "adjusted_root_cause_confidence": 0.95,
                "candidate_count": 1,
                "is_cross_module_task": True,
                "has_hard_signal": True,
            },
        },
        pillars={"lancedb": {"hits": 0}},
        codeintel={"impact_report_present": True},
    ).to_dict()

    assert plan["signal_snapshot"]["routing_tier"] == "L3_swarm_deep"
    assert plan["execution_depth"] == "FULL"
    policy = plan["signal_snapshot"]["execution_depth_policy"]
    assert policy["base_depth"] == "FULL"
    assert policy["effective_depth"] == "FULL"
    assert policy["escalated"] is False
    assert policy["reason"] == "base_depth_preserved"


def test_execution_depth_safety_ignores_caller_override():
    """Caller override cannot downgrade elevated effective depth or force invalid depth."""
    plan = CapabilityPlanner().plan(
        task_desc="Fix bug with candidate count 2.",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 15,
                "adjusted_root_cause_confidence": 0.90,
                "candidate_count": 2,
                "is_cross_module_task": False,
                "has_hard_signal": False,
            },
        },
    ).to_dict()

    assert plan["execution_depth"] == "STANDARD"
    assert plan["signal_snapshot"]["execution_depth"] == "STANDARD"


def test_replan_authorization_light_floor_to_standard():
    auth = ExecutionReplanAuthorization(
        task_id="task-replan-1",
        workspace_revision="rev-1",
        source_planner_decision_id="dec-1",
        source_replan_request_id="sha256:1111111111111111111111111111111111111111111111111111111111111111",
        source_receipt_hash="a" * 64,
        source_run_anchor_hash="b" * 64,
        requested_execution_depth="STANDARD",
        attempt_number=2,
        max_attempts=2,
    )
    planner = CapabilityPlanner()
    plan = planner.plan(
        task_desc="Safe low risk task",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 10,
                "adjusted_root_cause_confidence": 0.95,
                "candidate_count": 1,
            },
        },
        replan_authorization=auth,
    ).to_dict()

    assert plan["execution_depth"] == "STANDARD"
    policy = plan["signal_snapshot"]["execution_depth_policy"]
    assert policy["base_depth"] == "LIGHT"
    assert policy["effective_depth"] == "STANDARD"
    assert policy["escalated"] is True
    assert policy["reason"] == "replan_floor_applied"


def test_replan_authorization_standard_floor_to_full():
    auth = ExecutionReplanAuthorization(
        task_id="task-replan-2",
        workspace_revision="rev-1",
        source_planner_decision_id="dec-2",
        source_replan_request_id="sha256:2222222222222222222222222222222222222222222222222222222222222222",
        source_receipt_hash="c" * 64,
        source_run_anchor_hash="d" * 64,
        requested_execution_depth="FULL",
        attempt_number=2,
        max_attempts=2,
    )
    planner = CapabilityPlanner()
    plan = planner.plan(
        task_desc="Hardened L2 task",
        task_type="public_bugfix",
        route={
            "routing_tier": "L2_hardened",
            "execution_depth": "STANDARD",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 50,
                "adjusted_root_cause_confidence": 0.90,
                "candidate_count": 1,
            },
        },
        replan_authorization=auth,
    ).to_dict()

    assert plan["execution_depth"] == "FULL"
    policy = plan["signal_snapshot"]["execution_depth_policy"]
    assert policy["base_depth"] == "STANDARD"
    assert policy["effective_depth"] == "FULL"
    assert policy["escalated"] is True


def test_replan_authorization_never_downgrades_full():
    auth = ExecutionReplanAuthorization(
        task_id="task-replan-3",
        workspace_revision="rev-1",
        source_planner_decision_id="dec-3",
        source_replan_request_id="sha256:3333333333333333333333333333333333333333333333333333333333333333",
        source_receipt_hash="e" * 64,
        source_run_anchor_hash="f" * 64,
        requested_execution_depth="STANDARD",
        attempt_number=2,
        max_attempts=2,
    )
    planner = CapabilityPlanner()
    plan = planner.plan(
        task_desc="Deep swarm task",
        task_type="public_bugfix",
        route={
            "routing_tier": "L3_swarm_deep",
            "execution_depth": "FULL",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 86,
                "adjusted_root_cause_confidence": 0.90,
                "candidate_count": 1,
            },
        },
        replan_authorization=auth,
    ).to_dict()

    assert plan["execution_depth"] == "FULL"
    policy = plan["signal_snapshot"]["execution_depth_policy"]
    assert policy["base_depth"] == "FULL"
    assert policy["effective_depth"] == "FULL"


def test_replan_authorization_rejects_invalid_hash():
    with pytest.raises(ValueError, match="invalid_source_receipt_hash"):
        ExecutionReplanAuthorization(
            task_id="task-bad-hash-1",
            workspace_revision="rev-1",
            source_planner_decision_id="dec-1",
            source_replan_request_id="sha256:1111111111111111111111111111111111111111111111111111111111111111",
            source_receipt_hash="invalid_short_hash",
            source_run_anchor_hash="b" * 64,
            requested_execution_depth="STANDARD",
            attempt_number=2,
            max_attempts=2,
        )


def test_replan_authorization_rejects_attempt_above_budget():
    with pytest.raises(ValueError, match="attempt_number_must_be_2"):
        ExecutionReplanAuthorization(
            task_id="task-bad-attempt-1",
            workspace_revision="rev-1",
            source_planner_decision_id="dec-1",
            source_replan_request_id="sha256:1111111111111111111111111111111111111111111111111111111111111111",
            source_receipt_hash="a" * 64,
            source_run_anchor_hash="b" * 64,
            requested_execution_depth="STANDARD",
            attempt_number=3,
            max_attempts=2,
        )


def test_planner_ignores_route_replan_spoof():
    planner = CapabilityPlanner()
    plan = planner.plan(
        task_desc="Safe low risk task",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "execution_replan_request": {
                "replan_required": True,
                "requested_execution_depth": "FULL",
            },
            "replan_authorization": {
                "requested_execution_depth": "FULL",
            },
            "requested_execution_depth": "FULL",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 10,
                "adjusted_root_cause_confidence": 0.95,
                "candidate_count": 1,
            },
        },
    ).to_dict()

    assert plan["execution_depth"] == "LIGHT"
    assert "replan_authorization" not in plan["signal_snapshot"]


def test_planner_records_replan_authorization_lineage():
    auth = ExecutionReplanAuthorization(
        task_id="task-replan-lineage-1",
        workspace_revision="rev-1",
        source_planner_decision_id="dec-lineage-1",
        source_replan_request_id="sha256:4444444444444444444444444444444444444444444444444444444444444444",
        source_receipt_hash="1" * 64,
        source_run_anchor_hash="2" * 64,
        requested_execution_depth="STANDARD",
        attempt_number=2,
        max_attempts=2,
    )
    planner = CapabilityPlanner()
    plan = planner.plan(
        task_desc="Safe low risk task",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 10,
                "adjusted_root_cause_confidence": 0.95,
                "candidate_count": 1,
            },
        },
        replan_authorization=auth,
    ).to_dict()

    snap_auth = plan["signal_snapshot"]["replan_authorization"]
    assert snap_auth["schema"] == "nexus.execution_replan_authorization.v1"
    assert snap_auth["authority"] == "UnifiedRuntime"
    assert snap_auth["source_planner_decision_id"] == "dec-lineage-1"
    assert snap_auth["source_replan_request_id"] == "sha256:4444444444444444444444444444444444444444444444444444444444444444"
    assert snap_auth["source_receipt_hash"] == "1" * 64
    assert snap_auth["source_run_anchor_hash"] == "2" * 64
    assert snap_auth["requested_execution_depth"] == "STANDARD"
    assert snap_auth["attempt_number"] == 2
    assert snap_auth["max_attempts"] == 2
    assert snap_auth["floor_applied"] is True


def test_replan_authorization_rejects_invalid_schema():
    from nexus.engine.capability_contracts import ExecutionReplanAuthorization

    with pytest.raises(ValueError, match="invalid_replan_authorization_schema"):
        ExecutionReplanAuthorization(
            schema="evil.schema.v9",
            task_id="task-1",
            workspace_revision="rev-1",
            source_planner_decision_id="dec-1",
            source_replan_request_id="sha256:4444444444444444444444444444444444444444444444444444444444444444",
            source_receipt_hash="1" * 64,
            source_run_anchor_hash="2" * 64,
            requested_execution_depth="STANDARD",
            attempt_number=2,
            max_attempts=2,
        )


def test_replan_authorization_rejects_malformed_request_hash():
    from nexus.engine.capability_contracts import ExecutionReplanAuthorization

    with pytest.raises(ValueError, match="invalid_source_replan_request_id|malformed_replan_request_hash"):
        ExecutionReplanAuthorization(
            schema="nexus.execution_replan_authorization.v1",
            task_id="task-1",
            workspace_revision="rev-1",
            source_planner_decision_id="dec-1",
            source_replan_request_id="sha256:not-a-real-hash",
            source_receipt_hash="1" * 64,
            source_run_anchor_hash="2" * 64,
            requested_execution_depth="STANDARD",
            attempt_number=2,
            max_attempts=2,
        )


def test_workforce_demand_online_ordinary():
    plan = CapabilityPlanner().plan(
        task_desc="Implement simple bugfix in string utility module",
        task_type="bug",
        route={
            "workforce_admission_enabled": True,
            "online_enabled": True,
        },
    ).to_dict()

    demands = plan["signal_snapshot"]["workforce_demands"]
    assert demands["schema"] == "nexus.workforce_demands.v1"
    assert demands["route_authority"] == "CapabilityPlanner"
    assert len(demands["demands"]) == 1

    d = demands["demands"][0]
    assert d["schema"] == "nexus.workforce_demand.v1"
    assert d["demand_id"] == "demand_online"
    assert d["execution_channel"] == "online"
    assert d["requested_role"] == "fast_bounded_implementation"
    assert d["minimum_autonomy"] == "L2"
    assert d["context_class"] == "nexus_bounded"
    assert d["mutation_intent"] is True
    assert d["external_verification_required"] is True
    assert d["route_authority"] == "CapabilityPlanner"


def test_candidate_generation_only_projects_bounded_non_mutating_demand():
    plan = (
        CapabilityPlanner()
        .plan(
            task_desc="Produce one bounded implementation candidate for independent review",
            task_type="candidate_generation",
            route={
                "workforce_admission_enabled": True,
                "online_enabled": True,
                "topology_facts": {
                    "candidate_generation_only": True,
                    "mutation_requested": False,
                },
            },
        )
        .to_dict()
    )

    snapshot = plan["signal_snapshot"]
    assert snapshot["execution_topology"] == "ISOLATED_TARGET"
    demand = snapshot["workforce_demands"]["demands"][0]
    assert demand["requested_role"] == "bounded_candidate_generation"
    assert demand["minimum_autonomy"] == "L1"
    assert demand["context_class"] == "nexus_bounded"
    assert demand["mutation_intent"] is False
    assert demand["external_verification_required"] is True
    assert demand["route_authority"] == "CapabilityPlanner"
    assert not ({"worker_id", "provider", "model"} & set(demand))


@pytest.mark.parametrize(
    ("topology_facts", "route_mutation"),
    [
        ({"candidate_generation_only": True}, None),
        ({"candidate_generation_only": True, "mutation_requested": True}, None),
        ({"candidate_generation_only": "true", "mutation_requested": False}, None),
        ({"candidate_generation_only": True, "mutation_requested": False}, True),
        ({"candidate_generation_only": True, "mutation_requested": False}, "false"),
    ],
)
def test_candidate_generation_only_fails_closed_before_workforce_projection(
    topology_facts,
    route_mutation,
):
    route = {
        "workforce_admission_enabled": True,
        "online_enabled": True,
        "topology_facts": topology_facts,
    }
    if route_mutation is not None:
        route["mutation_requested"] = route_mutation
    with pytest.raises(ValueError, match="candidate_generation_only|topology_fact_must_be_bool"):
        CapabilityPlanner().plan(
            task_desc="Reject invalid candidate-only facts",
            task_type="candidate_generation",
            route=route,
        )


def test_candidate_required_retains_existing_isolation_and_workforce_semantics():
    plan = CapabilityPlanner().plan(
        task_desc="Implement one bounded candidate under the existing contract",
        task_type="bug",
        route={
            "workforce_admission_enabled": True,
            "online_enabled": True,
            "topology_facts": {"candidate_required": True},
        },
    ).to_dict()

    assert plan["signal_snapshot"]["execution_topology"] == "ISOLATED_TARGET"
    demand = plan["signal_snapshot"]["workforce_demands"]["demands"][0]
    assert demand["requested_role"] == "fast_bounded_implementation"
    assert demand["mutation_intent"] is True


def test_workforce_demand_online_complex_closure():
    plan = CapabilityPlanner().plan(
        task_desc="Perform self-hosted lifecycle runtime-closure for cross-module integration",
        task_type="runtime-closure",
        route={
            "workforce_admission_enabled": True,
            "online_enabled": True,
        },
    ).to_dict()

    demands = plan["signal_snapshot"]["workforce_demands"]
    assert len(demands["demands"]) == 1

    d = demands["demands"][0]
    assert d["demand_id"] == "demand_online"
    assert d["execution_channel"] == "online"
    assert d["requested_role"] == "main_engineering"
    assert d["minimum_autonomy"] == "L3_HISTORICAL"
    assert d["context_class"] == "nexus_full"
    assert d["external_verification_required"] is True


def test_workforce_demand_local_read_only():
    plan = CapabilityPlanner().plan(
        task_desc="Research prior lessons and document system architecture",
        task_type="research",
        route={
            "workforce_admission_enabled": True,
            "local_enabled": True,
        },
    ).to_dict()

    demands = plan["signal_snapshot"]["workforce_demands"]
    assert len(demands["demands"]) == 1

    d = demands["demands"][0]
    assert d["demand_id"] == "demand_local"
    assert d["execution_channel"] == "local"
    assert d["requested_role"] == "compact_diagnosis"
    assert d["minimum_autonomy"] == "L0.5"
    assert d["context_class"] == "nexus_bounded"
    assert d["mutation_intent"] is False
    assert d["external_verification_required"] is True


def test_workforce_demand_local_mutation():
    plan = CapabilityPlanner().plan(
        task_desc="Fix memory leak in buffer pool",
        task_type="bugfix",
        route={
            "workforce_admission_enabled": True,
            "local_enabled": True,
        },
    ).to_dict()

    demands = plan["signal_snapshot"]["workforce_demands"]
    assert len(demands["demands"]) == 1

    d = demands["demands"][0]
    assert d["demand_id"] == "demand_local"
    assert d["execution_channel"] == "local"
    assert d["requested_role"] == "bounded_code_candidate"
    assert d["minimum_autonomy"] == "L1"
    assert d["context_class"] == "nexus_bounded"
    assert d["mutation_intent"] is True
    assert d["external_verification_required"] is True


def test_workforce_demand_hybrid_stable_order():
    plan = CapabilityPlanner().plan(
        task_desc="Refactor database layer with local candidate and online implementation",
        task_type="refactor",
        route={
            "workforce_admission_enabled": True,
            "local_enabled": True,
            "online_enabled": True,
        },
    ).to_dict()

    demands = plan["signal_snapshot"]["workforce_demands"]["demands"]
    assert len(demands) == 2
    # Stable order: local then online
    assert demands[0]["execution_channel"] == "local"
    assert demands[0]["requested_role"] == "bounded_code_candidate"
    assert demands[1]["execution_channel"] == "online"
    assert demands[1]["requested_role"] == "fast_bounded_implementation"


def test_workforce_demand_no_identity_fields():
    plan = CapabilityPlanner().plan(
        task_desc="Check demands snapshot for identity leakage",
        task_type="feature",
        route={
            "workforce_admission_enabled": True,
            "local_enabled": True,
            "online_enabled": True,
        },
    ).to_dict()

    forbidden_fields = {"worker_id", "provider", "model", "availability", "state", "admission", "admission_decision"}
    snapshot = plan["signal_snapshot"]["workforce_demands"]

    assert not (set(snapshot.keys()) & forbidden_fields)
    for d in snapshot["demands"]:
        assert not (set(d.keys()) & forbidden_fields)


def test_workforce_demand_disabled_flag_preserves_current_snapshot():
    route_with_flags = {
        "local_enabled": True,
        "online_enabled": True,
    }

    plan_disabled = CapabilityPlanner().plan(
        task_desc="Fix bug without workforce admission enabled",
        task_type="bug",
        route={
            "workforce_admission_enabled": False,
            **route_with_flags,
        },
    ).to_dict()

    assert "workforce_demands" not in plan_disabled["signal_snapshot"]

    plan_default = CapabilityPlanner().plan(
        task_desc="Fix bug without workforce admission enabled",
        task_type="bug",
        route=route_with_flags,
    ).to_dict()

    assert "workforce_demands" not in plan_default["signal_snapshot"]
    assert plan_disabled["signal_snapshot"] == plan_default["signal_snapshot"]


def test_workforce_demand_documentation_closure_not_escalating():
    plan = CapabilityPlanner().plan(
        task_desc="Documentation closure for self-hosted lifecycle targets",
        task_type="docs_fix",
        route={
            "workforce_admission_enabled": True,
            "online_enabled": True,
        },
    ).to_dict()

    demands = plan["signal_snapshot"]["workforce_demands"]["demands"]
    assert len(demands) == 1
    d = demands[0]
    assert d["demand_id"] == "demand_online"
    assert d["requested_role"] == "fast_bounded_implementation"
    assert d["minimum_autonomy"] == "L2"
    assert d["context_class"] == "nexus_bounded"


def test_workforce_demand_review_integration_chooses_independent_review():
    plan = CapabilityPlanner().plan(
        task_desc="Review integration evidence only",
        task_type="review",
        route={
            "workforce_admission_enabled": True,
            "online_enabled": True,
        },
    ).to_dict()

    demands = plan["signal_snapshot"]["workforce_demands"]["demands"]
    assert len(demands) == 1
    d = demands[0]
    assert d["demand_id"] == "demand_online"
    assert d["requested_role"] == "independent_review"
    assert d["minimum_autonomy"] == "L2+"
    assert d["context_class"] == "nexus_bounded"


def test_workforce_demand_true_runtime_closure_remains_main_engineering():
    plan = CapabilityPlanner().plan(
        task_desc="Perform self-hosted lifecycle runtime-closure for cross-module integration",
        task_type="runtime-closure",
        route={
            "workforce_admission_enabled": True,
            "online_enabled": True,
        },
    ).to_dict()

    demands = plan["signal_snapshot"]["workforce_demands"]["demands"]
    assert len(demands) == 1
    d = demands[0]
    assert d["demand_id"] == "demand_online"
    assert d["requested_role"] == "main_engineering"
    assert d["minimum_autonomy"] == "L3_HISTORICAL"
    assert d["context_class"] == "nexus_full"
