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

    @classmethod
    def reduce(cls, condition, observations=(), reasons=(), *, complete=False, scope_escape=False):
        if not isinstance(condition, IntegrityStatus):
            raise TypeError("condition must be IntegrityStatus")
        codes = list(reasons)
        if scope_escape:
            return cls(VerificationStatus.FAILED_VERIFICATION, tuple(sorted(set(codes + ["SCOPE_ESCAPE"]))))
        if condition is not IntegrityStatus.VALID:
            return cls(VerificationStatus.UNVERIFIABLE, tuple(sorted(set(codes + [condition.value]))), condition)
        failures = [str(i) for i, observation in enumerate(observations) if observation is ObservationStatus.FAIL or observation == "FAIL"]
        codes.extend(failures)
        if failures:
            return cls(VerificationStatus.FAILED_VERIFICATION, tuple(sorted(set(codes))))
        return cls(VerificationStatus.VERIFIED if complete else VerificationStatus.UNVERIFIABLE, tuple(sorted(set(codes))))

    from_evidence = reduce


def verify(contract, change_set, plan, evidence):
    integrity = evidence.integrity(contract, change_set, plan)
    if integrity is not IntegrityStatus.VALID:
        return VerificationResult.reduce(integrity)
    if set(change_set.paths) - set(contract.allowed_paths):
        return VerificationResult.reduce(IntegrityStatus.VALID, scope_escape=True)
    if set(contract.required_verifier_ids) != set(plan.required_verifier_ids):
        return VerificationResult.reduce(IntegrityStatus.MISSING)
    obs = {o.verifier_id: o for o in evidence.observations}
    observed_ids = set(obs)
    if observed_ids != set(plan.required_verifier_ids):
        return VerificationResult.reduce(IntegrityStatus.MISSING)
    if any(
        o.status not in {ObservationStatus.PASS, ObservationStatus.FAIL}
        for o in evidence.observations
    ):
        return VerificationResult.reduce(IntegrityStatus.MALFORMED)
    missing = tuple(
        x
        for x in contract.required_verifier_ids
        if x not in obs or x not in plan.required_verifier_ids
    )
    if missing or not evidence.observations:
        return VerificationResult.reduce(IntegrityStatus.MISSING, missing)
    failed = tuple(
        x for x in contract.required_verifier_ids if obs[x].status is not ObservationStatus.PASS
    )
    return VerificationResult.reduce(IntegrityStatus.VALID, tuple(obs[x].status for x in contract.required_verifier_ids), failed, complete=not failed)
