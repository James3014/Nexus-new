from __future__ import annotations

from nexus.learning.zero_trust_v2_promotion import (
    BLOCKED,
    DIAGNOSTIC_ONLY,
    READY_FOR_MANUAL_APPLY,
    evaluate_zero_trust_v2_promotion_candidate,
)
from nexus.learning.zero_trust_v2_sandbox import sandbox_attestation_signature

SECRET = "test-only-secret-3249"


def _signed_attestation(secret: str = SECRET) -> dict:
    body = {
        "issuer": "nexus.runner",
        "sandbox_mode": "macos_sandbox",
        "status": "PASS",
        "network_disabled": True,
        "workspace_isolated": True,
        "tmp_isolated": True,
        "teardown_status": "PASS",
        "artifact_hash": "a" * 64,
    }
    return {**body, "signature": sandbox_attestation_signature(attestation_body=body, signing_secret=secret)}


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
        "sandbox_attestation": _signed_attestation(),
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

    verdict = evaluate_zero_trust_v2_promotion_candidate(row, signing_secret=SECRET)

    assert verdict["status"] == BLOCKED
    assert verdict["manual_apply_required"] is False
    assert verdict["reasons"] == [
        "baseline_not_clean",
        "missing_receipt_signature",
        "sandbox_attestation_not_pass",
        "sandbox_signature_invalid",
    ]


def test_complete_v2_row_requires_manual_apply() -> None:
    verdict = evaluate_zero_trust_v2_promotion_candidate(_complete_v2_row(), signing_secret=SECRET)

    assert verdict["status"] == READY_FOR_MANUAL_APPLY
    assert verdict["manual_apply_required"] is True
    assert verdict["reasons"] == []


def test_attestation_signature_mismatch_is_rejected_at_promotion() -> None:
    row = _complete_v2_row()
    row["sandbox_attestation"] = _signed_attestation("some-other-secret")

    verdict = evaluate_zero_trust_v2_promotion_candidate(row, signing_secret=SECRET)

    assert verdict["status"] == BLOCKED
    assert verdict["reasons"] == ["sandbox_signature_invalid"]


def test_tampered_attestation_field_is_rejected_at_promotion() -> None:
    row = _complete_v2_row()
    row["sandbox_attestation"]["artifact_hash"] = "b" * 64

    verdict = evaluate_zero_trust_v2_promotion_candidate(row, signing_secret=SECRET)

    assert verdict["status"] == BLOCKED
    assert "sandbox_signature_invalid" in verdict["reasons"]


def test_default_source_secret_never_earns_promotion() -> None:
    from nexus.learning.zero_trust_v2_signing_secret import NONPRODUCTION_DEFAULT_SECRETS

    for default in sorted(NONPRODUCTION_DEFAULT_SECRETS):
        row = _complete_v2_row()
        row["sandbox_attestation"] = _signed_attestation(default)
        verdict = evaluate_zero_trust_v2_promotion_candidate(row, signing_secret=default)
        assert verdict["status"] == BLOCKED
        assert verdict["reasons"] == ["nonproduction_signing_secret"]


def test_promotion_without_a_secret_cannot_verify_and_is_blocked() -> None:
    verdict = evaluate_zero_trust_v2_promotion_candidate(_complete_v2_row())

    assert verdict["status"] == BLOCKED
    assert verdict["reasons"] == ["sandbox_signature_not_verified"]
