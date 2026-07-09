from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p8_one_smoke_runner import (
    P8OneSmokeReceiptV2,
    execute_p8_one_smoke_v2,
    write_p8_smoke_receipt_v2_artifact,
    p8_smoke_receipt_v2_to_dict,
)


def _valid_v2_receipt():
    return execute_p8_one_smoke_v2(
        final_preflight_passed=True,
        network_execution_allowed=True,
        approval_artifact_ref="artifacts/effect_reports/p8_human_approval_artifact_v0.json",
        preflight_ref="docs/reports/p8_e1_final_preflight_revalidation_v0.md",
        lock_ref="artifacts/effect_reports/p8_one_call_lock_v0.json",
        provider_kind="openai",
        model_name="gpt-4o-mini",
        timeout_seconds=15,
        cost_budget_usd=0.50,
        redacted_prompt_hash="abc123",
        dry_run=True,
    )


# ============================================================
# E3-1: completed smoke receipt exists if executed
# ============================================================


def test_completed_receipt_exists():
    receipt = _valid_v2_receipt()
    assert receipt.receipt_complete is True
    assert receipt.network_call_attempted is True
    assert receipt.network_call_count == 1


# ============================================================
# E3-2: receipt reloads
# ============================================================


def test_receipt_reloads():
    receipt = _valid_v2_receipt()
    d = p8_smoke_receipt_v2_to_dict(receipt)
    assert isinstance(json.dumps(d), str)


# ============================================================
# E3-3: network_call_count==1 if executed
# ============================================================


def test_network_call_count_1():
    receipt = _valid_v2_receipt()
    assert receipt.network_call_count == 1


# ============================================================
# E3-4: network_call_count==0 if blocked
# ============================================================


def test_network_call_count_0_if_blocked():
    receipt = execute_p8_one_smoke_v2(
        final_preflight_passed=False,
        network_execution_allowed=False,
    )
    assert receipt.network_call_count == 0
    assert receipt.network_call_attempted is False


# ============================================================
# E3-5: retry_attempted=false
# ============================================================


def test_retry_attempted_false():
    receipt = _valid_v2_receipt()
    assert receipt.retry_attempted is False


# ============================================================
# E3-6: streaming_used=false
# ============================================================


def test_streaming_used_false():
    receipt = _valid_v2_receipt()
    assert receipt.streaming_used is False


# ============================================================
# E3-7: tool_call_used=false
# ============================================================


def test_tool_call_used_false():
    receipt = _valid_v2_receipt()
    assert receipt.tool_call_used is False


# ============================================================
# E3-8: api_key_logged=false
# ============================================================


def test_api_key_logged_false():
    receipt = _valid_v2_receipt()
    assert receipt.api_key_logged is False


# ============================================================
# E3-9: raw_prompt_logged=false
# ============================================================


def test_raw_prompt_logged_false():
    receipt = _valid_v2_receipt()
    assert receipt.raw_prompt_logged is False


# ============================================================
# E3-10: raw_response_logged=false
# ============================================================


def test_raw_response_logged_false():
    receipt = _valid_v2_receipt()
    assert receipt.raw_response_logged is False


# ============================================================
# E3-11: patch_apply_invoked=false
# ============================================================


def test_patch_apply_invoked_false():
    receipt = _valid_v2_receipt()
    assert receipt.patch_apply_invoked is False


# ============================================================
# E3-12: p2_apply_invoked=false
# ============================================================


def test_p2_apply_invoked_false():
    receipt = _valid_v2_receipt()
    assert receipt.p2_apply_invoked is False


# ============================================================
# E3-13: p4_verifier_invoked=false
# ============================================================


def test_p4_verifier_invoked_false():
    receipt = _valid_v2_receipt()
    assert receipt.p4_verifier_invoked is False


# ============================================================
# E3-14: runtime_behavior_changed=false
# ============================================================


def test_runtime_behavior_changed_false():
    receipt = _valid_v2_receipt()
    assert receipt.runtime_behavior_changed is False


# ============================================================
# E3-15: solved_claim=false
# ============================================================


def test_solved_claim_false():
    receipt = _valid_v2_receipt()
    assert receipt.solved_claim is False


# ============================================================
# E3-16: claim_eligible=false
# ============================================================


def test_claim_eligible_false():
    receipt = _valid_v2_receipt()
    assert receipt.claim_eligible is False


# ============================================================
# E3-17: public_claim_allowed=false
# ============================================================


def test_public_claim_allowed_false():
    receipt = _valid_v2_receipt()
    assert receipt.public_claim_allowed is False


# ============================================================
# E3-18: production_ready=false
# ============================================================


def test_production_ready_false():
    receipt = _valid_v2_receipt()
    assert receipt.production_ready is False


# ============================================================
# E3-19: P2/P4 gates true
# ============================================================


def test_p2_p4_gates_true():
    receipt = _valid_v2_receipt()
    assert receipt.p2_hash_truth_required is True
    assert receipt.p2_anchor_truth_required is True
    assert receipt.p4_verifier_required is True
    assert receipt.p4_claim_gate_required is True


# ============================================================
# E3-20: JSON serialization works
# ============================================================


def test_json_serializable():
    receipt = _valid_v2_receipt()
    d = p8_smoke_receipt_v2_to_dict(receipt)
    assert isinstance(json.dumps(d), str)
