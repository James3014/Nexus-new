from __future__ import annotations

from nexus.learning.zero_trust_v2_promotion import (
    BLOCKED,
    DIAGNOSTIC_ONLY,
    READY_FOR_MANUAL_APPLY,
    evaluate_zero_trust_v2_promotion_candidate,
)


def _complete_v2_row() -> dict:
    return {
        "capability_id": "repair_loop",
        "skill_id": "candidate-repair",
        "security_contract_version": "v2",
        "promotion_credit_source": "v2_only",
        "v2_evidence_count": 3,
        "v2_trust_mismatch_count": 0,
        "negative_control_blocked_count": 1,
        "receipt_provenance": "runtime_signed",
        "receipt_signature": "sig",
        "sandbox_attestation": {"status": "PASS"},
        "baseline_sandwich": {"baseline_delta_status": "CLEAN"},
        "cleanup_attestation": {"teardown_status": "PASS"},
    }


def test_v1_diagnostic_rows_cannot_promote() -> None:
    verdict = evaluate_zero_trust_v2_promotion_candidate(
        {
            "capability_id": "repair_loop",
            "skill_id": "candidate-repair",
            "security_contract_version": "v1_diagnostic_only",
            "promotion_credit_source": "none",
            "v2_evidence_count": 0,
        }
    )

    assert verdict["status"] == DIAGNOSTIC_ONLY
    assert verdict["manual_apply_required"] is False
    assert verdict["reasons"] == ["security_contract_not_v2"]


def test_incomplete_v2_row_is_blocked() -> None:
    row = _complete_v2_row()
    row.pop("receipt_signature")
    row["sandbox_attestation"] = {"status": "MISSING"}
    row["baseline_sandwich"] = {"baseline_delta_status": "POLLUTED"}

    verdict = evaluate_zero_trust_v2_promotion_candidate(row)

    assert verdict["status"] == BLOCKED
    assert verdict["manual_apply_required"] is False
    assert verdict["reasons"] == [
        "baseline_not_clean",
        "missing_receipt_signature",
        "sandbox_attestation_not_pass",
    ]


def test_complete_v2_row_requires_manual_apply() -> None:
    verdict = evaluate_zero_trust_v2_promotion_candidate(_complete_v2_row())

    assert verdict["status"] == READY_FOR_MANUAL_APPLY
    assert verdict["manual_apply_required"] is True
    assert verdict["reasons"] == []
