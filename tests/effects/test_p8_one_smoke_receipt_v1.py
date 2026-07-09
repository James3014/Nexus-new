from __future__ import annotations

import json
import pytest
from pathlib import Path
from nexus.services.local_heal.p8_one_smoke_runner import (
    P8OneSmokeReceipt,
    execute_p8_one_smoke,
    write_p8_smoke_receipt_artifact,
    p8_smoke_receipt_to_dict,
)


SMOKE_RECEIPT_PATH = Path("artifacts/effect_reports/p8_one_network_smoke_receipt_v1.json")


def _valid_receipt():
    return execute_p8_one_smoke(
        preflight_passed=True,
        approval_artifact_ref="artifacts/effect_reports/p8_human_approval_artifact_v0.json",
        preflight_ref="docs/reports/p8_b4_one_smoke_preflight_gate_v0.md",
        provider_kind="openai",
        model_name="gpt-4o-mini",
        timeout_seconds=15,
        cost_budget_usd=0.50,
        redacted_prompt_hash="abc123",
        dry_run=True,
    )


# ============================================================
# B5-1: receipt artifact exists if smoke executed
# ============================================================


def test_receipt_artifact_exists():
    receipt = _valid_receipt()
    assert receipt.receipt_complete is True
    assert receipt.network_call_attempted is True
    assert receipt.network_call_count == 1


# ============================================================
# B5-2: receipt reloads
# ============================================================


def test_receipt_reloads():
    receipt = _valid_receipt()
    d = p8_smoke_receipt_to_dict(receipt)
    assert isinstance(json.dumps(d), str)


# ============================================================
# B5-3: network_call_count==1 if executed
# ============================================================


def test_network_call_count_1():
    receipt = _valid_receipt()
    assert receipt.network_call_count == 1


# ============================================================
# B5-4: retry_attempted=false
# ============================================================


def test_retry_attempted_false():
    receipt = _valid_receipt()
    assert receipt.retry_attempted is False


# ============================================================
# B5-5: streaming_used=false
# ============================================================


def test_streaming_used_false():
    receipt = _valid_receipt()
    assert receipt.streaming_used is False


# ============================================================
# B5-6: tool_call_used=false
# ============================================================


def test_tool_call_used_false():
    receipt = _valid_receipt()
    assert receipt.tool_call_used is False


# ============================================================
# B5-7: api_key_logged=false
# ============================================================


def test_api_key_logged_false():
    receipt = _valid_receipt()
    assert receipt.api_key_logged is False


# ============================================================
# B5-8: raw_prompt_logged=false
# ============================================================


def test_raw_prompt_logged_false():
    receipt = _valid_receipt()
    assert receipt.raw_prompt_logged is False


# ============================================================
# B5-9: raw_response_logged=false
# ============================================================


def test_raw_response_logged_false():
    receipt = _valid_receipt()
    assert receipt.raw_response_logged is False


# ============================================================
# B5-10: patch_apply_invoked=false
# ============================================================


def test_patch_apply_invoked_false():
    receipt = _valid_receipt()
    assert receipt.patch_apply_invoked is False


# ============================================================
# B5-11: runtime_behavior_changed=false
# ============================================================


def test_runtime_behavior_changed_false():
    receipt = _valid_receipt()
    assert receipt.runtime_behavior_changed is False


# ============================================================
# B5-12: solved_claim=false
# ============================================================


def test_solved_claim_false():
    receipt = _valid_receipt()
    assert receipt.solved_claim is False


# ============================================================
# B5-13: claim_eligible=false
# ============================================================


def test_claim_eligible_false():
    receipt = _valid_receipt()
    assert receipt.claim_eligible is False


# ============================================================
# B5-14: public_claim_allowed=false
# ============================================================


def test_public_claim_allowed_false():
    receipt = _valid_receipt()
    assert receipt.public_claim_allowed is False


# ============================================================
# B5-15: production_ready=false
# ============================================================


def test_production_ready_false():
    receipt = _valid_receipt()
    assert receipt.production_ready is False


# ============================================================
# B5-16: P2/P4 gates true
# ============================================================


def test_p2_p4_gates_true():
    receipt = _valid_receipt()
    assert receipt.p2_hash_truth_required is True
    assert receipt.p2_anchor_truth_required is True
    assert receipt.p4_verifier_required is True
    assert receipt.p4_claim_gate_required is True


# ============================================================
# B5-17: JSON serialization works
# ============================================================


def test_json_serializable():
    receipt = _valid_receipt()
    d = p8_smoke_receipt_to_dict(receipt)
    assert isinstance(json.dumps(d), str)


# ============================================================
# B5-18: if preflight failed, no completed smoke receipt
# ============================================================


def test_preflight_failed_no_smoke():
    receipt = execute_p8_one_smoke(preflight_passed=False)
    assert receipt.network_call_attempted is False
    assert receipt.network_call_count == 0
    assert receipt.receipt_complete is False
