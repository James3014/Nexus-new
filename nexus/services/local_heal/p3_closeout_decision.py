from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_DECISIONS = frozenset({
    "P3_CLOSED_SYNTHETIC_PROVIDER_TRACE_READY",
    "P3_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY",
    "P3_CLOSED_BLOCKED",
    "P3_CLOSED_ROLLBACK_REQUIRED",
})


@dataclass(frozen=True)
class P3CloseoutDecision:
    """P3-O7/P0: Final P3 closure decision.

    Decision based on synthetic trace, authority coupling, and P6 advisory.
    Consumes blocked_reasons from authority coupling and P6 advisory.
    """
    closeout_version: str
    decision: str
    synthetic_trace_present: bool
    authority_coupling_present: bool
    p6_advisory_contract_present: bool
    real_provider_invoked: bool
    network_invoked: bool
    api_key_used: bool
    patch_apply_invoked: bool
    runtime_behavior_changed: bool
    synthetic_candidate_available: bool
    p2_hash_truth_required: bool
    p2_anchor_truth_required: bool
    p4_full_verifier_required: bool
    p4_claim_gate_required: bool
    p6_advisory_only: bool
    solved_by_p3: bool
    claim_eligible_by_p3: bool
    final_public_claim_allowed: bool
    final_production_ready: bool
    authority_coupling_blocked_reasons: list[str] = field(default_factory=list)
    p6_advisory_blocked_reasons: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)


def compute_p3_closeout_decision(
    *,
    synthetic_trace_present: bool = False,
    authority_coupling_present: bool = False,
    p6_advisory_contract_present: bool = False,
    real_provider_invoked: bool = False,
    network_invoked: bool = False,
    api_key_used: bool = False,
    patch_apply_invoked: bool = False,
    runtime_behavior_changed: bool = False,
    synthetic_candidate_available: bool = False,
    p2_hash_truth_required: bool = True,
    p2_anchor_truth_required: bool = True,
    p4_full_verifier_required: bool = True,
    p4_claim_gate_required: bool = True,
    p6_advisory_only: bool = True,
    solved_by_p3: bool = False,
    claim_eligible_by_p3: bool = False,
    final_public_claim_allowed: bool = False,
    final_production_ready: bool = False,
    human_approval_checklist_present: bool = False,
    authority_coupling_blocked_reasons: list[str] | None = None,
    p6_advisory_blocked_reasons: list[str] | None = None,
    p6_topology_override_attempted: bool = False,
    p6_verifier_override_attempted: bool = False,
    p6_claim_gate_override_attempted: bool = False,
    p6_p5_override_attempted: bool = False,
) -> P3CloseoutDecision:
    """Compute P3 closeout decision.

    Pure decision: no runtime, no provider, no apply, no verifier.
    Consumes blocked_reasons from authority coupling and P6 advisory.
    """
    blocked_reasons = []
    ac_blocked = list(authority_coupling_blocked_reasons or [])
    p6_blocked = list(p6_advisory_blocked_reasons or [])

    if not synthetic_trace_present:
        blocked_reasons.append("synthetic_trace_missing")
    if not authority_coupling_present:
        blocked_reasons.append("authority_coupling_missing")

    if ac_blocked:
        blocked_reasons.extend([f"authority_coupling:{r}" for r in ac_blocked])

    if real_provider_invoked:
        blocked_reasons.append("real_provider_invoked")
    if network_invoked:
        blocked_reasons.append("network_invoked")
    if api_key_used:
        blocked_reasons.append("api_key_used")
    if patch_apply_invoked:
        blocked_reasons.append("patch_apply_invoked")
    if runtime_behavior_changed:
        blocked_reasons.append("runtime_behavior_changed")

    if not p2_hash_truth_required:
        blocked_reasons.append("p2_hash_truth_not_required")
    if not p2_anchor_truth_required:
        blocked_reasons.append("p2_anchor_truth_not_required")
    if not p4_full_verifier_required:
        blocked_reasons.append("p4_full_verifier_not_required")
    if not p4_claim_gate_required:
        blocked_reasons.append("p4_claim_gate_not_required")

    if solved_by_p3:
        blocked_reasons.append("solved_by_p3")
    if claim_eligible_by_p3:
        blocked_reasons.append("claim_eligible_by_p3")
    if final_public_claim_allowed:
        blocked_reasons.append("public_claim_allowed")
    if final_production_ready:
        blocked_reasons.append("production_ready")

    if p6_topology_override_attempted:
        blocked_reasons.append("p6_topology_override")
    if p6_verifier_override_attempted:
        blocked_reasons.append("p6_verifier_override")
    if p6_claim_gate_override_attempted:
        blocked_reasons.append("p6_claim_gate_override")
    if p6_p5_override_attempted:
        blocked_reasons.append("p6_p5_override")

    if p6_blocked:
        blocked_reasons.extend([f"p6_advisory:{r}" for r in p6_blocked])

    safety_gates_pass = not any([
        real_provider_invoked, network_invoked, api_key_used,
        patch_apply_invoked, runtime_behavior_changed,
        solved_by_p3, claim_eligible_by_p3,
        final_public_claim_allowed, final_production_ready,
        p6_topology_override_attempted, p6_verifier_override_attempted,
        p6_claim_gate_override_attempted, p6_p5_override_attempted,
    ])

    authority_gates_pass = all([
        p2_hash_truth_required, p2_anchor_truth_required,
        p4_full_verifier_required, p4_claim_gate_required,
    ])

    evidence_present = (
        synthetic_trace_present
        and authority_coupling_present
        and not ac_blocked
        and not p6_blocked
    )

    if not safety_gates_pass or not authority_gates_pass:
        decision = "P3_CLOSED_ROLLBACK_REQUIRED"
    elif not evidence_present:
        decision = "P3_CLOSED_BLOCKED"
    elif human_approval_checklist_present and p6_advisory_only:
        decision = "P3_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY"
    else:
        decision = "P3_CLOSED_SYNTHETIC_PROVIDER_TRACE_READY"

    return P3CloseoutDecision(
        closeout_version="2.0",
        decision=decision,
        synthetic_trace_present=synthetic_trace_present,
        authority_coupling_present=authority_coupling_present,
        p6_advisory_contract_present=p6_advisory_contract_present,
        real_provider_invoked=real_provider_invoked,
        network_invoked=network_invoked,
        api_key_used=api_key_used,
        patch_apply_invoked=patch_apply_invoked,
        runtime_behavior_changed=runtime_behavior_changed,
        synthetic_candidate_available=synthetic_candidate_available,
        p2_hash_truth_required=p2_hash_truth_required,
        p2_anchor_truth_required=p2_anchor_truth_required,
        p4_full_verifier_required=p4_full_verifier_required,
        p4_claim_gate_required=p4_claim_gate_required,
        p6_advisory_only=p6_advisory_only,
        solved_by_p3=solved_by_p3,
        claim_eligible_by_p3=claim_eligible_by_p3,
        final_public_claim_allowed=final_public_claim_allowed,
        final_production_ready=final_production_ready,
        authority_coupling_blocked_reasons=ac_blocked,
        p6_advisory_blocked_reasons=p6_blocked,
        blocked_reasons=blocked_reasons,
    )


