from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


LEARNING_EXPERIENCE_SCHEMA_VERSION = "nexus_learning_experience.v1"
PHASE_CHAIN = ("S", "P", "X", "D", "R", "A", "C")


CAPABILITY_TAXONOMY: dict[str, dict[str, Any]] = {
    "direct_mode": {"category": "primary_execution", "phases": ("S", "P", "X", "D", "R", "A", "C")},
    "repair_loop": {"category": "primary_execution", "phases": ("R", "A")},
    "hyper": {"category": "primary_execution", "phases": ("P", "R", "A")},
    "nightshift": {"category": "primary_execution", "phases": ("D", "R", "C")},
    "codeintel": {"category": "recon_context", "phases": ("S", "P", "X", "A")},
    "research": {"category": "recon_context", "phases": ("X", "C")},
    "research_route": {"category": "recon_context", "phases": ("S", "P", "X")},
    "research_control_plane": {"category": "recon_context", "phases": ("X", "R", "A", "C")},
    "xray": {"category": "recon_context", "phases": ("X", "D")},
    "lancedb": {"category": "recon_context", "phases": ("X",)},
    "memory": {"category": "memory_learning", "phases": ("P", "X", "C")},
    "learn_mode": {"category": "memory_learning", "phases": ("X", "A", "C")},
    "learn_scheduler": {"category": "memory_learning", "phases": ("X", "C")},
    "learn_phase_slo": {"category": "memory_learning", "phases": ("P", "X", "D", "R", "A", "C")},
    "autoreason": {"category": "reasoning_acceleration", "phases": ("D", "R", "A")},
    "judge_panel": {"category": "reasoning_acceleration", "phases": ("D", "R", "A")},
    "llm_judge_panel": {"category": "reasoning_acceleration", "phases": ("D", "R", "A")},
    "ddtree": {"category": "reasoning_acceleration", "phases": ("X", "R", "A")},
    "belief": {"category": "reasoning_acceleration", "phases": ("D", "R")},
    "autonomic_router": {"category": "reasoning_acceleration", "phases": ("P", "D")},
    "forecast_gate": {"category": "reasoning_acceleration", "phases": ("P", "D")},
    "swarm": {"category": "collaboration", "phases": ("D", "R", "A")},
    "swarm_quiet_moment": {"category": "collaboration", "phases": ("D", "R", "A")},
    "drone": {"category": "collaboration", "phases": ("R", "A")},
    "multi_agent": {"category": "collaboration", "phases": ("P", "D", "R", "A", "C")},
    "file_lock": {"category": "collaboration", "phases": ("S", "P", "D")},
    "integration_manager": {"category": "collaboration", "phases": ("C",)},
    "mempalace_gate": {"category": "governance_risk", "phases": ("S", "D", "A")},
    "policy_gate": {"category": "governance_risk", "phases": ("S", "P", "D")},
    "capability_gate": {"category": "governance_risk", "phases": ("S", "P", "D")},
    "pregate": {"category": "governance_risk", "phases": ("S", "P")},
    "plan_quality_gate": {"category": "governance_risk", "phases": ("P", "D")},
    "ultra_review": {"category": "governance_risk", "phases": ("D", "A")},
    "artifact_gate": {"category": "validation_delivery", "phases": ("A", "C")},
    "claim_gate": {"category": "validation_delivery", "phases": ("A", "C")},
    "delivery_gate": {"category": "validation_delivery", "phases": ("A", "C")},
    "acceptance_check": {"category": "validation_delivery", "phases": ("A", "C")},
    "sandbox": {"category": "validation_delivery", "phases": ("R", "A")},
    "benchmark": {"category": "self_evolution", "phases": ("C",)},
    "meta_opt": {"category": "self_evolution", "phases": ("C",)},
    "regression_guard": {"category": "self_evolution", "phases": ("A", "C")},
    "registry_sync": {"category": "productization", "phases": ("S", "C")},
    "metabolism": {"category": "productization", "phases": ("C", "S")},
    "oracle_shadow": {"category": "productization", "phases": ("P", "R", "A", "C")},
    "federation": {"category": "productization", "phases": ("X", "R", "C")},
    "ui_validator": {"category": "productization", "phases": ("A",)},
    "stress_test": {"category": "productization", "phases": ("A", "C")},
}


@dataclass(frozen=True)
class CapabilityLifecycle:
    capability: str
    category: str
    phase: str
    selected: bool
    invoked: bool
    evidence: bool
    outcome: bool
    gate_passed: bool = False
    evidence_refs: tuple[str, ...] = ()
    failure_reason: str = ""

    @property
    def funnel_complete(self) -> bool:
        return bool(self.selected and self.invoked and self.evidence and self.outcome and self.gate_passed)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"evidence_refs": list(self.evidence_refs), "funnel_complete": self.funnel_complete}


@dataclass(frozen=True)
class LearningExperience:
    experience_id: str
    task_id: str
    task_type: str
    phase_continuity: dict[str, Any]
    capability_lifecycle: tuple[CapabilityLifecycle, ...]
    gate_chain: dict[str, str]
    outcome: str
    route_decision_ref: str = ""
    s2t_trace_refs: tuple[str, ...] = ()
    learning_steward_decision: str = "shadow"
    nexus_policy_targets: tuple[str, ...] = ("route_weight", "capability_weight", "s2t_prior")
    model_training_targets: tuple[str, ...] = ("preference_pair", "reward_row")
    promotion_status: str = "shadow"
    schema_version: str = LEARNING_EXPERIENCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "capability_lifecycle": [item.to_dict() for item in self.capability_lifecycle],
            "s2t_trace_refs": list(self.s2t_trace_refs),
            "nexus_policy_targets": list(self.nexus_policy_targets),
            "model_training_targets": list(self.model_training_targets),
        }


