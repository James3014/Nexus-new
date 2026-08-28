from dataclasses import dataclass
import hashlib
import json
from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
from product.evidence import AcceptanceContract, ChangeSet, EvidenceBundle, Observation, VerificationPlan
from product.verification import VerificationResult, verify
from product.certification import CertificationDisposition, CertificationPolicy, certify_result


@dataclass(frozen=True)
class CertificationInput:
    contract: AcceptanceContract
    change_set: ChangeSet
    plan: VerificationPlan
    observations: tuple[Observation, ...]
    policy_accepted: bool | None = None
    authority_present: bool | None = None
    approval_present: bool | None = None
    signing_present: bool | None = None
    evidence_hash: str | None = None


@dataclass(frozen=True)
class Receipt:
    acceptance_contract_hash: str
    change_set_hash: str
    verification_plan_hash: str
    evidence_hash: str
    verification: VerificationResult
    disposition: CertificationDisposition
    policy: CertificationPolicy
    claim_ceiling: tuple[str, ...]
    protocol_version: str = PUBLIC_PROTOCOL_VERSION
    implementation_schema: str = IMPLEMENTATION_SCHEMA

    @property
    def hash(self) -> str:
        payload = {"acceptance_contract_hash": self.acceptance_contract_hash, "change_set_hash": self.change_set_hash, "verification_plan_hash": self.verification_plan_hash, "evidence_hash": self.evidence_hash, "verification": (self.verification.status.value, self.verification.failed_checks, self.verification.integrity.value), "disposition": self.disposition.value, "policy": self.policy.__dict__, "claim_ceiling": self.claim_ceiling, "protocol_version": self.protocol_version, "implementation_schema": self.implementation_schema}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def validate_hash(self, expected: str) -> bool:
        return self.hash == expected


@dataclass(frozen=True)
class CertificationResult:
    verification: VerificationResult
    disposition: CertificationDisposition
    receipt: Receipt


CLAIM_CEILING = ("NO_MERGE_AUTHORIZATION", "NO_DEPLOYMENT_TRUTH", "NO_OUTCOME_TRUTH", "NO_PRODUCTION_READINESS", "NO_PUBLIC_PROTOCOL_STABILITY")


def certify(input: CertificationInput) -> CertificationResult:
    evidence = EvidenceBundle(input.contract.hash, input.change_set.hash, input.plan.hash, tuple(input.observations), input.evidence_hash)
    result = verify(input.contract, input.change_set, input.plan, evidence)
    policy = CertificationPolicy(input.policy_accepted, input.authority_present, input.approval_present, input.signing_present)
    disposition = certify_result(result, policy)
    receipt = Receipt(input.contract.hash, input.change_set.hash, input.plan.hash, evidence.hash, result, disposition, policy, CLAIM_CEILING)
    return CertificationResult(result, disposition, receipt)
