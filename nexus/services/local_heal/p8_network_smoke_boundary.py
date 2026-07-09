from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P8NetworkSmokeBoundary:
    boundary_version: str = "1.0"
    approval_valid: bool = False
    network_call_allowed: bool = False
    provider_kind: str = ""
    model_name: str = ""
    max_network_calls: int = 1
    network_calls_attempted: int = 0
    timeout_seconds: int = 0
    max_cost_usd: float = 0.0
    prompt_redaction_required: bool = True
    api_key_required: bool = False
    api_key_logging_allowed: bool = False
    raw_prompt_logging_allowed: bool = False
    raw_response_logging_allowed: bool = False
    retry_allowed: bool = False
    streaming_allowed: bool = False
    tool_call_allowed: bool = False
    patch_apply_allowed: bool = False
    runtime_behavior_change_allowed: bool = False
    solved_claim_allowed: bool = False
    claim_eligible_allowed: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    p2_hash_truth_required: bool = True
    p2_anchor_truth_required: bool = True
    p4_verifier_required: bool = True
    p4_claim_gate_required: bool = True
    boundary_valid: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def build_boundary(
    *,
    approval_valid: bool,
    provider_kind: str = "",
    model_name: str = "",
    max_network_calls: int = 1,
    network_calls_attempted: int = 0,
    timeout_seconds: int = 15,
    max_cost_usd: float = 0.50,
    retry_allowed: bool = False,
    streaming_allowed: bool = False,
    tool_call_allowed: bool = False,
    raw_prompt_logging_allowed: bool = False,
    raw_response_logging_allowed: bool = False,
    patch_apply_allowed: bool = False,
    runtime_behavior_change_allowed: bool = False,
    solved_claim_allowed: bool = False,
    claim_eligible_allowed: bool = False,
    public_claim_allowed: bool = False,
    production_ready: bool = False,
    p2_hash_truth_required: bool = True,
    p4_verifier_required: bool = True,
) -> P8NetworkSmokeBoundary:
    blocked = []
    if not approval_valid: blocked.append("approval_invalid")
    if max_network_calls != 1: blocked.append("max_network_calls_not_1")
    if network_calls_attempted > 0: blocked.append("pre_existing_calls")
    if retry_allowed: blocked.append("retry_not_allowed")
    if streaming_allowed: blocked.append("streaming_not_allowed")
    if tool_call_allowed: blocked.append("tool_call_not_allowed")
    if raw_prompt_logging_allowed: blocked.append("raw_prompt_logging_not_allowed")
    if raw_response_logging_allowed: blocked.append("raw_response_logging_not_allowed")
    if patch_apply_allowed: blocked.append("patch_apply_not_allowed")
    if runtime_behavior_change_allowed: blocked.append("runtime_change_not_allowed")
    if solved_claim_allowed: blocked.append("solved_claim_not_allowed")
    if claim_eligible_allowed: blocked.append("claim_eligible_not_allowed")
    if public_claim_allowed: blocked.append("public_claim_not_allowed")
    if production_ready: blocked.append("production_ready_not_allowed")
    if not p2_hash_truth_required: blocked.append("p2_hash_truth_missing")
    if not p4_verifier_required: blocked.append("p4_verifier_missing")

    valid = len(blocked) == 0
    return P8NetworkSmokeBoundary(
        approval_valid=approval_valid,
        network_call_allowed=valid,
        provider_kind=provider_kind, model_name=model_name,
        max_network_calls=max_network_calls,
        network_calls_attempted=network_calls_attempted,
        timeout_seconds=timeout_seconds, max_cost_usd=max_cost_usd,
        retry_allowed=retry_allowed, streaming_allowed=streaming_allowed,
        tool_call_allowed=tool_call_allowed,
        raw_prompt_logging_allowed=raw_prompt_logging_allowed,
        raw_response_logging_allowed=raw_response_logging_allowed,
        patch_apply_allowed=patch_apply_allowed,
        runtime_behavior_change_allowed=runtime_behavior_change_allowed,
        solved_claim_allowed=solved_claim_allowed,
        claim_eligible_allowed=claim_eligible_allowed,
        public_claim_allowed=public_claim_allowed,
        production_ready=production_ready,
        p2_hash_truth_required=p2_hash_truth_required,
        p4_verifier_required=p4_verifier_required,
        boundary_valid=valid,
        blocked_reasons=blocked,
    )
