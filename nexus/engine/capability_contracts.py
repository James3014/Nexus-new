from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PHASES = ("S", "P", "X", "D", "R", "A", "C")


def normalize_risk_score(value: Any) -> dict[str, Any]:
    """Normalize mixed 0-1 and 0-100 risk scores into an explicit contract."""
    raw_value = value
    raw_text = str(value).strip()
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0

    source_scale = "0_100"
    if 0.0 < numeric <= 1.0 and ("." in raw_text or isinstance(raw_value, float)):
        source_scale = "0_1"
        score_0_1 = max(0.0, min(1.0, numeric))
        score_0_100 = int(round(score_0_1 * 100))
    else:
        score_0_100 = int(round(max(0.0, min(100.0, numeric))))
        score_0_1 = round(score_0_100 / 100.0, 4)

    if score_0_100 >= 90:
        band = "critical"
    elif score_0_100 >= 70:
        band = "high"
    elif score_0_100 >= 30:
        band = "medium"
    else:
        band = "low"

    return {
        "raw": raw_value,
        "source_scale": source_scale,
        "risk_score_0_100": score_0_100,
        "risk_score_0_1": score_0_1,
        "risk_band": band,
        "risk_band_reason": f"{band}_risk:{score_0_100}",
    }


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
        return asdict(self) | {
            "phase_hooks": list(self.phase_hooks),
            "dependencies": list(self.dependencies),
            "parallelizable_with": list(self.parallelizable_with),
            "evidence_outputs": list(self.evidence_outputs),
        }


@dataclass(frozen=True)
class CapabilityScoringConfig:
    benefit_weight: float = 1.0
    risk_weight: float = 1.0
    cost_weight: float = 1.0

    @staticmethod
    def _weight(raw: Any, default: float = 1.0) -> float:
        try:
            return float(raw or default)
        except (TypeError, ValueError):
            return default

    @classmethod
    def from_budget(cls, budget: dict[str, Any] | None) -> "CapabilityScoringConfig":
        raw = (budget or {}).get("scoring", {})
        raw = raw if isinstance(raw, dict) else {}
        return cls(
            benefit_weight=cls._weight(raw.get("benefit_weight")),
            risk_weight=cls._weight(raw.get("risk_weight")),
            cost_weight=cls._weight(raw.get("cost_weight")),
        )

    def score(self, node: "CapabilityNode") -> float:
        return (
            float(node.benefit) * self.benefit_weight
            + float(node.risk_reduction) * self.risk_weight
            - float(node.cost) * self.cost_weight
        )

    def components(self, node: "CapabilityNode") -> dict[str, float]:
        return {
            "benefit": float(node.benefit) * self.benefit_weight,
            "risk_reduction": float(node.risk_reduction) * self.risk_weight,
            "cost_penalty": float(node.cost) * self.cost_weight,
        }

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilitySignalSet:
    task_desc: str
    task_type: str
    recommended_flow: str = ""
    route_decision_present: bool = False
    selected_seed: tuple[str, ...] = ()
    route_oracle_expected_capabilities: tuple[str, ...] = ()
    acceleration_seed: tuple[str, ...] = ()
    governance_seed: tuple[str, ...] = ()
    risk_score: int = 0
    risk_score_0_100: int = 0
    risk_score_0_1: float = 0.0
    risk_band: str = "low"
    risk_band_reason: str = "low_risk:0"
    confidence: float = 1.0
    candidate_count: int = 1
    candidate_factory_ready_estimate: bool = False
    candidate_factory_status: str = ""
    candidate_factory_reason: str = ""
    candidate_factory_estimated_candidates: int = 0
    memory_hits: int = 0
    findings_hits: int = 0
    lancedb_hits: int = 0
    cross_module: bool = False
    hard_signal: bool = False
    codeintel_impact_present: bool = False
    should_research: bool = False
    simple_hidden_bugfix: bool = False
    governance_signal: bool = False
    evidence_signal: bool = False
    repair_signal: bool = False
    learning_signal: bool = False
    multi_agent_signal: bool = False
    swarm_signal: bool = False
    drone_signal: bool = False
    nightshift_signal: bool = False
    ui_signal: bool = False
    continuity_signal: bool = False
    benchmark_signal: bool = False
    meta_opt_signal: bool = False
    registry_signal: bool = False
    oracle_signal: bool = False
    federation_signal: bool = False
    stress_signal: bool = False
    acceptance_signal: bool = False
    forecast_signal: bool = False
    xray_signal: bool = False
    research_control_signal: bool = False
    skill_candidates: tuple[str, ...] = ()
    skill_confidence: float = 0.0
    autonomic_suggested_mode: str = ""
    autonomic_policy_match_count: int = 0
    autonomic_research_requested: bool = False
    autonomic_swarm_candidate: bool = False
    msa_candidate_count: int = 0
    msa_top_score: float = 0.0
    msa_rerank_reasons: tuple[str, ...] = ()
    hazard_hits: tuple[str, ...] = ()
    hazard_forced_l3: bool = False
    routing_tier_hint: str = ""
    routing_tier_reason: str = ""
    research_role: str = ""
    claim_uncertainty: bool = False
    benchmark_required: bool = False
    plateau_detected: bool = False
    doc_scout_hits: int = 0
    blocked_assumptions_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityConstraints:
    hard_constraints: tuple[str, ...] = (
        "mempalace_fail_closed",
        "artifact_evidence_required",
        "claim_fail_closed",
    )
    forbidden_capabilities: tuple[str, ...] = ()
    max_cost: int = 999
    policy_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityPlan:
    schema_version: str
    selected_capabilities: list[str]
    required_capabilities: list[str]
    optional_capabilities: list[str]
    conditional_capabilities: list[str]
    pending_capabilities: list[str]
    forbidden_capabilities: list[str]
    constraints: list[str]
    decision_trace: list[dict[str, Any]]
    replan_trace: list[dict[str, Any]]
    score: float
    planner_mode: str = "dry_run"
    signal_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = self.schema_version
        payload["planner_mode"] = self.planner_mode
        return payload


