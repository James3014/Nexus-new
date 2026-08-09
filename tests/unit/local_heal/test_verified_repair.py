from __future__ import annotations

import pytest

from nexus.services.local_heal.verified_repair import (
    CALIBRATION_MANIFEST_HASH,
    KNOWN_WRONG_CASES,
    reduce_verified_repair,
    run_fixed_calibration,
)


def _correct() -> dict[str, object]:
    return {
        "upstream_receipt_refs": ["g1:receipt", "g2:receipt", "g3:receipt"],
        "patch_applied": True,
        "patch_sha": "patch-sha",
        "base_sha": "base-sha",
        "candidate_sha": "candidate-sha",
        "compile_passed": True,
        "hidden_verifier_passed": True,
        "behavioral_verifier_passed": True,
        "regression_passed": True,
        "mutation_assurance_passed": True,
        "public_claim_allowed": False,
    }


def test_correct_repair_is_accepted_but_not_public() -> None:
    result = reduce_verified_repair({**_correct(), "calibration_case": "correct"})

    assert result["status"] == "VERIFIED_REPAIR"
    assert result["accepted"] is True
    assert result["reasons"] == []
    assert result["public_claim_allowed"] is False


def test_missing_evidence_is_partially_verified() -> None:
    result = reduce_verified_repair({"calibration_case": "correct"})

    assert result["status"] == "PARTIALLY_VERIFIED"
    assert result["accepted"] is False
    assert "upstream_receipt_refs_missing" in result["reasons"]
    assert result["public_claim_allowed"] is False


def test_fixed_calibration_rejects_all_five_known_wrong_cases() -> None:
    cases = {
        "correct": _correct(),
        "no_op": {"upstream_receipt_refs": ["g1:receipt"]},
        "compile_only_wrong": {"upstream_receipt_refs": ["g1:receipt"], "compile_passed": True},
        "overfit": {"upstream_receipt_refs": ["g1:receipt"], "regression_passed": False},
        "boundary_wrong": {"upstream_receipt_refs": ["g1:receipt"]},
        "regression_inducing": {
            "upstream_receipt_refs": ["g1:receipt"],
            "regression_passed": False,
        },
    }

    calibration = run_fixed_calibration(cases)

    assert calibration["manifest_hash"] == CALIBRATION_MANIFEST_HASH
    assert calibration["known_wrong_count"] == 5
    assert calibration["false_green_count"] == 0
    assert calibration["false_green_rate"] == 0
    assert calibration["all_known_wrong_rejected"] is True
    assert calibration["correct_repair_accepted"] is True
    assert calibration["public_claim_allowed"] is False
    assert {row["case"] for row in calibration["outcomes"]} == {"correct", *KNOWN_WRONG_CASES}


def test_compile_only_wrong_cannot_pass_from_compile_evidence() -> None:
    result = reduce_verified_repair(
        {
            "calibration_case": "compile_only_wrong",
            "upstream_receipt_refs": ["g1:receipt", "g2:receipt"],
            "compile_passed": True,
            "hidden_verifier_passed": True,
        }
    )

    assert result["accepted"] is False
    assert result["status"] == "PARTIALLY_VERIFIED"
    assert "compile_only_rejected" in result["reasons"]


def test_manifest_hash_tampering_fails_closed() -> None:
    result = reduce_verified_repair(
        {**_correct(), "calibration_case": "correct", "calibration_manifest_hash": "0" * 64}
    )

    assert result["accepted"] is False
    assert "calibration_manifest_hash_mismatch" in result["reasons"]


def test_mapping_receipt_refs_fail_closed_instead_of_using_values() -> None:
    result = reduce_verified_repair(
        {
            **_correct(),
            "calibration_case": "correct",
            "upstream_receipt_refs": {"g1": "g1:receipt", "g2": "g2:receipt"},
        }
    )

    assert result["accepted"] is False
    assert result["status"] == "PARTIALLY_VERIFIED"
    assert "upstream_receipt_refs_invalid_type" in result["reasons"]
    assert result["upstream_receipt_refs"] == []


def test_duplicate_receipt_refs_fail_closed() -> None:
    result = reduce_verified_repair(
        {
            **_correct(),
            "calibration_case": "correct",
            "upstream_receipt_refs": ["g1:receipt", "g1:receipt"],
        }
    )

    assert result["accepted"] is False
    assert "upstream_receipt_refs_duplicate" in result["reasons"]


@pytest.mark.parametrize("invalid_ref", ["", "  ", None, 7, True])
def test_empty_or_non_string_receipt_ref_fails_closed(invalid_ref: object) -> None:
    result = reduce_verified_repair(
        {
            **_correct(),
            "calibration_case": "correct",
            "upstream_receipt_refs": ["g1:receipt", invalid_ref],
        }
    )

    assert result["accepted"] is False
    assert "upstream_receipt_ref_invalid" in result["reasons"]


def test_input_public_claim_allowed_true_is_tamper_and_fails_closed() -> None:
    result = reduce_verified_repair(
        {**_correct(), "calibration_case": "correct", "public_claim_allowed": True}
    )

    assert result["accepted"] is False
    assert result["status"] == "PARTIALLY_VERIFIED"
    assert "public_claim_allowed_tamper" in result["reasons"]
    assert result["public_claim_allowed"] is False
