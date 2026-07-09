from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P8SmokeValidationResult:
    validation_version: str = "1.0"
    smoke_receipt_present: bool = False
    smoke_completed_or_timed_out: bool = False
    network_call_count_valid: bool = False
    no_retry_confirmed: bool = True
    no_streaming_confirmed: bool = True
    no_tool_call_confirmed: bool = True
    api_key_not_logged: bool = True
    raw_prompt_not_logged: bool = True
    raw_response_not_logged: bool = True
    cost_budget_not_exceeded: bool = True
    patch_apply_not_invoked: bool = True
    runtime_behavior_unchanged: bool = True
    solved_claim_false: bool = True
    claim_eligible_false: bool = True
    public_claim_allowed_false: bool = True
    production_ready_false: bool = True
    p2_hash_truth_required: bool = True
    p2_anchor_truth_required: bool = True
    p4_verifier_required: bool = True
    p4_claim_gate_required: bool = True
    smoke_valid: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def validate_smoke_result(receipt: dict[str, Any]) -> P8SmokeValidationResult:
    blocked = []
    has_receipt = bool(receipt)
    attempted = receipt.get("network_call_attempted", False)
    completed = receipt.get("network_call_completed", False)
    timed_out = receipt.get("timed_out", False)
    count = receipt.get("network_call_count", 0)

    count_valid = (count == 1) if (attempted and (completed or timed_out)) else True
    if not count_valid: blocked.append("network_call_count_invalid")
    if receipt.get("api_key_logged"): blocked.append("api_key_logged")
    if receipt.get("raw_prompt_logged"): blocked.append("raw_prompt_logged")
    if receipt.get("raw_response_logged"): blocked.append("raw_response_logged")
    if receipt.get("cost_budget_exceeded"): blocked.append("cost_budget_exceeded")
    if receipt.get("patch_apply_invoked"): blocked.append("patch_apply_invoked")
    if receipt.get("runtime_behavior_changed"): blocked.append("runtime_behavior_changed")
    if receipt.get("solved_claim"): blocked.append("solved_claim")
    if receipt.get("claim_eligible"): blocked.append("claim_eligible")
    if receipt.get("public_claim_allowed"): blocked.append("public_claim_allowed")
    if receipt.get("production_ready"): blocked.append("production_ready")
    if not receipt.get("p2_hash_truth_required", True): blocked.append("p2_hash_truth_missing")
    if not receipt.get("p4_verifier_required", True): blocked.append("p4_verifier_missing")

    return P8SmokeValidationResult(
        smoke_receipt_present=has_receipt,
        smoke_completed_or_timed_out=completed or timed_out,
        network_call_count_valid=count_valid,
        api_key_not_logged=not receipt.get("api_key_logged"),
        raw_prompt_not_logged=not receipt.get("raw_prompt_logged"),
        raw_response_not_logged=not receipt.get("raw_response_logged"),
        cost_budget_not_exceeded=not receipt.get("cost_budget_exceeded"),
        patch_apply_not_invoked=not receipt.get("patch_apply_invoked"),
        runtime_behavior_unchanged=not receipt.get("runtime_behavior_changed"),
        solved_claim_false=not receipt.get("solved_claim"),
        claim_eligible_false=not receipt.get("claim_eligible"),
        public_claim_allowed_false=not receipt.get("public_claim_allowed"),
        production_ready_false=not receipt.get("production_ready"),
        p2_hash_truth_required=receipt.get("p2_hash_truth_required", True),
        p4_verifier_required=receipt.get("p4_verifier_required", True),
        smoke_valid=len(blocked) == 0 and has_receipt,
        blocked_reasons=blocked,
    )
