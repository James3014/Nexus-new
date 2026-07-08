from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class P3LocalRetryStubResult:
    """P3-E: Local retry / cascade planning stub.

    Shadow-only: records planned retry behavior without executing.
    No local model calls, no patch generation, no verifier invocation.
    """
    enabled: bool
    authority: str
    retry_trigger: str
    retry_planned: bool
    retry_invoked: bool
    cascade_models_planned: list[str]
    cascade_models_invoked: list[str]
    retry_candidate_generated: bool
    retry_candidate_hash: str
    full_verifier_required: bool
    claim_gate_required: bool
    solved_claim_allowed: bool
    public_claim_allowed: bool
    runtime_behavior_changed: bool
    blocked_reason: str
    reason: str


def compute_p3_local_retry(
    cheap_verifier_metadata: dict[str, Any],
    cloud_stub_metadata: dict[str, Any] | None = None,
    cascade_models: list[str] | None = None,
) -> P3LocalRetryStubResult:
    """Compute local retry stub result from cheap verifier metadata.

    Shadow-only mode: no local model calls, no runtime behavior change.
    """
    cheap_verifier_result = str(cheap_verifier_metadata.get("p3_cheap_verifier_result", "") or "")
    candidate_available = bool(cheap_verifier_metadata.get("p3_cheap_verifier_candidate_available", False))
    blocked_reason = str(cheap_verifier_metadata.get("p3_cheap_verifier_blocked_reason", "") or "")

    retry_planned = cheap_verifier_result in ("not_run_shadow_only", "fail")
    retry_trigger = cheap_verifier_result if retry_planned else "no_trigger"

    cascade_planned = list(cascade_models or [])

    reason_parts = []
    if not candidate_available:
        reason_parts.append("no_candidate_available")
    if blocked_reason:
        reason_parts.append(f"blocked:{blocked_reason}")
    if not retry_planned:
        reason_parts.append("retry_not_planned")
    if not reason_parts:
        reason_parts.append("retry_shadow_only")
    reason = ";".join(reason_parts)

    return P3LocalRetryStubResult(
        enabled=True,
        authority="shadow_only",
        retry_trigger=retry_trigger,
        retry_planned=retry_planned,
        retry_invoked=False,
        cascade_models_planned=cascade_planned,
        cascade_models_invoked=[],
        retry_candidate_generated=False,
        retry_candidate_hash="",
        full_verifier_required=True,
        claim_gate_required=True,
        solved_claim_allowed=False,
        public_claim_allowed=False,
        runtime_behavior_changed=False,
        blocked_reason=blocked_reason if not retry_planned else "",
        reason=reason,
    )


def p3_retry_stub_to_dict(result: P3LocalRetryStubResult) -> dict[str, Any]:
    """Convert P3LocalRetryStubResult to JSON-serializable dict."""
    return {
        "p3_local_retry_enabled": result.enabled,
        "p3_local_retry_authority": result.authority,
        "p3_local_retry_trigger": result.retry_trigger,
        "p3_local_retry_planned": result.retry_planned,
        "p3_local_retry_invoked": result.retry_invoked,
        "p3_local_retry_cascade_models_planned": result.cascade_models_planned,
        "p3_local_retry_cascade_models_invoked": result.cascade_models_invoked,
        "p3_local_retry_candidate_generated": result.retry_candidate_generated,
        "p3_local_retry_candidate_hash": result.retry_candidate_hash,
        "p3_local_retry_full_verifier_required": result.full_verifier_required,
        "p3_local_retry_claim_gate_required": result.claim_gate_required,
        "p3_local_retry_solved_claim_allowed": result.solved_claim_allowed,
        "p3_local_retry_public_claim_allowed": result.public_claim_allowed,
        "p3_local_retry_runtime_behavior_changed": result.runtime_behavior_changed,
        "p3_local_retry_blocked_reason": result.blocked_reason,
        "p3_local_retry_reason": result.reason,
    }
