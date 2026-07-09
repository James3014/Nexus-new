from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.services.local_heal.p3_local_cheap_verifier import (
    P3LocalCheapVerifierResult,
    compute_p3_cheap_verifier,
)


@dataclass(frozen=True)
class P3CheapVerifierRuntimeReceipt:
    """Runtime twin of P3LocalCheapVerifierResult with invoked=True."""
    enabled: bool
    authority: str
    candidate_available: bool
    canonical_candidate_hash: str
    cheap_verifier_planned: bool
    cheap_verifier_result: str
    cheap_verifier_confidence: float
    full_verifier_required: bool
    claim_gate_required: bool
    solved_claim_allowed: bool
    public_claim_allowed: bool
    blocked_reason: str
    reason: str
    cheap_verifier_invoked: bool = True
    runtime_behavior_changed: bool = True


def compute_p3_cheap_verifier_runtime(
    cloud_stub_metadata: dict[str, Any],
) -> P3CheapVerifierRuntimeReceipt:
    base = compute_p3_cheap_verifier(cloud_stub_metadata)

    return P3CheapVerifierRuntimeReceipt(
        enabled=base.enabled,
        authority="runtime_enabled",
        candidate_available=base.candidate_available,
        canonical_candidate_hash=base.canonical_candidate_hash,
        cheap_verifier_planned=base.cheap_verifier_planned,
        cheap_verifier_invoked=True,
        cheap_verifier_result="runtime_invoked",
        cheap_verifier_confidence=0.0,
        full_verifier_required=base.full_verifier_required,
        claim_gate_required=base.claim_gate_required,
        solved_claim_allowed=base.solved_claim_allowed,
        public_claim_allowed=base.public_claim_allowed,
        runtime_behavior_changed=True,
        blocked_reason="",
        reason=base.reason,
    )
