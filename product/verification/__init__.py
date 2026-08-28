from dataclasses import dataclass
from enum import Enum

from product.evidence import IntegrityStatus, ObservationStatus


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED_VERIFICATION = "FAILED_VERIFICATION"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True, init=False)
class VerificationResult:
    status: VerificationStatus
    reason_codes: tuple[str, ...] = ()
    integrity: IntegrityStatus = IntegrityStatus.VALID

    def __init__(self, status, reason_codes=(), integrity=IntegrityStatus.VALID, **kwargs):
        if kwargs.pop("_token", None) is not _INTERNAL_TOKEN:
            raise TypeError("VerificationResult is created by reduce_verification")
        if "failed_checks" in kwargs:
            if reason_codes != ():
                raise TypeError("use reason_codes or failed_checks, not both")
            reason_codes = kwargs.pop("failed_checks")
        if kwargs:
            raise TypeError(f"unexpected arguments: {', '.join(kwargs)}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(self, "integrity", integrity)
        self.__post_init__()

    def __post_init__(self):
        if not isinstance(self.status, VerificationStatus):
            raise TypeError("status must be VerificationStatus")
        if not isinstance(self.integrity, IntegrityStatus):
            raise TypeError("integrity must be IntegrityStatus")
        if not isinstance(self.reason_codes, tuple):
            raise TypeError("reason_codes must be a tuple")
        if len(self.reason_codes) > 64:
            raise ValueError("reason_codes is bounded")
        for code in self.reason_codes:
            if not isinstance(code, str) or not code or code != code.strip() or len(code) > 128:
                raise ValueError("reason_codes must contain bounded nonblank strings")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("reason_codes must be unique and sorted")
        if self.status is VerificationStatus.VERIFIED and (
            self.integrity is not IntegrityStatus.VALID or self.reason_codes
        ):
            raise ValueError("VERIFIED requires valid integrity and no failed checks")
        if (
            self.integrity is not IntegrityStatus.VALID
            and self.status is not VerificationStatus.UNVERIFIABLE
        ):
            raise ValueError("non-valid integrity requires UNVERIFIABLE status")

    @property
    def failed_checks(self):
        return self.reason_codes

_INTERNAL_TOKEN = object()


def reduce_verification(condition, observations=(), reasons=()):
    if not isinstance(condition, IntegrityStatus):
        raise TypeError("condition must be IntegrityStatus")
    codes = list(reasons)
    if condition is IntegrityStatus.SCOPE_ESCAPE:
        status, integrity = VerificationStatus.FAILED_VERIFICATION, IntegrityStatus.VALID
    elif condition is not IntegrityStatus.VALID:
        codes.append(condition.value)
        status, integrity = VerificationStatus.UNVERIFIABLE, condition
    elif not isinstance(observations, tuple):
        status, integrity = VerificationStatus.UNVERIFIABLE, IntegrityStatus.MALFORMED
        codes.append(IntegrityStatus.MALFORMED.value)
    elif not observations:
        status, integrity = VerificationStatus.UNVERIFIABLE, IntegrityStatus.MISSING
        codes.append(IntegrityStatus.MISSING.value)
    elif any(type(item) is str for item in observations):
        status, integrity = VerificationStatus.UNVERIFIABLE, IntegrityStatus.LEGACY_NON_CERTIFIABLE
        codes.append(IntegrityStatus.LEGACY_NON_CERTIFIABLE.value)
    elif not all(isinstance(item, ObservationStatus) for item in observations):
        status, integrity = VerificationStatus.UNVERIFIABLE, IntegrityStatus.MALFORMED
        codes.append(IntegrityStatus.MALFORMED.value)
    elif any(item is ObservationStatus.FAIL for item in observations):
        status, integrity = VerificationStatus.FAILED_VERIFICATION, IntegrityStatus.VALID
    else:
        status, integrity = VerificationStatus.VERIFIED, IntegrityStatus.VALID
    return VerificationResult(status, tuple(sorted(set(codes))), integrity, _token=_INTERNAL_TOKEN)


def verify(contract, change_set, plan, evidence):
    integrity = evidence.integrity(contract, change_set, plan)
    if integrity is not IntegrityStatus.VALID:
        return reduce_verification(integrity)
    if set(change_set.paths) - set(contract.allowed_paths):
        return reduce_verification(IntegrityStatus.SCOPE_ESCAPE)
    if set(contract.required_verifier_ids) != set(plan.required_verifier_ids):
        return reduce_verification(IntegrityStatus.MISSING)
    obs = {o.verifier_id: o for o in evidence.observations}
    observed_ids = set(obs)
    if observed_ids != set(plan.required_verifier_ids):
        return reduce_verification(IntegrityStatus.MISSING)
    if any(
        o.status not in {ObservationStatus.PASS, ObservationStatus.FAIL}
        for o in evidence.observations
    ):
        return reduce_verification(IntegrityStatus.MALFORMED)
    missing = tuple(
        x
        for x in contract.required_verifier_ids
        if x not in obs or x not in plan.required_verifier_ids
    )
    if missing or not evidence.observations:
        return reduce_verification(IntegrityStatus.MISSING, reasons=missing)
    failed = tuple(
        x for x in contract.required_verifier_ids if obs[x].status is not ObservationStatus.PASS
    )
    return reduce_verification(IntegrityStatus.VALID, tuple(obs[x].status for x in contract.required_verifier_ids), failed)
