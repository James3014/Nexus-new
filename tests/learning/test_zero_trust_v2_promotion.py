from __future__ import annotations

from nexus.learning.zero_trust_v2_promotion import (
    BLOCKED,
    DIAGNOSTIC_ONLY,
    READY_FOR_MANUAL_APPLY,
    evaluate_zero_trust_v2_promotion_candidate,
)
from nexus.learning.zero_trust_v2_receipts import build_runtime_signed_receipt
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
    return {
        **body,
        "signature": sandbox_attestation_signature(attestation_body=body, signing_secret=secret),
    }


def _receipt(row: dict, kind: str, secret: str = SECRET) -> dict:
    """The runtime-signed receipt the physical runner attaches to a row (#3355)."""
    return build_runtime_signed_receipt(
        run_id="run-1",
        row_id=row["row_id"],
        arm_id=row["arm_type"],
        capability_id=row["capability_id"],
        skill_id=row["skill_id"],
        source_skill_id=row.get("source_skill_id") or row["skill_id"],
        evidence_kind=kind,
        artifact_hash=(row.get("sandbox_attestation") or {}).get("artifact_hash", ""),
        raw_observation={},
        secret=secret,
    )


def _proof_row(row_id: str, arm_type: str = "candidate_skill_v2", secret: str = SECRET) -> dict:
    row = {
        "row_id": row_id,
        "arm_type": arm_type,
        "capability_id": "repair_loop",
        "skill_id": "candidate-repair",
    }
    if arm_type == "wrong_or_quarantined_skill_v2":
        return {**row, **_receipt(row, "negative_control_block", secret)}
    row["sandbox_attestation"] = _signed_attestation(secret)
    return {**row, **_receipt(row, "v2_evidence", secret)}


def _complete_v2_row() -> dict:
    row = {
        "row_id": "row-main",
        "arm_type": "candidate_skill_v2",
        "capability_id": "repair_loop",
        "skill_id": "candidate-repair",
        "security_contract_version": "v2",
        "promotion_credit_source": "v2_only",
        "v2_evidence_count": 3,
        "v2_trust_mismatch_count": 0,
        "negative_control_blocked_count": 1,
        "sandbox_attestation": _signed_attestation(),
        "baseline_sandwich": {"baseline_delta_status": "CLEAN"},
        "cleanup_attestation": {"teardown_status": "PASS"},
        "signed_proofs": [
            _proof_row("row-2"),
            _proof_row("row-3"),
            _proof_row("row-4"),
            _proof_row("row-neg", "wrong_or_quarantined_skill_v2"),
        ],
    }
    return {**row, **_receipt(row, "v2_evidence")}


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


def test_non_ascii_attestation_signature_blocks_the_row_instead_of_raising() -> None:
    row = _complete_v2_row()
    row["sandbox_attestation"]["signature"] = "sig\u00e9"

    verdict = evaluate_zero_trust_v2_promotion_candidate(row, signing_secret=SECRET)

    assert verdict["status"] == BLOCKED
    assert verdict["reasons"] == ["sandbox_signature_invalid"]


def _single_row_with_receipt(**over: object) -> dict:
    row = {**_complete_v2_row(), "signed_proofs": [_proof_row("row-neg", "wrong_or_quarantined_skill_v2")]}
    row.update(over)
    return row


def test_3355_edited_count_columns_do_not_earn_promotion() -> None:
    """One verified proof stays one, whatever the row's count columns say."""
    row = _single_row_with_receipt(v2_evidence_count=3, negative_control_blocked_count=1)

    verdict = evaluate_zero_trust_v2_promotion_candidate(row, signing_secret=SECRET)

    assert verdict["status"] == BLOCKED
    assert verdict["v2_evidence_count"] == 1
    assert "insufficient_v2_evidence" in verdict["reasons"]


def test_3355_unverified_receipt_signature_earns_nothing() -> None:
    row = _complete_v2_row()
    row["receipt_signature"] = "any-nonempty"
    row["signed_proofs"] = [_proof_row("row-neg", "wrong_or_quarantined_skill_v2")]

    verdict = evaluate_zero_trust_v2_promotion_candidate(row, min_v2_evidence_count=1, signing_secret=SECRET)

    assert verdict["status"] == BLOCKED
    assert verdict["v2_evidence_count"] == 0
    assert "receipt_not_verified" in verdict["reasons"]


def test_3355_duplicated_proofs_count_once_at_promotion() -> None:
    row = _complete_v2_row()
    copy = {key: value for key, value in row.items() if key != "signed_proofs"}
    row["signed_proofs"] = [copy, dict(copy), dict(copy), _proof_row("row-neg", "wrong_or_quarantined_skill_v2")]

    verdict = evaluate_zero_trust_v2_promotion_candidate(row, signing_secret=SECRET)

    assert verdict["status"] == BLOCKED
    assert verdict["v2_evidence_count"] == 1


def test_3355_negative_control_count_comes_from_signed_receipt_only() -> None:
    row = _complete_v2_row()
    row["signed_proofs"] = row["signed_proofs"][:3]  # no negative-control proof
    row["negative_control_blocked_count"] = 5

    verdict = evaluate_zero_trust_v2_promotion_candidate(row, signing_secret=SECRET)

    assert verdict["status"] == BLOCKED
    assert verdict["reasons"] == ["missing_negative_control_block"]


def test_3355_negative_control_receipt_with_tampered_identity_does_not_count() -> None:
    row = _complete_v2_row()
    negative = row["signed_proofs"][3]
    for field, value in (("skill_id", "other-skill"), ("arm_type", "candidate_skill_v2"), ("row_id", "row-x")):
        tampered_row = {**row, "signed_proofs": [*row["signed_proofs"][:3], {**negative, field: value}]}
        verdict = evaluate_zero_trust_v2_promotion_candidate(tampered_row, signing_secret=SECRET)
        assert verdict["status"] == BLOCKED, field
        assert "missing_negative_control_block" in verdict["reasons"], field


def test_3355_receipt_hash_not_matching_inputs_is_rejected() -> None:
    row = _complete_v2_row()
    row["receipt_signature_inputs"] = {**row["receipt_signature_inputs"], "skill_id": "other-skill"}
    row["skill_id"] = "other-skill"
    row["signed_proofs"] = [_proof_row("row-neg", "wrong_or_quarantined_skill_v2")]

    verdict = evaluate_zero_trust_v2_promotion_candidate(row, min_v2_evidence_count=1, signing_secret=SECRET)

    assert verdict["status"] == BLOCKED
    assert "receipt_not_verified" in verdict["reasons"]


def test_3355_complete_signed_row_with_min_one_is_ready() -> None:
    verdict = evaluate_zero_trust_v2_promotion_candidate(
        _single_row_with_receipt(), min_v2_evidence_count=1, signing_secret=SECRET
    )

    assert verdict["status"] == READY_FOR_MANUAL_APPLY
    assert verdict["v2_evidence_count"] == 1
