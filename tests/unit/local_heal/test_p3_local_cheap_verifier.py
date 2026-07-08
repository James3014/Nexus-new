from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_local_cheap_verifier import (
    P3LocalCheapVerifierResult,
    compute_p3_cheap_verifier,
    p3_cheap_verifier_to_dict,
)


def _make_cloud_stub_with_candidate():
    return {
        "p3_cloud_stub_candidate_generated": True,
        "p3_cloud_stub_canonical_candidate_available": True,
        "p3_cloud_stub_candidate_raw_output_hash": "abc123",
        "p3_cloud_stub_blocked_reason": "",
    }


def _make_cloud_stub_without_candidate():
    return {
        "p3_cloud_stub_candidate_generated": False,
        "p3_cloud_stub_canonical_candidate_available": False,
        "p3_cloud_stub_candidate_raw_output_hash": "",
        "p3_cloud_stub_blocked_reason": "cloud_not_ready:missing_anchor",
    }


# ============================================================
# P3-D-1: Candidate available creates cheap_verifier_planned=true
# ============================================================


def test_candidate_available_plans_cheap_verifier():
    result = compute_p3_cheap_verifier(cloud_stub_metadata=_make_cloud_stub_with_candidate())
    assert result.cheap_verifier_planned is True
    assert result.cheap_verifier_result == "not_run_shadow_only"
    assert result.full_verifier_required is True


# ============================================================
# P3-D-2: Missing candidate creates cheap_verifier_planned=false
# ============================================================


def test_missing_candidate_blocks_cheap_verifier():
    result = compute_p3_cheap_verifier(cloud_stub_metadata=_make_cloud_stub_without_candidate())
    assert result.cheap_verifier_planned is False
    assert result.cheap_verifier_result == "not_applicable"
    assert "no_candidate_available" in result.reason


# ============================================================
# P3-D-3: cheap_verifier_invoked=false always
# ============================================================


def test_cheap_verifier_invoked_always_false():
    for has_candidate in (True, False):
        stub = _make_cloud_stub_with_candidate() if has_candidate else _make_cloud_stub_without_candidate()
        result = compute_p3_cheap_verifier(cloud_stub_metadata=stub)
        assert result.cheap_verifier_invoked is False


# ============================================================
# P3-D-4: full_verifier_required=true always
# ============================================================


def test_full_verifier_required_always_true():
    result = compute_p3_cheap_verifier(cloud_stub_metadata=_make_cloud_stub_with_candidate())
    assert result.full_verifier_required is True


# ============================================================
# P3-D-5: claim_gate_required=true always
# ============================================================


def test_claim_gate_required_always_true():
    result = compute_p3_cheap_verifier(cloud_stub_metadata=_make_cloud_stub_with_candidate())
    assert result.claim_gate_required is True


# ============================================================
# P3-D-6: solved_claim_allowed=false always
# ============================================================


def test_solved_claim_allowed_always_false():
    result = compute_p3_cheap_verifier(cloud_stub_metadata=_make_cloud_stub_with_candidate())
    assert result.solved_claim_allowed is False


# ============================================================
# P3-D-7: public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false():
    result = compute_p3_cheap_verifier(cloud_stub_metadata=_make_cloud_stub_with_candidate())
    assert result.public_claim_allowed is False


# ============================================================
# P3-D-8: runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false():
    result = compute_p3_cheap_verifier(cloud_stub_metadata=_make_cloud_stub_with_candidate())
    assert result.runtime_behavior_changed is False


# ============================================================
# P3-D-9: Metadata JSON serializable
# ============================================================


def test_metadata_json_serializable():
    result = compute_p3_cheap_verifier(cloud_stub_metadata=_make_cloud_stub_with_candidate())
    meta = p3_cheap_verifier_to_dict(result)
    serialized = json.dumps(meta)
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["p3_cheap_verifier_full_verifier_required"] is True


# ============================================================
# P3-D-10: Existing P3-C tests still pass
# ============================================================


def test_p3_c_still_works():
    from nexus.services.local_heal.p3_cloud_candidate_stub import compute_cloud_candidate_stub
    stub = compute_cloud_candidate_stub(
        diagnosis_metadata={"p3_diagnosis_cloud_ready": True, "p3_diagnosis_compact_prompt_hash": "h"},
    )
    assert stub.cloud_call_planned is True
    assert stub.cloud_call_invoked is False


# ============================================================
# P3-D-11: Existing P2 hash/apply truth tests still pass
# ============================================================


def test_p2_still_works():
    from nexus.services.local_heal.output_understanding import compute_applied_patch_hash
    h = compute_applied_patch_hash("diff")
    assert h != ""
