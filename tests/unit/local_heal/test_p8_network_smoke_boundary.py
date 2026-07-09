from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path
from nexus.services.local_heal.p8_human_approval_intake import validate_p8_human_approval
from nexus.services.local_heal.p8_network_smoke_boundary import (
    P8NetworkSmokeBoundaryResult,
    compute_p8_network_smoke_boundary,
    p8_boundary_to_dict,
)


def _valid_approval_result():
    artifact = {
        "approval_version": "1.0", "human_approved": True, "approver": "test",
        "approval_timestamp_utc": "2025-07-10T00:00:00Z",
        "approval_scope": "P8_ONE_NETWORK_SMOKE_NO_APPLY",
        "provider_kind": "openai", "model_name": "gpt-4o-mini",
        "max_network_calls": 1, "max_cost_usd": 0.50, "timeout_seconds": 15,
        "synthetic_prompt_only": True, "prompt_redaction_required": True,
        "api_key_logging_allowed": False, "raw_prompt_logging_allowed": False,
        "raw_response_logging_allowed": False, "retry_allowed": False,
        "streaming_allowed": False, "tool_call_allowed": False,
        "patch_apply_allowed": False, "runtime_behavior_change_allowed": False,
        "solved_claim_allowed": False, "claim_eligible_allowed": False,
        "public_claim_allowed": False, "production_ready": False,
        "p2_hash_truth_required": True, "p2_anchor_truth_required": True,
        "p4_verifier_required": True, "p4_claim_gate_required": True,
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        path = f.name
    result = validate_p8_human_approval(path)
    Path(path).unlink()
    return result


# ============================================================
# B2-1: valid approval boundary passes
# ============================================================


def test_valid_approval_boundary_passes():
    approval = _valid_approval_result()
    boundary = compute_p8_network_smoke_boundary(approval_result=approval)
    assert boundary.boundary_valid is True
    assert boundary.network_call_allowed is True


# ============================================================
# B2-2: invalid approval blocks
# ============================================================


def test_invalid_approval_blocks():
    boundary = compute_p8_network_smoke_boundary(approval_result=None)
    assert boundary.boundary_valid is False
    assert boundary.network_call_allowed is False


# ============================================================
# B2-3: p2_hash_truth_required=false blocks
# ============================================================


def test_p2_hash_truth_false_blocks():
    approval = _valid_approval_result()
    boundary = compute_p8_network_smoke_boundary(
        approval_result=approval, p2_hash_truth_required=False
    )
    assert boundary.boundary_valid is False
    assert "p2_hash_truth_missing" in boundary.blocked_reasons


# ============================================================
# B2-4: p2_anchor_truth_required=false blocks
# ============================================================


def test_p2_anchor_truth_false_blocks():
    approval = _valid_approval_result()
    boundary = compute_p8_network_smoke_boundary(
        approval_result=approval, p2_anchor_truth_required=False
    )
    assert boundary.boundary_valid is False
    assert "p2_anchor_truth_missing" in boundary.blocked_reasons


# ============================================================
# B2-5: p4_verifier_required=false blocks
# ============================================================


def test_p4_verifier_false_blocks():
    approval = _valid_approval_result()
    boundary = compute_p8_network_smoke_boundary(
        approval_result=approval, p4_verifier_required=False
    )
    assert boundary.boundary_valid is False
    assert "p4_verifier_missing" in boundary.blocked_reasons


# ============================================================
# B2-6: p4_claim_gate_required=false blocks
# ============================================================


def test_p4_claim_gate_false_blocks():
    approval = _valid_approval_result()
    boundary = compute_p8_network_smoke_boundary(
        approval_result=approval, p4_claim_gate_required=False
    )
    assert boundary.boundary_valid is False
    assert "p4_claim_gate_missing" in boundary.blocked_reasons


# ============================================================
# B2-7: pre_existing network_calls_attempted>0 blocks
# ============================================================


def test_pre_existing_calls_blocks():
    approval = _valid_approval_result()
    boundary = compute_p8_network_smoke_boundary(
        approval_result=approval, network_calls_attempted=1
    )
    assert boundary.boundary_valid is False
    assert "pre_existing_network_calls" in boundary.blocked_reasons


# ============================================================
# B2-8: runtime_behavior_change_allowed=false always
# ============================================================


def test_runtime_behavior_always_false():
    approval = _valid_approval_result()
    boundary = compute_p8_network_smoke_boundary(approval_result=approval)
    assert boundary.runtime_behavior_change_allowed is False


# ============================================================
# B2-9: public_claim_allowed=false always
# ============================================================


def test_public_claim_always_false():
    approval = _valid_approval_result()
    boundary = compute_p8_network_smoke_boundary(approval_result=approval)
    assert boundary.public_claim_allowed is False


# ============================================================
# B2-10: production_ready=false always
# ============================================================


def test_production_ready_always_false():
    approval = _valid_approval_result()
    boundary = compute_p8_network_smoke_boundary(approval_result=approval)
    assert boundary.production_ready is False


# ============================================================
# B2-11: JSON serialization works
# ============================================================


def test_json_serializable():
    approval = _valid_approval_result()
    boundary = compute_p8_network_smoke_boundary(approval_result=approval)
    d = p8_boundary_to_dict(boundary)
    assert isinstance(json.dumps(d), str)
