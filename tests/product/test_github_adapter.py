import hashlib

import pytest

import product.adapters.github as github
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
from product.kernel import CertificationInput, certify
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
    reversed_value = GitHubPullRequestSnapshot(
        "octo", "repo", 7, "a" * 40, "b" * 40, "sha256:" + "c" * 64, ("z", "a")
    )
    assert to_changeset(reversed_value).paths == ("a", "z")
    assert serialize_github_pull_request_snapshot(reversed_value)["changed_paths"] == ["a", "z"]


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


def test_certification_matches_direct_kernel_and_omitted_policy_does_not_infer_authority():
    contract, plan, evidence = certification_case()
    direct = certify(
        CertificationInput(
            contract, to_changeset(snapshot()), plan, evidence, True, True, True, True
        )
    )
    explicit = github.certify_pull_request(
        snapshot(),
        contract,
        plan,
        evidence,
        policy_accepted=True,
        authority_present=True,
        approval_present=True,
        signing_present=True,
    )
    omitted = github.certify_pull_request(snapshot(), contract, plan, evidence)
    assert direct.receipt.hash == explicit.receipt.hash
    assert direct.verification == explicit.verification
    assert direct.receipt.hash != omitted.receipt.hash
    assert omitted.verification.status is VerificationStatus.VERIFIED
    assert omitted.disposition.value == "BLOCKED"


def test_github_name_grammar_prevents_change_set_id_collisions():
    left = GitHubPullRequestSnapshot(
        "a", "b.c", 1, "a" * 40, "b" * 40, "sha256:" + "c" * 64, ("x",)
    )
    right = GitHubPullRequestSnapshot(
        "a.b", "c", 1, "a" * 40, "b" * 40, "sha256:" + "c" * 64, ("x",)
    )
    assert to_changeset(left).change_set_id != to_changeset(right).change_set_id
    with pytest.raises(ValueError):
        GitHubPullRequestSnapshot(
            "a/b", "repo", 1, "a" * 40, "b" * 40, "sha256:" + "c" * 64, ("x",)
        )


def test_public_adapter_revalidates_forged_snapshot_after_module_rebinding(monkeypatch):
    values = vars(snapshot()).copy()
    values["diff_hash"] = "bad"
    forged = object.__new__(GitHubPullRequestSnapshot)
    for key, value in values.items():
        object.__setattr__(forged, key, value)
    monkeypatch.setattr(
        github, "certify", lambda *args, **kwargs: pytest.fail("rebound certify used")
    )
    monkeypatch.setattr(github, "ChangeSet", lambda *args: pytest.fail("rebound ChangeSet used"))
    with pytest.raises(ValueError):
        github.to_changeset(forged)


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
