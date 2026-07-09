from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p8_one_smoke_runner import execute_p8_one_smoke
from nexus.services.local_heal.p8_post_smoke_validator import (
    P8PostSmokeValidationResult,
    validate_p8_post_smoke,
    p8_post_smoke_to_dict,
)


def _valid_receipt():
    return execute_p8_one_smoke(
        preflight_passed=True,
        approval_artifact_ref="test",
        preflight_ref="test",
        provider_kind="openai",
        model_name="gpt-4o-mini",
        timeout_seconds=15,
        cost_budget_usd=0.50,
        redacted_prompt_hash="abc123",
        dry_run=True,
    )


# ============================================================
# B6-1: valid receipt passes
# ============================================================


def test_valid_receipt_passes():
    receipt = _valid_receipt()
    result = validate_p8_post_smoke(receipt)
    assert result.smoke_valid is True
    assert result.rollback_required is False


# ============================================================
# B6-2: missing receipt blocks
# ============================================================


def test_missing_receipt_blocks():
    result = validate_p8_post_smoke(receipt=None)
    assert result.smoke_valid is False
    assert "receipt_missing" in result.blocked_reasons


# ============================================================
# B6-3: network_call_count=0 blocks if smoke expected
# ============================================================


def test_network_call_count_0_blocks():
    from nexus.services.local_heal.p8_one_smoke_runner import P8OneSmokeReceipt
    receipt = P8OneSmokeReceipt(
        receipt_version="1.0", smoke_id="test", approval_artifact_ref="",
        preflight_ref="", provider_kind="openai", model_name="gpt-4o-mini",
        network_call_attempted=False, network_call_completed=False,
        network_call_count=0, timed_out=False, timeout_seconds=15,
        cost_budget_usd=0.50, estimated_cost_usd=0.0, cost_budget_exceeded=False,
        retry_attempted=False, streaming_used=False, tool_call_used=False,
        api_key_used=False, api_key_logged=False, raw_prompt_logged=False,
        raw_response_logged=False, redacted_prompt_hash="h",
        provider_response_hash="", provider_response_redacted_summary="",
        candidate_like_output_available=False, patch_apply_invoked=False,
        runtime_behavior_changed=False, solved_claim=False, claim_eligible=False,
        public_claim_allowed=False, production_ready=False,
        p2_hash_truth_required=True, p2_anchor_truth_required=True,
        p4_verifier_required=True, p4_claim_gate_required=True,
        receipt_complete=True, blocked_reasons=[],
    )
    result = validate_p8_post_smoke(receipt)
    assert result.smoke_valid is False


# ============================================================
# B6-4: network_call_count>1 rollback
# ============================================================


def test_network_call_count_gt1_rollback():
    receipt = _valid_receipt()
    d = {
        "receipt_version": "1.0", "smoke_id": "test", "approval_artifact_ref": "",
        "preflight_ref": "", "provider_kind": "openai", "model_name": "gpt-4o-mini",
        "network_call_attempted": True, "network_call_completed": True,
        "network_call_count": 2, "timed_out": False, "timeout_seconds": 15,
        "cost_budget_usd": 0.50, "estimated_cost_usd": 0.001, "cost_budget_exceeded": False,
        "retry_attempted": False, "streaming_used": False, "tool_call_used": False,
        "api_key_used": False, "api_key_logged": False, "raw_prompt_logged": False,
        "raw_response_logged": False, "redacted_prompt_hash": "h",
        "provider_response_hash": "h", "provider_response_redacted_summary": "",
        "candidate_like_output_available": True, "patch_apply_invoked": False,
        "runtime_behavior_changed": False, "solved_claim": False, "claim_eligible": False,
        "public_claim_allowed": False, "production_ready": False,
        "p2_hash_truth_required": True, "p2_anchor_truth_required": True,
        "p4_verifier_required": True, "p4_claim_gate_required": True,
        "receipt_complete": True, "blocked_reasons": [],
    }
    from nexus.services.local_heal.p8_one_smoke_runner import P8OneSmokeReceipt
    receipt = P8OneSmokeReceipt(**d)
    result = validate_p8_post_smoke(receipt)
    assert result.rollback_required is True
    assert "network_call_count>1" in result.blocked_reasons


# ============================================================
# B6-5: retry_attempted=true rollback
# ============================================================


