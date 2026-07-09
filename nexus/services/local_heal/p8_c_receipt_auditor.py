from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P8CReceiptAuditResult:
    audit_version: str = "1.0"
    receipt_present: bool = False
    receipt_json_valid: bool = False
    required_fields_present: bool = False
    network_call_count: int = 0
    retry_attempted: bool = False
    streaming_used: bool = False
    tool_call_used: bool = False
    api_key_logged: bool = False
    raw_prompt_logged: bool = False
    raw_response_logged: bool = False
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
    receipt_structurally_valid: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


REQUIRED_FIELDS = [
    "receipt_version", "smoke_id", "network_call_count", "api_key_logged",
    "raw_prompt_logged", "raw_response_logged", "patch_apply_invoked",
    "runtime_behavior_changed", "solved_claim", "claim_eligible",
    "public_claim_allowed", "production_ready", "p2_hash_truth_required",
    "p4_verifier_required",
]


def audit_smoke_receipt(receipt_data: dict[str, Any]) -> P8CReceiptAuditResult:
    blocked = []
    if not isinstance(receipt_data, dict) or not receipt_data:
        return P8CReceiptAuditResult(blocked_reasons=["receipt_missing"])

    missing = [f for f in REQUIRED_FIELDS if f not in receipt_data]
    if missing:
        blocked.append("missing_required_fields")

    cc = receipt_data.get("network_call_count", 0)
    retry = receipt_data.get("retry_attempted", False)
    streaming = receipt_data.get("streaming_used", False)
    tool = receipt_data.get("tool_call_used", False)
    akl = receipt_data.get("api_key_logged", False)
    rpl = receipt_data.get("raw_prompt_logged", False)
    rrl = receipt_data.get("raw_response_logged", False)
    pa = receipt_data.get("patch_apply_invoked", False)
    rb = receipt_data.get("runtime_behavior_changed", False)
    sc = receipt_data.get("solved_claim", False)
    ce = receipt_data.get("claim_eligible", False)
    pc = receipt_data.get("public_claim_allowed", False)
    pr = receipt_data.get("production_ready", False)
    p2h = receipt_data.get("p2_hash_truth_required", True)
    p2a = receipt_data.get("p2_anchor_truth_required", True)
    p4v = receipt_data.get("p4_verifier_required", True)
    p4cg = receipt_data.get("p4_claim_gate_required", True)

    if cc > 1: blocked.append("network_call_count_exceeded")
    if retry: blocked.append("retry_attempted")
    if streaming: blocked.append("streaming_used")
    if tool: blocked.append("tool_call_used")
    if akl: blocked.append("api_key_logged")
    if rpl: blocked.append("raw_prompt_logged")
    if rrl: blocked.append("raw_response_logged")
    if pa: blocked.append("patch_apply_invoked")
    if rb: blocked.append("runtime_behavior_changed")
    if sc: blocked.append("solved_claim")
    if ce: blocked.append("claim_eligible")
    if pc: blocked.append("public_claim_allowed")
    if pr: blocked.append("production_ready")
    if not p2h: blocked.append("p2_hash_truth_missing")
    if not p2a: blocked.append("p2_anchor_truth_missing")
    if not p4v: blocked.append("p4_verifier_missing")
    if not p4cg: blocked.append("p4_claim_gate_missing")

    return P8CReceiptAuditResult(
        receipt_present=True,
        receipt_json_valid=True,
        required_fields_present=len(missing) == 0,
        network_call_count=cc, retry_attempted=retry,
        streaming_used=streaming, tool_call_used=tool,
        api_key_logged=akl, raw_prompt_logged=rpl, raw_response_logged=rrl,
        patch_apply_invoked=pa, runtime_behavior_changed=rb,
        solved_claim=sc, claim_eligible=ce, public_claim_allowed=pc,
        production_ready=pr, p2_hash_truth_required=p2h,
        p2_anchor_truth_required=p2a, p4_verifier_required=p4v,
        p4_claim_gate_required=p4cg,
        receipt_structurally_valid=len(blocked) == 0,
        blocked_reasons=blocked,
    )
