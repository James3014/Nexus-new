from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_shadow_promotion_policy import (
    P3PromotionDecision,
    evaluate_p3_promotion,
    p3_promotion_to_dict,
)


# ============================================================
# P3-J5-1: All gates pass → GUARDED_RUNTIME_DESIGN_CANDIDATE
# ============================================================


def test_all_gates_pass():
    decision = evaluate_p3_promotion()
    assert decision.decision == "P3_GUARDED_RUNTIME_DESIGN_CANDIDATE"
    assert decision.blocking_reasons == []


# ============================================================
# P3-J5-2: Invariant gate fails → SHADOW_BLOCKED
# ============================================================


def test_invariant_gate_fails():
    decision = evaluate_p3_promotion(j2_invariant_gate_passed=False)
    assert decision.decision == "P3_SHADOW_BLOCKED"
    assert "j2_invariant_gate_failed" in decision.blocking_reasons


# ============================================================
# P3-J5-3: Evidence incomplete → CONTINUE_ONLY
# ============================================================


def test_evidence_incomplete():
    decision = evaluate_p3_promotion(j1_inventory_complete=False, j4_evidence_matrix_complete=False)
    assert decision.decision == "P3_SHADOW_CONTINUE_ONLY"
    assert "evidence_incomplete" in decision.blocking_reasons


# ============================================================
# P3-J5-4: Runtime changed → ROLLBACK_REQUIRED
# ============================================================


def test_runtime_changed():
    decision = evaluate_p3_promotion(no_runtime_behavior_changed=False)
    assert decision.decision == "P3_ROLLBACK_REQUIRED"
    assert "runtime_behavior_changed_unsafe" in decision.blocking_reasons


# ============================================================
# P3-J5-5: Public claim passes → SHADOW_BLOCKED
# ============================================================


def test_public_claim_passes():
    decision = evaluate_p3_promotion(j4_public_claim_never_passes=False)
    assert decision.decision == "P3_SHADOW_BLOCKED"
    assert "j4_public_claim_passed" in decision.blocking_reasons


# ============================================================
# P3-J5-6: Solved passes → SHADOW_BLOCKED
# ============================================================


def test_solved_passes():
    decision = evaluate_p3_promotion(j4_solved_never_passes=False)
    assert decision.decision == "P3_SHADOW_BLOCKED"
    assert "j4_solved_passed" in decision.blocking_reasons


# ============================================================
# P3-J5-7: Violations not caught → SHADOW_BLOCKED
# ============================================================


def test_violations_not_caught():
    decision = evaluate_p3_promotion(j4_cloud_local_patch_runtime_fail_closed=False)
    assert decision.decision == "P3_SHADOW_BLOCKED"
    assert "j4_violations_not_caught" in decision.blocking_reasons


# ============================================================
# P3-J5-8: JSON serializable
# ============================================================


def test_json_serializable():
    decision = evaluate_p3_promotion()
    d = p3_promotion_to_dict(decision)
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["p3_promotion_decision"] == "P3_GUARDED_RUNTIME_DESIGN_CANDIDATE"


# ============================================================
# P3-J5-9: Decision is one of allowed values
# ============================================================


def test_decision_is_allowed():
    for j2, j3, j4v, j4u, j4p, j4s, j4c, runtime in [
        (True, True, True, True, True, True, True, True),
        (False, True, True, True, True, True, True, True),
        (True, False, True, True, True, True, True, True),
        (True, True, True, True, False, True, True, True),
        (True, True, True, True, True, False, True, True),
        (True, True, True, True, True, True, False, True),
        (True, True, True, True, True, True, True, False),
    ]:
        decision = evaluate_p3_promotion(
            j2_invariant_gate_passed=j2,
            j3_receipt_consolidator_passed=j3,
            j4_all_valid_scenarios_pass=j4v,
            j4_all_unsafe_scenarios_fail=j4u,
            j4_public_claim_never_passes=j4p,
            j4_solved_never_passes=j4s,
            j4_cloud_local_patch_runtime_fail_closed=j4c,
            no_runtime_behavior_changed=runtime,
        )
        assert decision.decision in (
            "P3_SHADOW_CONTINUE_ONLY",
            "P3_GUARDED_RUNTIME_DESIGN_CANDIDATE",
            "P3_SHADOW_BLOCKED",
            "P3_ROLLBACK_REQUIRED",
        )
