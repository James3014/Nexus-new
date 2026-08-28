from dataclasses import dataclass

from product.certification import CertificationDisposition, CertificationPolicy, certify_result
from product.evidence import (
    AcceptanceContract,
    ChangeSet,
    EvidenceBundle,
    VerificationPlan,
)
from product.verification import VerificationResult, verify
from product.certification.receipt import Receipt, CertificationResult, validate_receipt_envelope, CLAIM_CEILING


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
    expected = certify(input).receipt
    return receipt.hash == expected.hash and receipt.validate()

def validate_serialized_receipt(payload, input: CertificationInput) -> tuple[str, ...]:
    return validate_receipt_envelope(payload, certify(input).receipt)
