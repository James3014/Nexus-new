from __future__ import annotations

from typing import Any

from nexus.engine.capability_contracts import CapabilityNode, CapabilityPlan, CapabilityScoringConfig
from nexus.engine.policy_evaluator import apply_signal_policies, apply_tier_policies
from nexus.engine.route_signal_adapter import build_replan_trace, build_signal_snapshot
from nexus.engine.capability_signals import build_capability_constraints, build_capability_signals

PENDING_EXECUTOR_CAPABILITIES = {"swarm", "drone", "nightshift"}


def _cost_tier(cost: int) -> str:
    if cost >= 5:
        return "high"
    if cost >= 3:
        return "medium"
    return "low"


def default_capability_nodes() -> dict[str, CapabilityNode]:
    nodes = [
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
        self._apply_route_cost_policy(states=states, reasons=reasons, route_cost_policy=route_cost_policy)
        self._apply_candidate_factory_readiness_policy(states=states, reasons=reasons, route=route)
        self._apply_route_oracle_expected_contract(states=states, reasons=reasons, signals=signals)
        self._apply_research_evidence_demand_policy(states=states, reasons=reasons, signals=signals)
        self._apply_simple_hidden_contract_policy(states=states, reasons=reasons, signals=signals)

        selected = [name for name, state in states.items() if state in {"required", "conditional"}]
        pending = [name for name in selected if name in PENDING_EXECUTOR_CAPABILITIES]
        total_cost = sum(self.nodes[name].cost for name in selected)
        states, reasons, forbidden, total_cost = self._apply_budget_downgrade(
            states=states,
            reasons=reasons,
            scoring=scoring,
            max_cost=constraint_model.max_cost,
        )

        decision_trace: list[dict[str, Any]] = []
        score = 0
        for name, node in self.nodes.items():
            state = states[name]
            score_delta = scoring.score(node) if state in {"required", "conditional"} else 0
            score += score_delta
            decision_trace.append(
                {
                    "capability": name,
                    "state": state,
                    "phase_hooks": list(node.phase_hooks),
                    "reasons": reasons[name] or ["available_but_not_selected"],
                    "dependencies": list(node.dependencies),
                    "parallelizable_with": list(node.parallelizable_with),
                    "cost_tier": _cost_tier(int(node.cost)),
                    "score_delta": score_delta,
                    "score_components": scoring.components(node),
                    "scoring_weights": scoring.to_dict(),
                }
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
        for name in learning_policy.get("promoted_capabilities", ()) or ():
            cap = str(name)
            if cap in self.nodes:
                enable(cap, "learning_policy_promoted")
        for name in learning_policy.get("penalized_capabilities", ()) or ():
            cap = str(name)
            if cap not in self.nodes:
                continue
            reasons[cap].append("learning_policy_penalized")
            if learning_policy.get("enforce_penalties") is True and states.get(cap) == "conditional":
                states[cap] = "optional"

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
    ) -> None:
        if route_cost_policy.get("current_lite_route") is not True:
            return
        for cap in (
            "research",
            "ultra_review",
            "sandbox",
            "autoreason",
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
        ):
            if states.get(cap) == "conditional":
                states[cap] = "optional"
                reasons[cap].append("route_cost_lite_policy")

    def _apply_budget_downgrade(
        self,
        *,
        states: dict[str, str],
        reasons: dict[str, list[str]],
        scoring: CapabilityScoringConfig,
        max_cost: int,
    ) -> tuple[dict[str, str], dict[str, list[str]], list[str], int]:
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
            states[name] = "forbidden"
            forbidden.append(name)
            reasons[name].append("budget_downgrade")
            total_cost -= self.nodes[name].cost
        return states, reasons, forbidden, total_cost
