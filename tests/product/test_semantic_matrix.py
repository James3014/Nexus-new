import pytest

from product.certification import CertificationDisposition, CertificationPolicy, certify_result
from product.evidence import IntegrityStatus, ObservationStatus
from product.verification import VerificationResult, VerificationStatus


@pytest.mark.parametrize(
    ("condition", "observations", "complete", "scope_escape", "status"),
    [
        (IntegrityStatus.VALID, (ObservationStatus.FAIL,), True, False, VerificationStatus.FAILED_VERIFICATION),
        (IntegrityStatus.VALID, (ObservationStatus.PASS,), True, True, VerificationStatus.FAILED_VERIFICATION),
        (IntegrityStatus.VALID, (ObservationStatus.PASS,), True, False, VerificationStatus.VERIFIED),
        (IntegrityStatus.MISSING, (), False, False, VerificationStatus.UNVERIFIABLE),
        (IntegrityStatus.STALE, (), False, False, VerificationStatus.UNVERIFIABLE),
        (IntegrityStatus.TAMPERED, (), False, False, VerificationStatus.UNVERIFIABLE),
        (IntegrityStatus.MALFORMED, (), False, False, VerificationStatus.UNVERIFIABLE),
        (IntegrityStatus.CROSS_BOUND, (), False, False, VerificationStatus.UNVERIFIABLE),
        (IntegrityStatus.DUPLICATE, (), False, False, VerificationStatus.UNVERIFIABLE),
        (IntegrityStatus.LEGACY_NON_CERTIFIABLE, (), False, False, VerificationStatus.UNVERIFIABLE),
    ],
)
def test_factual_reducer_matrix(condition, observations, complete, scope_escape, status):
    result = VerificationResult.reduce(condition, observations, complete=complete, scope_escape=scope_escape)
    assert result.status is status


def test_reason_codes_are_sorted_unique_and_compatibly_exposed():
    result = VerificationResult.reduce(IntegrityStatus.MALFORMED, reasons=("z", "a"))
    assert result.reason_codes == ("MALFORMED", "a", "z")
    assert result.failed_checks == result.reason_codes


def test_certification_reduces_only_from_factual_result():
    policy = CertificationPolicy(True, True, True, True)
    assert certify_result(VerificationResult.reduce(IntegrityStatus.TAMPERED), policy) is CertificationDisposition.REJECTED
    assert certify_result(VerificationResult.reduce(IntegrityStatus.MISSING), policy) is CertificationDisposition.BLOCKED
    assert certify_result(VerificationResult.reduce(IntegrityStatus.VALID, (ObservationStatus.PASS,), complete=True), policy) is CertificationDisposition.CERTIFIED
