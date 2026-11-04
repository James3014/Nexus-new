from __future__ import annotations

from nexus.learning.zero_trust_v2_receipts import (
    build_runtime_signed_receipt,
    canonical_json_hash,
    stamp_runtime_signed_behavior_bundle,
    verify_runtime_signed_receipt,
)
from nexus.learning.zero_trust_v2_sandbox import (
    sandbox_attestation_signature,
    sandbox_attestation_signed_content,
    validate_sandbox_attestation,
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


_PURPOSE_SECRET = "purpose-test-secret-3362"


def _attestation_body() -> dict:
    return {
        "issuer": "nexus.runner",
        "sandbox_mode": "macos_sandbox",
        "status": "PASS",
        "network_disabled": True,
        "workspace_isolated": True,
        "tmp_isolated": True,
        "teardown_status": "PASS",
        "artifact_hash": "a" * 64,
    }


def test_3362_attestation_signature_does_not_verify_as_receipt() -> None:
    body = _attestation_body()
    signature = sandbox_attestation_signature(attestation_body=body, signing_secret=_PURPOSE_SECRET)
    for signed in (body, sandbox_attestation_signed_content(body)):
        inputs = {**signed, "receipt_hash": canonical_json_hash(signed)}
        receipt = {
            "receipt_provenance": "runtime_signed",
            "receipt_signature": signature,
            "receipt_signature_algorithm": "hmac-sha256",
            "receipt_signature_inputs": inputs,
        }
        assert verify_runtime_signed_receipt(receipt, secret=_PURPOSE_SECRET) is False


def test_3362_receipt_signature_does_not_verify_as_attestation() -> None:
    receipt = build_runtime_signed_receipt(
        run_id="run-1",
        row_id="row-1",
        arm_id="candidate_skill_v2",
        capability_id="cap",
        skill_id="skill",
        artifact_hash="a" * 64,
        raw_observation={},
        secret=_PURPOSE_SECRET,
    )
    body = {
        key: value
        for key, value in receipt["receipt_signature_inputs"].items()
        if key != "receipt_hash"
    }
    attestation = {**body, "signature": receipt["receipt_signature"]}

    verdict = validate_sandbox_attestation(attestation, signing_secret=_PURPOSE_SECRET)

    assert "invalid_sandbox_signature" in verdict["reasons"]
    assert verify_runtime_signed_receipt(receipt, secret=_PURPOSE_SECRET) is True


def test_3362_each_kind_still_verifies_in_its_own_position() -> None:
    body = _attestation_body()
    attestation = {
        **body,
        "signature": sandbox_attestation_signature(
            attestation_body=body, signing_secret=_PURPOSE_SECRET
        ),
    }

    assert (
        validate_sandbox_attestation(attestation, signing_secret=_PURPOSE_SECRET)["status"]
        == "PASS"
    )


def test_verify_runtime_signed_receipt_binds_expected_identity() -> None:
    receipt = build_runtime_signed_receipt(
        run_id="run-a",
        row_id="run-a:with_nexus",
        arm_id="candidate_skill_v2",
        capability_id="cap-a",
        skill_id="skill-a",
        artifact_hash="artifact",
        raw_observation={"x": 1},
        secret="s",
    )

    assert verify_runtime_signed_receipt(receipt, secret="s") is True
    assert verify_runtime_signed_receipt(
        receipt, secret="s", expected={"run_id": "run-a", "row_id": "run-a:with_nexus", "capability_id": "cap-a"}
    ) is True
    assert verify_runtime_signed_receipt(receipt, secret="s", expected={"run_id": "run-b"}) is False
    assert verify_runtime_signed_receipt(receipt, secret="s", expected={"capability_id": "cap-b"}) is False
    assert verify_runtime_signed_receipt(receipt, secret="s", expected={"row_id": "run-b:with_nexus"}) is False
    assert verify_runtime_signed_receipt(receipt, secret="s", expected={"evidence_kind": "anything"}) is False
