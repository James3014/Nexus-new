from dataclasses import dataclass
from enum import Enum

from product.verification import VerificationResult, VerificationStatus


class CertificationDisposition(str, Enum):
    CERTIFIED = "CERTIFIED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CertificationPolicy:
    accepted: bool | None = None
    authority_present: bool | None = None
    approval_present: bool | None = None
    signing_present: bool | None = None


def certify_result(
    result: VerificationResult, policy: CertificationPolicy
) -> CertificationDisposition:
    if (
        result.status is VerificationStatus.FAILED_VERIFICATION
        or result.integrity is not None
        and result.integrity.value == "TAMPERED"
    ):
        return CertificationDisposition.REJECTED
    if result.status is VerificationStatus.UNVERIFIABLE:
        return (
            CertificationDisposition.REJECTED
            if result.integrity.value == "TAMPERED"
            else CertificationDisposition.BLOCKED
        )
    if policy.accepted is False:
        return CertificationDisposition.REJECTED
    if any(
        value is not True
        for value in (
            policy.accepted,
            policy.authority_present,
            policy.approval_present,
            policy.signing_present,
        )
    ):
        return CertificationDisposition.BLOCKED
    return CertificationDisposition.CERTIFIED
