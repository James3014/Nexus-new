from dataclasses import dataclass
from enum import Enum

from product.evidence import IntegrityStatus, ObservationStatus


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED_VERIFICATION = "FAILED_VERIFICATION"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    failed_checks: tuple[str, ...] = ()
    integrity: IntegrityStatus = IntegrityStatus.VALID

    def __post_init__(self):
        if not isinstance(self.status, VerificationStatus):
            raise TypeError("status must be VerificationStatus")
        if not isinstance(self.integrity, IntegrityStatus):
            raise TypeError("integrity must be IntegrityStatus")


def verify(contract, change_set, plan, evidence):
    integrity = evidence.integrity(contract, change_set, plan)
    if integrity is not IntegrityStatus.VALID:
        return VerificationResult(VerificationStatus.UNVERIFIABLE, integrity=integrity)
    if set(change_set.paths) - set(contract.allowed_paths):
        return VerificationResult(VerificationStatus.FAILED_VERIFICATION)
    if set(contract.required_verifier_ids) != set(plan.required_verifier_ids):
        return VerificationResult(VerificationStatus.UNVERIFIABLE)
    obs = {o.verifier_id: o for o in evidence.observations}
    observed_ids = set(obs)
    if observed_ids != set(plan.required_verifier_ids):
        return VerificationResult(VerificationStatus.UNVERIFIABLE)
    if any(
        o.status not in {ObservationStatus.PASS, ObservationStatus.FAIL}
        for o in evidence.observations
    ):
        return VerificationResult(VerificationStatus.UNVERIFIABLE)
    missing = tuple(
        x
        for x in contract.required_verifier_ids
        if x not in obs or x not in plan.required_verifier_ids
    )
    if missing or not evidence.observations:
        return VerificationResult(VerificationStatus.UNVERIFIABLE, missing)
    failed = tuple(
        x for x in contract.required_verifier_ids if obs[x].status is not ObservationStatus.PASS
    )
    return VerificationResult(
        VerificationStatus.FAILED_VERIFICATION if failed else VerificationStatus.VERIFIED, failed
    )
