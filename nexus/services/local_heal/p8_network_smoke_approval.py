from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P8NetworkSmokeApproval:
    approval_version: str = "1.0"
    human_approved: bool = False
    approver: str = ""
    approval_timestamp_utc: str = ""
    provider_kind: str = ""
    model_name: str = ""
    max_network_calls: int = 0
    max_cost_usd: float = 0.0
    timeout_seconds: int = 0
    prompt_redaction_required: bool = True
    api_key_logging_allowed: bool = False
    raw_response_logging_allowed: bool = False
    patch_apply_allowed: bool = False
    solved_claim_allowed: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    p2_hash_truth_required: bool = True
    p2_anchor_truth_required: bool = True
    p4_verifier_required: bool = True
    p4_claim_gate_required: bool = True
    approval_valid: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def evaluate_approval(
    *,
    human_approved: bool = False,
    approver: str = "",
    provider_kind: str = "",
    model_name: str = "",
    max_network_calls: int = 1,
    max_cost_usd: float = 0.50,
    timeout_seconds: int = 15,
    prompt_redaction_required: bool = True,
    api_key_logging_allowed: bool = False,
    raw_response_logging_allowed: bool = False,
    patch_apply_allowed: bool = False,
    solved_claim_allowed: bool = False,
    public_claim_allowed: bool = False,
    production_ready: bool = False,
    p2_hash_truth_required: bool = True,
    p2_anchor_truth_required: bool = True,
    p4_verifier_required: bool = True,
    p4_claim_gate_required: bool = True,
) -> P8NetworkSmokeApproval:
    blocked = []
    if not human_approved: blocked.append("human_approved_false")
    if not approver: blocked.append("approver_missing")
    if not provider_kind: blocked.append("provider_kind_missing")
    if not model_name: blocked.append("model_name_missing")
    if max_network_calls != 1: blocked.append("max_network_calls_not_1")
    if max_cost_usd <= 0 or max_cost_usd > 1.00: blocked.append("cost_budget_invalid")
    if timeout_seconds <= 0 or timeout_seconds > 30: blocked.append("timeout_invalid")
    if not prompt_redaction_required: blocked.append("prompt_redaction_not_required")
    if api_key_logging_allowed: blocked.append("api_key_logging_allowed")
    if raw_response_logging_allowed: blocked.append("raw_response_logging_allowed")
    if patch_apply_allowed: blocked.append("patch_apply_allowed")
    if solved_claim_allowed: blocked.append("solved_claim_allowed")
    if public_claim_allowed: blocked.append("public_claim_allowed")
    if production_ready: blocked.append("production_ready")
    if not p2_hash_truth_required: blocked.append("p2_hash_truth_missing")
    if not p2_anchor_truth_required: blocked.append("p2_anchor_truth_missing")
    if not p4_verifier_required: blocked.append("p4_verifier_missing")
    if not p4_claim_gate_required: blocked.append("p4_claim_gate_missing")

    return P8NetworkSmokeApproval(
        human_approved=human_approved, approver=approver,
        provider_kind=provider_kind, model_name=model_name,
        max_network_calls=max_network_calls, max_cost_usd=max_cost_usd,
        timeout_seconds=timeout_seconds,
        prompt_redaction_required=prompt_redaction_required,
        api_key_logging_allowed=api_key_logging_allowed,
        raw_response_logging_allowed=raw_response_logging_allowed,
        patch_apply_allowed=patch_apply_allowed,
        solved_claim_allowed=solved_claim_allowed,
        public_claim_allowed=public_claim_allowed,
        production_ready=production_ready,
        p2_hash_truth_required=p2_hash_truth_required,
        p2_anchor_truth_required=p2_anchor_truth_required,
        p4_verifier_required=p4_verifier_required,
        p4_claim_gate_required=p4_claim_gate_required,
        approval_valid=len(blocked) == 0,
        blocked_reasons=blocked,
    )
