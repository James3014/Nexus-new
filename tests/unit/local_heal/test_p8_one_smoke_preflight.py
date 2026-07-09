from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p8_one_smoke_preflight import (
    P8OneSmokePreflightResult,
    compute_p8_one_smoke_preflight,
    p8_preflight_to_dict,
)


# ============================================================
# B4-1: valid preflight passes
# ============================================================


def test_valid_preflight_passes():
    result = compute_p8_one_smoke_preflight(
        approval_valid=True, boundary_valid=True,
        redaction_passed=True, prompt_capsule_valid=True,
        p7_seal_present=True, max_network_calls=1,
    )
    assert result.preflight_passed is True


# ============================================================
# B4-2: missing approval blocks
# ============================================================


def test_missing_approval_blocks():
    result = compute_p8_one_smoke_preflight(approval_valid=False)
    assert result.preflight_passed is False
    assert "approval_invalid" in result.blocked_reasons


# ============================================================
# B4-3: invalid boundary blocks
# ============================================================


def test_invalid_boundary_blocks():
    result = compute_p8_one_smoke_preflight(
        approval_valid=True, boundary_valid=False
    )
    assert result.preflight_passed is False
    assert "boundary_invalid" in result.blocked_reasons


# ============================================================
# B4-4: redaction failed blocks
# ============================================================


def test_redaction_failed_blocks():
    result = compute_p8_one_smoke_preflight(
        approval_valid=True, boundary_valid=True, redaction_passed=False
    )
    assert result.preflight_passed is False
    assert "redaction_failed" in result.blocked_reasons


# ============================================================
# B4-5: prompt capsule invalid blocks
# ============================================================


def test_prompt_capsule_invalid_blocks():
    result = compute_p8_one_smoke_preflight(
        approval_valid=True, boundary_valid=True,
        redaction_passed=True, prompt_capsule_valid=False,
    )
    assert result.preflight_passed is False
    assert "prompt_capsule_invalid" in result.blocked_reasons


# ============================================================
# B4-6: missing P7 seal blocks
# ============================================================


def test_missing_p7_seal_blocks():
    result = compute_p8_one_smoke_preflight(
        approval_valid=True, boundary_valid=True,
        redaction_passed=True, prompt_capsule_valid=True,
        p7_seal_present=False,
    )
    assert result.preflight_passed is False
    assert "p7_seal_missing" in result.blocked_reasons


# ============================================================
# B4-7: max_network_calls>1 blocks
# ============================================================


def test_max_network_calls_too_high_blocks():
    result = compute_p8_one_smoke_preflight(
        approval_valid=True, boundary_valid=True,
        redaction_passed=True, prompt_capsule_valid=True,
        p7_seal_present=True, max_network_calls=5,
    )
    assert result.preflight_passed is False


# ============================================================
# B4-8: network_calls_attempted>0 blocks
# ============================================================


def test_network_calls_already_attempted_blocks():
    result = compute_p8_one_smoke_preflight(
        approval_valid=True, boundary_valid=True,
        redaction_passed=True, prompt_capsule_valid=True,
        p7_seal_present=True, max_network_calls=1,
        network_calls_attempted=1,
    )
    assert result.preflight_passed is False
    assert "network_calls_already_attempted" in result.blocked_reasons


# ============================================================
# B4-9: missing P2/P4 gates block
# ============================================================


def test_missing_p2_p4_gates_block():
    result = compute_p8_one_smoke_preflight(
        approval_valid=True, boundary_valid=True,
        redaction_passed=True, prompt_capsule_valid=True,
        p7_seal_present=True, max_network_calls=1,
        p2_hash_truth_required=False,
    )
    assert result.preflight_passed is False
    assert "p2_hash_truth_missing" in result.blocked_reasons


# ============================================================
# B4-10: JSON serialization works
# ============================================================


def test_json_serializable():
    result = compute_p8_one_smoke_preflight(
        approval_valid=True, boundary_valid=True,
        redaction_passed=True, prompt_capsule_valid=True,
        p7_seal_present=True, max_network_calls=1,
    )
    d = p8_preflight_to_dict(result)
    assert isinstance(json.dumps(d), str)
