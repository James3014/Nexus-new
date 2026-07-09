from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P8NetworkSmokeReceipt:
    receipt_version: str = "1.0"
    smoke_id: str = ""
    approval_valid: bool = False
    boundary_valid: bool = False
    redaction_passed: bool = False
    provider_kind: str = ""
    model_name: str = ""
    network_call_attempted: bool = False
    network_call_completed: bool = False
    network_call_count: int = 0
    timeout_seconds: int = 0
    timed_out: bool = False
    cost_budget_usd: float = 0.0
    estimated_cost_usd: float = 0.0
    cost_budget_exceeded: bool = False
    api_key_used: bool = False
    api_key_logged: bool = False
    raw_prompt_logged: bool = False
    raw_response_logged: bool = False
    redacted_prompt_hash: str = ""
    provider_response_hash: str = ""
    provider_response_redacted: str = ""
    candidate_like_output_available: bool = False
    patch_apply_invoked: bool = False
    runtime_behavior_changed: bool = False
    solved_claim: bool = False
    claim_eligible: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    p2_hash_truth_required: bool = True
    p2_anchor_truth_required: bool = True
    p4_verifier_required: bool = True
    p4_claim_gate_required: bool = True
    receipt_complete: bool = True
    blocked_reasons: list[str] = field(default_factory=list)


def validate_smoke_receipt(receipt: dict[str, Any]) -> tuple[bool, list[str]]:
    blocked = []
    if receipt.get("network_call_count", 0) > 1: blocked.append("network_call_count_exceeded")
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
    return len(blocked) == 0, blocked
