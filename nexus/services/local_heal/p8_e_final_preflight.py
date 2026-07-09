from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


APPROVAL_PATH = Path("artifacts/effect_reports/p8_human_approval_artifact_v0.json")
CAPSULE_PATH = Path("artifacts/effect_reports/p8_smoke_prompt_capsule_v0.json")


@dataclass(frozen=True)
class P8EFinalPreflightResult:
    """P8-E1: Final preflight revalidation."""
    preflight_version: str
    previous_p8_status: str
    approval_artifact_present: bool
    approval_valid: bool
    approval_scope: str
    prompt_capsule_present: bool
    prompt_capsule_valid: bool
    boundary_valid: bool
    dry_run_status_corrected: bool
    previous_network_call_attempted: bool
    previous_network_call_count: int
    max_network_calls: int
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
    final_preflight_passed: bool
    blocked_reasons: list[str] = field(default_factory=list)


def compute_p8_e_final_preflight() -> P8EFinalPreflightResult:
    """Revalidate P8 state for exactly one network smoke."""
    blocked_reasons: list[str] = []

    previous_p8_status = "P8_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY"
    dry_run_status_corrected = True
    previous_network_call_attempted = False
    previous_network_call_count = 0

    approval_artifact_present = APPROVAL_PATH.exists()
    approval_valid = False
    approval_scope = ""

    if approval_artifact_present:
        try:
            with open(APPROVAL_PATH) as f:
                artifact = json.load(f)
            approval_valid = bool(artifact.get("human_approved", False))
            approval_scope = str(artifact.get("approval_scope", "") or "")
            if approval_scope != "P8_ONE_NETWORK_SMOKE_NO_APPLY":
                blocked_reasons.append(f"wrong_approval_scope:{approval_scope}")
        except Exception:
            blocked_reasons.append("approval_artifact_unreadable")

    if not approval_artifact_present:
        blocked_reasons.append("approval_artifact_missing")
    if not approval_valid:
        blocked_reasons.append("approval_invalid")

    prompt_capsule_present = CAPSULE_PATH.exists()
    prompt_capsule_valid = False

    if prompt_capsule_present:
        try:
            with open(CAPSULE_PATH) as f:
                capsule = json.load(f)
            prompt_capsule_valid = bool(capsule.get("prompt_capsule_valid", False))
        except Exception:
            blocked_reasons.append("prompt_capsule_unreadable")

    if not prompt_capsule_present:
        blocked_reasons.append("prompt_capsule_missing")
    if not prompt_capsule_valid:
        blocked_reasons.append("prompt_capsule_invalid")

    boundary_valid = approval_valid and prompt_capsule_valid and not blocked_reasons

    max_network_calls = 1
    if previous_network_call_count > 0:
        blocked_reasons.append("previous_network_call_exists")

    final_preflight_passed = (
        previous_p8_status == "P8_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY"
        and approval_artifact_present
        and approval_valid
        and approval_scope == "P8_ONE_NETWORK_SMOKE_NO_APPLY"
        and prompt_capsule_present
        and prompt_capsule_valid
        and boundary_valid
        and previous_network_call_attempted is False
        and previous_network_call_count == 0
        and max_network_calls == 1
        and not blocked_reasons
    )

    return P8EFinalPreflightResult(
        preflight_version="1.0",
        previous_p8_status=previous_p8_status,
        approval_artifact_present=approval_artifact_present,
        approval_valid=approval_valid,
        approval_scope=approval_scope,
        prompt_capsule_present=prompt_capsule_present,
        prompt_capsule_valid=prompt_capsule_valid,
        boundary_valid=boundary_valid,
        dry_run_status_corrected=dry_run_status_corrected,
        previous_network_call_attempted=previous_network_call_attempted,
        previous_network_call_count=previous_network_call_count,
        max_network_calls=max_network_calls,
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
        p2_hash_truth_required=True,
        p2_anchor_truth_required=True,
        p4_verifier_required=True,
        p4_claim_gate_required=True,
        final_preflight_passed=final_preflight_passed,
        blocked_reasons=blocked_reasons,
    )


def p8_e_preflight_to_dict(result: P8EFinalPreflightResult) -> dict[str, Any]:
    return {
        "p8_e_preflight_version": result.preflight_version,
        "p8_e_previous_status": result.previous_p8_status,
        "p8_e_approval_present": result.approval_artifact_present,
        "p8_e_approval_valid": result.approval_valid,
        "p8_e_approval_scope": result.approval_scope,
        "p8_e_capsule_present": result.prompt_capsule_present,
        "p8_e_capsule_valid": result.prompt_capsule_valid,
        "p8_e_boundary_valid": result.boundary_valid,
        "p8_e_dry_run_corrected": result.dry_run_status_corrected,
        "p8_e_prev_call_attempted": result.previous_network_call_attempted,
        "p8_e_prev_call_count": result.previous_network_call_count,
        "p8_e_max_calls": result.max_network_calls,
        "p8_e_preflight_passed": result.final_preflight_passed,
        "p8_e_blocked_reasons": result.blocked_reasons,
    }
