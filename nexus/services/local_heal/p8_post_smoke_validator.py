from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.p8_one_smoke_runner import P8OneSmokeReceipt


@dataclass(frozen=True)
class P8PostSmokeValidationResult:
    """P8-B6: Post-smoke safety validator."""
    validation_version: str
    receipt_present: bool
    network_call_attempted: bool
    network_call_completed: bool
    network_call_count: int
    timed_out: bool
    retry_attempted: bool
    streaming_used: bool
    tool_call_used: bool
    api_key_logged: bool
    raw_prompt_logged: bool
    raw_response_logged: bool
    cost_budget_exceeded: bool
    patch_apply_invoked: bool
    runtime_behavior_changed: bool
    solved_claim: bool
    claim_eligible: bool
    public_claim_allowed: bool
    production_ready: bool
    p2_hash_truth_required: bool
    p2_anchor_truth_required: bool
    p4_verifier_required: bool
    p4_claim_gate_required: bool
    smoke_valid: bool
    rollback_required: bool
    blocked_reasons: list[str] = field(default_factory=list)


def validate_p8_post_smoke(
    receipt: P8OneSmokeReceipt | None = None,
) -> P8PostSmokeValidationResult:
    """Validate post-smoke receipt."""
    blocked_reasons: list[str] = []

    if receipt is None:
        return P8PostSmokeValidationResult(
            validation_version="1.0",
            receipt_present=False,
            network_call_attempted=False,
            network_call_completed=False,
            network_call_count=0,
            timed_out=False,
            retry_attempted=False,
            streaming_used=False,
            tool_call_used=False,
            api_key_logged=False,
            raw_prompt_logged=False,
            raw_response_logged=False,
            cost_budget_exceeded=False,
            patch_apply_invoked=False,
            runtime_behavior_changed=False,
            solved_claim=False,
            claim_eligible=False,
            public_claim_allowed=False,
            production_ready=False,
            p2_hash_truth_required=True,
            p2_anchor_truth_required=True,
            p4_verifier_required=True,
            p4_claim_gate_required=True,
            smoke_valid=False,
            rollback_required=False,
            blocked_reasons=["receipt_missing"],
        )

    rollback_triggers = []
    if receipt.network_call_count > 1:
        rollback_triggers.append("network_call_count>1")
    if receipt.retry_attempted:
        rollback_triggers.append("retry_attempted")
    if receipt.streaming_used:
        rollback_triggers.append("streaming_used")
    if receipt.tool_call_used:
        rollback_triggers.append("tool_call_used")
    if receipt.api_key_logged:
        rollback_triggers.append("api_key_logged")
    if receipt.raw_prompt_logged:
        rollback_triggers.append("raw_prompt_logged")
    if receipt.raw_response_logged:
        rollback_triggers.append("raw_response_logged")
    if receipt.patch_apply_invoked:
        rollback_triggers.append("patch_apply_invoked")
    if receipt.runtime_behavior_changed:
        rollback_triggers.append("runtime_behavior_changed")
    if receipt.solved_claim:
        rollback_triggers.append("solved_claim")
    if receipt.claim_eligible:
        rollback_triggers.append("claim_eligible")
    if receipt.public_claim_allowed:
        rollback_triggers.append("public_claim_allowed")
    if receipt.production_ready:
        rollback_triggers.append("production_ready")
    if not receipt.p2_hash_truth_required:
        rollback_triggers.append("p2_hash_truth_not_required")
    if not receipt.p2_anchor_truth_required:
        rollback_triggers.append("p2_anchor_truth_not_required")
    if not receipt.p4_verifier_required:
        rollback_triggers.append("p4_verifier_not_required")
    if not receipt.p4_claim_gate_required:
        rollback_triggers.append("p4_claim_gate_not_required")

    rollback_required = len(rollback_triggers) > 0
    blocked_reasons.extend(rollback_triggers)

    smoke_valid = (
        receipt.receipt_complete
        and receipt.network_call_attempted
        and receipt.network_call_count == 1
        and not rollback_required
    )

    return P8PostSmokeValidationResult(
        validation_version="1.0",
        receipt_present=True,
        network_call_attempted=receipt.network_call_attempted,
        network_call_completed=receipt.network_call_completed,
        network_call_count=receipt.network_call_count,
        timed_out=receipt.timed_out,
        retry_attempted=receipt.retry_attempted,
        streaming_used=receipt.streaming_used,
        tool_call_used=receipt.tool_call_used,
        api_key_logged=receipt.api_key_logged,
        raw_prompt_logged=receipt.raw_prompt_logged,
        raw_response_logged=receipt.raw_response_logged,
        cost_budget_exceeded=receipt.cost_budget_exceeded,
        patch_apply_invoked=receipt.patch_apply_invoked,
        runtime_behavior_changed=receipt.runtime_behavior_changed,
        solved_claim=receipt.solved_claim,
        claim_eligible=receipt.claim_eligible,
        public_claim_allowed=receipt.public_claim_allowed,
        production_ready=receipt.production_ready,
        p2_hash_truth_required=receipt.p2_hash_truth_required,
        p2_anchor_truth_required=receipt.p2_anchor_truth_required,
        p4_verifier_required=receipt.p4_verifier_required,
        p4_claim_gate_required=receipt.p4_claim_gate_required,
        smoke_valid=smoke_valid,
        rollback_required=rollback_required,
        blocked_reasons=blocked_reasons,
    )


def p8_post_smoke_to_dict(result: P8PostSmokeValidationResult) -> dict[str, Any]:
    return {
        "p8_validation_version": result.validation_version,
        "p8_receipt_present": result.receipt_present,
        "p8_network_call_attempted": result.network_call_attempted,
        "p8_network_call_completed": result.network_call_completed,
        "p8_network_call_count": result.network_call_count,
        "p8_timed_out": result.timed_out,
        "p8_retry_attempted": result.retry_attempted,
        "p8_streaming_used": result.streaming_used,
        "p8_tool_call_used": result.tool_call_used,
        "p8_api_key_logged": result.api_key_logged,
        "p8_raw_prompt_logged": result.raw_prompt_logged,
        "p8_raw_response_logged": result.raw_response_logged,
        "p8_cost_budget_exceeded": result.cost_budget_exceeded,
        "p8_patch_apply_invoked": result.patch_apply_invoked,
        "p8_runtime_behavior_changed": result.runtime_behavior_changed,
        "p8_solved_claim": result.solved_claim,
        "p8_claim_eligible": result.claim_eligible,
        "p8_public_claim_allowed": result.public_claim_allowed,
        "p8_production_ready": result.production_ready,
        "p8_p2_hash_truth_required": result.p2_hash_truth_required,
        "p8_p2_anchor_truth_required": result.p2_anchor_truth_required,
        "p8_p4_verifier_required": result.p4_verifier_required,
        "p8_p4_claim_gate_required": result.p4_claim_gate_required,
        "p8_smoke_valid": result.smoke_valid,
        "p8_rollback_required": result.rollback_required,
        "p8_blocked_reasons": result.blocked_reasons,
    }
