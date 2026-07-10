from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_dry_run_invariants import (
    P3DryRunInvariantResult,
    validate_p3_dry_run_receipt,
    p3_dry_run_invariant_to_dict,
)
from nexus.services.local_heal.p3_dry_run_schema import REQUIRED_P3_DRY_RUN_RECEIPT_FIELDS


def _valid_receipt():
    """Full valid receipt with all required schema fields."""
    return {
        "p3_l_receipt_version": "1.0",
        "p3_l_enabled": True,
        "p3_l_authority": "shadow_only",
        "p3_l_runtime_state": "shadow_only",
        "p3_l_env_guard_present": False,
        "p3_l_dry_run_only": True,
        "p3_l_intended_topology": "cloud_with_local_assist",
        "p3_l_task_difficulty": "medium",
        "p3_l_provider_request_built": False,
        "p3_l_provider_invoked": False,
        "p3_l_network_invoked": False,
        "p3_l_api_key_used": False,
        "p3_l_local_model_invoked": False,
        "p3_l_patch_apply_invoked": False,
        "p3_l_runtime_behavior_changed": False,
        "p3_l_full_verifier_required": True,
        "p3_l_claim_gate_required": True,
        "p3_l_claim_eligible": False,
        "p3_l_public_claim_allowed": False,
        "p3_l_production_ready": False,
        "p3_l_blocked_reasons": [],
        "p3_l_receipt_complete": True,
    }


# ============================================================
# P3-L4-1: valid dry-run receipt passes
# ============================================================


def test_valid_receipt_passes():
    result = validate_p3_dry_run_receipt(_valid_receipt())
    assert result.invariant_passed is True


# ============================================================
# P3-L4-2: provider_invoked=true fails
# ============================================================


def test_provider_invoked_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_provider_invoked"] = True
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False


# ============================================================
# P3-L4-3: network_invoked=true fails
# ============================================================


def test_network_invoked_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_network_invoked"] = True
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False


# ============================================================
# P3-L4-4: api_key_used=true fails
# ============================================================


def test_api_key_used_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_api_key_used"] = True
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False


# ============================================================
# P3-L4-5: local_model_invoked=true fails
# ============================================================


def test_local_model_invoked_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_local_model_invoked"] = True
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False


# ============================================================
# P3-L4-6: patch_apply_invoked=true fails
# ============================================================


def test_patch_apply_invoked_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_patch_apply_invoked"] = True
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False


# ============================================================
# P3-L4-7: runtime_behavior_changed=true fails
# ============================================================


def test_runtime_behavior_changed_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_runtime_behavior_changed"] = True
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False


# ============================================================
# P3-L4-8: full_verifier_required=false fails
# ============================================================


def test_full_verifier_required_false_fails():
    receipt = _valid_receipt()
    receipt["p3_l_full_verifier_required"] = False
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False


# ============================================================
# P3-L4-9: claim_gate_required=false fails
# ============================================================


def test_claim_gate_required_false_fails():
    receipt = _valid_receipt()
    receipt["p3_l_claim_gate_required"] = False
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False


# ============================================================
# P3-L4-10: claim_eligible=true fails
# ============================================================


def test_claim_eligible_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_claim_eligible"] = True
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False


# ============================================================
# P3-L4-11: public_claim_allowed=true fails
# ============================================================


def test_public_claim_allowed_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_public_claim_allowed"] = True
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False


# ============================================================
# P3-L4-12: production_ready=true fails
# ============================================================


def test_production_ready_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_production_ready"] = True
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False


# ============================================================
# P3-L4-13: multiple violations all recorded
# ============================================================


def test_multiple_violations_recorded():
    receipt = _valid_receipt()
    receipt["p3_l_provider_invoked"] = True
    receipt["p3_l_network_invoked"] = True
    receipt["p3_l_public_claim_allowed"] = True
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False
    assert len(result.blocked_reasons) >= 3


# ============================================================
# P3-M1-17: invariant gate now fails on missing fields
# ============================================================


def test_invariant_gate_fails_on_missing_fields():
    receipt = _valid_receipt()
    del receipt["p3_l_provider_invoked"]
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False
    assert result.schema_passed is False


# ============================================================
# P3-L4-15: result JSON serializable
# ============================================================


def test_result_json_serializable():
    result = validate_p3_dry_run_receipt(_valid_receipt())
    d = p3_dry_run_invariant_to_dict(result)
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
