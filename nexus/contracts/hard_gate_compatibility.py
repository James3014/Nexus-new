from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


HARD_GATE_COMPATIBILITY_SCHEMA = "nexus.hard_gate_compatibility.v1"
PASS_LIKE = {"PASS", "NOT_APPLICABLE"}


@dataclass(frozen=True)
class HardGateCompatibility:
    route_context_changed: bool = False
    route_hardened: bool = False
    mfp_confidence_min: float = 0.98
    router_acceptance_status: str = "NOT_APPLICABLE"
    closeout_claim: bool = False
    completion_status: str = "NOT_APPLICABLE"
    context_sources_dropped: bool = False
    hallucination_guard_status: str = "NOT_APPLICABLE"
    mutation_assurance_required: bool = False
    mutation_assurance_status: str = "NOT_APPLICABLE"
    bdd_acceptance_required: bool = False
    bdd_preflight_status: str = "NOT_APPLICABLE"
    capability_contract_type: str = "NOT_APPLICABLE"
    pre_model_rescue_planned: bool = False
    skill_tier_status: str = "NOT_APPLICABLE"
    quarantined_skill_detected: bool = False
    research_supply_gap: bool = False
    live_benchmark_requested: bool = False
    forced_swarm: bool = False
    parallel_slot_planned: bool = False
    runtime_update_allowed: bool = False
    public_benchmark_allowed: bool = False
    evidence_refs: tuple[str, ...] = ()
    schema: str = HARD_GATE_COMPATIBILITY_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "route_context_changed": self.route_context_changed,
            "route_hardened": self.route_hardened,
            "mfp_confidence_min": self.mfp_confidence_min,
            "router_acceptance_status": _status(self.router_acceptance_status),
            "closeout_claim": self.closeout_claim,
            "completion_status": _status(self.completion_status),
            "context_sources_dropped": self.context_sources_dropped,
            "hallucination_guard_status": _status(self.hallucination_guard_status),
            "mutation_assurance_required": self.mutation_assurance_required,
            "mutation_assurance_status": _status(self.mutation_assurance_status),
            "bdd_acceptance_required": self.bdd_acceptance_required,
            "bdd_preflight_status": _status(self.bdd_preflight_status),
            "capability_contract_type": _contract_type(self.capability_contract_type),
            "pre_model_rescue_planned": self.pre_model_rescue_planned,
            "skill_tier_status": _status(self.skill_tier_status),
            "quarantined_skill_detected": self.quarantined_skill_detected,
            "research_supply_gap": self.research_supply_gap,
            "live_benchmark_requested": self.live_benchmark_requested,
            "forced_swarm": self.forced_swarm,
            "parallel_slot_planned": self.parallel_slot_planned,
            "runtime_update_allowed": self.runtime_update_allowed,
            "public_benchmark_allowed": self.public_benchmark_allowed,
            "evidence_refs": list(self.evidence_refs),
            "claim_boundary": [
                "This compatibility contract checks existing hard gates before optimization work.",
                "It does not approve runtime updates or public benchmark claims.",
            ],
        }
        payload["blockers"] = validate_hard_gate_compatibility(payload)
        payload["status"] = "PASS" if not payload["blockers"] else "RETURN"
        return payload


