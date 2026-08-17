from __future__ import annotations

import hashlib

import pytest

from nexus.contracts.changeset_certification import (
    CHANGESET_CERTIFICATION_SCHEMA,
    CLAIM_CEILING,
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
    result = certify_changeset({
        "change_set": _identity(),
        "evidence": [_evidence()],
        "status": "BLOCKED",
    })

    assert result.status is CertificationStatus.REJECTED
    assert result.reason_codes == ("status_substitution",)


def test_missing_change_set_is_blocked() -> None:
    result = certify_changeset({"evidence": [_evidence()]})

    assert result.status is CertificationStatus.BLOCKED
    assert result.reason_codes == ("change_set_missing",)


def test_canonical_hash_binding_rejects_tamper() -> None:
    result = certify_changeset({"change_set": _identity(), "evidence": [_evidence()]})
    tampered = certify_changeset({
        "change_set": _identity(),
        "evidence": [_evidence()],
        "canonical_hash": result.canonical_hash().replace("a", "c", 1),
    })

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


def _envelope(*, verifier_status: str = "PASS") -> dict[str, object]:
    manifest: dict[str, object] = {
        "manifest_id": "manifest-1",
        "task_id": "task-367",
        "attempt_id": "attempt-1",
        "source": "source-tree-1",
        "tree": "tree-base-1",
        "verifiers": [
            {
                "verifier_id": "pytest",
                "artifact_id": "pytest:attempt-1",
                "artifact_hash": "sha256:" + "d" * 64,
                "status": verifier_status,
            }
        ],
    }
    manifest["manifest_hash"] = canonical_hash(manifest)
    payload: dict[str, object] = {
        "schema": CHANGESET_CERTIFICATION_SCHEMA,
        "version": 1,
        "task": {"task_id": "task-367", "attempt_id": "attempt-1"},
        "repository": {"repository": "James3014/Nexus-new", "source": "source-tree-1"},
        "base": {"commit": "base-commit-1", "tree": "tree-base-1"},
        "diff": {
            "hash": "sha256:" + "a" * 64,
            "paths": ["nexus/contracts/changeset_certification.py"],
        },
        "allowed_scope": {
            "paths": ["nexus/contracts/changeset_certification.py"],
            "deletion_policy": "FORBID",
        },
        "candidate": {
            "commit": "candidate-1",
            "tree": "tree-candidate-1",
            "diff_hash": "sha256:" + "b" * 64,
        },
        "verifier_manifest": manifest,
        "disposition": "CERTIFIED",
        "reasons": [],
        "claim_ceiling": CLAIM_CEILING,
    }
    payload["canonical_payload_hash"] = canonical_hash(payload)
    return payload


def test_full_envelope_certifies_and_validates() -> None:
    payload = _envelope()
    result = certify_changeset(payload)
    assert result.status is CertificationStatus.CERTIFIED
    assert validate_changeset_certification(result) == ()
    assert result.to_dict()["version"] == 1


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda value: value["task"].__setitem__("attempt_id", "other"), "cross_binding_mismatch"),
        (
            lambda value: value["verifier_manifest"].__setitem__("source", "other"),
            "cross_binding_mismatch",
        ),
        (
            lambda value: value["verifier_manifest"]["verifiers"][0].__setitem__(
                "artifact_hash", "sha256:" + "e" * 64
            ),
            "payload_hash_mismatch",
        ),
        (lambda value: value.__setitem__("reasons", ["not-a-reason"]), "reason_invalid"),
        (lambda value: value.__setitem__("unknown", True), "unknown_field"),
    ],
)
def test_hostile_envelope_substitutions_never_certify(mutation, reason: str) -> None:
    payload = _envelope()
    mutation(payload)
    result = certify_changeset(payload)
    assert result.status is not CertificationStatus.CERTIFIED
    assert reason in result.reason_codes


def test_failed_verifier_rejects_and_missing_manifest_blocks() -> None:
    failed = certify_changeset(_envelope(verifier_status="FAIL"))
    assert failed.status is CertificationStatus.REJECTED
    assert failed.reason_codes == ("verifier_failed",)
    missing = _envelope()
    missing.pop("verifier_manifest")
    blocked = certify_changeset(missing)
    assert blocked.status is CertificationStatus.BLOCKED
    assert blocked.reason_codes == ("verifier_manifest_missing",)


def test_semantically_unordered_envelope_lists_have_same_hash() -> None:
    left: dict[str, object] = _envelope()
    right: dict[str, object] = _envelope()
    left_diff = left["diff"]
    right_diff = right["diff"]
    assert isinstance(left_diff, dict)
    assert isinstance(right_diff, dict)
    left_diff["paths"] = ["z.py", "a.py"]
    right_diff["paths"] = ["a.py", "z.py"]
    assert canonical_json(left_diff) == canonical_json(right_diff)
