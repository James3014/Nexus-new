from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PROMOTION_DECISIONS = (
    "P3_SHADOW_CONTINUE_ONLY",
    "P3_GUARDED_RUNTIME_DESIGN_CANDIDATE",
    "P3_SHADOW_BLOCKED",
    "P3_ROLLBACK_REQUIRED",
)


@dataclass(frozen=True)
class P3PromotionDecision:
    """P3-J5: Shadow pipeline promotion decision.

    Conservative decision: whether P3 is ready for guarded runtime design.
    """
    decision: str
    invariant_gate_passed: bool
    receipt_consolidator_passed: bool
    evidence_matrix_complete: bool
    all_valid_scenarios_pass: bool
    all_unsafe_scenarios_fail: bool
    public_claim_never_passes: bool
    solved_never_passes: bool
    cloud_local_patch_runtime_fail_closed: bool
    no_runtime_behavior_changed: bool
    p2_hash_truth_required: bool
    p4_verifier_claim_gate_required: bool
    blocking_reasons: list[str]


def evaluate_p3_promotion(
    *,
    j1_inventory_complete: bool = True,
    j2_invariant_gate_passed: bool = True,
    j3_receipt_consolidator_passed: bool = True,
    j4_evidence_matrix_complete: bool = True,
    j4_all_valid_scenarios_pass: bool = True,
    j4_all_unsafe_scenarios_fail: bool = True,
    j4_public_claim_never_passes: bool = True,
    j4_solved_never_passes: bool = True,
    j4_cloud_local_patch_runtime_fail_closed: bool = True,
    no_runtime_behavior_changed: bool = True,
    p2_hash_truth_required: bool = True,
    p4_verifier_claim_gate_required: bool = True,
) -> P3PromotionDecision:
    """Evaluate P3 promotion readiness.

    Decision rules:
    - B only if ALL safety gates pass
    - A if gates pass but evidence incomplete
    - C if any safety gate fails
    - D if runtime was changed unsafely
    """
    blocking_reasons = []

    all_safety_gates_pass = all([
        j2_invariant_gate_passed,
        j3_receipt_consolidator_passed,
        j4_all_valid_scenarios_pass,
        j4_all_unsafe_scenarios_fail,
        j4_public_claim_never_passes,
        j4_solved_never_passes,
        j4_cloud_local_patch_runtime_fail_closed,
        no_runtime_behavior_changed,
        p2_hash_truth_required,
        p4_verifier_claim_gate_required,
    ])

    all_evidence_complete = all([
        j1_inventory_complete,
        j4_evidence_matrix_complete,
    ])

    if not no_runtime_behavior_changed:
        return P3PromotionDecision(
            decision="P3_ROLLBACK_REQUIRED",
            invariant_gate_passed=j2_invariant_gate_passed,
            receipt_consolidator_passed=j3_receipt_consolidator_passed,
            evidence_matrix_complete=j4_evidence_matrix_complete,
            all_valid_scenarios_pass=j4_all_valid_scenarios_pass,
            all_unsafe_scenarios_fail=j4_all_unsafe_scenarios_fail,
            public_claim_never_passes=j4_public_claim_never_passes,
            solved_never_passes=j4_solved_never_passes,
            cloud_local_patch_runtime_fail_closed=j4_cloud_local_patch_runtime_fail_closed,
            no_runtime_behavior_changed=no_runtime_behavior_changed,
            p2_hash_truth_required=p2_hash_truth_required,
            p4_verifier_claim_gate_required=p4_verifier_claim_gate_required,
            blocking_reasons=["runtime_behavior_changed_unsafe"],
        )

    if not all_safety_gates_pass:
        if not j2_invariant_gate_passed:
            blocking_reasons.append("j2_invariant_gate_failed")
        if not j3_receipt_consolidator_passed:
            blocking_reasons.append("j3_receipt_consolidator_failed")
        if not j4_all_valid_scenarios_pass:
            blocking_reasons.append("j4_valid_scenarios_failed")
        if not j4_all_unsafe_scenarios_fail:
            blocking_reasons.append("j4_unsafe_scenarios_passed")
        if not j4_public_claim_never_passes:
            blocking_reasons.append("j4_public_claim_passed")
        if not j4_solved_never_passes:
            blocking_reasons.append("j4_solved_passed")
        if not j4_cloud_local_patch_runtime_fail_closed:
            blocking_reasons.append("j4_violations_not_caught")
        if not p2_hash_truth_required:
            blocking_reasons.append("p2_hash_truth_not_required")
        if not p4_verifier_claim_gate_required:
            blocking_reasons.append("p4_verifier_claim_gate_not_required")
        return P3PromotionDecision(
            decision="P3_SHADOW_BLOCKED",
            invariant_gate_passed=j2_invariant_gate_passed,
            receipt_consolidator_passed=j3_receipt_consolidator_passed,
            evidence_matrix_complete=j4_evidence_matrix_complete,
            all_valid_scenarios_pass=j4_all_valid_scenarios_pass,
            all_unsafe_scenarios_fail=j4_all_unsafe_scenarios_fail,
            public_claim_never_passes=j4_public_claim_never_passes,
            solved_never_passes=j4_solved_never_passes,
            cloud_local_patch_runtime_fail_closed=j4_cloud_local_patch_runtime_fail_closed,
            no_runtime_behavior_changed=no_runtime_behavior_changed,
            p2_hash_truth_required=p2_hash_truth_required,
            p4_verifier_claim_gate_required=p4_verifier_claim_gate_required,
            blocking_reasons=blocking_reasons,
        )

    if all_evidence_complete:
        return P3PromotionDecision(
            decision="P3_GUARDED_RUNTIME_DESIGN_CANDIDATE",
            invariant_gate_passed=j2_invariant_gate_passed,
            receipt_consolidator_passed=j3_receipt_consolidator_passed,
            evidence_matrix_complete=j4_evidence_matrix_complete,
            all_valid_scenarios_pass=j4_all_valid_scenarios_pass,
            all_unsafe_scenarios_fail=j4_all_unsafe_scenarios_fail,
            public_claim_never_passes=j4_public_claim_never_passes,
            solved_never_passes=j4_solved_never_passes,
            cloud_local_patch_runtime_fail_closed=j4_cloud_local_patch_runtime_fail_closed,
            no_runtime_behavior_changed=no_runtime_behavior_changed,
            p2_hash_truth_required=p2_hash_truth_required,
            p4_verifier_claim_gate_required=p4_verifier_claim_gate_required,
            blocking_reasons=[],
        )

    return P3PromotionDecision(
        decision="P3_SHADOW_CONTINUE_ONLY",
        invariant_gate_passed=j2_invariant_gate_passed,
        receipt_consolidator_passed=j3_receipt_consolidator_passed,
        evidence_matrix_complete=j4_evidence_matrix_complete,
        all_valid_scenarios_pass=j4_all_valid_scenarios_pass,
        all_unsafe_scenarios_fail=j4_all_unsafe_scenarios_fail,
        public_claim_never_passes=j4_public_claim_never_passes,
        solved_never_passes=j4_solved_never_passes,
        cloud_local_patch_runtime_fail_closed=j4_cloud_local_patch_runtime_fail_closed,
        no_runtime_behavior_changed=no_runtime_behavior_changed,
        p2_hash_truth_required=p2_hash_truth_required,
        p4_verifier_claim_gate_required=p4_verifier_claim_gate_required,
        blocking_reasons=["evidence_incomplete"],
    )


