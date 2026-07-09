from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p8_e_final_preflight import (
    P8EFinalPreflightResult,
    compute_p8_e_final_preflight,
    p8_e_preflight_to_dict,
)


# ============================================================
# E1-1: valid corrected P8 ready state passes
# ============================================================


def test_valid_ready_state_passes():
    result = compute_p8_e_final_preflight()
    assert result.final_preflight_passed is True
    assert result.previous_p8_status == "P8_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY"
    assert result.approval_valid is True
    assert result.prompt_capsule_valid is True


# ============================================================
# E1-2: previous status COMPLETED with dry_run blocks
# ============================================================


def test_completed_status_blocks():
    from nexus.services.local_heal.p8_e_final_preflight import P8EFinalPreflightResult
    result = P8EFinalPreflightResult(
        preflight_version="1.0",
        previous_p8_status="P8_CLOSED_ONE_NETWORK_SMOKE_COMPLETED_NO_APPLY",
        approval_artifact_present=True, approval_valid=True,
        approval_scope="P8_ONE_NETWORK_SMOKE_NO_APPLY",
        prompt_capsule_present=True, prompt_capsule_valid=True,
        boundary_valid=True, dry_run_status_corrected=False,
        previous_network_call_attempted=True, previous_network_call_count=1,
        max_network_calls=1, retry_allowed=False, streaming_allowed=False,
        tool_call_allowed=False, api_key_logging_allowed=False,
        raw_prompt_logging_allowed=False, raw_response_logging_allowed=False,
        patch_apply_allowed=False, runtime_behavior_change_allowed=False,
        solved_claim_allowed=False, claim_eligible_allowed=False,
        public_claim_allowed=False, production_ready=False,
        p2_hash_truth_required=True, p2_anchor_truth_required=True,
        p4_verifier_required=True, p4_claim_gate_required=True,
        final_preflight_passed=False, blocked_reasons=["already_completed"],
    )
    assert result.final_preflight_passed is False


# ============================================================
# E1-3: previous_network_call_count>0 blocks
# ============================================================


def test_previous_call_count_blocks():
    from nexus.services.local_heal.p8_e_final_preflight import P8EFinalPreflightResult
    result = P8EFinalPreflightResult(
        preflight_version="1.0",
        previous_p8_status="P8_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY",
        approval_artifact_present=True, approval_valid=True,
        approval_scope="P8_ONE_NETWORK_SMOKE_NO_APPLY",
        prompt_capsule_present=True, prompt_capsule_valid=True,
        boundary_valid=True, dry_run_status_corrected=True,
        previous_network_call_attempted=False, previous_network_call_count=1,
        max_network_calls=1, retry_allowed=False, streaming_allowed=False,
        tool_call_allowed=False, api_key_logging_allowed=False,
        raw_prompt_logging_allowed=False, raw_response_logging_allowed=False,
        patch_apply_allowed=False, runtime_behavior_change_allowed=False,
        solved_claim_allowed=False, claim_eligible_allowed=False,
        public_claim_allowed=False, production_ready=False,
        p2_hash_truth_required=True, p2_anchor_truth_required=True,
        p4_verifier_required=True, p4_claim_gate_required=True,
        final_preflight_passed=False, blocked_reasons=["previous_network_call_exists"],
    )
    assert result.final_preflight_passed is False


# ============================================================
# E1-4: max_network_calls must be 1
# ============================================================


def test_max_calls_must_be_1():
    result = compute_p8_e_final_preflight()
    assert result.max_network_calls == 1


# ============================================================
# E1-5: runtime behavior unchanged
# ============================================================


def test_runtime_unchanged():
    result = compute_p8_e_final_preflight()
    assert result.runtime_behavior_change_allowed is False
    assert result.patch_apply_allowed is False
    assert result.solved_claim_allowed is False
    assert result.public_claim_allowed is False
    assert result.production_ready is False


# ============================================================
# E1-6: P2/P4 gates true
# ============================================================


def test_p2_p4_gates_true():
    result = compute_p8_e_final_preflight()
    assert result.p2_hash_truth_required is True
    assert result.p2_anchor_truth_required is True
    assert result.p4_verifier_required is True
    assert result.p4_claim_gate_required is True


# ============================================================
# E1-7: JSON serialization works
# ============================================================


def test_json_serializable():
    result = compute_p8_e_final_preflight()
    d = p8_e_preflight_to_dict(result)
    assert isinstance(json.dumps(d), str)
