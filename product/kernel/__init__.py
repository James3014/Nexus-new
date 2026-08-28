from dataclasses import dataclass

from product.certification import CertificationDisposition, CertificationPolicy, certify_result
from product.evidence import (
    AcceptanceContract,
    ChangeSet,
    EvidenceBundle,
    VerificationPlan,
    _hash,
    _require_hash,
)
from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
from product.verification import VerificationResult, verify

CLAIM_CEILING = (
    "NO_MERGE_AUTHORIZATION",
    "NO_DEPLOYMENT_TRUTH",
    "NO_OUTCOME_TRUTH",
    "NO_PRODUCTION_READINESS",
    "NO_PUBLIC_PROTOCOL_STABILITY",
)


@dataclass(frozen=True)
class CertificationInput:
    contract: AcceptanceContract
    change_set: ChangeSet
    plan: VerificationPlan
    evidence: EvidenceBundle
    policy_accepted: bool | None = None
    authority_present: bool | None = None
    approval_present: bool | None = None
    signing_present: bool | None = None


@dataclass(frozen=True)
class Receipt:
    acceptance_contract_hash: str
    change_set_hash: str
    verification_plan_hash: str
    evidence_hash: str
    verification: VerificationResult
    disposition: CertificationDisposition
    policy: CertificationPolicy
    claim_ceiling: tuple[str, ...] = CLAIM_CEILING
    protocol_version: str = PUBLIC_PROTOCOL_VERSION
    implementation_schema: str = IMPLEMENTATION_SCHEMA
    claimed_receipt_hash: str | None = None

    def __post_init__(self):
        for field in (
            "acceptance_contract_hash",
            "change_set_hash",
            "verification_plan_hash",
            "evidence_hash",
        ):
            _require_hash(getattr(self, field), field)
        if self.claimed_receipt_hash is not None:
            _require_hash(self.claimed_receipt_hash, "claimed_receipt_hash")

    @property
    def canonical_value(self):
        return (
            self.acceptance_contract_hash,
            self.change_set_hash,
            self.verification_plan_hash,
            self.evidence_hash,
            self.verification.status.value,
            self.verification.reason_codes,
            self.verification.integrity.value,
            self.disposition.value,
            self.policy.accepted,
            self.policy.authority_present,
            self.policy.approval_present,
            self.policy.signing_present,
            self.claim_ceiling,
            self.protocol_version,
            self.implementation_schema,
        )

    @property
    def hash(self):
        return _hash(self.canonical_value)

    def validate(self):
        return self.claimed_receipt_hash is None or self.claimed_receipt_hash == self.hash


@dataclass(frozen=True)
class CertificationResult:
    verification: VerificationResult
    disposition: CertificationDisposition
    receipt: Receipt


def certify(input: CertificationInput):
    result = verify(input.contract, input.change_set, input.plan, input.evidence)
    policy = CertificationPolicy(
        input.policy_accepted,
        input.authority_present,
        input.approval_present,
        input.signing_present,
    )
    disposition = certify_result(result, policy)
    receipt = Receipt(
        input.contract.hash,
        input.change_set.hash,
        input.plan.hash,
        input.evidence.hash,
        result,
        disposition,
        policy,
    )
    return CertificationResult(result, disposition, receipt)


def validate_receipt(receipt: Receipt, input: CertificationInput) -> bool:
    expected = certify(input).receipt
    return receipt.hash == expected.hash and receipt.validate()
