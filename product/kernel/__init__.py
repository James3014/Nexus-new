from dataclasses import dataclass

from product.certification import CertificationPolicy, certify_result
from product.certification.receipt import (
    CLAIM_CEILING,
    CertificationResult,
    Receipt,
    validate_receipt_envelope,
)
from product.evidence import (
    AcceptanceContract,
    ChangeSet,
    EvidenceBundle,
    VerificationPlan,
)
from product.verification import verify


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
    if type(receipt) is not Receipt:
        raise TypeError("receipt must be Receipt")
    expected = certify(input).receipt
    return receipt.hash == expected.hash and receipt.validate()


def validate_serialized_receipt(payload, input: CertificationInput) -> tuple[str, ...]:
    return validate_receipt_envelope(payload, certify(input).receipt)


__all__ = [
    "CLAIM_CEILING",
    "CertificationInput",
    "CertificationResult",
    "Receipt",
    "certify",
    "validate_receipt",
    "validate_receipt_envelope",
    "validate_serialized_receipt",
]
