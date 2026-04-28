from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PHASES = ("S", "P", "X", "D", "R", "A", "C")


@dataclass(frozen=True)
class CapabilityNode:
    name: str
    phase_hooks: tuple[str, ...]
    default_state: str = "optional"
    category: str = "execution"
    maturity: str = "planned"
    dependencies: tuple[str, ...] = ()
    parallelizable_with: tuple[str, ...] = ()
    cost: int = 1
    benefit: int = 1
    risk_reduction: int = 0
    evidence_outputs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "phase_hooks": list(self.phase_hooks),
            "default_state": self.default_state,
            "category": self.category,
            "maturity": self.maturity,
            "dependencies": list(self.dependencies),
            "parallelizable_with": list(self.parallelizable_with),
            "cost": self.cost,
            "benefit": self.benefit,
            "risk_reduction": self.risk_reduction,
            "evidence_outputs": list(self.evidence_outputs),
        }


@dataclass(frozen=True)
class CapabilityPlan:
    schema_version: str
    selected_capabilities: list[str]
    required_capabilities: list[str]
    optional_capabilities: list[str]
    conditional_capabilities: list[str]
    forbidden_capabilities: list[str]
    constraints: list[str]
    decision_trace: list[dict[str, Any]]
    replan_trace: list[dict[str, Any]]
    score: int
    planner_mode: str = "dry_run"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "planner_mode": self.planner_mode,
            "selected_capabilities": self.selected_capabilities,
            "required_capabilities": self.required_capabilities,
            "optional_capabilities": self.optional_capabilities,
            "conditional_capabilities": self.conditional_capabilities,
            "forbidden_capabilities": self.forbidden_capabilities,
            "constraints": self.constraints,
            "decision_trace": self.decision_trace,
            "replan_trace": self.replan_trace,
            "score": self.score,
        }


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
    ) -> CapabilityPlan:
        pillars = pillars or {}
        codeintel = codeintel or {}
        phase_trace = phase_trace or {}
        budget = budget or {}
        route_features = route.get("route_features", {}) if isinstance(route, dict) else {}
        capability_stack = route.get("capability_stack", {}) if isinstance(route, dict) else {}
        selected_seed = set(capability_stack.get("selected_capabilities", []) or [])
        acceleration_seed = set(capability_stack.get("acceleration_layers", []) or [])
        governance_seed = set(capability_stack.get("governance_layers", []) or [])
        risk_score = int(route_features.get("risk_score", 0) or 0)
        confidence = float(route_features.get("adjusted_root_cause_confidence", 1.0) or 1.0)
        candidate_count = int(route_features.get("candidate_count", 1) or 1)
        memory_hits = int(route_features.get("memory_hits", 0) or 0)
        findings_hits = int(route_features.get("findings_hits", 0) or 0)
        cross_module = bool(route_features.get("is_cross_module_task", False))
        hard_signal = bool(route_features.get("has_hard_signal", False))
        task_lower = f"{task_desc} {task_type}".lower()
        governance_signal = any(
            token in task_lower
            for token in ("secret", "credential", "redact", "auth", "authorization", "deny by default", "governance")
        )
        evidence_signal = any(token in task_lower for token in ("evidence", "artifact", "claim", "semantic", "trust"))
        repair_signal = any(token in task_lower for token in ("repair", "self-heal", "failing branch", "timeout", "flaky"))
        learning_signal = any(token in task_lower for token in ("learn", "citation", "slo", "kpi", "source", "claim"))
        multi_agent_signal = any(token in task_lower for token in ("multi-agent", "owner", "file lock", "worktree", "integrate"))
        swarm_signal = "swarm" in task_lower
        drone_signal = "drone" in task_lower
        nightshift_signal = "nightshift" in task_lower
        ui_signal = any(token in task_lower for token in ("ui", "browser", "screen", "accessibility", "visual"))
        continuity_signal = any(token in task_lower for token in ("resume", "distill", "checkpoint", "metabolism"))

        states: dict[str, str] = {
            name: ("required" if node.default_state == "required" else "optional")
            for name, node in self.nodes.items()
        }
        reasons: dict[str, list[str]] = {name: [] for name in self.nodes}
        constraints = ["mempalace_fail_closed", "artifact_evidence_required", "claim_fail_closed"]

        for required in ("mempalace_gate", "artifact_gate", "claim_gate"):
            reasons[required].append("governance_hard_constraint")
        reasons["delivery_gate"].append("delivery_fail_closed_contract")
        reasons["research_route"].append("routing_contract_required")

        def enable(name: str, reason: str) -> None:
            if name not in states or states[name] == "required":
                return
            states[name] = "conditional"
            reasons[name].append(reason)

        if "hyper_sprint" in selected_seed or route.get("recommended_flow") == "hyper_sprint":
            enable("hyper", "route_selected_hyper")
        if route.get("recommended_flow") == "baseline":
            enable("direct_mode", "baseline_execution_path")
        if (
            "autoreason" in selected_seed
            or confidence < 0.75
            or candidate_count >= 2
            or memory_hits
            or findings_hits
            or repair_signal
            or evidence_signal
        ):
            enable("autoreason", "low_confidence_or_multi_candidate_or_history")
        if confidence < 0.8:
            enable("belief", "confidence_control_needed")
        if memory_hits or findings_hits:
            enable("memory", "prior_lesson_or_findings_available")
        if int((pillars.get("lancedb", {}) or {}).get("hits", 0) or 0):
            enable("lancedb", "semantic_memory_hits_available")
        if "ddtree" in acceleration_seed or candidate_count >= 3 or repair_signal:
            enable("ddtree", "candidate_space_pruning")
        if "ultra_review" in governance_seed or risk_score >= 70 or hard_signal or governance_signal:
            enable("ultra_review", "high_risk_or_governance_route")
            enable("sandbox", "high_risk_isolated_execution")
        if cross_module or codeintel.get("impact_report_present") or risk_score >= 30:
            enable("codeintel", "impact_or_blast_radius_needed")
        if route.get("should_research") or not int((pillars.get("lancedb", {}) or {}).get("hits", 0) or 0):
            enable("research", "context_or_retrieval_gap")
        if learning_signal:
            enable("learn_mode", "claim_or_citation_learning_signal")
            enable("learn_phase_slo", "learn_phase_policy_needed")
        if risk_score >= 30 or governance_signal or evidence_signal:
            enable("pregate", "risk_or_policy_precheck")
            enable("plan_quality_gate", "plan_review_required")
        if swarm_signal or (cross_module and risk_score >= 70):
            enable("swarm", "cross_module_high_risk_review")
        if drone_signal or "parallel" in task_lower or "split" in task_lower or (cross_module and candidate_count >= 2):
            enable("drone", "parallelizable_subtask_signal")
        if multi_agent_signal or (cross_module and risk_score >= 60):
            enable("file_lock", "multi_agent_write_boundary")
            enable("multi_agent", "coordinated_ownership_required")
        if "merge" in task_lower or "integrate" in task_lower or "integration" in task_lower:
            enable("integration_manager", "integration_or_merge_signal")
        if risk_score >= 90 or "long" in task_lower or nightshift_signal or "nightshift" in governance_seed:
            enable("nightshift", "long_or_critical_risk")
        if ui_signal:
            enable("ui_validator", "ui_validation_signal")
        if continuity_signal:
            enable("metabolism", "continuity_or_resume_signal")
        if "benchmark" in task_lower or "public report" in task_lower:
            enable("benchmark", "evaluation_or_public_report_signal")
        if "meta-opt" in task_lower or "autotune" in task_lower:
            enable("meta_opt", "optimization_signal")
        if "registry" in task_lower or "skill" in task_lower:
            enable("registry_sync", "platform_registry_signal")
        if "oracle" in task_lower or "shadow" in task_lower:
            enable("oracle_shadow", "shadow_promotion_signal")
        if "federation" in task_lower or "tenant" in task_lower:
            enable("federation", "federated_learning_signal")
        if "stress" in task_lower or "recursion" in task_lower:
            enable("stress_test", "stress_or_recursion_signal")

        max_cost = int(budget.get("max_cost", 999) or 999)
        selected = [name for name, state in states.items() if state in {"required", "conditional"}]
        total_cost = sum(self.nodes[name].cost for name in selected)
        forbidden: list[str] = []
        if total_cost > max_cost:
            for name in sorted(
                [item for item in selected if states[item] == "conditional"],
                key=lambda item: (self.nodes[item].benefit + self.nodes[item].risk_reduction - self.nodes[item].cost, self.nodes[item].cost),
            ):
                if total_cost <= max_cost:
                    break
                states[name] = "forbidden"
                forbidden.append(name)
                reasons[name].append("budget_downgrade")
                total_cost -= self.nodes[name].cost

        decision_trace: list[dict[str, Any]] = []
        score = 0
        for name, node in self.nodes.items():
            state = states[name]
            score_delta = node.benefit + node.risk_reduction - node.cost if state in {"required", "conditional"} else 0
            score += score_delta
            decision_trace.append(
                {
                    "capability": name,
                    "state": state,
                    "phase_hooks": list(node.phase_hooks),
                    "reasons": reasons[name] or ["available_but_not_selected"],
                    "dependencies": list(node.dependencies),
                    "parallelizable_with": list(node.parallelizable_with),
                    "score_delta": score_delta,
                }
            )

        replan_trace = self._build_replan_trace(states=states, phase_trace=phase_trace, risk_score=risk_score, confidence=confidence)

        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            planner_mode="dry_run",
            selected_capabilities=[name for name, state in states.items() if state in {"required", "conditional"}],
            required_capabilities=[name for name, state in states.items() if state == "required"],
            optional_capabilities=[name for name, state in states.items() if state == "optional"],
            conditional_capabilities=[name for name, state in states.items() if state == "conditional"],
            forbidden_capabilities=[name for name, state in states.items() if state == "forbidden"],
            constraints=constraints,
            decision_trace=decision_trace,
            replan_trace=replan_trace,
            score=score,
        )

    def _build_replan_trace(
        self,
        *,
        states: dict[str, str],
        phase_trace: dict[str, Any],
        risk_score: int,
        confidence: float,
    ) -> list[dict[str, Any]]:
        trace: list[dict[str, Any]] = []
        for phase in PHASES:
            active = [
                name
                for name, state in states.items()
                if state in {"required", "conditional"} and phase in self.nodes[name].phase_hooks
            ]
            reasons = []
            if phase == "X" and "research" in active:
                reasons.append("fill_context_gap")
            if phase == "D" and (risk_score >= 70 or confidence < 0.75):
                reasons.append("recheck_governance_and_belief")
            if phase == "A":
                reasons.append("claim_and_artifact_fail_closed")
            trace.append(
                {
                    "phase": phase,
                    "prior_state": str(phase_trace.get(phase) or ""),
                    "active_capabilities": active,
                    "replan_reasons": reasons or ["keep_current_plan"],
                }
            )
        return trace