def p3_closeout_decision_to_dict(decision: P3CloseoutDecision) -> dict[str, Any]:
    """Convert P3CloseoutDecision to JSON-serializable dict."""
    return {
        "p3_closeout_version": decision.closeout_version,
        "p3_closeout_decision": decision.decision,
        "p3_closeout_synthetic_trace_present": decision.synthetic_trace_present,
        "p3_closeout_authority_coupling_present": decision.authority_coupling_present,
        "p3_closeout_p6_advisory_contract_present": decision.p6_advisory_contract_present,
        "p3_closeout_real_provider_invoked": decision.real_provider_invoked,
        "p3_closeout_network_invoked": decision.network_invoked,
        "p3_closeout_api_key_used": decision.api_key_used,
        "p3_closeout_patch_apply_invoked": decision.patch_apply_invoked,
        "p3_closeout_runtime_behavior_changed": decision.runtime_behavior_changed,
        "p3_closeout_synthetic_candidate_available": decision.synthetic_candidate_available,
        "p3_closeout_p2_hash_truth_required": decision.p2_hash_truth_required,
        "p3_closeout_p2_anchor_truth_required": decision.p2_anchor_truth_required,
        "p3_closeout_p4_full_verifier_required": decision.p4_full_verifier_required,
        "p3_closeout_p4_claim_gate_required": decision.p4_claim_gate_required,
        "p3_closeout_p6_advisory_only": decision.p6_advisory_only,
        "p3_closeout_solved_by_p3": decision.solved_by_p3,
        "p3_closeout_claim_eligible_by_p3": decision.claim_eligible_by_p3,
        "p3_closeout_final_public_claim_allowed": decision.final_public_claim_allowed,
        "p3_closeout_final_production_ready": decision.final_production_ready,
        "p3_closeout_authority_coupling_blocked_reasons": decision.authority_coupling_blocked_reasons,
        "p3_closeout_p6_advisory_blocked_reasons": decision.p6_advisory_blocked_reasons,
        "p3_closeout_blocked_reasons": decision.blocked_reasons,
    }
