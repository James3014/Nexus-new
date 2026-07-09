from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path
from nexus.services.local_heal.p8_e_post_smoke_validator import (
    P8EPostSmokeValidationResult,
    validate_p8_e_post_smoke,
    p8_e_post_smoke_to_dict,
)


def _valid_receipt():
    return {
        "receipt_version": "2.0", "smoke_id": "smoke-test",
        "network_call_attempted": True, "network_call_completed": True,
        "network_call_count": 1, "timed_out": False, "retry_attempted": False,
        "streaming_used": False, "tool_call_used": False, "api_key_logged": False,
        "raw_prompt_logged": False, "raw_response_logged": False,
        "cost_budget_exceeded": False, "patch_apply_invoked": False,
        "p2_apply_invoked": False, "p4_verifier_invoked": False,
        "runtime_behavior_changed": False, "solved_claim": False,
        "claim_eligible": False, "public_claim_allowed": False,
        "production_ready": False, "p2_hash_truth_required": True,
        "p2_anchor_truth_required": True, "p4_verifier_required": True,
        "p4_claim_gate_required": True, "receipt_complete": True,
        "blocked_reasons": [],
    }


# ============================================================
# E4-1: valid executed receipt passes
# ============================================================


def test_valid_receipt_passes():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_valid_receipt(), f)
        path = f.name
    result = validate_p8_e_post_smoke(path)
    assert result.smoke_valid is True
    assert result.rollback_required is False
    Path(path).unlink()


# ============================================================
# E4-2: missing receipt blocks
# ============================================================


def test_missing_receipt_blocks():
    result = validate_p8_e_post_smoke("/nonexistent/path.json")
    assert result.smoke_valid is False
    assert "receipt_missing" in result.blocked_reasons


# ============================================================
# E4-3: network_call_count=0 blocks
# ============================================================


def test_network_call_count_0_blocks():
    receipt = _valid_receipt()
    receipt["network_call_count"] = 0
    receipt["network_call_attempted"] = False
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(receipt, f)
        path = f.name
    result = validate_p8_e_post_smoke(path)
    assert result.smoke_valid is False
    Path(path).unlink()


# ============================================================
# E4-4: network_call_count>1 rollback
# ============================================================


def test_network_call_count_gt1_rollback():
    receipt = _valid_receipt()
    receipt["network_call_count"] = 2
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(receipt, f)
        path = f.name
    result = validate_p8_e_post_smoke(path)
    assert result.rollback_required is True
    assert "network_call_count>1" in result.blocked_reasons
    Path(path).unlink()


# ============================================================
# E4-5: patch_apply_invoked=true rollback
# ============================================================


def test_patch_apply_rollback():
    receipt = _valid_receipt()
    receipt["patch_apply_invoked"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(receipt, f)
        path = f.name
    result = validate_p8_e_post_smoke(path)
    assert result.rollback_required is True
    assert "patch_apply_invoked" in result.blocked_reasons
    Path(path).unlink()


# ============================================================
# E4-6: runtime_behavior_changed=true rollback
# ============================================================


def test_runtime_behavior_rollback():
    receipt = _valid_receipt()
    receipt["runtime_behavior_changed"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(receipt, f)
        path = f.name
    result = validate_p8_e_post_smoke(path)
    assert result.rollback_required is True
    assert "runtime_behavior_changed" in result.blocked_reasons
    Path(path).unlink()


# ============================================================
# E4-7: public_claim_allowed=true rollback
# ============================================================


def test_public_claim_rollback():
    receipt = _valid_receipt()
    receipt["public_claim_allowed"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(receipt, f)
        path = f.name
    result = validate_p8_e_post_smoke(path)
    assert result.rollback_required is True
    assert "public_claim_allowed" in result.blocked_reasons
    Path(path).unlink()


# ============================================================
# E4-8: production_ready=true rollback
# ============================================================


def test_production_ready_rollback():
    receipt = _valid_receipt()
    receipt["production_ready"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(receipt, f)
        path = f.name
    result = validate_p8_e_post_smoke(path)
    assert result.rollback_required is True
    assert "production_ready" in result.blocked_reasons
    Path(path).unlink()


# ============================================================
# E4-9: missing P2/P4 gates rollback
# ============================================================


def test_missing_p2_p4_gates_rollback():
    receipt = _valid_receipt()
    receipt["p2_hash_truth_required"] = False
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(receipt, f)
        path = f.name
    result = validate_p8_e_post_smoke(path)
    assert result.rollback_required is True
    assert "p2_hash_truth_not_required" in result.blocked_reasons
    Path(path).unlink()


# ============================================================
# E4-10: JSON serialization works
# ============================================================


def test_json_serializable():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_valid_receipt(), f)
        path = f.name
    result = validate_p8_e_post_smoke(path)
    d = p8_e_post_smoke_to_dict(result)
    assert isinstance(json.dumps(d), str)
    Path(path).unlink()
