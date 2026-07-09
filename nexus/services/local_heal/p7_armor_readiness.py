from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P7ArmorReadinessDecision:
    readiness_version: str = "1.0"
    decision: str = "P7_CLOSED_BLOCKED_WITH_REASONS"
    manifest_complete: bool = False
    invariants_passed: bool = False
    synthetic_trace_present: bool = False
    receipts_present: bool = False
    all_receipts_complete: bool = False
    p3_closed: bool = False
    p6_closed: bool = False
    p2_hash_truth_required: bool = True
    p2_anchor_truth_required: bool = True
    p4_verifier_required: bool = True
    p4_claim_gate_required: bool = True
    p5_metadata_required: bool = True
    p6_advisory_only: bool = True
    provider_invoked: bool = False
    network_invoked: bool = False
    api_key_used: bool = False
    patch_apply_invoked: bool = False
    runtime_behavior_changed: bool = False
    solved_claim: bool = False
    claim_eligible: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def evaluate_armor_readiness(
    *,
    manifest_complete: bool,
    invariants_passed: bool,
    synthetic_trace_present: bool,
    receipts_present: bool,
    all_receipts_complete: bool,
    p3_closed: bool = True,
    p6_closed: bool = True,
    p2_hash_truth_required: bool = True,
    p2_anchor_truth_required: bool = True,
    p4_verifier_required: bool = True,
    p4_claim_gate_required: bool = True,
    p5_metadata_required: bool = True,
    p6_advisory_only: bool = True,
    provider_invoked: bool = False,
    network_invoked: bool = False,
    api_key_used: bool = False,
    patch_apply_invoked: bool = False,
    runtime_behavior_changed: bool = False,
    solved_claim: bool = False,
    claim_eligible: bool = False,
    public_claim_allowed: bool = False,
    production_ready: bool = False,
) -> P7ArmorReadinessDecision:
    blocked = []
    rollback = []

    if not manifest_complete:
        blocked.append("manifest_incomplete")
    if not invariants_passed:
        blocked.append("invariants_failed")
    if not synthetic_trace_present:
        blocked.append("synthetic_trace_missing")
    if not receipts_present:
        blocked.append("receipts_missing")
    if not all_receipts_complete:
        blocked.append("receipts_incomplete")
    if not p3_closed:
        blocked.append("p3_not_closed")
    if not p6_closed:
        blocked.append("p6_not_closed")

    if provider_invoked: rollback.append("provider_invoked")
    if network_invoked: rollback.append("network_invoked")
    if api_key_used: rollback.append("api_key_used")
    if patch_apply_invoked: rollback.append("patch_apply_invoked")
    if runtime_behavior_changed: rollback.append("runtime_behavior_changed")
    if solved_claim: rollback.append("solved_claim")
    if claim_eligible: rollback.append("claim_eligible")
    if public_claim_allowed: rollback.append("public_claim_allowed")
    if production_ready: rollback.append("production_ready")
    if not p2_hash_truth_required: rollback.append("p2_hash_truth_missing")
    if not p4_verifier_required: rollback.append("p4_verifier_missing")
    if not p6_advisory_only: rollback.append("p6_not_advisory")

    all_blocked = blocked + rollback

    if rollback:
        decision = "P7_CLOSED_ROLLBACK_REQUIRED"
    elif len(blocked) > 0:
        decision = "P7_CLOSED_BLOCKED_WITH_REASONS"
    elif (manifest_complete and invariants_passed and synthetic_trace_present
          and receipts_present and all_receipts_complete and p3_closed and p6_closed):
        decision = "P7_CLOSED_ARMOR_SYNTHETIC_E2E_READY"
    else:
        decision = "P7_CLOSED_BLOCKED_WITH_REASONS"

    return P7ArmorReadinessDecision(
        decision=decision,
        manifest_complete=manifest_complete,
        invariants_passed=invariants_passed,
        synthetic_trace_present=synthetic_trace_present,
        receipts_present=receipts_present,
        all_receipts_complete=all_receipts_complete,
        p3_closed=p3_closed,
        p6_closed=p6_closed,
        p2_hash_truth_required=p2_hash_truth_required,
        p2_anchor_truth_required=p2_anchor_truth_required,
        p4_verifier_required=p4_verifier_required,
        p4_claim_gate_required=p4_claim_gate_required,
        p5_metadata_required=p5_metadata_required,
        p6_advisory_only=p6_advisory_only,
        provider_invoked=provider_invoked,
        network_invoked=network_invoked,
        api_key_used=api_key_used,
        patch_apply_invoked=patch_apply_invoked,
        runtime_behavior_changed=runtime_behavior_changed,
        solved_claim=solved_claim,
        claim_eligible=claim_eligible,
        public_claim_allowed=public_claim_allowed,
        production_ready=production_ready,
        blocked_reasons=all_blocked,
    )
