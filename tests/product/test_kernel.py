from typing import Any

import pytest

from product.certification import CertificationDisposition
from product.evidence import (
    AcceptanceContract,
    ChangeSet,
    EvidenceBundle,
    Observation,
    VerificationPlan,
)
from product.kernel import CertificationInput, certify, validate_receipt
from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
from product.verification import VerificationStatus


def case(**kwargs):
    contract = AcceptanceContract("ac-1", "req-1", ("unit", "lint"), ("src/a.py",), "DENY")
    change = ChangeSet("cs-1", "rev-a", "rev-b", "diff-1", ("src/a.py",))
    plan = VerificationPlan("vp-1", contract.hash, change.hash, ("unit", "lint"))
    observations = tuple(
        kwargs.pop(
            "observations",
            (
                Observation("unit", "art-u", "hash-u", "PASS"),
                Observation("lint", "art-l", "hash-l", "PASS"),
            ),
        )
    )
    evidence = EvidenceBundle("eb-1", contract.hash, change.hash, plan.hash, observations)
    kwargs.setdefault("policy_accepted", True)
    kwargs.setdefault("authority_present", True)
    kwargs.setdefault("approval_present", True)
    kwargs.setdefault("signing_present", True)
    return CertificationInput(contract, change, plan, evidence=evidence, **kwargs)


def test_happy_path_is_stable_and_bound():
    result = certify(
        case(
            policy_accepted=True,
            authority_present=True,
            approval_present=True,
            signing_present=True,
        )
    )
    assert result.verification.status is VerificationStatus.VERIFIED
    assert result.disposition is CertificationDisposition.CERTIFIED
    assert (
        result.receipt.hash
        == certify(
            case(
                policy_accepted=True,
                authority_present=True,
                approval_present=True,
                signing_present=True,
            )
        ).receipt.hash
    )


def test_fail_missing_and_scope_escape_are_fail_closed():
    failed = certify(
        case(
            observations=(
                Observation("unit", "u", "hu", "FAIL"),
                Observation("lint", "l", "hl", "PASS"),
            ),
            policy_accepted=True,
            authority_present=True,
            approval_present=True,
            signing_present=True,
        )
    )
    assert failed.verification.status is VerificationStatus.FAILED_VERIFICATION
    assert failed.disposition is CertificationDisposition.REJECTED
    missing = certify(case(observations=(Observation("unit", "u", "hu", "PASS"),)))
    assert missing.verification.status is VerificationStatus.UNVERIFIABLE
    assert missing.disposition is CertificationDisposition.BLOCKED


def test_policy_and_prerequisites_are_certification_only():
    assert certify(case(policy_accepted=False)).disposition is CertificationDisposition.REJECTED
    assert certify(case(policy_accepted=None)).disposition is CertificationDisposition.BLOCKED
    assert certify(case(authority_present=False)).disposition is CertificationDisposition.BLOCKED


def test_protocol_versions_are_distinct():
    assert PUBLIC_PROTOCOL_VERSION != IMPLEMENTATION_SCHEMA


def test_kernel_input_does_not_accept_claimed_results():
    with pytest.raises(TypeError):
        CertificationInput(**(case().__dict__ | {"disposition": "CERTIFIED"}))  # type: ignore[call-arg]


def test_scope_is_derived_and_evidence_is_exact():
    contract = AcceptanceContract("ac", "req", ("unit",), ("src/a.py",), "DENY")
    change = ChangeSet("cs", "a", "b", "d", ("src/secret.py",))
    plan = VerificationPlan("vp", contract.hash, change.hash, ("unit",))
    evidence = EvidenceBundle(
        "eb", contract.hash, change.hash, plan.hash, (Observation("unit", "art", "ah", "PASS"),)
    )
    result = certify(CertificationInput(contract, change, plan, evidence, True, True, True, True))
    assert result.verification.status is VerificationStatus.FAILED_VERIFICATION
    assert result.disposition is CertificationDisposition.REJECTED


def test_observation_has_no_caller_scope_flag_and_duplicate_identity_blocks():
    with pytest.raises(TypeError):
        Observation("unit", "art", "hash", "PASS", **{"scope_escaped": True})  # type: ignore[call-arg]
    contract = AcceptanceContract("ac", "req", ("unit", "lint"), ("src/a.py",), "DENY")
    change = ChangeSet("cs", "a", "b", "d", ("src/a.py",))
    plan = VerificationPlan("vp", contract.hash, change.hash, ("unit", "lint"))
    evidence = EvidenceBundle(
        "eb",
        contract.hash,
        change.hash,
        plan.hash,
        (Observation("unit", "a", "h", "PASS"), Observation("unit", "a", "h", "PASS")),
    )
    result = certify(CertificationInput(contract, change, plan, evidence, True, True, True, True))
    assert result.verification.status is VerificationStatus.UNVERIFIABLE


def test_receipt_round_trip_and_tamper_validation():
    result = certify(case())
    assert validate_receipt(result.receipt, case())
    from dataclasses import replace

    assert not validate_receipt(
        replace(result.receipt, disposition=CertificationDisposition.REJECTED), case()
    )


def test_stale_bindings_are_unverifiable():
    c = case().contract
    ch = case().change_set
    p = case().plan
    e = case().evidence
    stale = EvidenceBundle(
        e.bundle_id, "sha256:stale", e.change_set_hash, e.verification_plan_hash, e.observations
    )
    assert (
        certify(CertificationInput(c, ch, p, stale, True, True, True, True)).verification.status
        is VerificationStatus.UNVERIFIABLE
    )


def test_claimed_evidence_hash_tamper_rejects():
    x = case()
    e = x.evidence
    bad = EvidenceBundle(
        e.bundle_id,
        e.acceptance_contract_hash,
        e.change_set_hash,
        e.verification_plan_hash,
        e.observations,
        "sha256:bad",
    )
    r = certify(CertificationInput(x.contract, x.change_set, x.plan, bad, True, True, True, True))
    assert r.disposition is CertificationDisposition.REJECTED


@pytest.mark.parametrize(
    "field", ["policy_accepted", "authority_present", "approval_present", "signing_present"]
)
def test_each_missing_prerequisite_blocks_after_verified(field):
    values: dict[str, Any] = {
        k: True
        for k in ("policy_accepted", "authority_present", "approval_present", "signing_present")
    }
    values[field] = None
    r = certify(case(**values))
    assert (
        r.verification.status is VerificationStatus.VERIFIED
        and r.disposition is CertificationDisposition.BLOCKED
    )


def test_claim_ceiling_and_schema_contract():
    r = certify(case()).receipt
    assert set(r.claim_ceiling) == {
        "NO_MERGE_AUTHORIZATION",
        "NO_DEPLOYMENT_TRUTH",
        "NO_OUTCOME_TRUTH",
        "NO_PRODUCTION_READINESS",
        "NO_PUBLIC_PROTOCOL_STABILITY",
    }
    assert not hasattr(r, "kernel_version")


def test_invalid_status_is_unverifiable():
    x = case(
        observations=(Observation("unit", "u", "h", "MAYBE"), Observation("lint", "l", "h", "PASS"))
    )
    assert certify(x).verification.status is VerificationStatus.UNVERIFIABLE


def test_canonical_json_rejects_unsupported_values_and_sorts_sets():
    from product.evidence import canonical_json

    with pytest.raises(TypeError):
        canonical_json({1: "x"})
    with pytest.raises(TypeError):
        canonical_json({"x": object()})
    assert canonical_json(("b", "a")) != canonical_json(tuple(sorted(("b", "a"))))
