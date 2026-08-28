import pytest

from product.certification import CertificationDisposition
from product.evidence import (
    AcceptanceContract,
    ChangeSet,
    EvidenceBundle,
    Observation,
    VerificationPlan,
)
from product.kernel import CertificationInput, certify
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
        CertificationInput(**case().__dict__, disposition="CERTIFIED")


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
        Observation("unit", "art", "hash", "PASS", scope_escaped=True)
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
