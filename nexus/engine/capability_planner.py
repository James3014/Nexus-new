from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexus.engine.capability_contracts import CapabilityNode, CapabilityPlan, CapabilityScoringConfig
from nexus.engine.harness_route_policy import (
    apply_harness_cost_lane_policy,
    apply_harness_relevance_policy,
    apply_harness_sensor_policy,
    build_semantic_failure_snapshot,
)
from nexus.engine.harness_sensors import build_harness_preflight_sensor
from nexus.engine.policy_evaluator import apply_signal_policies, apply_tier_policies
from nexus.engine.planner.ab_evaluator import build_decision_trace
from nexus.engine.planner.policy_applier import apply_learning_policy
from nexus.engine.route_signal_adapter import build_replan_trace, build_signal_snapshot
from nexus.engine.capability_signals import build_capability_constraints, build_capability_signals
from nexus.learning.skill_catalog import SkillCatalog

PENDING_EXECUTOR_CAPABILITIES: set[str] = set()

DEFAULT_SKILL_STATUS_REPORT = "docs/reports/NEXUS_SKILL_STATUS_2026-05-15.json"


def _cost_tier(cost: int) -> str:
    if cost >= 5:
        return "high"
    if cost >= 3:
        return "medium"
    return "low"


def default_capability_nodes() -> dict[str, CapabilityNode]:
    nodes = [
        CapabilityNode(
            "harness_preflight_sensor",
            ("S", "P"),
            default_state="required",
            category="governance",
            maturity="production",
            dependencies=("pregate",),
            cost=1,
            benefit=3,
            risk_reduction=3,
            evidence_outputs=("capability_wired", "executor_ready", "cost_lane", "escalation_required"),
        ),
        CapabilityNode(
            "semantic_failure_sensor",
            ("R", "A"),
            category="validation",
            maturity="production",
            dependencies=("artifact_gate",),
            cost=1,
            benefit=3,
            risk_reduction=3,
            evidence_outputs=("failure_cause", "likely_fix", "retry_policy"),
        ),
        CapabilityNode(
            "bdd_acceptance_skill",
            ("A", "C"),
            category="validation",
            maturity="beta",
            dependencies=("acceptance_check", "claim_gate"),
            cost=2,
            benefit=4,
            risk_reduction=3,
            evidence_outputs=("given_when_then", "business_verified", "evidence_refs"),
        ),
        CapabilityNode(
            "codeintel",
            ("S", "P", "X", "A"),
            category="recon",
            maturity="production",
            dependencies=("artifact_gate",),
            parallelizable_with=("research",),
            cost=2,
            benefit=4,
            risk_reduction=3,
            evidence_outputs=("code_scan", "code_impact", "related_tests"),
        ),
        CapabilityNode(
            "research",
            ("X", "C"),
            category="recon",
            maturity="production",
            parallelizable_with=("codeintel",),
            cost=3,
            benefit=4,
            risk_reduction=2,
            evidence_outputs=("research_pack", "citations"),
        ),
        CapabilityNode(
            "hyper",
            ("P", "R", "A"),
            category="repair",
            maturity="production",
            dependencies=("artifact_gate",),
            cost=4,
            benefit=5,
            risk_reduction=2,
            evidence_outputs=("candidate_attempts", "repair_trace"),
        ),
        CapabilityNode(
            "nightshift",
            ("D", "R", "C"),
            category="repair",
            maturity="production",
            dependencies=("artifact_gate", "claim_gate"),
            cost=6,
            benefit=5,
            risk_reduction=4,
            evidence_outputs=("nightshift_report",),
        ),
        CapabilityNode(
            "swarm",
            ("D", "R", "A"),
            category="collaboration",
            maturity="beta",
            dependencies=("mempalace_gate", "artifact_gate"),
            parallelizable_with=("drone",),
            cost=5,
            benefit=5,
            risk_reduction=4,
            evidence_outputs=("role_findings", "consensus"),
        ),
        CapabilityNode(
            "swarm_quiet_moment",
            ("D", "R", "A"),
            category="collaboration",
            maturity="production",
            dependencies=("swarm",),
            cost=1,
            benefit=3,
            risk_reduction=5,
            evidence_outputs=("quiet_moment_event", "observe", "rollback", "non_mutating_gate"),
        ),
        CapabilityNode(
            "drone",
            ("R", "A"),
            category="collaboration",
            maturity="beta",
            dependencies=("artifact_gate",),
            parallelizable_with=("swarm",),
            cost=3,
            benefit=3,
            risk_reduction=2,
            evidence_outputs=("subtask_artifact",),
        ),
        CapabilityNode(
            "ultra_review",
            ("D", "A"),
            category="governance",
            maturity="beta",
            dependencies=("mempalace_gate", "artifact_gate", "claim_gate"),
            cost=5,
            benefit=5,
            risk_reduction=5,
            evidence_outputs=("verified_findings", "sandbox_repro", "gate_verdict"),
        ),
        CapabilityNode(
            "autoreason",
            ("D", "R", "A"),
            category="reasoning",
            maturity="beta",
            dependencies=("artifact_gate",),
            cost=3,
            benefit=4,
            risk_reduction=3,
            evidence_outputs=("judge_votes", "winner", "stop_reason"),
        ),
        CapabilityNode(
            "judge_panel",
            ("D", "R", "A"),
            category="reasoning",
            maturity="beta",
            dependencies=("artifact_gate", "claim_gate"),
            cost=3,
            benefit=5,
            risk_reduction=4,
            evidence_outputs=("panel_votes", "winner", "judge_mode", "judge_report", "gate_verdict"),
        ),
        CapabilityNode(
            "llm_judge_panel",
            ("D", "R", "A"),
            category="reasoning",
            maturity="legacy_alias",
            dependencies=("judge_panel",),
            cost=0,
            benefit=0,
            risk_reduction=0,
            evidence_outputs=("legacy_judge_panel_receipt",),
        ),
        CapabilityNode(
            "ddtree",
            ("X", "R", "A"),
            category="acceleration",
            maturity="beta",
            dependencies=("artifact_gate",),
            cost=1,
            benefit=3,
            risk_reduction=1,
            evidence_outputs=("pruned_candidates", "saved_steps"),
        ),
        CapabilityNode(
            "msa_router",
            ("P", "D"),
            category="routing",
            maturity="production",
            dependencies=("lancedb", "belief"),
            cost=1,
            benefit=3,
            risk_reduction=2,
            evidence_outputs=("candidate_count", "top_score", "rerank_reasons"),
        ),
        CapabilityNode(
            "jit_validation",
            ("A", "C"),
            category="validation",
            maturity="production",
            dependencies=("artifact_gate", "claim_gate"),
            cost=1,
            benefit=3,
            risk_reduction=4,
            evidence_outputs=("jit_report", "verify_commands", "replay_refs"),
        ),
        CapabilityNode(
            "memory",
            ("P", "X", "C"),
            category="memory",
            maturity="production",
            parallelizable_with=("research", "codeintel"),
            cost=2,
            benefit=4,
            risk_reduction=2,
            evidence_outputs=("memory_hits", "findings_hits", "lesson_writeback"),
        ),
        CapabilityNode(
            "lancedb",
            ("X",),
            category="memory",
            maturity="production",
            dependencies=("memory",),
            parallelizable_with=("research",),
            cost=2,
            benefit=3,
            risk_reduction=2,
            evidence_outputs=("vector_hits", "semantic_dedup"),
        ),
        CapabilityNode(
            "semantic_searcher",
            ("X", "D"),
            category="memory",
            maturity="production",
            dependencies=("lancedb",),
            parallelizable_with=("research", "codeintel"),
            cost=1,
            benefit=3,
            risk_reduction=2,
            evidence_outputs=("semantic_hits", "semantic_refs", "relevance"),
        ),
        CapabilityNode(
            "asi_constraint_extractor",
            ("S", "P", "D"),
            category="governance",
            maturity="beta",
            dependencies=("mempalace_gate",),
            cost=2,
            benefit=4,
            risk_reduction=5,
            evidence_outputs=("extracted_constraints", "blocked_assumptions", "constraint_report"),
        ),
        CapabilityNode(
            "belief",
            ("D", "R"),
            category="governance",
            maturity="beta",
            cost=1,
            benefit=3,
            risk_reduction=3,
            evidence_outputs=("belief_confidence", "budget_adjustment"),
        ),
        CapabilityNode(
            "repair_loop",
            ("R", "A"),
            category="repair",
            maturity="production",
            dependencies=("artifact_gate",),
            cost=3,
            benefit=4,
            risk_reduction=3,
            evidence_outputs=("repair_attempts", "settlement"),
        ),
        CapabilityNode(
            "direct_mode",
            ("S", "P", "X", "D", "R", "A", "C"),
            category="execution",
            maturity="production",
            dependencies=("delivery_gate",),
            cost=2,
            benefit=3,
            risk_reduction=2,
            evidence_outputs=("run_report", "completion_envelope", "verify_commands"),
        ),
        CapabilityNode(
            "learn_mode",
            ("X", "A", "C"),
            category="learning",
            maturity="production",
            dependencies=("claim_gate",),
            parallelizable_with=("research",),
            cost=3,
            benefit=4,
            risk_reduction=3,
            evidence_outputs=("claims_count", "verified_claims_count", "citations", "unresolved_questions"),
        ),
        CapabilityNode(
            "learn_scheduler",
            ("X", "C"),
            category="learning",
            maturity="beta",
            dependencies=("learn_mode",),
            cost=2,
            benefit=3,
            risk_reduction=2,
            evidence_outputs=("due_count", "sources_total", "last_run", "alert_paths"),
        ),
        CapabilityNode(
            "learn_phase_slo",
            ("P", "X", "D", "R", "A", "C"),
            category="learning",
            maturity="production",
            dependencies=("learn_mode",),
            cost=2,
            benefit=4,
            risk_reduction=3,
            evidence_outputs=("phase_slo_pass", "required_done_ratio", "success_ratio", "policy_reasoning"),
        ),
        CapabilityNode(
            "research_route",
            ("S", "P", "X"),
            default_state="required",
            category="routing",
            maturity="production",
            cost=1,
            benefit=4,
            risk_reduction=2,
            evidence_outputs=("recommended_flow", "route_features", "explain_payload"),
        ),
        CapabilityNode(
            "research_control_plane",
            ("X", "R", "A", "C"),
            category="self_improvement",
            maturity="beta",
            dependencies=("research", "artifact_gate"),
            cost=5,
            benefit=5,
            risk_reduction=3,
            evidence_outputs=("winner", "elimination_matrix", "rollback_trace", "semantic_status"),
        ),
        CapabilityNode(
            "architecture_scout",
            ("X", "D"),
            category="recon",
            maturity="beta",
            dependencies=("codeintel",),
            parallelizable_with=("research",),
            cost=3,
            benefit=5,
            risk_reduction=4,
            evidence_outputs=("architecture_map", "blast_radius", "boundary_refs"),
        ),
        CapabilityNode(
            "external_doc_scout",
            ("X",),
            category="recon",
            maturity="beta",
            dependencies=("research",),
            parallelizable_with=("codeintel",),
            cost=3,
            benefit=4,
            risk_reduction=3,
            evidence_outputs=("doc_hits", "citations", "verified_claims", "rejected_claims"),
        ),
        CapabilityNode(
            "sandbox",
            ("R", "A"),
            category="governance",
            maturity="production",
            dependencies=("artifact_gate",),
            cost=3,
            benefit=3,
            risk_reduction=4,
            evidence_outputs=("sandbox_path", "exit_code", "replay_artifact"),
        ),
        CapabilityNode(
            "multi_agent",
            ("P", "D", "R", "A", "C"),
            category="collaboration",
            maturity="beta",
            dependencies=("file_lock", "artifact_gate", "claim_gate"),
            parallelizable_with=("swarm", "drone"),
            cost=5,
            benefit=5,
            risk_reduction=4,
            evidence_outputs=("task_id", "owner", "allowed_files", "worktree", "gate_status"),
        ),
        CapabilityNode(
            "file_lock",
            ("S", "P", "D"),
            category="governance",
            maturity="production",
            cost=1,
            benefit=3,
            risk_reduction=5,
            evidence_outputs=("locked_files", "conflicts", "denied_paths", "briefing_enforced"),
        ),
        CapabilityNode(
            "integration_manager",
            ("C",),
            category="collaboration",
            maturity="beta",
            dependencies=("delivery_gate", "file_lock"),
            cost=3,
            benefit=4,
            risk_reduction=3,
            evidence_outputs=("target_branch", "merge_result", "evidence_chain"),
        ),
        CapabilityNode(
            "delivery_gate",
            ("A", "C"),
            default_state="required",
            category="validation",
            maturity="production",
            dependencies=("artifact_gate", "claim_gate"),
            benefit=4,
            risk_reduction=5,
            evidence_outputs=("delivery_receipt", "gate_verdict"),
        ),
        CapabilityNode(
            "acceptance_check",
            ("A", "C"),
            category="validation",
            maturity="production",
            dependencies=("delivery_gate",),
            cost=2,
            benefit=3,
            risk_reduction=3,
            evidence_outputs=("acceptance_report",),
        ),
        CapabilityNode(
            "benchmark",
            ("C",),
            category="self_improvement",
            maturity="production",
            dependencies=("artifact_gate",),
            cost=4,
            benefit=4,
            risk_reduction=2,
            evidence_outputs=("benchmark_report", "public_claim_gate"),
        ),
        CapabilityNode(
            "formal_report",
            ("C",),
            category="validation",
            maturity="beta",
            dependencies=("delivery_gate", "claim_gate"),
            cost=2,
            benefit=4,
            risk_reduction=4,
            evidence_outputs=("formal_report_path", "schema_version", "verification_summary"),
        ),
        CapabilityNode(
            "meta_opt",
            ("C",),
            category="self_improvement",
            maturity="beta",
            dependencies=("benchmark", "memory"),
            cost=5,
            benefit=5,
            risk_reduction=3,
            evidence_outputs=("tuning_delta", "rule_lifecycle_decision"),
        ),
        CapabilityNode(
            "autonomic_router",
            ("P", "D"),
            category="routing",
            maturity="prototype",
            dependencies=("belief",),
            cost=2,
            benefit=3,
            risk_reduction=2,
            evidence_outputs=("autonomic_route", "policy_reason"),
        ),
        CapabilityNode(
            "pregate",
            ("S", "P"),
            category="governance",
            maturity="production",
            dependencies=("mempalace_gate",),
            cost=1,
            benefit=3,
            risk_reduction=4,
            evidence_outputs=("pregate_verdict", "blocked_reason"),
        ),
        CapabilityNode(
            "forecast_gate",
            ("P", "D"),
            category="governance",
            maturity="beta",
            dependencies=("belief",),
            cost=2,
            benefit=3,
            risk_reduction=3,
            evidence_outputs=("risk_forecast",),
        ),
        CapabilityNode(
            "plan_quality_gate",
            ("P", "D"),
            category="governance",
            maturity="production",
            cost=1,
            benefit=3,
            risk_reduction=3,
            evidence_outputs=("plan_quality_verdict",),
        ),
        CapabilityNode(
            "xray",
            ("X", "D"),
            category="recon",
            maturity="beta",
            parallelizable_with=("codeintel", "research"),
            cost=3,
            benefit=4,
            risk_reduction=2,
            evidence_outputs=("xray_findings",),
        ),
        CapabilityNode(
            "ui_validator",
            ("A",),
            category="validation",
            maturity="beta",
            dependencies=("artifact_gate",),
            cost=3,
            benefit=3,
            risk_reduction=2,
            evidence_outputs=("ui_validation_report",),
        ),
        CapabilityNode(
            "stress_test",
            ("A", "C"),
            category="validation",
            maturity="beta",
            dependencies=("artifact_gate",),
            cost=4,
            benefit=3,
            risk_reduction=3,
            evidence_outputs=("stress_test_report",),
        ),
        CapabilityNode(
            "registry_sync",
            ("S", "C"),
            category="platform",
            maturity="beta",
            cost=2,
            benefit=3,
            risk_reduction=2,
            evidence_outputs=("skills_count", "models_configured", "policies_count", "sync_delta"),
        ),
        CapabilityNode(
            "metabolism",
            ("C", "S"),
            category="continuity",
            maturity="beta",
            dependencies=("memory",),
            cost=1,
            benefit=3,
            risk_reduction=2,
            evidence_outputs=("checkpoint", "task_id", "resume_available"),
        ),
        CapabilityNode(
            "oracle_shadow",
            ("P", "R", "A", "C"),
            category="repair",
            maturity="experimental",
            dependencies=("sandbox", "delivery_gate"),
            cost=5,
            benefit=4,
            risk_reduction=3,
            evidence_outputs=("shadow_tid", "promotion_status", "advice", "report_path"),
        ),
        CapabilityNode(
            "federation",
            ("X", "R", "C"),
            category="self_improvement",
            maturity="experimental",
            dependencies=("benchmark", "meta_opt"),
            cost=6,
            benefit=4,
            risk_reduction=2,
            evidence_outputs=("tenants", "aggregation_ratio", "fitness", "generation"),
        ),
        CapabilityNode(
            "mempalace_gate",
            ("S", "D", "A"),
            default_state="required",
            category="governance",
            maturity="production",
            benefit=3,
            risk_reduction=5,
            evidence_outputs=("policy_verdict", "blocked_reason"),
        ),
        CapabilityNode(
            "artifact_gate",
            ("A", "C"),
            default_state="required",
            category="validation",
            maturity="production",
            benefit=4,
            risk_reduction=5,
            evidence_outputs=("artifact_manifest",),
        ),
        CapabilityNode(
            "claim_gate",
            ("A", "C"),
            default_state="required",
            category="validation",
            maturity="production",
            benefit=4,
            risk_reduction=5,
            evidence_outputs=("claim_verdict",),
        ),
    ]
    return {node.name: node for node in nodes}


