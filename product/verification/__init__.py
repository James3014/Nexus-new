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

    def __init__(self, *args, **kwargs):
        raise TypeError("VerificationResult is created by reduce_verification")

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

_REDUCED_RESULTS = set()


def is_reduced_result(result):
    return isinstance(result, VerificationResult) and id(result) in _REDUCED_RESULTS


def _validate_reasons(reasons):
    if not isinstance(reasons, tuple):
        raise TypeError("reasons must be a tuple")
    for reason in reasons:
        if not isinstance(reason, str) or not reason or reason != reason.strip() or len(reason) > 128:
            raise ValueError("reasons must contain bounded nonblank strings")
    if reasons != tuple(sorted(set(reasons))):
        raise ValueError("reasons must be unique and sorted")


def reduce_verification(condition, observations=(), reasons=()):
    if not isinstance(condition, IntegrityStatus):
        raise TypeError("condition must be IntegrityStatus")
    _validate_reasons(reasons)
    if not isinstance(observations, tuple):
        raise TypeError("observations must be a tuple")
    codes = list(reasons)
    if condition is IntegrityStatus.SCOPE_ESCAPE:
        codes.append("SCOPE_ESCAPE")
        status, integrity = VerificationStatus.FAILED_VERIFICATION, IntegrityStatus.VALID
    elif condition is not IntegrityStatus.VALID:
        codes.append(condition.value)
        status, integrity = VerificationStatus.UNVERIFIABLE, condition
    elif not observations:
        status, integrity = VerificationStatus.UNVERIFIABLE, IntegrityStatus.MISSING
        codes.append(IntegrityStatus.MISSING.value)
    elif any(type(item) is str for item in observations) and all(item in {"PASS", "FAIL"} for item in observations):
        status, integrity = VerificationStatus.UNVERIFIABLE, IntegrityStatus.LEGACY_NON_CERTIFIABLE
        codes.append(IntegrityStatus.LEGACY_NON_CERTIFIABLE.value)
    elif any(type(item) is str for item in observations):
        status, integrity = VerificationStatus.UNVERIFIABLE, IntegrityStatus.MALFORMED
        codes.append(IntegrityStatus.MALFORMED.value)
    elif not all(isinstance(item, ObservationStatus) for item in observations):
        status, integrity = VerificationStatus.UNVERIFIABLE, IntegrityStatus.MALFORMED
        codes.append(IntegrityStatus.MALFORMED.value)
    elif any(item is ObservationStatus.FAIL for item in observations):
        status, integrity = VerificationStatus.FAILED_VERIFICATION, IntegrityStatus.VALID
        codes.append("VERIFIER_FAILED")
    else:
        status, integrity = VerificationStatus.VERIFIED, IntegrityStatus.VALID
    result = object.__new__(VerificationResult)
    object.__setattr__(result, "status", status)
    object.__setattr__(result, "reason_codes", tuple(sorted(set(codes))) if status is not VerificationStatus.VERIFIED else ())
    object.__setattr__(result, "integrity", integrity)
    VerificationResult.__post_init__(result)
    _REDUCED_RESULTS.add(id(result))
    return result


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
