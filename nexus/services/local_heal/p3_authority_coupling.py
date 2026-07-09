from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P3AuthorityCouplingDecision:
    """P3-O4: P2/P4 authority coupling contract.

    Maps P3 synthetic candidate availability into required P2/P4 obligations.
    Proves P3 cannot claim solved or apply patches without P2/P4.
    """
    coupling_version: str
    candidate_available: bool
    candidate_is_synthetic: bool
    p2_apply_required: bool
    p2_hash_truth_required: bool
    p2_anchor_truth_required: bool
    p4_full_verifier_required: bool
    p4_claim_gate_required: bool
    patch_apply_allowed: bool
    solved_allowed: bool
    claim_eligible_allowed: bool
    public_claim_allowed: bool
    production_ready: bool
    runtime_behavior_change_allowed: bool
    blocked_reasons: list[str] = field(default_factory=list)


def compute_p3_authority_coupling(
    candidate_available: bool = False,
    candidate_is_synthetic: bool = False,
    p2_hash_truth_present: bool = True,
    p2_anchor_truth_present: bool = True,
    p4_full_verifier_present: bool = True,
    p4_claim_gate_present: bool = True,
) -> P3AuthorityCouplingDecision:
    """Compute P3 authority coupling decision.

    Pure contract: no apply, no verifier execution, no runtime mutation.
    """
    blocked_reasons = []

    if candidate_available and not p2_hash_truth_present:
        blocked_reasons.append("p2_hash_truth_missing")
    if candidate_available and not p2_anchor_truth_present:
        blocked_reasons.append("p2_anchor_truth_missing")
    if candidate_available and not p4_full_verifier_present:
        blocked_reasons.append("p4_full_verifier_missing")
    if candidate_available and not p4_claim_gate_present:
        blocked_reasons.append("p4_claim_gate_missing")

    return P3AuthorityCouplingDecision(
        coupling_version="1.0",
        candidate_available=candidate_available,
        candidate_is_synthetic=candidate_is_synthetic,
        p2_apply_required=candidate_available,
        p2_hash_truth_required=True,
        p2_anchor_truth_required=True,
        p4_full_verifier_required=True,
        p4_claim_gate_required=True,
        patch_apply_allowed=False,
        solved_allowed=False,
        claim_eligible_allowed=False,
        public_claim_allowed=False,
        production_ready=False,
        runtime_behavior_change_allowed=False,
        blocked_reasons=blocked_reasons,
    )


def p3_authority_coupling_to_dict(decision: P3AuthorityCouplingDecision) -> dict[str, Any]:
    """Convert P3AuthorityCouplingDecision to JSON-serializable dict."""
    return {
        "p3_coupling_version": decision.coupling_version,
        "p3_coupling_candidate_available": decision.candidate_available,
        "p3_coupling_candidate_is_synthetic": decision.candidate_is_synthetic,
        "p3_coupling_p2_apply_required": decision.p2_apply_required,
        "p3_coupling_p2_hash_truth_required": decision.p2_hash_truth_required,
        "p3_coupling_p2_anchor_truth_required": decision.p2_anchor_truth_required,
        "p3_coupling_p4_full_verifier_required": decision.p4_full_verifier_required,
        "p3_coupling_p4_claim_gate_required": decision.p4_claim_gate_required,
        "p3_coupling_patch_apply_allowed": decision.patch_apply_allowed,
        "p3_coupling_solved_allowed": decision.solved_allowed,
        "p3_coupling_claim_eligible_allowed": decision.claim_eligible_allowed,
        "p3_coupling_public_claim_allowed": decision.public_claim_allowed,
        "p3_coupling_production_ready": decision.production_ready,
        "p3_coupling_runtime_behavior_change_allowed": decision.runtime_behavior_change_allowed,
        "p3_coupling_blocked_reasons": decision.blocked_reasons,
    }