def test_retry_attempted_rollback():
    from nexus.services.local_heal.p8_one_smoke_runner import P8OneSmokeReceipt
    receipt = P8OneSmokeReceipt(
        receipt_version="1.0", smoke_id="test", approval_artifact_ref="",
        preflight_ref="", provider_kind="openai", model_name="gpt-4o-mini",
        network_call_attempted=True, network_call_completed=True,
        network_call_count=1, timed_out=False, timeout_seconds=15,
        cost_budget_usd=0.50, estimated_cost_usd=0.001, cost_budget_exceeded=False,
        retry_attempted=True, streaming_used=False, tool_call_used=False,
        api_key_used=False, api_key_logged=False, raw_prompt_logged=False,
        raw_response_logged=False, redacted_prompt_hash="h",
        provider_response_hash="h", provider_response_redacted_summary="",
        candidate_like_output_available=True, patch_apply_invoked=False,
        runtime_behavior_changed=False, solved_claim=False, claim_eligible=False,
        public_claim_allowed=False, production_ready=False,
        p2_hash_truth_required=True, p2_anchor_truth_required=True,
        p4_verifier_required=True, p4_claim_gate_required=True,
        receipt_complete=True, blocked_reasons=[],
    )
    result = validate_p8_post_smoke(receipt)
    assert result.rollback_required is True
    assert "retry_attempted" in result.blocked_reasons


# ============================================================
# B6-6: patch_apply_invoked=true rollback
# ============================================================


def test_patch_apply_rollback():
    from nexus.services.local_heal.p8_one_smoke_runner import P8OneSmokeReceipt
    receipt = P8OneSmokeReceipt(
        receipt_version="1.0", smoke_id="test", approval_artifact_ref="",
        preflight_ref="", provider_kind="openai", model_name="gpt-4o-mini",
        network_call_attempted=True, network_call_completed=True,
        network_call_count=1, timed_out=False, timeout_seconds=15,
        cost_budget_usd=0.50, estimated_cost_usd=0.001, cost_budget_exceeded=False,
        retry_attempted=False, streaming_used=False, tool_call_used=False,
        api_key_used=False, api_key_logged=False, raw_prompt_logged=False,
        raw_response_logged=False, redacted_prompt_hash="h",
        provider_response_hash="h", provider_response_redacted_summary="",
        candidate_like_output_available=True, patch_apply_invoked=True,
        runtime_behavior_changed=False, solved_claim=False, claim_eligible=False,
        public_claim_allowed=False, production_ready=False,
        p2_hash_truth_required=True, p2_anchor_truth_required=True,
        p4_verifier_required=True, p4_claim_gate_required=True,
        receipt_complete=True, blocked_reasons=[],
    )
    result = validate_p8_post_smoke(receipt)
    assert result.rollback_required is True
    assert "patch_apply_invoked" in result.blocked_reasons


# ============================================================
# B6-7: runtime_behavior_changed=true rollback
# ============================================================


def test_runtime_behavior_rollback():
    from nexus.services.local_heal.p8_one_smoke_runner import P8OneSmokeReceipt
    receipt = P8OneSmokeReceipt(
        receipt_version="1.0", smoke_id="test", approval_artifact_ref="",
        preflight_ref="", provider_kind="openai", model_name="gpt-4o-mini",
        network_call_attempted=True, network_call_completed=True,
        network_call_count=1, timed_out=False, timeout_seconds=15,
        cost_budget_usd=0.50, estimated_cost_usd=0.001, cost_budget_exceeded=False,
        retry_attempted=False, streaming_used=False, tool_call_used=False,
        api_key_used=False, api_key_logged=False, raw_prompt_logged=False,
        raw_response_logged=False, redacted_prompt_hash="h",
        provider_response_hash="h", provider_response_redacted_summary="",
        candidate_like_output_available=True, patch_apply_invoked=False,
        runtime_behavior_changed=True, solved_claim=False, claim_eligible=False,
        public_claim_allowed=False, production_ready=False,
        p2_hash_truth_required=True, p2_anchor_truth_required=True,
        p4_verifier_required=True, p4_claim_gate_required=True,
        receipt_complete=True, blocked_reasons=[],
    )
    result = validate_p8_post_smoke(receipt)
    assert result.rollback_required is True
    assert "runtime_behavior_changed" in result.blocked_reasons


# ============================================================
# B6-8: solved_claim=true rollback
# ============================================================


def test_solved_claim_rollback():
    from nexus.services.local_heal.p8_one_smoke_runner import P8OneSmokeReceipt
    receipt = P8OneSmokeReceipt(
        receipt_version="1.0", smoke_id="test", approval_artifact_ref="",
        preflight_ref="", provider_kind="openai", model_name="gpt-4o-mini",
        network_call_attempted=True, network_call_completed=True,
        network_call_count=1, timed_out=False, timeout_seconds=15,
        cost_budget_usd=0.50, estimated_cost_usd=0.001, cost_budget_exceeded=False,
        retry_attempted=False, streaming_used=False, tool_call_used=False,
        api_key_used=False, api_key_logged=False, raw_prompt_logged=False,
        raw_response_logged=False, redacted_prompt_hash="h",
        provider_response_hash="h", provider_response_redacted_summary="",
        candidate_like_output_available=True, patch_apply_invoked=False,
        runtime_behavior_changed=False, solved_claim=True, claim_eligible=False,
        public_claim_allowed=False, production_ready=False,
        p2_hash_truth_required=True, p2_anchor_truth_required=True,
        p4_verifier_required=True, p4_claim_gate_required=True,
        receipt_complete=True, blocked_reasons=[],
    )
    result = validate_p8_post_smoke(receipt)
    assert result.rollback_required is True
    assert "solved_claim" in result.blocked_reasons


