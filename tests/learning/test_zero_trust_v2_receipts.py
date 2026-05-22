from __future__ import annotations

from nexus.learning.zero_trust_v2_receipts import (
    build_runtime_signed_receipt,
    stamp_runtime_signed_behavior_bundle,
    verify_runtime_signed_receipt,
)


def test_runtime_signed_receipt_verifies_with_same_secret() -> None:
    receipt = build_runtime_signed_receipt(
        run_id="run-1",
        row_id="row-1",
        arm_id="candidate",
        capability_id="repair_loop",
        skill_id="candidate-repair",
        artifact_hash="artifact",
        raw_observation={"selected": True, "outcome_contributed": True},
        secret="test-secret",
    )

    assert receipt["receipt_provenance"] == "runtime_signed"
    assert verify_runtime_signed_receipt(receipt, secret="test-secret") is True
    assert verify_runtime_signed_receipt(receipt, secret="wrong-secret") is False


def test_skill_supplied_receipt_does_not_verify_for_promotion() -> None:
    receipt = {
        "receipt_provenance": "skill_supplied",
        "receipt_signature": "fake",
        "receipt_signature_algorithm": "hmac-sha256",
        "receipt_signature_inputs": {"receipt_hash": "fake"},
    }

    assert verify_runtime_signed_receipt(receipt, secret="test-secret") is False


def test_runtime_signed_receipt_does_not_expose_secret() -> None:
    receipt = build_runtime_signed_receipt(
        run_id="run-1",
        row_id="row-1",
        arm_id="candidate",
        capability_id="repair_loop",
        skill_id="candidate-repair",
        artifact_hash="artifact",
        raw_observation={"value": "test-secret"},
        secret="test-secret",
    )

    assert "test-secret" not in str(receipt)


def test_stamp_runtime_signed_behavior_bundle_requires_clean_rows() -> None:
    result = stamp_runtime_signed_behavior_bundle(
        {
            "row_counts": {"eligible_with_nexus": 0, "infra_invalid_with_nexus": 1},
            "rubric_contract": {"with_nexus": {"hard_fail_reasons": ["semantic_not_verified"]}},
        },
        run_id="run-1",
        capability_id="policy_capability_gate",
        skill_id="browse",
        secret="test-secret",
    )

    assert result["status"] == "BLOCKED"
    assert "no_eligible_behavior_row" in result["blockers"]
    assert "semantic_not_verified" in result["blockers"]


def test_stamp_runtime_signed_behavior_bundle_exports_verifiable_receipt() -> None:
    result = stamp_runtime_signed_behavior_bundle(
        {
            "row_counts": {"eligible_with_nexus": 1, "infra_invalid_with_nexus": 0},
            "raw_files": {"with_nexus": {"sha256": "artifact-hash"}},
            "rubric_contract": {"with_nexus": {"hard_fail_reasons": []}},
        },
        run_id="run-1",
        capability_id="policy_capability_gate",
        skill_id="browse",
        secret="test-secret",
    )

    assert result["status"] == "PASS"
    stamped = result["bundle"]
    receipt = stamped["zero_trust_v2_runtime_receipt"]
    assert receipt["receipt_provenance"] == "runtime_signed"
    assert verify_runtime_signed_receipt(receipt, secret="test-secret") is True
    assert "test-secret" not in str(stamped)
