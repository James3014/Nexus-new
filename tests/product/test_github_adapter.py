import hashlib

import pytest

from product.adapters.github import (
    GitHubPullRequestSnapshot,
    certify_pull_request,
    load_github_pull_request_snapshot,
    serialize_github_pull_request_snapshot,
    to_changeset,
)
from product.evidence import (
    AcceptanceContract,
    EvidenceBundle,
    Observation,
    ObservationStatus,
    VerificationPlan,
    _hash,
)
from product.verification import VerificationStatus


def snapshot():
    return GitHubPullRequestSnapshot(
        "octo", "repo", 7, "a" * 40, "b" * 40, "sha256:" + "c" * 64, ("src/a.py",)
    )


def certification_case():
    change = to_changeset(snapshot())
    contract = AcceptanceContract("ac", _hash("requirements"), ("unit",), ("src/a.py",), "FORBID")
    plan = VerificationPlan("plan", contract.hash, change.hash, ("unit",))
    evidence = EvidenceBundle(
        "bundle",
        contract.hash,
        change.hash,
        plan.hash,
        (Observation("unit", "artifact", _hash("artifact"), ObservationStatus.PASS),),
    )
    return contract, plan, evidence


def test_snapshot_mapping_and_serialized_replay_are_deterministic():
    value = snapshot()
    assert to_changeset(value) == to_changeset(
        load_github_pull_request_snapshot(serialize_github_pull_request_snapshot(value))
    )
    assert to_changeset(value).change_set_id == "github:octo/repo#pr-7@" + "b" * 40


def test_certification_delegates_with_explicit_policy_and_bound_evidence():
    contract, plan, evidence = certification_case()
    result = certify_pull_request(
        snapshot(),
        contract,
        plan,
        evidence,
        policy_accepted=True,
        authority_present=True,
        approval_present=True,
        signing_present=True,
    )
    assert result.verification.status is VerificationStatus.VERIFIED


@pytest.mark.parametrize(
    "field,value", [("pr_number", True), ("base_sha", "A" * 40), ("changed_paths", ("../unsafe",))]
)
def test_snapshot_rejects_malformed_values(field, value):
    values = serialize_github_pull_request_snapshot(snapshot())
    values[field] = value
    with pytest.raises((TypeError, ValueError)):
        load_github_pull_request_snapshot(values)


def test_snapshot_loader_rejects_unknown_or_claimed_hash_fields():
    values = serialize_github_pull_request_snapshot(snapshot())
    values["unknown"] = True
    with pytest.raises(ValueError):
        load_github_pull_request_snapshot(values)
    values = serialize_github_pull_request_snapshot(snapshot())
    values["snapshot_hash"] = hashlib.sha256(b"forged").hexdigest()
    with pytest.raises(ValueError):
        load_github_pull_request_snapshot(values)
