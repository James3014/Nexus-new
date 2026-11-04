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
    assert (
        verify_runtime_signed_receipt(
            receipt,
            secret="s",
            expected={"run_id": "run-a", "row_id": "run-a:with_nexus", "capability_id": "cap-a"},
        )
        is True
    )
    assert verify_runtime_signed_receipt(receipt, secret="s", expected={"run_id": "run-b"}) is False
    assert (
        verify_runtime_signed_receipt(receipt, secret="s", expected={"capability_id": "cap-b"})
        is False
    )
    assert (
        verify_runtime_signed_receipt(receipt, secret="s", expected={"row_id": "run-b:with_nexus"})
        is False
    )
    assert (
        verify_runtime_signed_receipt(receipt, secret="s", expected={"evidence_kind": "anything"})
        is False
    )


def test_3374_report_signature_roundtrip_and_tamper() -> None:
    from nexus.learning.zero_trust_v2_receipts import (
        REPORT_KIND_POST_APPLY_SMOKE,
        sign_report,
        verify_report_signature,
    )

    report = {"status": "PASS", "summary": {"case_count": 34, "pass_count": 34}}
    signed = sign_report(report, kind=REPORT_KIND_POST_APPLY_SMOKE, secret="k")
    assert verify_report_signature(signed, kind=REPORT_KIND_POST_APPLY_SMOKE, secret="k")
    assert not verify_report_signature(signed, kind=REPORT_KIND_POST_APPLY_SMOKE, secret="other")
    assert not verify_report_signature(report, kind=REPORT_KIND_POST_APPLY_SMOKE, secret="k")
    edited = {**signed, "summary": {"case_count": 34, "pass_count": 33}}
    assert not verify_report_signature(edited, kind=REPORT_KIND_POST_APPLY_SMOKE, secret="k")


def test_3374_report_signature_rejects_other_kind_and_other_purpose() -> None:
    from nexus.learning.zero_trust_v2_receipts import (
        REPORT_KIND_POST_APPLY_SMOKE,
        REPORT_KIND_ROLLOUT,
        sign_report,
        verify_report_signature,
    )

    report = {"status": "PASS", "summary": {}}
    signed = sign_report(report, kind=REPORT_KIND_ROLLOUT, secret="k")
    assert not verify_report_signature(signed, kind=REPORT_KIND_POST_APPLY_SMOKE, secret="k")
    relabeled = {
        **signed,
        "report_signature": {
            **signed["report_signature"],
            "report_kind": REPORT_KIND_POST_APPLY_SMOKE,
        },
    }
    assert not verify_report_signature(relabeled, kind=REPORT_KIND_POST_APPLY_SMOKE, secret="k")
    receipt = build_runtime_signed_receipt(
        run_id="r",
        row_id="x",
        arm_id="a",
        capability_id="c",
        skill_id="s",
        artifact_hash="h",
        raw_observation={},
        secret="k",
    )
    as_report = {**report, "report_signature": receipt}
    assert not verify_report_signature(as_report, kind=REPORT_KIND_ROLLOUT, secret="k")


def test_3374_load_signing_secret_never_creates_key(tmp_path, monkeypatch) -> None:
    from nexus.learning.zero_trust_v2_receipts import load_signing_secret

    monkeypatch.delenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", raising=False)
    missing = tmp_path / "nokey"
    assert load_signing_secret(str(missing)) == ""
    assert not missing.exists()
    keyfile = tmp_path / "key"
    keyfile.write_text("abc\n", encoding="utf-8")
    assert load_signing_secret(str(keyfile)) == "abc"
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "envkey")
    assert load_signing_secret(str(keyfile)) == "envkey"


def _forged_report_signature(
    report: dict, *, purpose: str, label_kind: str, fields: dict, key: str
) -> dict:
    import hashlib
    import hmac

    digest = canonical_json_hash({
        "signature_purpose": purpose,
        "report_kind": label_kind,
        "fields": fields,
    })
    return {
        **report,
        "report_signature": {
            "signature_purpose": purpose,
            "report_kind": label_kind,
            "algorithm": "hmac-sha256",
            "fields": fields,
            "signature": hmac.new(key.encode(), digest.encode(), hashlib.sha256).hexdigest(),
        },
    }


def test_3374_purpose_check_rejects_same_key_signature_of_other_purpose() -> None:
    from nexus.learning.zero_trust_v2_receipts import (
        REPORT_KIND_POST_APPLY_SMOKE,
        report_signed_fields,
        verify_report_signature,
    )

    report = {"status": "PASS", "summary": {"case_count": 34, "pass_count": 34}}
    fields = report_signed_fields(REPORT_KIND_POST_APPLY_SMOKE, report)
    forged = _forged_report_signature(
        report,
        purpose="nexus.zero_trust_v2.runtime_receipt",
        label_kind=REPORT_KIND_POST_APPLY_SMOKE,
        fields=fields,
        key="k",
    )
    assert not verify_report_signature(forged, kind=REPORT_KIND_POST_APPLY_SMOKE, secret="k")
    good = _forged_report_signature(
        report,
        purpose="nexus.zero_trust_v2.report",
        label_kind=REPORT_KIND_POST_APPLY_SMOKE,
        fields=fields,
        key="k",
    )
    assert verify_report_signature(good, kind=REPORT_KIND_POST_APPLY_SMOKE, secret="k")


def test_3374_kind_check_rejects_signature_labelled_for_other_kind() -> None:
    from nexus.learning.zero_trust_v2_receipts import (
        REPORT_KIND_POST_APPLY_SMOKE,
        REPORT_KIND_ROLLOUT,
        report_signed_fields,
        verify_report_signature,
    )

    report = {"status": "PASS", "summary": {"case_count": 34, "pass_count": 34}}
    fields = report_signed_fields(REPORT_KIND_POST_APPLY_SMOKE, report)
    mislabelled = _forged_report_signature(
        report,
        purpose="nexus.zero_trust_v2.report",
        label_kind=REPORT_KIND_ROLLOUT,
        fields=fields,
        key="k",
    )
    assert not verify_report_signature(mislabelled, kind=REPORT_KIND_POST_APPLY_SMOKE, secret="k")
