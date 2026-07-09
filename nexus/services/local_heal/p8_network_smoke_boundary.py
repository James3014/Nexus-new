from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.p8_human_approval_intake import (
    P8HumanApprovalIntakeResult,
    validate_p8_human_approval,
)


@dataclass(frozen=True)
class P8NetworkSmokeBoundaryResult:
    """P8-B2: Network smoke boundary."""
    boundary_version: str
    approval_valid: bool
    boundary_valid: bool
    p2_hash_truth_required: bool
    p2_anchor_truth_required: bool
    p4_verifier_required: bool
    p4_claim_gate_required: bool
    max_network_calls: int
    network_calls_attempted: int
    network_call_allowed: bool
    retry_allowed: bool
    streaming_allowed: bool
    tool_call_allowed: bool
    api_key_logging_allowed: bool
    raw_prompt_logging_allowed: bool
    raw_response_logging_allowed: bool
    patch_apply_allowed: bool
    runtime_behavior_change_allowed: bool
    solved_claim_allowed: bool
    claim_eligible_allowed: bool
    public_claim_allowed: bool
    production_ready: bool
    blocked_reasons: list[str] = field(default_factory=list)


def compute_p8_network_smoke_boundary(
    approval_result: P8HumanApprovalIntakeResult | None = None,
    p2_hash_truth_required: bool = True,
    p2_anchor_truth_required: bool = True,
    p4_verifier_required: bool = True,
    p4_claim_gate_required: bool = True,
    network_calls_attempted: int = 0,
) -> P8NetworkSmokeBoundaryResult:
    """Compute network smoke boundary from approval result."""
    blocked_reasons: list[str] = []

    if approval_result is None or not approval_result.approval_valid:
        blocked_reasons.append("approval_invalid")
        return P8NetworkSmokeBoundaryResult(
            boundary_version="1.0",
            approval_valid=False,
            boundary_valid=False,
            p2_hash_truth_required=p2_hash_truth_required,
            p2_anchor_truth_required=p2_anchor_truth_required,
            p4_verifier_required=p4_verifier_required,
            p4_claim_gate_required=p4_claim_gate_required,
            max_network_calls=0,
            network_calls_attempted=network_calls_attempted,
            network_call_allowed=False,
            retry_allowed=False,
            streaming_allowed=False,
            tool_call_allowed=False,
            api_key_logging_allowed=False,
            raw_prompt_logging_allowed=False,
            raw_response_logging_allowed=False,
            patch_apply_allowed=False,
            runtime_behavior_change_allowed=False,
            solved_claim_allowed=False,
            claim_eligible_allowed=False,
            public_claim_allowed=False,
            production_ready=False,
            blocked_reasons=blocked_reasons,
        )

    if not p2_hash_truth_required:
        blocked_reasons.append("p2_hash_truth_missing")
    if not p2_anchor_truth_required:
        blocked_reasons.append("p2_anchor_truth_missing")
    if not p4_verifier_required:
        blocked_reasons.append("p4_verifier_missing")
    if not p4_claim_gate_required:
        blocked_reasons.append("p4_claim_gate_missing")

    if network_calls_attempted > 0:
        blocked_reasons.append("pre_existing_network_calls")

    boundary_valid = len(blocked_reasons) == 0
    network_call_allowed = (
        boundary_valid
        and approval_result.max_network_calls == 1
        and network_calls_attempted == 0
    )

    return P8NetworkSmokeBoundaryResult(
        boundary_version="1.0",
        approval_valid=True,
        boundary_valid=boundary_valid,
        p2_hash_truth_required=p2_hash_truth_required,
        p2_anchor_truth_required=p2_anchor_truth_required,
        p4_verifier_required=p4_verifier_required,
        p4_claim_gate_required=p4_claim_gate_required,
        max_network_calls=approval_result.max_network_calls,
        network_calls_attempted=network_calls_attempted,
        network_call_allowed=network_call_allowed,
        retry_allowed=False,
        streaming_allowed=False,
        tool_call_allowed=False,
        api_key_logging_allowed=False,
        raw_prompt_logging_allowed=False,
        raw_response_logging_allowed=False,
        patch_apply_allowed=False,
        runtime_behavior_change_allowed=False,
        solved_claim_allowed=False,
        claim_eligible_allowed=False,
        public_claim_allowed=False,
        production_ready=False,
        blocked_reasons=blocked_reasons,
    )


def p8_boundary_to_dict(result: P8NetworkSmokeBoundaryResult) -> dict[str, Any]:
    return {
        "p8_boundary_version": result.boundary_version,
        "p8_approval_valid": result.approval_valid,
        "p8_boundary_valid": result.boundary_valid,
        "p8_p2_hash_truth_required": result.p2_hash_truth_required,
        "p8_p2_anchor_truth_required": result.p2_anchor_truth_required,
        "p8_p4_verifier_required": result.p4_verifier_required,
        "p8_p4_claim_gate_required": result.p4_claim_gate_required,
        "p8_max_network_calls": result.max_network_calls,
        "p8_network_calls_attempted": result.network_calls_attempted,
        "p8_network_call_allowed": result.network_call_allowed,
        "p8_retry_allowed": result.retry_allowed,
        "p8_streaming_allowed": result.streaming_allowed,
        "p8_tool_call_allowed": result.tool_call_allowed,
        "p8_api_key_logging_allowed": result.api_key_logging_allowed,
        "p8_raw_prompt_logging_allowed": result.raw_prompt_logging_allowed,
        "p8_raw_response_logging_allowed": result.raw_response_logging_allowed,
        "p8_patch_apply_allowed": result.patch_apply_allowed,
        "p8_runtime_behavior_change_allowed": result.runtime_behavior_change_allowed,
        "p8_solved_claim_allowed": result.solved_claim_allowed,
        "p8_claim_eligible_allowed": result.claim_eligible_allowed,
        "p8_public_claim_allowed": result.public_claim_allowed,
        "p8_production_ready": result.production_ready,
        "p8_blocked_reasons": result.blocked_reasons,
    }
