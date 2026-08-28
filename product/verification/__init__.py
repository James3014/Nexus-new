from dataclasses import dataclass
from enum import Enum
from product.evidence import AcceptanceContract, ChangeSet, EvidenceBundle, IntegrityStatus, VerificationPlan


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED_VERIFICATION = "FAILED_VERIFICATION"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    failed_checks: tuple[str, ...] = ()
    integrity: IntegrityStatus = IntegrityStatus.VALID


def verify(contract: AcceptanceContract, change_set: ChangeSet, plan: VerificationPlan, evidence: EvidenceBundle) -> VerificationResult:
    integrity = evidence.integrity(contract, change_set, plan)
    if integrity is not IntegrityStatus.VALID:
        return VerificationResult(VerificationStatus.FAILED_VERIFICATION if integrity is IntegrityStatus.SCOPE_ESCAPE else VerificationStatus.UNVERIFIABLE, integrity=integrity)
    observed = {o.check_id: o for o in evidence.observations}
    missing = tuple(check for check in contract.required_observations if check not in observed or check not in plan.required_checks)
    if missing:
        return VerificationResult(VerificationStatus.UNVERIFIABLE, missing)
    failed = tuple(check for check in contract.required_observations if observed[check].status != "PASS")
    return VerificationResult(VerificationStatus.FAILED_VERIFICATION if failed else VerificationStatus.VERIFIED, failed)