def build_hard_gate_compatibility(
    *,
    route_context_changed: bool = False,
    route_hardened: bool = False,
    mfp_confidence_min: float = 0.98,
    router_acceptance_status: str = "NOT_APPLICABLE",
    closeout_claim: bool = False,
    completion_status: str = "NOT_APPLICABLE",
    context_sources_dropped: bool = False,
    hallucination_guard_status: str = "NOT_APPLICABLE",
    mutation_assurance_required: bool = False,
    mutation_assurance_status: str = "NOT_APPLICABLE",
    bdd_acceptance_required: bool = False,
    bdd_preflight_status: str = "NOT_APPLICABLE",
    capability_contract_type: str = "NOT_APPLICABLE",
    pre_model_rescue_planned: bool = False,
    skill_tier_status: str = "NOT_APPLICABLE",
    quarantined_skill_detected: bool = False,
    research_supply_gap: bool = False,
    live_benchmark_requested: bool = False,
    forced_swarm: bool = False,
    parallel_slot_planned: bool = False,
    runtime_update_allowed: bool = False,
    public_benchmark_allowed: bool = False,
    evidence_refs: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    return HardGateCompatibility(
        route_context_changed=bool(route_context_changed),
        route_hardened=bool(route_hardened),
        mfp_confidence_min=float(mfp_confidence_min),
        router_acceptance_status=router_acceptance_status,
        closeout_claim=bool(closeout_claim),
        completion_status=completion_status,
        context_sources_dropped=bool(context_sources_dropped),
        hallucination_guard_status=hallucination_guard_status,
        mutation_assurance_required=bool(mutation_assurance_required),
        mutation_assurance_status=mutation_assurance_status,
        bdd_acceptance_required=bool(bdd_acceptance_required),
        bdd_preflight_status=bdd_preflight_status,
        capability_contract_type=capability_contract_type,
        pre_model_rescue_planned=bool(pre_model_rescue_planned),
        skill_tier_status=skill_tier_status,
        quarantined_skill_detected=bool(quarantined_skill_detected),
        research_supply_gap=bool(research_supply_gap),
        live_benchmark_requested=bool(live_benchmark_requested),
        forced_swarm=bool(forced_swarm),
        parallel_slot_planned=bool(parallel_slot_planned),
        runtime_update_allowed=bool(runtime_update_allowed),
        public_benchmark_allowed=bool(public_benchmark_allowed),
        evidence_refs=tuple(str(item) for item in evidence_refs if str(item).strip()),
    ).to_dict()


def validate_hard_gate_compatibility(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if bool(payload.get("runtime_update_allowed", False)):
        blockers.append("compatibility_contract_must_not_update_runtime")
    if bool(payload.get("public_benchmark_allowed", False)):
        blockers.append("compatibility_contract_must_not_unlock_public_benchmark")
    if bool(payload.get("route_context_changed", False)):
        if not bool(payload.get("route_hardened", False)):
            blockers.append("hardened_router_not_enabled")
        if _status(payload.get("router_acceptance_status")) != "PASS":
            blockers.append("router_acceptance_not_pass")
        if _as_float(payload.get("mfp_confidence_min")) <= 0:
            blockers.append("invalid_mfp_confidence_min")
    if bool(payload.get("closeout_claim", False)) and _status(payload.get("completion_status")) != "PASS":
        blockers.append("completion_envelope_not_pass")
    if bool(payload.get("context_sources_dropped", False)):
        if _status(payload.get("hallucination_guard_status")) != "PASS":
            blockers.append("hallucination_guard_not_pass")
    if bool(payload.get("mutation_assurance_required", False)):
        if _status(payload.get("mutation_assurance_status")) != "PASS":
            blockers.append("mutation_assurance_not_pass")
    if bool(payload.get("bdd_acceptance_required", False)):
        if _status(payload.get("bdd_preflight_status")) != "PASS":
            blockers.append("bdd_preflight_not_pass")
    if _contract_type(payload.get("capability_contract_type")) == "required":
        if bool(payload.get("pre_model_rescue_planned", False)):
            blockers.append("required_capability_pre_model_rescue_planned")
    if bool(payload.get("quarantined_skill_detected", False)):
        blockers.append("quarantined_skill_detected")
    if _status(payload.get("skill_tier_status")) not in PASS_LIKE:
        blockers.append("skill_tier_status_not_pass")
    if bool(payload.get("research_supply_gap", False)) and bool(payload.get("live_benchmark_requested", False)):
        blockers.append("research_supply_gap_blocks_live_benchmark")
    if bool(payload.get("forced_swarm", False)) and bool(payload.get("parallel_slot_planned", False)):
        blockers.append("forced_swarm_must_be_serialized")
    return sorted(set(blockers))


def _status(value: Any) -> str:
    return str(value or "NOT_APPLICABLE").strip().upper()


def _contract_type(value: Any) -> str:
    return str(value or "NOT_APPLICABLE").strip().lower()


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