# ============================================================
# B6-9: public_claim_allowed=true rollback
# ============================================================


def test_public_claim_rollback():
    from nexus.services.local_heal.p8_one_smoke_runner import P8OneSmokeReceipt
    receipt = P8OneSmokeReceipt(
        receipt_version="1.0", smoke_id="test", approval_artifact_ref="",
        preflight_ref="", provider_kind="openai", model_name="gpt-4o-mini",
        network_call_attempted=True, network_call_completed=True,
        network_call_count=1, timed_out=False, timeout_seconds=15,
        cost_budget_usd=0.50, estimated_cost_usd=0.001, cost_budget_exceeded=False,
        retry_attempted=False, streaming_used=False, tool_call_used=False,
        api_key_used=False, api_key_logged=False, raw_prompt_logged=False,
        raw_response_logged=False, redacted_prompt_hash="h",
        provider_response_hash="h", provider_response_redacted_summary="",
        candidate_like_output_available=True, patch_apply_invoked=False,
        runtime_behavior_changed=False, solved_claim=False, claim_eligible=False,
        public_claim_allowed=True, production_ready=False,
        p2_hash_truth_required=True, p2_anchor_truth_required=True,
        p4_verifier_required=True, p4_claim_gate_required=True,
        receipt_complete=True, blocked_reasons=[],
    )
    result = validate_p8_post_smoke(receipt)
    assert result.rollback_required is True
    assert "public_claim_allowed" in result.blocked_reasons


# ============================================================
# B6-10: production_ready=true rollback
# ============================================================


def test_production_ready_rollback():
    from nexus.services.local_heal.p8_one_smoke_runner import P8OneSmokeReceipt
    receipt = P8OneSmokeReceipt(
        receipt_version="1.0", smoke_id="test", approval_artifact_ref="",
        preflight_ref="", provider_kind="openai", model_name="gpt-4o-mini",
        network_call_attempted=True, network_call_completed=True,
        network_call_count=1, timed_out=False, timeout_seconds=15,
        cost_budget_usd=0.50, estimated_cost_usd=0.001, cost_budget_exceeded=False,
        retry_attempted=False, streaming_used=False, tool_call_used=False,
        api_key_used=False, api_key_logged=False, raw_prompt_logged=False,
        raw_response_logged=False, redacted_prompt_hash="h",
        provider_response_hash="h", provider_response_redacted_summary="",
        candidate_like_output_available=True, patch_apply_invoked=False,
        runtime_behavior_changed=False, solved_claim=False, claim_eligible=False,
        public_claim_allowed=False, production_ready=True,
        p2_hash_truth_required=True, p2_anchor_truth_required=True,
        p4_verifier_required=True, p4_claim_gate_required=True,
        receipt_complete=True, blocked_reasons=[],
    )
    result = validate_p8_post_smoke(receipt)
    assert result.rollback_required is True
    assert "production_ready" in result.blocked_reasons


# ============================================================
# B6-11: missing P2/P4 gates rollback
# ============================================================


def test_missing_p2_p4_gates_rollback():
    from nexus.services.local_heal.p8_one_smoke_runner import P8OneSmokeReceipt
    receipt = P8OneSmokeReceipt(
        receipt_version="1.0", smoke_id="test", approval_artifact_ref="",
        preflight_ref="", provider_kind="openai", model_name="gpt-4o-mini",
        network_call_attempted=True, network_call_completed=True,
        network_call_count=1, timed_out=False, timeout_seconds=15,
        cost_budget_usd=0.50, estimated_cost_usd=0.001, cost_budget_exceeded=False,
        retry_attempted=False, streaming_used=False, tool_call_used=False,
        api_key_used=False, api_key_logged=False, raw_prompt_logged=False,
        raw_response_logged=False, redacted_prompt_hash="h",
        provider_response_hash="h", provider_response_redacted_summary="",
        candidate_like_output_available=True, patch_apply_invoked=False,
        runtime_behavior_changed=False, solved_claim=False, claim_eligible=False,
        public_claim_allowed=False, production_ready=False,
        p2_hash_truth_required=False, p2_anchor_truth_required=True,
        p4_verifier_required=True, p4_claim_gate_required=True,
        receipt_complete=True, blocked_reasons=[],
    )
    result = validate_p8_post_smoke(receipt)
    assert result.rollback_required is True
    assert "p2_hash_truth_not_required" in result.blocked_reasons


# ============================================================
# B6-12: JSON serialization works
# ============================================================


def test_json_serializable():
    receipt = _valid_receipt()
    result = validate_p8_post_smoke(receipt)
    d = p8_post_smoke_to_dict(result)
    assert isinstance(json.dumps(d), str)
