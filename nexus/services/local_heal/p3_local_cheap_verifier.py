from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class P3LocalCheapVerifierResult:
    """P3-D: Local cheap verifier stub contract.

    Shadow-only: records whether candidate would be eligible for cheap screening.
    Cannot mark solved, claim eligible, or replace full verifier.
    """
    enabled: bool
    authority: str
    candidate_available: bool
    canonical_candidate_hash: str
    cheap_verifier_planned: bool
    cheap_verifier_invoked: bool
    cheap_verifier_result: str
    cheap_verifier_confidence: float
    full_verifier_required: bool
    claim_gate_required: bool
    solved_claim_allowed: bool
    public_claim_allowed: bool
    runtime_behavior_changed: bool
    blocked_reason: str
    reason: str


def compute_p3_cheap_verifier(
    cloud_stub_metadata: dict[str, Any],
) -> P3LocalCheapVerifierResult:
    """Compute cheap verifier result from cloud candidate stub metadata.

    Shadow-only mode: no verifier invocation, no runtime behavior change.
    """
    candidate_generated = bool(cloud_stub_metadata.get("p3_cloud_stub_candidate_generated", False))
    canonical_available = bool(cloud_stub_metadata.get("p3_cloud_stub_canonical_candidate_available", False))
    candidate_hash = str(cloud_stub_metadata.get("p3_cloud_stub_candidate_raw_output_hash", "") or "")
    blocked_reason = str(cloud_stub_metadata.get("p3_cloud_stub_blocked_reason", "") or "")

    cheap_verifier_planned = candidate_generated or canonical_available
    cheap_verifier_result = "not_run_shadow_only" if cheap_verifier_planned else "not_applicable"
    cheap_verifier_confidence = 0.0

    reason_parts = []
    if not candidate_generated and not canonical_available:
        reason_parts.append("no_candidate_available")
    if blocked_reason:
        reason_parts.append(f"blocked:{blocked_reason}")
    if not reason_parts:
        reason_parts.append("cheap_verifier_shadow_only")
    reason = ";".join(reason_parts)

    return P3LocalCheapVerifierResult(
        enabled=True,
        authority="shadow_only",
        candidate_available=candidate_generated or canonical_available,
        canonical_candidate_hash=candidate_hash,
        cheap_verifier_planned=cheap_verifier_planned,
        cheap_verifier_invoked=False,
        cheap_verifier_result=cheap_verifier_result,
        cheap_verifier_confidence=cheap_verifier_confidence,
        full_verifier_required=True,
        claim_gate_required=True,
        solved_claim_allowed=False,
        public_claim_allowed=False,
        runtime_behavior_changed=False,
        blocked_reason=blocked_reason if not cheap_verifier_planned else "",
        reason=reason,
    )


def p3_cheap_verifier_to_dict(result: P3LocalCheapVerifierResult) -> dict[str, Any]:
    """Convert P3LocalCheapVerifierResult to JSON-serializable dict."""
    return {
        "p3_cheap_verifier_enabled": result.enabled,
        "p3_cheap_verifier_authority": result.authority,
        "p3_cheap_verifier_candidate_available": result.candidate_available,
        "p3_cheap_verifier_canonical_candidate_hash": result.canonical_candidate_hash,
        "p3_cheap_verifier_planned": result.cheap_verifier_planned,
        "p3_cheap_verifier_invoked": result.cheap_verifier_invoked,
        "p3_cheap_verifier_result": result.cheap_verifier_result,
        "p3_cheap_verifier_confidence": result.cheap_verifier_confidence,
        "p3_cheap_verifier_full_verifier_required": result.full_verifier_required,
        "p3_cheap_verifier_claim_gate_required": result.claim_gate_required,
        "p3_cheap_verifier_solved_claim_allowed": result.solved_claim_allowed,
        "p3_cheap_verifier_public_claim_allowed": result.public_claim_allowed,
        "p3_cheap_verifier_runtime_behavior_changed": result.runtime_behavior_changed,
        "p3_cheap_verifier_blocked_reason": result.blocked_reason,
        "p3_cheap_verifier_reason": result.reason,
    }
