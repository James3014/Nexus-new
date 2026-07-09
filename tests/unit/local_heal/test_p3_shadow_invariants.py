from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_shadow_invariants import (
    P3ShadowInvariantResult,
    validate_p3_shadow_invariants,
)


# ============================================================
# P3-J2-1: Empty metadata passes as safe absent defaults
# ============================================================


def test_empty_metadata_passes():
    result = validate_p3_shadow_invariants({})
    assert result.invariant_passed is True
    assert result.blocked_reasons == []


# ============================================================
# P3-J2-2: Valid P3 shadow metadata passes
# ============================================================


def test_valid_shadow_metadata_passes():
    metadata = {
        "p3_shadow_authority": "shadow_only",
        "p3_cloud_call_invoked": False,
        "p3_local_model_call_invoked": False,
        "p3_patch_apply_invoked": False,
        "p3_runtime_behavior_changed": False,
        "p3_full_verifier_required": True,
        "p3_claim_gate_required": True,
        "p3_claim_eligible": False,
        "p3_public_claim_allowed": False,
    }
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is True


# ============================================================
# P3-J2-3: runtime_authoritative fails
# ============================================================


def test_runtime_authoritative_fails():
    metadata = {"p3_shadow_authority": "runtime_authoritative"}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert any("authority_violation" in r for r in result.blocked_reasons)


# ============================================================
# P3-J2-4: cloud_call_invoked=true fails
# ============================================================


def test_cloud_call_invoked_true_fails():
    metadata = {"p3_cloud_call_invoked": True}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert result.cloud_call_not_invoked is False


# ============================================================
# P3-J2-5: local_model_call_invoked=true fails
# ============================================================


def test_local_model_call_invoked_true_fails():
    metadata = {"p3_local_model_call_invoked": True}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert result.local_model_not_invoked is False


# ============================================================
# P3-J2-6: patch_apply_invoked=true fails
# ============================================================


def test_patch_apply_invoked_true_fails():
    metadata = {"p3_patch_apply_invoked": True}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert result.patch_apply_not_invoked is False


# ============================================================
# P3-J2-7: runtime_behavior_changed=true fails
# ============================================================


def test_runtime_behavior_changed_true_fails():
    metadata = {"p3_runtime_behavior_changed": True}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert result.runtime_behavior_unchanged is False


# ============================================================
# P3-J2-8: full_verifier_required=false fails
# ============================================================


def test_full_verifier_required_false_fails():
    metadata = {"p3_full_verifier_required": False}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert result.full_verifier_required is False


# ============================================================
# P3-J2-9: claim_gate_required=false fails
# ============================================================


def test_claim_gate_required_false_fails():
    metadata = {"p3_claim_gate_required": False}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert result.claim_gate_required is False


# ============================================================
# P3-J2-10: claim_eligible=true fails
# ============================================================


def test_claim_eligible_true_fails():
    metadata = {"p3_claim_eligible": True}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert result.claim_not_eligible is False


# ============================================================
# P3-J2-11: public_claim_allowed=true fails
# ============================================================


def test_public_claim_allowed_true_fails():
    metadata = {"p3_public_claim_allowed": True}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert result.public_claim_not_allowed is False


# ============================================================
# P3-J2-12: solved=true fails
# ============================================================


def test_solved_true_fails():
    metadata = {"solved": True}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert result.solved_not_claimed is False


# ============================================================
# P3-J2-13: p5_promoted=true fails
# ============================================================


def test_p5_promoted_true_fails():
    metadata = {"p5_promoted": True}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert result.p5_not_promoted is False


# ============================================================
# P3-J2-14: p6_override=true fails
# ============================================================


def test_p6_override_true_fails():
    metadata = {"p6_override": True}
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert result.p6_not_overridden is False


# ============================================================
# P3-J2-15: Multiple violations are all recorded
# ============================================================


def test_multiple_violations_recorded():
    metadata = {
        "p3_cloud_call_invoked": True,
        "p3_runtime_behavior_changed": True,
        "p3_public_claim_allowed": True,
    }
    result = validate_p3_shadow_invariants(metadata)
    assert result.invariant_passed is False
    assert len(result.blocked_reasons) >= 3


# ============================================================
# P3-J2-16: Result is JSON serializable
# ============================================================


def test_result_json_serializable():
    result = validate_p3_shadow_invariants({"p3_shadow_authority": "shadow_only"})
    d = {
        "invariant_version": result.invariant_version,
        "invariant_passed": result.invariant_passed,
        "blocked_reasons": result.blocked_reasons,
    }
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