def p3_promotion_to_dict(decision: P3PromotionDecision) -> dict[str, Any]:
    """Convert P3PromotionDecision to JSON-serializable dict."""
    return {
        "p3_promotion_decision": decision.decision,
        "p3_promotion_invariant_gate_passed": decision.invariant_gate_passed,
        "p3_promotion_receipt_consolidator_passed": decision.receipt_consolidator_passed,
        "p3_promotion_evidence_matrix_complete": decision.evidence_matrix_complete,
        "p3_promotion_all_valid_scenarios_pass": decision.all_valid_scenarios_pass,
        "p3_promotion_all_unsafe_scenarios_fail": decision.all_unsafe_scenarios_fail,
        "p3_promotion_public_claim_never_passes": decision.public_claim_never_passes,
        "p3_promotion_solved_never_passes": decision.solved_never_passes,
        "p3_promotion_cloud_local_patch_runtime_fail_closed": decision.cloud_local_patch_runtime_fail_closed,
        "p3_promotion_no_runtime_behavior_changed": decision.no_runtime_behavior_changed,
        "p3_promotion_p2_hash_truth_required": decision.p2_hash_truth_required,
        "p3_promotion_p4_verifier_claim_gate_required": decision.p4_verifier_claim_gate_required,
        "p3_promotion_blocking_reasons": decision.blocking_reasons,
    }
