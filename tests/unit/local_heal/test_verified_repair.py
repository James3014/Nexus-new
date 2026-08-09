from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nexus.services.local_heal.verified_repair import (
    CALIBRATION_MANIFEST_HASH,
    KNOWN_WRONG_CASES,
    reduce_verified_repair,
    run_fixed_calibration,
)


def _sha256_ref(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _adequacy_payload() -> dict[str, Any]:
    refs = {gate: f"sha256:{gate * 64}" for gate in ("a", "b", "c")}
    gate_refs = {gate: refs[value] for gate, value in zip(("g1", "g2", "g3"), refs)}
    payload: dict[str, Any] = {
        "schema": "nexus.world_c.adequacy_projection.v1",
        "task_id": "repair-1",
        "status": "VERIFIED_REPAIR",
        "reasons": [],
        "upstream_evidence_refs": gate_refs,
        "upstream_evidence": {gate: {"ref": ref} for gate, ref in gate_refs.items()},
        "world_c_receipt_hash": "sha256:" + "d" * 64,
        "root_receipt_hash": "sha256:" + "e" * 64,
        "world_c_receipt_valid": True,
        "root_receipt_valid": True,
        "public_claim_allowed": False,
    }
    payload["adequacy_hash"] = _sha256_ref(payload)
    return payload


def _mutation_payload() -> dict[str, Any]:
    return {
        "schema_version": "nexus_issue16_mutation_assurance.v1",
        "decision": "REQUIRED",
        "required": True,
        "status": "PASS",
        "passed": True,
        "failures": [],
    }


def _bound_receipts() -> tuple[list[str], dict[str, dict[str, Any]]]:
    payloads = {"adequacy": _adequacy_payload(), "mutation": _mutation_payload()}
    receipts: dict[str, dict[str, Any]] = {}
    refs: list[str] = []
    for kind, payload in payloads.items():
        ref = _sha256_ref(payload)
        refs.append(ref)
        receipts[kind] = {"ref": ref, "content_hash": ref, "payload": payload}
    return refs, receipts


def _correct() -> dict[str, Any]:
    refs, receipts = _bound_receipts()
    return {
        "upstream_receipt_refs": refs,
        "upstream_receipts": receipts,
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


def test_forged_nonempty_receipt_ref_without_content_fails_closed() -> None:
    result = reduce_verified_repair(
        {
            **_correct(),
            "calibration_case": "correct",
            "upstream_receipt_refs": ["forged-ref"],
            "upstream_receipts": {},
        }
    )

    assert result["accepted"] is False
    assert "upstream_receipt_kinds_mismatch" in result["reasons"]
    assert "upstream_receipt_refs_binding_mismatch" in result["reasons"]


def test_tampered_receipt_payload_hash_fails_closed() -> None:
    evidence = _correct()
    receipts = dict(evidence["upstream_receipts"])
    adequacy = dict(receipts["adequacy"])
    adequacy["payload"] = {**adequacy["payload"], "task_id": "tampered"}
    receipts["adequacy"] = adequacy

    result = reduce_verified_repair(
        {**evidence, "calibration_case": "correct", "upstream_receipts": receipts}
    )

    assert result["accepted"] is False
    assert "adequacy_receipt_content_hash_mismatch" in result["reasons"]
    assert "adequacy_receipt_ref_hash_mismatch" in result["reasons"]


def test_failed_mutation_receipt_cannot_become_verified_repair() -> None:
    evidence = _correct()
    receipts = dict(evidence["upstream_receipts"])
    failed_payload = {**_mutation_payload(), "status": "FAIL", "passed": False}
    failed_ref = _sha256_ref(failed_payload)
    receipts["mutation"] = {
        "ref": failed_ref,
        "content_hash": failed_ref,
        "payload": failed_payload,
    }
    refs = [receipts[kind]["ref"] for kind in ("adequacy", "mutation")]

    result = reduce_verified_repair(
        {
            **evidence,
            "calibration_case": "correct",
            "upstream_receipt_refs": refs,
            "upstream_receipts": receipts,
        }
    )

    assert result["accepted"] is False
    assert "mutation_receipt_semantics_invalid" in result["reasons"]
