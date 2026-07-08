from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_local_retry_stub import (
    P3LocalRetryStubResult,
    compute_p3_local_retry,
    p3_retry_stub_to_dict,
)


def _make_cheap_verifier_with_candidate():
    return {
        "p3_cheap_verifier_result": "not_run_shadow_only",
        "p3_cheap_verifier_candidate_available": True,
        "p3_cheap_verifier_blocked_reason": "",
    }


def _make_cheap_verifier_without_candidate():
    return {
        "p3_cheap_verifier_result": "not_applicable",
        "p3_cheap_verifier_candidate_available": False,
        "p3_cheap_verifier_blocked_reason": "no_candidate_available",
    }


# ============================================================
# P3-E-1: Cheap verifier fail plans local retry
# ============================================================


def test_cheap_verifier_fail_plans_retry():
    result = compute_p3_local_retry(
        cheap_verifier_metadata=_make_cheap_verifier_with_candidate(),
        cascade_models=["ornith:9b", "qwythos:9b"],
    )
    assert result.retry_planned is True
    assert result.retry_trigger == "not_run_shadow_only"
    assert result.cascade_models_planned == ["ornith:9b", "qwythos:9b"]


# ============================================================
# P3-E-2: Missing candidate blocks retry with explicit reason
# ============================================================


def test_missing_candidate_blocks_retry():
    result = compute_p3_local_retry(
        cheap_verifier_metadata=_make_cheap_verifier_without_candidate(),
    )
    assert result.retry_planned is False
    assert "no_candidate_available" in result.reason


# ============================================================
# P3-E-3: retry_invoked=false always
# ============================================================


def test_retry_invoked_always_false():
    for has_candidate in (True, False):
        verifier = _make_cheap_verifier_with_candidate() if has_candidate else _make_cheap_verifier_without_candidate()
        result = compute_p3_local_retry(cheap_verifier_metadata=verifier)
        assert result.retry_invoked is False


# ============================================================
# P3-E-4: cascade_models_invoked=[] always
# ============================================================


def test_cascade_models_invoked_always_empty():
    result = compute_p3_local_retry(
        cheap_verifier_metadata=_make_cheap_verifier_with_candidate(),
        cascade_models=["model1", "model2"],
    )
    assert result.cascade_models_invoked == []


# ============================================================
# P3-E-5: retry_candidate_generated=false always
# ============================================================


def test_retry_candidate_generated_always_false():
    result = compute_p3_local_retry(
        cheap_verifier_metadata=_make_cheap_verifier_with_candidate(),
    )
    assert result.retry_candidate_generated is False


# ============================================================
# P3-E-6: full_verifier_required=true always
# ============================================================


def test_full_verifier_required_always_true():
    result = compute_p3_local_retry(
        cheap_verifier_metadata=_make_cheap_verifier_with_candidate(),
    )
    assert result.full_verifier_required is True


# ============================================================
# P3-E-7: claim_gate_required=true always
# ============================================================


def test_claim_gate_required_always_true():
    result = compute_p3_local_retry(
        cheap_verifier_metadata=_make_cheap_verifier_with_candidate(),
    )
    assert result.claim_gate_required is True


# ============================================================
# P3-E-8: solved_claim_allowed=false always
# ============================================================


def test_solved_claim_allowed_always_false():
    result = compute_p3_local_retry(
        cheap_verifier_metadata=_make_cheap_verifier_with_candidate(),
    )
    assert result.solved_claim_allowed is False


# ============================================================
# P3-E-9: public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false():
    result = compute_p3_local_retry(
        cheap_verifier_metadata=_make_cheap_verifier_with_candidate(),
    )
    assert result.public_claim_allowed is False


# ============================================================
# P3-E-10: runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false():
    result = compute_p3_local_retry(
        cheap_verifier_metadata=_make_cheap_verifier_with_candidate(),
    )
    assert result.runtime_behavior_changed is False


# ============================================================
# P3-E-11: Metadata JSON serializable
# ============================================================


def test_metadata_json_serializable():
    result = compute_p3_local_retry(
        cheap_verifier_metadata=_make_cheap_verifier_with_candidate(),
    )
    meta = p3_retry_stub_to_dict(result)
    serialized = json.dumps(meta)
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["p3_local_retry_full_verifier_required"] is True


# ============================================================
# P3-E-12: Existing P3-D tests still pass
# ============================================================


def test_p3_d_still_works():
    from nexus.services.local_heal.p3_local_cheap_verifier import compute_p3_cheap_verifier
    result = compute_p3_cheap_verifier(
        cloud_stub_metadata={"p3_cloud_stub_candidate_generated": True, "p3_cloud_stub_canonical_candidate_available": True},
    )
    assert result.full_verifier_required is True
