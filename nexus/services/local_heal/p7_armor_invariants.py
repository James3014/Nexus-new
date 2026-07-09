from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P7ArmorInvariantResult:
    invariant_version: str = "1.0"
    invariant_passed: bool = False
    p3_closed: bool = False
    p6_closed: bool = False
    p2_hash_truth_required: bool = True
    p2_anchor_truth_required: bool = True
    p4_verifier_required: bool = True
    p4_claim_gate_required: bool = True
    p5_metadata_present_or_required: bool = True
    p6_advisory_only: bool = True
    no_real_provider_required: bool = True
    no_network_required: bool = True
    no_api_key_required: bool = True
    no_patch_apply: bool = True
    no_runtime_behavior_change: bool = True
    no_solved_claim: bool = True
    no_claim_eligible: bool = True
    no_public_claim: bool = True
    no_production_ready: bool = True
    no_p3_topology_override: bool = True
    no_p4_verifier_override: bool = True
    no_claim_gate_override: bool = True
    no_p5_selection_override: bool = True
    blocked_reasons: list[str] = field(default_factory=list)


def evaluate_armor_invariants(
    *,
    p3_closed: bool = True,
    p6_closed: bool = True,
    p2_hash_truth_required: bool = True,
    p2_anchor_truth_required: bool = True,
    p4_verifier_required: bool = True,
    p4_claim_gate_required: bool = True,
    p6_advisory_only: bool = True,
    real_provider_required: bool = False,
    network_required: bool = False,
    api_key_required: bool = False,
    patch_apply_allowed: bool = False,
    runtime_behavior_changed: bool = False,
    solved_claim: bool = False,
    claim_eligible: bool = False,
    public_claim_allowed: bool = False,
    production_ready: bool = False,
    p3_topology_override: bool = False,
    p4_verifier_override: bool = False,
    claim_gate_override: bool = False,
    p5_selection_override: bool = False,
) -> P7ArmorInvariantResult:
    blocked = []
    if not p3_closed:
        blocked.append("p3_not_closed")
    if not p6_closed:
        blocked.append("p6_not_closed")
    if not p2_hash_truth_required:
        blocked.append("p2_hash_truth_missing")
    if not p2_anchor_truth_required:
        blocked.append("p2_anchor_truth_missing")
    if not p4_verifier_required:
        blocked.append("p4_verifier_missing")
    if not p4_claim_gate_required:
        blocked.append("p4_claim_gate_missing")
    if not p6_advisory_only:
        blocked.append("p6_not_advisory_only")
    if real_provider_required:
        blocked.append("real_provider_required")
    if network_required:
        blocked.append("network_required")
    if api_key_required:
        blocked.append("api_key_required")
    if patch_apply_allowed:
        blocked.append("patch_apply_allowed")
    if runtime_behavior_changed:
        blocked.append("runtime_behavior_changed")
    if solved_claim:
        blocked.append("solved_claim")
    if claim_eligible:
        blocked.append("claim_eligible")
    if public_claim_allowed:
        blocked.append("public_claim_allowed")
    if production_ready:
        blocked.append("production_ready")
    if p3_topology_override:
        blocked.append("p3_topology_override")
    if p4_verifier_override:
        blocked.append("p4_verifier_override")
    if claim_gate_override:
        blocked.append("claim_gate_override")
    if p5_selection_override:
        blocked.append("p5_selection_override")

    return P7ArmorInvariantResult(
        invariant_passed=len(blocked) == 0,
        p3_closed=p3_closed,
        p6_closed=p6_closed,
        p2_hash_truth_required=p2_hash_truth_required,
        p2_anchor_truth_required=p2_anchor_truth_required,
        p4_verifier_required=p4_verifier_required,
        p4_claim_gate_required=p4_claim_gate_required,
        p6_advisory_only=p6_advisory_only,
        no_real_provider_required=not real_provider_required,
        no_network_required=not network_required,
        no_api_key_required=not api_key_required,
        no_patch_apply=not patch_apply_allowed,
        no_runtime_behavior_change=not runtime_behavior_changed,
        no_solved_claim=not solved_claim,
        no_claim_eligible=not claim_eligible,
        no_public_claim=not public_claim_allowed,
        no_production_ready=not production_ready,
        no_p3_topology_override=not p3_topology_override,
        no_p4_verifier_override=not p4_verifier_override,
        no_claim_gate_override=not claim_gate_override,
        no_p5_selection_override=not p5_selection_override,
        blocked_reasons=blocked,
    )
