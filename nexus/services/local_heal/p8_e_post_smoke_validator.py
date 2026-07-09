from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


RECEIPT_PATH = Path("artifacts/effect_reports/p8_one_network_smoke_receipt_v2.json")


@dataclass(frozen=True)
class P8EPostSmokeValidationResult:
    """P8-E4: Post-smoke validation."""
    validation_version: str
    receipt_present: bool
    receipt_json_valid: bool
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
    p2_apply_invoked: bool
    p4_verifier_invoked: bool
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


def validate_p8_e_post_smoke(
    receipt_path: str | Path | None = None,
) -> P8EPostSmokeValidationResult:
    """Validate post-smoke receipt v2."""
    path = Path(receipt_path) if receipt_path else RECEIPT_PATH
    blocked_reasons: list[str] = []

    if not path.exists():
        return P8EPostSmokeValidationResult(
            validation_version="1.0",
            receipt_present=False, receipt_json_valid=False,
            network_call_attempted=False, network_call_completed=False,
            network_call_count=0, timed_out=False, retry_attempted=False,
            streaming_used=False, tool_call_used=False, api_key_logged=False,
            raw_prompt_logged=False, raw_response_logged=False,
            cost_budget_exceeded=False, patch_apply_invoked=False,
            p2_apply_invoked=False, p4_verifier_invoked=False,
            runtime_behavior_changed=False, solved_claim=False,
            claim_eligible=False, public_claim_allowed=False,
            production_ready=False, p2_hash_truth_required=True,
            p2_anchor_truth_required=True, p4_verifier_required=True,
            p4_claim_gate_required=True, smoke_valid=False,
            rollback_required=False, blocked_reasons=["receipt_missing"],
        )

    try:
        with open(path) as f:
            receipt = json.load(f)
    except Exception:
        return P8EPostSmokeValidationResult(
            validation_version="1.0",
            receipt_present=True, receipt_json_valid=False,
            network_call_attempted=False, network_call_completed=False,
            network_call_count=0, timed_out=False, retry_attempted=False,
            streaming_used=False, tool_call_used=False, api_key_logged=False,
            raw_prompt_logged=False, raw_response_logged=False,
            cost_budget_exceeded=False, patch_apply_invoked=False,
            p2_apply_invoked=False, p4_verifier_invoked=False,
            runtime_behavior_changed=False, solved_claim=False,
            claim_eligible=False, public_claim_allowed=False,
            production_ready=False, p2_hash_truth_required=True,
            p2_anchor_truth_required=True, p4_verifier_required=True,
            p4_claim_gate_required=True, smoke_valid=False,
            rollback_required=False, blocked_reasons=["receipt_json_invalid"],
        )

    rollback_triggers = []
    network_call_count = int(receipt.get("network_call_count", 0) or 0)
    retry_attempted = bool(receipt.get("retry_attempted", False))
    streaming_used = bool(receipt.get("streaming_used", False))
    tool_call_used = bool(receipt.get("tool_call_used", False))
    api_key_logged = bool(receipt.get("api_key_logged", False))
    raw_prompt_logged = bool(receipt.get("raw_prompt_logged", False))
    raw_response_logged = bool(receipt.get("raw_response_logged", False))
    patch_apply_invoked = bool(receipt.get("patch_apply_invoked", False))
    p2_apply_invoked = bool(receipt.get("p2_apply_invoked", False))
    p4_verifier_invoked = bool(receipt.get("p4_verifier_invoked", False))
    runtime_behavior_changed = bool(receipt.get("runtime_behavior_changed", False))
    solved_claim = bool(receipt.get("solved_claim", False))
    claim_eligible = bool(receipt.get("claim_eligible", False))
    public_claim_allowed = bool(receipt.get("public_claim_allowed", False))
    production_ready = bool(receipt.get("production_ready", False))
    p2_hash_truth_required = bool(receipt.get("p2_hash_truth_required", True))
    p2_anchor_truth_required = bool(receipt.get("p2_anchor_truth_required", True))
    p4_verifier_required = bool(receipt.get("p4_verifier_required", True))
    p4_claim_gate_required = bool(receipt.get("p4_claim_gate_required", True))

    if network_call_count > 1:
        rollback_triggers.append("network_call_count>1")
    if retry_attempted:
        rollback_triggers.append("retry_attempted")
    if streaming_used:
        rollback_triggers.append("streaming_used")
    if tool_call_used:
        rollback_triggers.append("tool_call_used")
    if api_key_logged:
        rollback_triggers.append("api_key_logged")
    if raw_prompt_logged:
        rollback_triggers.append("raw_prompt_logged")
    if raw_response_logged:
        rollback_triggers.append("raw_response_logged")
    if patch_apply_invoked:
        rollback_triggers.append("patch_apply_invoked")
    if p2_apply_invoked:
        rollback_triggers.append("p2_apply_invoked")
    if p4_verifier_invoked:
        rollback_triggers.append("p4_verifier_invoked")
    if runtime_behavior_changed:
        rollback_triggers.append("runtime_behavior_changed")
    if solved_claim:
        rollback_triggers.append("solved_claim")
    if claim_eligible:
        rollback_triggers.append("claim_eligible")
    if public_claim_allowed:
        rollback_triggers.append("public_claim_allowed")
    if production_ready:
        rollback_triggers.append("production_ready")
    if not p2_hash_truth_required:
        rollback_triggers.append("p2_hash_truth_not_required")
    if not p2_anchor_truth_required:
        rollback_triggers.append("p2_anchor_truth_not_required")
    if not p4_verifier_required:
        rollback_triggers.append("p4_verifier_not_required")
    if not p4_claim_gate_required:
        rollback_triggers.append("p4_claim_gate_not_required")

    rollback_required = len(rollback_triggers) > 0
    blocked_reasons.extend(rollback_triggers)

    network_call_attempted = bool(receipt.get("network_call_attempted", False))
    receipt_complete = bool(receipt.get("receipt_complete", False))

    smoke_valid = (
        receipt_complete
        and network_call_attempted
        and network_call_count == 1
        and not rollback_required
    )

    return P8EPostSmokeValidationResult(
        validation_version="1.0",
        receipt_present=True,
        receipt_json_valid=True,
        network_call_attempted=network_call_attempted,
        network_call_completed=bool(receipt.get("network_call_completed", False)),
        network_call_count=network_call_count,
        timed_out=bool(receipt.get("timed_out", False)),
        retry_attempted=retry_attempted,
        streaming_used=streaming_used,
        tool_call_used=tool_call_used,
        api_key_logged=api_key_logged,
        raw_prompt_logged=raw_prompt_logged,
        raw_response_logged=raw_response_logged,
        cost_budget_exceeded=bool(receipt.get("cost_budget_exceeded", False)),
        patch_apply_invoked=patch_apply_invoked,
        p2_apply_invoked=p2_apply_invoked,
        p4_verifier_invoked=p4_verifier_invoked,
        runtime_behavior_changed=runtime_behavior_changed,
        solved_claim=solved_claim,
        claim_eligible=claim_eligible,
        public_claim_allowed=public_claim_allowed,
        production_ready=production_ready,
        p2_hash_truth_required=p2_hash_truth_required,
        p2_anchor_truth_required=p2_anchor_truth_required,
        p4_verifier_required=p4_verifier_required,
        p4_claim_gate_required=p4_claim_gate_required,
        smoke_valid=smoke_valid,
        rollback_required=rollback_required,
        blocked_reasons=blocked_reasons,
    )


def p8_e_post_smoke_to_dict(result: P8EPostSmokeValidationResult) -> dict[str, Any]:
    return {
        "p8_e_validation_version": result.validation_version,
        "p8_e_receipt_present": result.receipt_present,
        "p8_e_receipt_json_valid": result.receipt_json_valid,
        "p8_e_network_call_attempted": result.network_call_attempted,
        "p8_e_network_call_count": result.network_call_count,
        "p8_e_smoke_valid": result.smoke_valid,
        "p8_e_rollback_required": result.rollback_required,
        "p8_e_blocked_reasons": result.blocked_reasons,
    }
