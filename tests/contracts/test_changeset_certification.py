from __future__ import annotations

import hashlib

import pytest

from nexus.contracts.changeset_certification import (
    CHANGESET_CERTIFICATION_SCHEMA,
    CertificationStatus,
    build_changeset_certification,
    canonical_hash,
    canonical_json,
    certify_changeset,
    validate_changeset_certification,
)


def _identity(**overrides: str) -> dict[str, str]:
    value = {
        "change_set_id": "cs-001",
        "source_revision": "source-abc",
        "target_revision": "target-def",
        "diff_hash": "sha256:" + "a" * 64,
    }
    value.update(overrides)
    return value


def _evidence(**overrides: str) -> dict[str, str]:
    value = {
        "evidence_id": "ev-001",
        "kind": "test",
        "content_hash": "sha256:" + "b" * 64,
        "source": "local-verifier",
    }
    value.update(overrides)
    return value


def test_complete_payload_certifies_with_stable_wire_contract() -> None:
    result = certify_changeset({"change_set": _identity(), "evidence": [_evidence()]})

    assert result.status is CertificationStatus.CERTIFIED
    payload = result.to_dict()
    assert payload["schema"] == CHANGESET_CERTIFICATION_SCHEMA
    assert payload["reason_codes"] == []
    assert validate_changeset_certification(result) == ()


def test_canonical_serialization_and_hash_are_order_independent() -> None:
    left = {"b": [2, 1], "a": {"z": True, "x": "value"}}
    right = {"a": {"x": "value", "z": True}, "b": [2, 1]}

    assert canonical_json(left) == canonical_json(right)
    expected = hashlib.sha256(canonical_json(left).encode()).hexdigest()
    assert canonical_hash(left) == f"sha256:{expected}"


def test_missing_evidence_is_blocked_not_certified() -> None:
    result = certify_changeset({"change_set": _identity()})

    assert result.status is CertificationStatus.BLOCKED
    assert result.reason_codes == ("evidence_missing",)


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (
            {"change_set": _identity(diff_hash="not-a-hash"), "evidence": [_evidence()]},
            "identity_diff_hash_invalid",
        ),
        (
            {"change_set": _identity(), "evidence": [{**_evidence(), "content_hash": "wrong"}]},
            "evidence_0_invalid",
        ),
        (
            {"change_set": _identity(), "evidence": [_evidence(), _evidence()]},
            "evidence_duplicate_id",
        ),
        ({"change_set": _identity(), "evidence": "not-a-list"}, "evidence_not_sequence"),
    ],
)
def test_hostile_identity_or_evidence_substitution_rejects(
    payload: dict[str, object], reason: str
) -> None:
    result = certify_changeset(payload)

    assert result.status is CertificationStatus.REJECTED
    assert reason in result.reason_codes


def test_explicit_status_cannot_override_derived_certification() -> None:
    result = certify_changeset(
        {"change_set": _identity(), "evidence": [_evidence()], "status": "BLOCKED"}
    )

    assert result.status is CertificationStatus.REJECTED
    assert result.reason_codes == ("status_substitution",)


def test_missing_change_set_is_blocked() -> None:
    result = certify_changeset({"evidence": [_evidence()]})

    assert result.status is CertificationStatus.BLOCKED
    assert result.reason_codes == ("change_set_missing",)


def test_canonical_hash_binding_rejects_tamper() -> None:
    result = certify_changeset({"change_set": _identity(), "evidence": [_evidence()]})
    tampered = certify_changeset(
        {
            "change_set": _identity(),
            "evidence": [_evidence()],
            "canonical_hash": result.canonical_hash().replace("a", "c", 1),
        }
    )

    assert tampered.status is CertificationStatus.REJECTED
    assert tampered.reason_codes == ("canonical_hash_mismatch",)


def test_builder_returns_only_contract_data_and_no_execution_authority() -> None:
    payload = build_changeset_certification(change_set=_identity(), evidence=[_evidence()])

    assert payload["status"] == "CERTIFIED"
    assert "runtime" not in payload
    assert "apply" not in payload
    assert payload["claim_boundary"]


def test_canonical_json_rejects_ambiguous_object_stringification() -> None:
    with pytest.raises(TypeError, match="unsupported canonical JSON value"):
        canonical_json({"value": object()})