def build_learning_experience(
    *,
    task_id: str,
    task_type: str = "",
    usage_trace: dict[str, Any] | None = None,
    capability_receipts: list[dict[str, Any]] | None = None,
    route_decision_ref: str = "",
    learning_steward_decision: str = "shadow",
) -> LearningExperience:
    usage = usage_trace or {}
    receipts = capability_receipts or usage.get("capability_receipts", []) or []
    phase_trace = usage.get("phase_trace", {}) if isinstance(usage.get("phase_trace"), dict) else {}
    observed = [phase for phase in PHASE_CHAIN if phase in phase_trace or phase in usage.get("phase_wall_sec", {})]
    capabilities = tuple(_lifecycle_from_receipt(item) for item in receipts if isinstance(item, dict))
    gate_chain = _gate_chain(usage)
    outcome = "verified_success" if all(gate_chain.get(key) == "pass" for key in ("artifact", "claim", "delivery")) else "unverified"
    s2t = usage.get("s2t", {}) if isinstance(usage.get("s2t"), dict) else {}
    s2t_refs = tuple(str(ref) for ref in [s2t.get("trace_path", "")] if str(ref).strip())
    experience_id = f"exp:{task_id or 'unknown'}:{abs(hash((task_id, len(capabilities), outcome))) % 10_000_000}"
    return LearningExperience(
        experience_id=experience_id,
        task_id=task_id or "unknown",
        task_type=task_type,
        phase_continuity={
            "expected": list(PHASE_CHAIN),
            "observed": observed,
            "complete": observed == list(PHASE_CHAIN),
            "broken_at": _first_missing_phase(observed),
            "phase_wall_sec": dict(usage.get("phase_wall_sec", {}) or {}),
        },
        capability_lifecycle=capabilities,
        gate_chain=gate_chain,
        outcome=outcome,
        route_decision_ref=route_decision_ref,
        s2t_trace_refs=s2t_refs,
        learning_steward_decision=learning_steward_decision,
        promotion_status="shadow" if outcome == "verified_success" else "frozen",
    )


def project_nexus_policy(experience: LearningExperience) -> dict[str, Any]:
    complete = [item.capability for item in experience.capability_lifecycle if item.funnel_complete]
    unnecessary = [item.capability for item in experience.capability_lifecycle if item.selected and not item.invoked]
    return {
        "schema_version": "nexus_policy_learning_projection.v1",
        "experience_id": experience.experience_id,
        "promotion_status": experience.promotion_status,
        "route_weight_updates": complete,
        "capability_penalties": unnecessary,
        "s2t_prior_eligible": bool(experience.s2t_trace_refs and experience.outcome == "verified_success"),
    }


def project_model_training(experience: LearningExperience) -> dict[str, Any]:
    eligible = experience.outcome == "verified_success" and experience.gate_chain.get("claim") == "pass"
    return {
        "schema_version": "nexus_model_training_projection.v1",
        "experience_id": experience.experience_id,
        "training_eligible": eligible,
        "targets": list(experience.model_training_targets) if eligible else ["hard_negative"],
        "source_trace_refs": list(experience.s2t_trace_refs),
    }


def _lifecycle_from_receipt(receipt: dict[str, Any]) -> CapabilityLifecycle:
    name = str(receipt.get("name") or receipt.get("capability") or "unknown")
    meta = CAPABILITY_TAXONOMY.get(name, {"category": "unknown", "phases": ("C",)})
    refs = tuple(str(ref) for ref in receipt.get("evidence_refs", []) or [] if str(ref).strip())
    return CapabilityLifecycle(
        capability=name,
        category=str(meta["category"]),
        phase=str(tuple(meta["phases"])[0]),
        selected=bool(receipt.get("selected", False)),
        invoked=bool(receipt.get("invoked", False)),
        evidence=bool(receipt.get("evidence_present", False) or refs),
        outcome=bool(receipt.get("outcome_contributed", False)),
        gate_passed=bool(receipt.get("gate_passed", False)),
        evidence_refs=refs,
        failure_reason=str(receipt.get("failure_reason") or ""),
    )


def _gate_chain(usage: dict[str, Any]) -> dict[str, str]:
    caps = usage.get("capabilities", {}) if isinstance(usage.get("capabilities"), dict) else {}

    def status(key: str) -> str:
        value = caps.get(f"{key}_gate_passed")
        if value is True:
            return "pass"
        if value is False and (caps.get(f"{key}_refs") or caps.get(f"{key}_invoked")):
            return "fail"
        return "not_run"

    return {
        "mempalace": status("mempalace"),
        "belief": status("belief"),
        "artifact": status("artifact"),
        "claim": "pass" if caps.get("claim_verified") or caps.get("claim_gate_passed") else "not_run",
        "delivery": status("delivery"),
    }


def _first_missing_phase(observed: list[str]) -> str:
    for phase in PHASE_CHAIN:
        if phase not in observed:
            return phase
    return ""
