from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_dry_run_schema import (
    P3DryRunSchemaResult,
    REQUIRED_P3_DRY_RUN_RECEIPT_FIELDS,
    validate_p3_dry_run_schema,
    p3_dry_run_schema_to_dict,
)


def _valid_receipt():
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
# P3-M1-1: complete valid receipt passes schema
# ============================================================


def test_complete_valid_receipt_passes():
    result = validate_p3_dry_run_schema(_valid_receipt())
    assert result.schema_passed is True


# ============================================================
# P3-M1-2: missing provider_invoked fails
# ============================================================


def test_missing_provider_invoked_fails():
    receipt = _valid_receipt()
    del receipt["p3_l_provider_invoked"]
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert "p3_l_provider_invoked" in result.missing_fields


# ============================================================
# P3-M1-3: missing public_claim_allowed fails
# ============================================================


def test_missing_public_claim_allowed_fails():
    receipt = _valid_receipt()
    del receipt["p3_l_public_claim_allowed"]
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert "p3_l_public_claim_allowed" in result.missing_fields


# ============================================================
# P3-M1-4: missing full_verifier_required fails
# ============================================================


def test_missing_full_verifier_required_fails():
    receipt = _valid_receipt()
    del receipt["p3_l_full_verifier_required"]
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert "p3_l_full_verifier_required" in result.missing_fields


# ============================================================
# P3-M1-5: wrong boolean type fails
# ============================================================


def test_wrong_boolean_type_fails():
    receipt = _valid_receipt()
    receipt["p3_l_provider_invoked"] = "not_bool"
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_provider_invoked" in e for e in result.type_errors)


# ============================================================
# P3-M1-6: blocked_reasons non-list fails
# ============================================================


def test_blocked_reasons_non_list_fails():
    receipt = _valid_receipt()
    receipt["p3_l_blocked_reasons"] = "not_a_list"
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_blocked_reasons" in e for e in result.type_errors)


# ============================================================
# P3-M1-7: authority unknown fails
# ============================================================


def test_authority_unknown_fails():
    receipt = _valid_receipt()
    receipt["p3_l_authority"] = "unknown_authority"
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_authority" in e for e in result.value_errors)


# ============================================================
# P3-M1-8: dry_run_only=false fails
# ============================================================


def test_dry_run_only_false_fails():
    receipt = _valid_receipt()
    receipt["p3_l_dry_run_only"] = False
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_dry_run_only" in e for e in result.value_errors)


# ============================================================
# P3-M1-9: provider_invoked=true fails
# ============================================================


def test_provider_invoked_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_provider_invoked"] = True
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_provider_invoked" in e for e in result.value_errors)


# ============================================================
# P3-M1-10: network_invoked=true fails
# ============================================================


def test_network_invoked_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_network_invoked"] = True
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_network_invoked" in e for e in result.value_errors)


# ============================================================
# P3-M1-11: api_key_used=true fails
# ============================================================


def test_api_key_used_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_api_key_used"] = True
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_api_key_used" in e for e in result.value_errors)


# ============================================================
# P3-M1-12: patch_apply_invoked=true fails
# ============================================================


def test_patch_apply_invoked_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_patch_apply_invoked"] = True
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_patch_apply_invoked" in e for e in result.value_errors)


# ============================================================
# P3-M1-13: runtime_behavior_changed=true fails
# ============================================================


def test_runtime_behavior_changed_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_runtime_behavior_changed"] = True
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_runtime_behavior_changed" in e for e in result.value_errors)


# ============================================================
# P3-M1-14: claim_eligible=true fails
# ============================================================


def test_claim_eligible_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_claim_eligible"] = True
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_claim_eligible" in e for e in result.value_errors)


# ============================================================
# P3-M1-15: public_claim_allowed=true fails
# ============================================================


def test_public_claim_allowed_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_public_claim_allowed"] = True
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_public_claim_allowed" in e for e in result.value_errors)


# ============================================================
# P3-M1-16: production_ready=true fails
# ============================================================


def test_production_ready_true_fails():
    receipt = _valid_receipt()
    receipt["p3_l_production_ready"] = True
    result = validate_p3_dry_run_schema(receipt)
    assert result.schema_passed is False
    assert any("p3_l_production_ready" in e for e in result.value_errors)


# ============================================================
# P3-M1-17: invariant gate now fails on missing fields
# ============================================================


def test_invariant_gate_fails_on_missing_fields():
    from nexus.services.local_heal.p3_dry_run_invariants import validate_p3_dry_run_receipt
    receipt = _valid_receipt()
    del receipt["p3_l_provider_invoked"]
    result = validate_p3_dry_run_receipt(receipt)
    assert result.invariant_passed is False
    assert result.schema_passed is False


# ============================================================
# P3-M1-18: JSON serialization works
# ============================================================


def test_json_serializable():
    result = validate_p3_dry_run_schema(_valid_receipt())
    d = p3_dry_run_schema_to_dict(result)
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
