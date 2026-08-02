from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class EpistemicAuthorityBoundary:
    identity_authority: str = "nexus.lifecycle"
    task_authority: str = "nexus.task_card"
    receipt_authority: str = "nexus.receipt"
    claim_boundary_authority: str = "nexus.evidence.claim_boundary"
    claim_evidence_authority: str = "nexus.contracts.claim_evidence_read_model"
    replay_authority: str = "nexus.replay"
    acceptance_authority: str = "nexus.acceptance"
    integration_authority: str = "owner_or_formal_integrator"
    profile_domain_authority: str = "nexus.research.epistemic_profile"

    profile_may_update_runtime: bool = False
    profile_may_approve_candidate: bool = False
    profile_may_integrate: bool = False
    profile_may_push: bool = False
    profile_may_unlock_public_claim: bool = False
    profile_may_unlock_public_benchmark: bool = False
    profile_may_claim_production_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_authority": self.identity_authority,
            "task_authority": self.task_authority,
            "receipt_authority": self.receipt_authority,
            "claim_boundary_authority": self.claim_boundary_authority,
            "claim_evidence_authority": self.claim_evidence_authority,
            "replay_authority": self.replay_authority,
            "acceptance_authority": self.acceptance_authority,
            "integration_authority": self.integration_authority,
            "profile_domain_authority": self.profile_domain_authority,
            "profile_may_update_runtime": self.profile_may_update_runtime,
            "profile_may_approve_candidate": self.profile_may_approve_candidate,
            "profile_may_integrate": self.profile_may_integrate,
            "profile_may_push": self.profile_may_push,
            "profile_may_unlock_public_claim": self.profile_may_unlock_public_claim,
            "profile_may_unlock_public_benchmark": self.profile_may_unlock_public_benchmark,
            "profile_may_claim_production_ready": self.profile_may_claim_production_ready,
        }


def default_epistemic_authority_boundary() -> EpistemicAuthorityBoundary:
    return EpistemicAuthorityBoundary()


def validate_epistemic_authority_payload(payload: Mapping[str, Any]) -> tuple[str, ...]:
    blockers: list[str] = []
    receipt_auth = payload.get("receipt_authority", "nexus.receipt")
    if receipt_auth != "nexus.receipt":
        blockers.append("EP_AUTHORITY_RECEIPT_OVERRIDE")

    acceptance_auth = payload.get("acceptance_authority", "nexus.acceptance")
    if acceptance_auth != "nexus.acceptance":
        blockers.append("EP_AUTHORITY_ACCEPTANCE_OVERRIDE")

    if bool(payload.get("profile_may_update_runtime", False)):
        blockers.append("EP_AUTHORITY_RUNTIME_UNLOCK")

    if bool(payload.get("profile_may_unlock_public_claim", False)):
        blockers.append("EP_AUTHORITY_PUBLIC_CLAIM_UNLOCK")

    if bool(payload.get("profile_may_unlock_public_benchmark", False)):
        blockers.append("EP_AUTHORITY_PUBLIC_BENCHMARK_UNLOCK")

    if bool(payload.get("profile_may_integrate", False)):
        blockers.append("EP_AUTHORITY_INTEGRATION_UNLOCK")

    if bool(payload.get("profile_may_claim_production_ready", False)):
        blockers.append("EP_AUTHORITY_PRODUCTION_UNLOCK")

    return tuple(blockers)