@dataclass(frozen=True)
class CapabilityExecutionPlan:
    schema_version: str
    phase_order: tuple[str, ...]
    selected_capabilities: tuple[str, ...]
    executor_controls: dict[str, Any] = field(default_factory=dict)
    fallback_policy: str = "fail_closed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "phase_order": list(self.phase_order),
            "selected_capabilities": list(self.selected_capabilities),
        }


@dataclass(frozen=True)
class CapabilityReceipt:
    name: str
    selected: bool
    invoked: bool = False
    evidence_present: bool = False
    gate_passed: bool = False
    outcome_contributed: bool = False
    selection_source: str = "planner"
    executor_id: str = ""
    evidence_refs: tuple[str, ...] = ()
    failure_reason: str = ""
    semantic_hash: str = ""
    evidence_alignment: bool = True

    @property
    def public_claim_safe(self) -> bool:
        return bool(
            self.selected
            and self.invoked
            and self.evidence_present
            and self.gate_passed
            and self.outcome_contributed
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "evidence_refs": list(self.evidence_refs),
            "public_claim_safe": self.public_claim_safe,
        }


@dataclass(frozen=True)
class RouteDecision:
    schema_version: str
    plan_schema_version: str
    plan_mode: str
    plan_score: int
    task_id: str
    task_type: str
    task_desc_hash: str
    recommended_flow: str
    decision_source: str
    signal_snapshot: dict[str, Any]
    selected_capabilities: tuple[str, ...]
    required_capabilities: tuple[str, ...] = ()
    conditional_capabilities: tuple[str, ...] = ()
    pending_capabilities: tuple[str, ...] = ()
    forbidden_capabilities: tuple[str, ...] = ()
    acceleration_layers: tuple[str, ...] = ()
    governance_layers: tuple[str, ...] = ()
    executor_controls: dict[str, Any] = field(default_factory=dict)
    constraints: tuple[str, ...] = ()
    decision_trace: tuple[dict[str, Any], ...] = ()
    stop_policy: dict[str, Any] = field(default_factory=dict)
    receipt_requirements: tuple[str, ...] = ()
    public_claim_scope: str = "receipt_backed"
    fallback_policy: str = "fail_closed"
    forecast_gate_shadow: dict[str, Any] = field(default_factory=dict)
    routing_tier: str = "L2_hardened"
    routing_tier_reason: str = ""
    hazard_hits: tuple[str, ...] = ()
    hazard_forced_l3: bool = False
    early_exit_used: bool = False
    policy_loaded_count: int = 0
    policy_pruned_count: int = 0
    tuning_snapshot: dict[str, Any] = field(default_factory=dict)
    derivation_meta: dict[str, Any] = field(default_factory=dict)
    misclassification_audit: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "selected_capabilities": list(self.selected_capabilities),
            "required_capabilities": list(self.required_capabilities),
            "conditional_capabilities": list(self.conditional_capabilities),
            "pending_capabilities": list(self.pending_capabilities),
            "forbidden_capabilities": list(self.forbidden_capabilities),
            "acceleration_layers": list(self.acceleration_layers),
            "governance_layers": list(self.governance_layers),
            "hazard_hits": list(self.hazard_hits),
            "constraints": list(self.constraints),
            "decision_trace": list(self.decision_trace),
            "receipt_requirements": list(self.receipt_requirements),
        }


@dataclass(frozen=True)
class RouteExperiment:
    schema_version: str
    experiment_id: str
    baseline_route_decision_id: str
    candidate_route_decision_id: str
    variant_source: str
    modifiable_scope: tuple[str, ...]
    fixed_eval_manifest: str
    seed: int
    sample_count: int
    metrics: dict[str, Any] = field(default_factory=dict)
    capability_receipts: tuple[dict[str, Any], ...] = ()
    winner: str = ""
    elimination_matrix: tuple[dict[str, Any], ...] = ()
    rollback_plan: dict[str, Any] = field(default_factory=dict)
    promotion_decision: str = "quarantine"
    public_claim_gate: dict[str, Any] = field(default_factory=dict)
    failure_lessons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "modifiable_scope": list(self.modifiable_scope),
            "capability_receipts": list(self.capability_receipts),
            "elimination_matrix": list(self.elimination_matrix),
            "failure_lessons": list(self.failure_lessons),
        }


@dataclass(frozen=True)
class SkillSignalSet:
    top_skill_ids: tuple[str, ...] = ()
    skill_confidence: float = 0.0
    trust_level: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"top_skill_ids": list(self.top_skill_ids)}


@dataclass(frozen=True)
class SkillReceipt:
    skill_id: str
    selected: bool
    injected: bool = False
    used: bool = False
    evidence_present: bool = False
    outcome_contributed: bool = False
    failure_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
