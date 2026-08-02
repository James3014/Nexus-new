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


CANONICAL_AUTHORITY_MAP = {
    "identity_authority": ("nexus.lifecycle", "EP_AUTHORITY_IDENTITY_OVERRIDE"),
    "task_authority": ("nexus.task_card", "EP_AUTHORITY_TASK_OVERRIDE"),
    "receipt_authority": ("nexus.receipt", "EP_AUTHORITY_RECEIPT_OVERRIDE"),
    "claim_boundary_authority": ("nexus.evidence.claim_boundary", "EP_AUTHORITY_CLAIM_BOUNDARY_OVERRIDE"),
    "claim_evidence_authority": ("nexus.contracts.claim_evidence_read_model", "EP_AUTHORITY_CLAIM_EVIDENCE_OVERRIDE"),
    "replay_authority": ("nexus.replay", "EP_AUTHORITY_REPLAY_OVERRIDE"),
    "acceptance_authority": ("nexus.acceptance", "EP_AUTHORITY_ACCEPTANCE_OVERRIDE"),
    "integration_authority": ("owner_or_formal_integrator", "EP_AUTHORITY_INTEGRATION_AUTHORITY_OVERRIDE"),
    "profile_domain_authority": ("nexus.research.epistemic_profile", "EP_AUTHORITY_PROFILE_DOMAIN_OVERRIDE"),
}

PERMISSION_FLAG_MAP = {
    "profile_may_update_runtime": "EP_AUTHORITY_RUNTIME_UNLOCK",
    "profile_may_approve_candidate": "EP_AUTHORITY_CANDIDATE_APPROVAL_UNLOCK",
    "profile_may_integrate": "EP_AUTHORITY_INTEGRATION_UNLOCK",
    "profile_may_push": "EP_AUTHORITY_PUSH_UNLOCK",
    "profile_may_unlock_public_claim": "EP_AUTHORITY_PUBLIC_CLAIM_UNLOCK",
    "profile_may_unlock_public_benchmark": "EP_AUTHORITY_PUBLIC_BENCHMARK_UNLOCK",
    "profile_may_claim_production_ready": "EP_AUTHORITY_PRODUCTION_UNLOCK",
}


def validate_epistemic_authority_payload(payload: Mapping[str, Any]) -> tuple[str, ...]:
    blockers: list[str] = []

    for field_name, (expected_val, blocker) in CANONICAL_AUTHORITY_MAP.items():
        val = payload.get(field_name, expected_val)
        if val != expected_val:
            blockers.append(blocker)

    for flag_name, blocker in PERMISSION_FLAG_MAP.items():
        if bool(payload.get(flag_name, False)):
            blockers.append(blocker)

    return tuple(blockers)
