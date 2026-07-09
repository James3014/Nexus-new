from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P8OneSmokePreflightResult:
    """P8-B4: One-smoke preflight gate."""
    preflight_version: str
    approval_valid: bool
    boundary_valid: bool
    redaction_passed: bool
    prompt_capsule_valid: bool
    p7_seal_present: bool
    max_network_calls: int
    network_calls_attempted: int
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
    p2_hash_truth_required: bool
    p2_anchor_truth_required: bool
    p4_verifier_required: bool
    p4_claim_gate_required: bool
    preflight_passed: bool
    blocked_reasons: list[str] = field(default_factory=list)


def compute_p8_one_smoke_preflight(
    *,
    approval_valid: bool = False,
    boundary_valid: bool = False,
    redaction_passed: bool = False,
    prompt_capsule_valid: bool = False,
    p7_seal_present: bool = False,
    max_network_calls: int = 0,
    network_calls_attempted: int = 0,
    p2_hash_truth_required: bool = True,
    p2_anchor_truth_required: bool = True,
    p4_verifier_required: bool = True,
    p4_claim_gate_required: bool = True,
) -> P8OneSmokePreflightResult:
    """Compute preflight gate result."""
    blocked_reasons: list[str] = []

    if not approval_valid:
        blocked_reasons.append("approval_invalid")
    if not boundary_valid:
        blocked_reasons.append("boundary_invalid")
    if not redaction_passed:
        blocked_reasons.append("redaction_failed")
    if not prompt_capsule_valid:
        blocked_reasons.append("prompt_capsule_invalid")
    if not p7_seal_present:
        blocked_reasons.append("p7_seal_missing")
    if max_network_calls != 1:
        blocked_reasons.append(f"max_network_calls_not_1:{max_network_calls}")
    if network_calls_attempted > 0:
        blocked_reasons.append("network_calls_already_attempted")
    if not p2_hash_truth_required:
        blocked_reasons.append("p2_hash_truth_missing")
    if not p2_anchor_truth_required:
        blocked_reasons.append("p2_anchor_truth_missing")
    if not p4_verifier_required:
        blocked_reasons.append("p4_verifier_missing")
    if not p4_claim_gate_required:
        blocked_reasons.append("p4_claim_gate_missing")

    preflight_passed = len(blocked_reasons) == 0

    return P8OneSmokePreflightResult(
        preflight_version="1.0",
        approval_valid=approval_valid,
        boundary_valid=boundary_valid,
        redaction_passed=redaction_passed,
        prompt_capsule_valid=prompt_capsule_valid,
        p7_seal_present=p7_seal_present,
        max_network_calls=max_network_calls,
        network_calls_attempted=network_calls_attempted,
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
        p2_hash_truth_required=p2_hash_truth_required,
        p2_anchor_truth_required=p2_anchor_truth_required,
        p4_verifier_required=p4_verifier_required,
        p4_claim_gate_required=p4_claim_gate_required,
        preflight_passed=preflight_passed,
        blocked_reasons=blocked_reasons,
    )


def p8_preflight_to_dict(result: P8OneSmokePreflightResult) -> dict[str, Any]:
    return {
        "p8_preflight_version": result.preflight_version,
        "p8_approval_valid": result.approval_valid,
        "p8_boundary_valid": result.boundary_valid,
        "p8_redaction_passed": result.redaction_passed,
        "p8_prompt_capsule_valid": result.prompt_capsule_valid,
        "p8_p7_seal_present": result.p7_seal_present,
        "p8_max_network_calls": result.max_network_calls,
        "p8_network_calls_attempted": result.network_calls_attempted,
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
        "p8_p2_hash_truth_required": result.p2_hash_truth_required,
        "p8_p2_anchor_truth_required": result.p2_anchor_truth_required,
        "p8_p4_verifier_required": result.p4_verifier_required,
        "p8_p4_claim_gate_required": result.p4_claim_gate_required,
        "p8_preflight_passed": result.preflight_passed,
        "p8_blocked_reasons": result.blocked_reasons,
    }