class CapabilityPlanner:
    """Dry-run constrained planner for Nexus capability composition."""

    def __init__(self, nodes: dict[str, CapabilityNode] | None = None) -> None:
        self.nodes = nodes or default_capability_nodes()

    def plan(
        self,
        *,
        task_desc: str,
        task_type: str,
        route: dict[str, Any],
        pillars: dict[str, Any] | None = None,
        codeintel: dict[str, Any] | None = None,
        phase_trace: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        skills: list[dict[str, Any]] | None = None,
    ) -> CapabilityPlan:
        pillars = pillars or {}
        codeintel = codeintel or {}
        phase_trace = phase_trace or {}
        budget = budget or {}
        signals = build_capability_signals(
            task_desc=task_desc,
            task_type=task_type,
            route=route,
            pillars=pillars,
            codeintel=codeintel,
            skills=skills,
        )
        constraint_model = build_capability_constraints(budget)
        scoring = CapabilityScoringConfig.from_budget(budget)

        states: dict[str, str] = {
            name: ("required" if node.default_state == "required" else "optional")
            for name, node in self.nodes.items()
        }
        reasons: dict[str, list[str]] = {name: [] for name in self.nodes}
        constraints = list(constraint_model.hard_constraints)

        for required in ("mempalace_gate", "artifact_gate", "claim_gate"):
            reasons[required].append("governance_hard_constraint")
        reasons["delivery_gate"].append("delivery_fail_closed_contract")
        reasons["research_route"].append("routing_contract_required")
        reasons["harness_preflight_sensor"].append("feed_forward_harness_required")

        def enable(name: str, reason: str) -> None:
            if name not in states or states[name] == "required":
                return
            states[name] = "conditional"
            reasons[name].append(reason)

        routing_tier, routing_tier_reason = self._decide_routing_tier(signals)
        apply_signal_policies(
            signals=signals,
            task_desc=task_desc,
            task_type=task_type,
            enable=enable,
        )
        apply_tier_policies(
            states=states,
            reasons=reasons,
            routing_tier=routing_tier,
            signals=signals,
            enable=enable,
        )
        learning_policy = budget.get("learning_policy", {}) if isinstance(budget.get("learning_policy", {}), dict) else {}
        self._apply_learning_policy(states=states, reasons=reasons, learning_policy=learning_policy, enable=enable)
        self._apply_research_evidence_demand_policy(states=states, reasons=reasons, signals=signals)
        route_cost_policy = budget.get("route_cost_policy", {}) if isinstance(budget.get("route_cost_policy", {}), dict) else {}
        safety_floor = self._budget_safety_floor(signals=signals, routing_tier=routing_tier)
        self._apply_route_cost_policy(
            states=states,
            reasons=reasons,
            route_cost_policy=route_cost_policy,
            protected_capabilities=set(getattr(signals, "route_oracle_expected_capabilities", ()) or ()),
        )
        s2t_policy_draft = (
            budget.get("s2t_policy_draft", {}) if isinstance(budget.get("s2t_policy_draft", {}), dict) else {}
        )
        s2t_shadow_score = self._score_s2t_policy_draft(
            route=route,
            signals=signals,
            states=states,
            s2t_policy_draft=s2t_policy_draft,
        )
        self._apply_s2t_policy_promotion(
            states=states,
            reasons=reasons,
            s2t_shadow_score=s2t_shadow_score,
            safety_floor=safety_floor,
        )
        self._apply_mutation_assurance_policy(states=states, reasons=reasons, route=route)
        self._apply_candidate_factory_readiness_policy(states=states, reasons=reasons, route=route)
        self._apply_route_oracle_expected_contract(states=states, reasons=reasons, signals=signals)
        self._apply_research_evidence_demand_policy(states=states, reasons=reasons, signals=signals)
        self._apply_simple_hidden_contract_policy(states=states, reasons=reasons, signals=signals)
        apply_harness_sensor_policy(
            states=states,
            reasons=reasons,
            route=route,
            task_desc=task_desc,
        )
        harness_relevance_policy = apply_harness_relevance_policy(
            states=states,
            reasons=reasons,
            route=route,
            task_desc=task_desc,
            route_oracle_expected_capabilities=getattr(signals, "route_oracle_expected_capabilities", ()) or (),
        )
        harness_cost_lane_policy = apply_harness_cost_lane_policy(
            states=states,
            reasons=reasons,
            route=route,
            task_desc=task_desc,
            task_type=task_type,
            routing_tier=routing_tier,
            route_oracle_expected_capabilities=getattr(signals, "route_oracle_expected_capabilities", ()) or (),
        )

        selected = [name for name, state in states.items() if state in {"required", "conditional"}]
        pending = [name for name in selected if name in PENDING_EXECUTOR_CAPABILITIES]
        total_cost = sum(self.nodes[name].cost for name in selected)
        states, reasons, forbidden, total_cost = self._apply_budget_downgrade(
            states=states,
            reasons=reasons,
            scoring=scoring,
            max_cost=constraint_model.max_cost,
            safety_floor=self._budget_safety_floor(signals=signals, routing_tier=routing_tier),
        )
        ssd_route_map = self._build_ssd_route_map(
            states=states,
            reasons=reasons,
            signals=signals,
            routing_tier=routing_tier,
            total_cost=total_cost,
        )
        context_slimming_policy = self._build_context_slimming_policy(
            states=states,
            signals=signals,
            routing_tier=routing_tier,
        )
        harness_preflight_sensor = build_harness_preflight_sensor(
            task_desc=task_desc,
            task_type=task_type,
            route=route,
            pending_capabilities=pending,
            selected_capabilities=[name for name, state in states.items() if state in {"required", "conditional"}],
        )
        semantic_failure_sensor = build_semantic_failure_snapshot(route=route, task_desc=task_desc)

        leverage_roles = ssd_route_map.get("leverage_roles", {})
        score, decision_trace = build_decision_trace(
            nodes=self.nodes,
            states=states,
            reasons=reasons,
            scoring=scoring,
            s2t_shadow_score=s2t_shadow_score,
            leverage_roles=leverage_roles,
            cost_tier=_cost_tier,
        )

        replan_trace = build_replan_trace(
            states=states,
            phase_trace=phase_trace,
            risk_score=signals.risk_score,
            confidence=signals.confidence,
            nodes=self.nodes,
        )
        signal_snapshot = build_signal_snapshot(
            signals=signals,
            routing_tier=routing_tier,
            routing_tier_reason=routing_tier_reason,
        )
        signal_snapshot["recommended_flow_source"] = "route.recommended_flow"
        signal_snapshot["planner_version"] = "capability_planner_v1"
        if learning_policy:
            signal_snapshot["learning_policy"] = {
                "influenced": True,
                "source_experiences": tuple(learning_policy.get("source_experiences", ()) or ()),
                "promoted_capabilities": tuple(learning_policy.get("promoted_capabilities", ()) or ()),
                "penalized_capabilities": tuple(learning_policy.get("penalized_capabilities", ()) or ()),
            }
        if route_cost_policy:
            signal_snapshot["route_cost_policy"] = {
                "influenced": True,
                "source": str(route_cost_policy.get("source") or ""),
                "current_lite_route": bool(route_cost_policy.get("current_lite_route", False)),
                "current_candidate_cap": route_cost_policy.get("current_candidate_cap"),
            }
        skill_mount_evidence = self._build_skill_mount_evidence(
            skills=skills or [],
            budget=budget,
            selected_capabilities=[name for name, state in states.items() if state in {"required", "conditional"}],
        )
        if skill_mount_evidence["skill_mount_contracts"] or skill_mount_evidence["skill_mount_violations"]:
            signal_snapshot["planned_skill_mount_contracts"] = skill_mount_evidence["skill_mount_contracts"]
            signal_snapshot["skill_mount_violations"] = skill_mount_evidence["skill_mount_violations"]
        if s2t_policy_draft:
            signal_snapshot["s2t_policy_draft"] = s2t_shadow_score
        signal_snapshot["ssd_route_map"] = ssd_route_map
        signal_snapshot["context_slimming_policy"] = context_slimming_policy
        signal_snapshot["harness_relevance_policy"] = harness_relevance_policy
        signal_snapshot["harness_cost_lane_policy"] = harness_cost_lane_policy
        signal_snapshot["harness_preflight_sensor"] = harness_preflight_sensor
        if semantic_failure_sensor:
            signal_snapshot["semantic_failure_sensor"] = semantic_failure_sensor

        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            planner_mode="dry_run",
            selected_capabilities=[name for name, state in states.items() if state in {"required", "conditional"}],
            required_capabilities=[name for name, state in states.items() if state == "required"],
            optional_capabilities=[name for name, state in states.items() if state == "optional"],
            conditional_capabilities=[name for name, state in states.items() if state == "conditional"],
            pending_capabilities=pending,
            forbidden_capabilities=[name for name, state in states.items() if state == "forbidden"],
            constraints=constraints,
            decision_trace=decision_trace,
            replan_trace=replan_trace,
            score=score,
            signal_snapshot=signal_snapshot,
        )

    @staticmethod
    def _runtime_policy_overlay_skill_requests(
        *,
        budget: dict[str, Any],
        selected_capabilities: list[str],
    ) -> list[dict[str, str]]:
        overlay = budget.get("runtime_skill_policy_overlay")
        overlay_path = str(budget.get("runtime_skill_policy_overlay_path") or "").strip()
        if overlay is None and overlay_path:
            try:
                overlay = json.loads(Path(overlay_path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
        if not isinstance(overlay, dict) or overlay.get("status") != "PASS":
            return []
        mapping = overlay.get("primary_skill_by_capability")
        if not isinstance(mapping, dict):
            return []
        aliases = overlay.get("capability_aliases")
        aliases = aliases if isinstance(aliases, dict) else {}
        selected = set(selected_capabilities)
        requests: list[dict[str, str]] = []
        for capability, skill_id in mapping.items():
            capability_id = str(capability or "").strip()
            skill_name = str(skill_id or "").strip()
            capability_aliases = {
                str(alias)
                for alias in aliases.get(capability_id, [])
                if str(alias)
            }
            if skill_name and (capability_id in selected or selected.intersection(capability_aliases)):
                requests.append(
                    {
                        "skill_id": skill_name,
                        "capability_id": capability_id,
                        "source": "sf_runtime_policy_overlay",
                    }
                )
        return requests

    @staticmethod
    def _build_skill_mount_evidence(
        *,
        skills: list[dict[str, Any]],
        budget: dict[str, Any],
        selected_capabilities: list[str],
    ) -> dict[str, Any]:
        requested_skills = [
            skill
            for skill in skills
            if isinstance(skill, dict) and str(skill.get("skill_id") or skill.get("task_id") or "").strip()
        ]
        if not requested_skills:
            requested_skills = CapabilityPlanner._runtime_policy_overlay_skill_requests(
                budget=budget,
                selected_capabilities=selected_capabilities,
            )
        skill_ids = [
            str(skill.get("skill_id") or skill.get("task_id") or "").strip()
            for skill in requested_skills
        ]
        if not skill_ids:
            return {"skill_mount_contracts": [], "skill_mount_violations": []}
        capability_overrides = {
            str(skill.get("skill_id") or skill.get("task_id") or "").strip(): str(
                skill.get("capability_id") or skill.get("capability_mount") or ""
            ).strip()
            for skill in requested_skills
            if isinstance(skill, dict)
            and str(skill.get("skill_id") or skill.get("task_id") or "").strip()
            and str(skill.get("capability_id") or skill.get("capability_mount") or "").strip()
        }
        overlay_skill_ids = {
            str(skill.get("skill_id") or skill.get("task_id") or "").strip()
            for skill in requested_skills
            if isinstance(skill, dict) and str(skill.get("source") or "") == "sf_runtime_policy_overlay"
        }

        status_report = str(
            budget.get("skill_status_report")
            or budget.get("skill_catalog_status_report")
            or DEFAULT_SKILL_STATUS_REPORT
        )
        try:
            catalog = SkillCatalog.from_status_report(status_report)
        except (OSError, json.JSONDecodeError):
            return {
                "skill_mount_contracts": [],
                "skill_mount_violations": [
                    {
                        "skill_name": skill_id,
                        "path": "",
                        "reason": "skill_catalog_unavailable",
                    }
                    for skill_id in skill_ids
                ],
            }

        selected_set = set(selected_capabilities)
        allow_ablation_skill_mounts = bool(budget.get("allow_ablation_skill_mounts"))
        contracts: list[dict[str, Any]] = []
        for skill_id in skill_ids:
            entry = catalog.get(skill_id)
            if entry is None:
                continue
            overlay_request = skill_id in overlay_skill_ids
            if (
                not entry.is_runtime_mount_candidate
                and not (allow_ablation_skill_mounts and entry.is_reference_only)
                and not overlay_request
            ):
                continue
            capability_mount = capability_overrides.get(skill_id) or entry.capability_mount or "unmapped_skill_capability"
            if capability_mount.startswith("reference:"):
                capability_mount = capability_mount.removeprefix("reference:")
            load_reason_codes = [
                "capability_planner_skill_signal",
                f"catalog_status:{entry.skill_status}",
            ]
            if allow_ablation_skill_mounts and entry.is_reference_only:
                load_reason_codes.append("benchmark_ablation_only_mount")
            if overlay_request:
                load_reason_codes.append("sf_runtime_policy_overlay")
            contracts.append(
                {
                    "skill_id": entry.name,
                    "skill_status": entry.skill_status,
                    "capability_mount": capability_mount,
                    "capability": capability_mount,
                    "load_reason_codes": load_reason_codes,
                    "evidence_refs": [
                        f"skill_catalog:{entry.name}",
                        f"skill_path:{entry.path}",
                    ],
                    "planner_selected_capability": capability_mount in selected_set or overlay_request,
                }
            )
        validation_skill_ids = [skill_id for skill_id in skill_ids if skill_id not in overlay_skill_ids]
        violations = [
            violation.to_dict()
            for violation in catalog.validate_requested_mounts(
                validation_skill_ids,
                allow_ablation=allow_ablation_skill_mounts,
            )
        ]
        return {"skill_mount_contracts": contracts, "skill_mount_violations": violations}

    @staticmethod
    def _decide_routing_tier(signals: Any) -> tuple[str, str]:
        if signals.simple_hidden_bugfix and signals.confidence >= 0.85:
            return "L0_micro_patch", "simple_hidden_bugfix_low_risk"
        if signals.hazard_forced_l3:
            return "L3_swarm_deep", "hazard_mapping_forced_l3"
        if signals.risk_score < 30 and signals.confidence >= 0.7 and not signals.cross_module:
            return "L1_green_lane", "low_risk_low_ambiguity"
        if signals.risk_score >= 70 or signals.cross_module:
            return "L3_swarm_deep", "high_risk_or_cross_module"
        return "L2_hardened", "default_hardened_lane"

    def _apply_learning_policy(
        self,
        *,
        states: dict[str, str],
        reasons: dict[str, list[str]],
        learning_policy: dict[str, Any],
        enable: Any,
    ) -> None:
        apply_learning_policy(
            nodes=self.nodes,
            states=states,
            reasons=reasons,
            learning_policy=learning_policy,
            enable=enable,
        )

    def _apply_route_oracle_expected_contract(
        self,
        *,
        states: dict[str, str],
        reasons: dict[str, list[str]],
        signals: Any,
    ) -> None:
        for name in getattr(signals, "route_oracle_expected_capabilities", ()) or ():
            cap = str(name)
            if cap not in self.nodes:
                continue
            if states.get(cap) != "required":
                states[cap] = "required"
                reasons[cap].append("route_oracle_expected_receipt_required")

    def _apply_simple_hidden_contract_policy(
        self,
        *,
        states: dict[str, str],
        reasons: dict[str, list[str]],
        signals: Any,
    ) -> None:
        if not getattr(signals, "simple_hidden_bugfix", False):
            return
        protected = set(getattr(signals, "route_oracle_expected_capabilities", ()) or ())
        protected.update(str(item) for item in getattr(signals, "selected_seed", ()) or ())
        for cap in (
            "research",
            "external_doc_scout",
            "research_control_plane",
            "architecture_scout",
            "autoreason",
            "judge_panel",
            "llm_judge_panel",
            "benchmark",
            "meta_opt",
        ):
            if cap in protected:
                continue
            if states.get(cap) == "conditional":
                states[cap] = "optional"
                reasons[cap].append("simple_hidden_contract_fast_path_cost_control")

    def _apply_research_evidence_demand_policy(
        self,
        *,
        states: dict[str, str],
        reasons: dict[str, list[str]],
        signals: Any,
    ) -> None:
        if states.get("research") != "conditional":
            return
        task_text = str(getattr(signals, "task_desc", "") or "").lower()
        explicit_research_demand = bool(
            signals.claim_uncertainty
            or signals.autonomic_research_requested
            or signals.benchmark_required
            or signals.plateau_detected
            or signals.research_role in {"claim_scout", "architecture_scout", "benchmark_framer"}
            or "use research" in task_text
            or "research control" in task_text
            or "citation" in task_text
            or "citations" in task_text
            or "replay evidence" in task_text
            or "receipt contract" in task_text
            or (
                "expected capability receipts" in task_text
                and "research" in getattr(signals, "route_oracle_expected_capabilities", ())
            )
        )
        if explicit_research_demand:
            return
        states["research"] = "optional"
        reasons["research"].append("research_no_substantive_evidence_demand_cost_control")

    def _apply_candidate_factory_readiness_policy(
        self,
        *,
        states: dict[str, str],
        reasons: dict[str, list[str]],
        route: dict[str, Any],
    ) -> None:
        route_features = route.get("route_features", {}) if isinstance(route.get("route_features", {}), dict) else {}
        readiness = route_features.get("candidate_factory_readiness_estimate", {})
        if not isinstance(readiness, dict):
            return
        if readiness.get("ready") is not False and str(readiness.get("status") or "").upper() != "SKIPPED":
            return
        for cap in ("autoreason", "judge_panel", "llm_judge_panel"):
            if states.get(cap) == "conditional":
                states[cap] = "optional"
                reasons[cap].append("candidate_factory_skipped")

    def _apply_route_cost_policy(
        self,
        *,
        states: dict[str, str],
        reasons: dict[str, list[str]],
        route_cost_policy: dict[str, Any],
        protected_capabilities: set[str] | None = None,
    ) -> None:
        protected = set(protected_capabilities or set())
        protected.update(str(item) for item in route_cost_policy.get("protected_expected_capabilities", ()) or ())
        route_lane = str(route_cost_policy.get("current_route_lane") or "")
        capped_lane = route_lane in {
            "context_sync_capped",
            "governance_hardened_capped",
            "hidden_bugfix_supervised",
            "hidden_lite",
            "repair_capped",
        }
        cost_capped = any(
            route_cost_policy.get(key) not in (None, "", False)
            for key in (
                "current_candidate_cap",
                "current_context_mode",
                "current_disable_research",
                "current_max_rounds",
                "current_skip_llm_baseline",
                "current_supervised_bare_first",
            )
        )
        if route_cost_policy.get("current_lite_route") is not True and not capped_lane and not cost_capped:
            return
        preserve_governance_review = route_lane in {
            "governance_hardened",
            "governance_hardened_capped",
            "trust_supervised",
            "trust_supervised_scope_only",
        }
        preserve_autoreason = route_lane == "repair_capped"
        for cap in (
            "research",
            "sandbox",
            "judge_panel",
            "external_doc_scout",
            "research_control_plane",
            "architecture_scout",
            "swarm",
            "drone",
            "nightshift",
            "multi_agent",
            "xray",
            "benchmark",
            "meta_opt",
            "stress_test",
            "formal_report",
            "oracle_shadow",
            "federation",
        ):
            if cap in protected:
                continue
            if states.get(cap) == "conditional":
                states[cap] = "optional"
                reasons[cap].append(f"route_cost_capped_lane:{route_lane or 'cost_cap'}")
        if (
            route_cost_policy.get("current_disable_research") is True
            and states.get("research_route") == "required"
            and "research" not in protected
        ):
            states["research_route"] = "optional"
            reasons["research_route"].append(f"route_cost_disable_research:{route_lane or 'cost_cap'}")
        if not preserve_governance_review and "ultra_review" not in protected and states.get("ultra_review") == "conditional":
            states["ultra_review"] = "optional"
            reasons["ultra_review"].append(f"route_cost_capped_lane:{route_lane or 'cost_cap'}")
        if not preserve_autoreason and "autoreason" not in protected and states.get("autoreason") == "conditional":
            states["autoreason"] = "optional"
            reasons["autoreason"].append(f"route_cost_capped_lane:{route_lane or 'cost_cap'}")

    def _apply_s2t_policy_promotion(
        self,
        *,
        states: dict[str, str],
        reasons: dict[str, list[str]],
        s2t_shadow_score: dict[str, Any],
        safety_floor: set[str],
    ) -> None:
        if not s2t_shadow_score.get("runtime_promotable"):
            return
        for cap, hint in (s2t_shadow_score.get("capability_hints", {}) or {}).items():
            if not isinstance(hint, dict) or hint.get("would_downgrade") is not True:
                continue
            if cap in safety_floor or states.get(cap) != "conditional":
                if cap in states:
                    reasons[cap].append("s2t_promoted_policy_preserved_by_safety_floor")
                continue
            states[cap] = "optional"
            reasons[cap].append("s2t_promoted_policy_cost_downgrade")

    def _apply_mutation_assurance_policy(
        self,
        *,
        states: dict[str, str],
        reasons: dict[str, list[str]],
        route: dict[str, Any],
    ) -> None:
        assurance = route.get("mutation_assurance", {}) if isinstance(route.get("mutation_assurance", {}), dict) else {}
        survived = bool(assurance.get("survived_mutants_present", False))
        required = bool(assurance.get("required", False))
        if not (required and survived):
            return
        for cap in ("ultra_review", "sandbox", "autoreason", "jit_validation"):
            if cap in states and states[cap] != "required":
                states[cap] = "conditional"
                reasons[cap].append("mutation_assurance_blind_spot_escalation")

    def _build_ssd_route_map(
        self,
        *,
        states: dict[str, str],
        reasons: dict[str, list[str]],
        signals: Any,
        routing_tier: str,
        total_cost: int,
    ) -> dict[str, Any]:
        selected = [name for name, state in states.items() if state in {"required", "conditional"}]
        capability_reasons = {
            name: list(reasons.get(name) or ["available_but_not_selected"])
            for name in selected
        }
        leverage_roles: dict[str, str] = {}
        for name in selected:
            node = self.nodes[name]
            if node.category in {"governance", "validation"} or name.endswith("_gate"):
                leverage_roles[name] = "risk_control"
            elif node.category in {"recon", "memory"}:
                leverage_roles[name] = "evidence_resolution"
            elif node.category in {"repair", "execution"}:
                leverage_roles[name] = "repair_execution"
            elif node.category in {"reasoning", "acceleration", "routing"}:
                leverage_roles[name] = "selection_quality"
            else:
                leverage_roles[name] = "supporting_capability"

        missing_reason = [
            name
            for name, reason_list in capability_reasons.items()
            if not reason_list or reason_list == ["available_but_not_selected"]
        ]
        leverage_points = tuple(dict.fromkeys(leverage_roles.values()))
        return {
            "schema_version": "nexus_ssd_route_map_v1",
            "map_status": "PASS" if not missing_reason else "INCOMPLETE",
            "routing_tier": routing_tier,
            "task_risk_score": int(getattr(signals, "risk_score", 0) or 0),
            "selected_capability_count": len(selected),
            "total_cost": int(total_cost),
            "capability_reasons": capability_reasons,
            "capability_dependencies": {
                name: list(self.nodes[name].dependencies)
                for name in selected
            },
            "leverage_roles": leverage_roles,
            "leverage_points": list(leverage_points),
            "missing_reason_capabilities": missing_reason,
        }

    def _build_context_slimming_policy(
        self,
        *,
        states: dict[str, str],
        signals: Any,
        routing_tier: str,
    ) -> dict[str, Any]:
        selected = {name for name, state in states.items() if state in {"required", "conditional"}}
        if getattr(signals, "simple_hidden_bugfix", False):
            mode = "dream_micro"
            max_context_items = 4
            phase_budgets = {"X": 2, "D": 1, "R": 3, "A": 2}
            allow_research_context = "research" in selected and "research" in getattr(
                signals, "route_oracle_expected_capabilities", ()
            )
        elif routing_tier == "L3_swarm_deep" or getattr(signals, "risk_score", 0) >= 70:
            mode = "dream_hardened"
            max_context_items = 12
            phase_budgets = {"X": 8, "D": 6, "R": 8, "A": 8}
            allow_research_context = "research" in selected
        else:
            mode = "dream_standard"
            max_context_items = 8
            phase_budgets = {"X": 5, "D": 3, "R": 5, "A": 4}
            allow_research_context = "research" in selected
        return {
            "schema_version": "nexus_context_slimming_policy_v1",
            "mode": mode,
            "max_context_items": max_context_items,
            "phase_budgets": phase_budgets,
            "allow_research_context": bool(allow_research_context),
            "include_only": [
                "route_map_leverage_points",
                "selected_capability_reasons",
                "direct_evidence_refs",
                "target_symbols",
                "verify_commands",
            ],
            "drop_by_default": [
                "unreferenced_codeintel_sections",
                "duplicate_research_hits",
                "chat_repetition",
                "non_evidence_narrative",
            ],
        }

    def _score_s2t_policy_draft(
        self,
        *,
        route: dict[str, Any],
        signals: Any,
        states: dict[str, str],
        s2t_policy_draft: dict[str, Any],
    ) -> dict[str, Any]:
        if not s2t_policy_draft:
            return {}
        route_features = route.get("route_features", {}) if isinstance(route.get("route_features", {}), dict) else {}
        task_id = str(route.get("task_id") or route_features.get("task_id") or "")
        task_rules = s2t_policy_draft.get("task_rules", {})
        task_rules = task_rules if isinstance(task_rules, dict) else {}
        rule = task_rules.get(task_id, {}) if task_id else {}
        rule = rule if isinstance(rule, dict) else {}
        profile = str(rule.get("selector_profile") or self._default_s2t_shadow_profile(signals))
        action = str(rule.get("recommended_action") or "observe_more")
        high_cost_selected = [
            cap
            for cap in (
                "research",
                "external_doc_scout",
                "research_control_plane",
                "architecture_scout",
                "ultra_review",
                "swarm",
                "drone",
                "nightshift",
                "benchmark",
                "meta_opt",
            )
            if states.get(cap) == "conditional"
        ]
        capability_hints: dict[str, dict[str, Any]] = {}
        if action in {"prefer_lite_or_standard", "try_standard_with_cost_cap", "try_lite_with_defensive_gate"} or profile == "lite":
            for cap in high_cost_selected:
                capability_hints[cap] = {
                    "would_downgrade": True,
                    "reason": "s2t_shadow_cost_candidate",
                    "action": action,
                    "profile": profile,
                }
        if action == "keep_strict_repair_selector" or profile == "strict":
            for cap in ("hyper", "repair_loop", "claim_gate", "delivery_gate"):
                if cap in states:
                    capability_hints[cap] = {
                        "would_preserve": True,
                        "reason": "s2t_shadow_verified_repair_path",
                        "action": action,
                        "profile": profile,
                    }

        return {
            "influenced": True,
            "mode": "promoted_runtime_candidate" if s2t_policy_draft.get("runtime_promotable") else "shadow_only_no_runtime_decision_change",
            "runtime_promotable": bool(s2t_policy_draft.get("runtime_promotable", False)),
            "source_schema": str(s2t_policy_draft.get("schema") or ""),
            "status": str(s2t_policy_draft.get("status") or ""),
            "task_id": task_id,
            "matched_task_rule": bool(rule),
            "selector_profile": profile,
            "recommended_action": action,
            "high_cost_selected": tuple(high_cost_selected),
            "capability_hints": capability_hints,
        }

    @staticmethod
    def _default_s2t_shadow_profile(signals: Any) -> str:
        if getattr(signals, "risk_score", 0) >= 70 or getattr(signals, "cross_module", False):
            return "strict"
        if getattr(signals, "evidence_signal", False) or getattr(signals, "candidate_count", 1) > 1:
            return "standard"
        return "lite"

    def _apply_budget_downgrade(
        self,
        *,
        states: dict[str, str],
        reasons: dict[str, list[str]],
        scoring: CapabilityScoringConfig,
        max_cost: int,
        safety_floor: set[str] | None = None,
    ) -> tuple[dict[str, str], dict[str, list[str]], list[str], int]:
        safety_floor = safety_floor or set()
        selected = [name for name, state in states.items() if state in {"required", "conditional"}]
        total_cost = sum(self.nodes[name].cost for name in selected)
        forbidden: list[str] = []
        if total_cost <= max_cost:
            return states, reasons, forbidden, total_cost

        for name in sorted(
            [item for item in selected if states[item] == "conditional"],
            key=lambda item: (scoring.score(self.nodes[item]), self.nodes[item].cost),
        ):
            if total_cost <= max_cost:
                break
            if name in safety_floor:
                reasons[name].append("budget_safety_floor_preserved")
                continue
            states[name] = "forbidden"
            forbidden.append(name)
            reasons[name].append("budget_downgrade")
            total_cost -= self.nodes[name].cost
        return states, reasons, forbidden, total_cost

    @staticmethod
    def _budget_safety_floor(*, signals: Any, routing_tier: str) -> set[str]:
        floor = {"mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"}
        if (
            routing_tier == "L3_swarm_deep"
            or getattr(signals, "risk_score", 0) >= 70
            or getattr(signals, "governance_signal", False)
            or getattr(signals, "hazard_forced_l3", False)
        ):
            floor.update({"ultra_review", "sandbox", "pregate", "plan_quality_gate", "forecast_gate"})
        floor.update(str(cap) for cap in getattr(signals, "route_oracle_expected_capabilities", ()) or ())
        return floor
