from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
        return asdict(self) | {
            "phase_hooks": list(self.phase_hooks),
            "dependencies": list(self.dependencies),
            "parallelizable_with": list(self.parallelizable_with),
            "evidence_outputs": list(self.evidence_outputs),
        }


@dataclass(frozen=True)
class CapabilitySignalSet:
    task_desc: str
    task_type: str
    recommended_flow: str = ""
    selected_seed: tuple[str, ...] = ()
    acceleration_seed: tuple[str, ...] = ()
    governance_seed: tuple[str, ...] = ()
    risk_score: int = 0
    confidence: float = 1.0
    candidate_count: int = 1
    memory_hits: int = 0
    findings_hits: int = 0
    lancedb_hits: int = 0
    cross_module: bool = False
    hard_signal: bool = False
    codeintel_impact_present: bool = False
    should_research: bool = False
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
    skill_candidates: tuple[str, ...] = ()
    skill_confidence: float = 0.0

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
    score: int
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

    @property
    def public_claim_safe(self) -> bool:
        return bool(self.selected and self.invoked and self.evidence_present and self.gate_passed)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "evidence_refs": list(self.evidence_refs),
            "public_claim_safe": self.public_claim_safe,
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
