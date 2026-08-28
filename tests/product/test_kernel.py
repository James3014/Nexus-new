import pytest

from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
from product.evidence import AcceptanceContract, ChangeSet, Observation, VerificationPlan
from product.kernel import CertificationInput, certify
from product.verification import VerificationStatus
from product.certification import CertificationDisposition


def case(**kwargs):
    contract = AcceptanceContract("ac-1", ("unit", "lint"), ("src/a.py",))
    change = ChangeSet("cs-1", ("src/a.py",), "content-1")
    plan = VerificationPlan("vp-1", ("unit", "lint"), change.hash)
    observations = tuple(kwargs.pop("observations", (Observation("unit", "PASS"), Observation("lint", "PASS"))))
    return CertificationInput(contract, change, plan, observations=observations, **kwargs)


def test_happy_path_is_stable_and_bound():
    result = certify(case(policy_accepted=True, authority_present=True, approval_present=True, signing_present=True))
    assert result.verification.status is VerificationStatus.VERIFIED
    assert result.disposition is CertificationDisposition.CERTIFIED
    assert result.receipt.hash == certify(case(policy_accepted=True, authority_present=True, approval_present=True, signing_present=True)).receipt.hash


def test_fail_missing_and_scope_escape_are_fail_closed():
    failed = certify(case(observations=(Observation("unit", "FAIL"), Observation("lint", "PASS")), policy_accepted=True, authority_present=True, approval_present=True, signing_present=True))
    assert failed.verification.status is VerificationStatus.FAILED_VERIFICATION
    assert failed.disposition is CertificationDisposition.REJECTED
    missing = certify(case(observations=(Observation("unit", "PASS"),)))
    assert missing.verification.status is VerificationStatus.UNVERIFIABLE
    assert missing.disposition is CertificationDisposition.BLOCKED
    escaped = certify(case(observations=(Observation("unit", "PASS"), Observation("lint", "PASS", scope_escaped=True))))
    assert escaped.disposition is CertificationDisposition.REJECTED


def test_policy_and_prerequisites_are_certification_only():
    assert certify(case(policy_accepted=False)).disposition is CertificationDisposition.REJECTED
    assert certify(case(policy_accepted=None)).disposition is CertificationDisposition.BLOCKED
    assert certify(case(authority_present=False)).disposition is CertificationDisposition.BLOCKED


def test_protocol_versions_are_distinct():
    assert PUBLIC_PROTOCOL_VERSION != IMPLEMENTATION_SCHEMA


def test_kernel_input_does_not_accept_claimed_results():
    with pytest.raises(TypeError):
        CertificationInput(**case().__dict__, disposition="CERTIFIED")
