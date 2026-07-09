from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path
from nexus.services.local_heal.p8_human_approval_intake import (
    P8HumanApprovalIntakeResult,
    validate_p8_human_approval,
    p8_human_approval_intake_to_dict,
)


def _valid_approval():
    return {
        "approval_version": "1.0",
        "human_approved": True,
        "approver": "james.chen",
        "approval_timestamp_utc": "2025-07-10T00:00:00Z",
        "approval_scope": "P8_ONE_NETWORK_SMOKE_NO_APPLY",
        "provider_kind": "openai",
        "model_name": "gpt-4o-mini",
        "max_network_calls": 1,
        "max_cost_usd": 0.50,
        "timeout_seconds": 15,
        "synthetic_prompt_only": True,
        "prompt_redaction_required": True,
        "api_key_logging_allowed": False,
        "raw_prompt_logging_allowed": False,
        "raw_response_logging_allowed": False,
        "retry_allowed": False,
        "streaming_allowed": False,
        "tool_call_allowed": False,
        "patch_apply_allowed": False,
        "runtime_behavior_change_allowed": False,
        "solved_claim_allowed": False,
        "claim_eligible_allowed": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "p2_hash_truth_required": True,
        "p2_anchor_truth_required": True,
        "p4_verifier_required": True,
        "p4_claim_gate_required": True,
    }


# ============================================================
# B1-1: missing artifact blocks
# ============================================================


def test_missing_artifact_blocks():
    result = validate_p8_human_approval("/nonexistent/path.json")
    assert result.approval_valid is False
    assert "approval_artifact_missing" in result.blocked_reasons


# ============================================================
# B1-2: valid artifact passes
# ============================================================


def test_valid_artifact_passes():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_valid_approval(), f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is True
    Path(path).unlink()


# ============================================================
# B1-3: human_approved=false blocks
# ============================================================


def test_human_approved_false_blocks():
    artifact = _valid_approval()
    artifact["human_approved"] = False
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    assert "human_approved_false" in result.blocked_reasons
    Path(path).unlink()


# ============================================================
# B1-4: missing approver blocks
# ============================================================


def test_missing_approver_blocks():
    artifact = _valid_approval()
    artifact["approver"] = ""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    assert "approver_missing" in result.blocked_reasons
    Path(path).unlink()


# ============================================================
# B1-5: wrong approval_scope blocks
# ============================================================


def test_wrong_scope_blocks():
    artifact = _valid_approval()
    artifact["approval_scope"] = "WRONG_SCOPE"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-6: max_network_calls>1 blocks
# ============================================================


def test_max_network_calls_too_high_blocks():
    artifact = _valid_approval()
    artifact["max_network_calls"] = 5
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-7: max_cost_usd>1.00 blocks
# ============================================================


def test_max_cost_too_high_blocks():
    artifact = _valid_approval()
    artifact["max_cost_usd"] = 5.00
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-8: timeout_seconds>30 blocks
# ============================================================


def test_timeout_too_high_blocks():
    artifact = _valid_approval()
    artifact["timeout_seconds"] = 60
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-9: api_key_logging_allowed=true blocks
# ============================================================


def test_api_key_logging_blocks():
    artifact = _valid_approval()
    artifact["api_key_logging_allowed"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-10: raw_prompt_logging_allowed=true blocks
# ============================================================


def test_raw_prompt_logging_blocks():
    artifact = _valid_approval()
    artifact["raw_prompt_logging_allowed"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-11: raw_response_logging_allowed=true blocks
# ============================================================


def test_raw_response_logging_blocks():
    artifact = _valid_approval()
    artifact["raw_response_logging_allowed"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-12: retry_allowed=true blocks
# ============================================================


def test_retry_allowed_blocks():
    artifact = _valid_approval()
    artifact["retry_allowed"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-13: patch_apply_allowed=true blocks
# ============================================================


def test_patch_apply_allowed_blocks():
    artifact = _valid_approval()
    artifact["patch_apply_allowed"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-14: solved_claim_allowed=true blocks
# ============================================================


def test_solved_claim_allowed_blocks():
    artifact = _valid_approval()
    artifact["solved_claim_allowed"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-15: public_claim_allowed=true blocks
# ============================================================


def test_public_claim_allowed_blocks():
    artifact = _valid_approval()
    artifact["public_claim_allowed"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-16: production_ready=true blocks
# ============================================================


def test_production_ready_blocks():
    artifact = _valid_approval()
    artifact["production_ready"] = True
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-17: missing P2/P4 gates block
# ============================================================


def test_missing_p2_p4_gates_block():
    artifact = _valid_approval()
    del artifact["p2_hash_truth_required"]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    assert result.approval_valid is False
    Path(path).unlink()


# ============================================================
# B1-18: JSON serialization works
# ============================================================


def test_json_serializable():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_valid_approval(), f)
        path = f.name
    result = validate_p8_human_approval(path)
    d = p8_human_approval_intake_to_dict(result)
    assert isinstance(json.dumps(d), str)
    Path(path).unlink()
