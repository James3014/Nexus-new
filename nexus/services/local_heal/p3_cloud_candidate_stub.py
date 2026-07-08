from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CloudCandidateStubResult:
    """P3-C: Cloud candidate stub contract.

    Shadow-only: accepts compact diagnosis and returns stub result.
    No real cloud call. No API key. No network.
    """
    enabled: bool
    authority: str
    cloud_provider: str
    cloud_model: str
    compact_prompt_hash: str
    compact_prompt_token_estimate: int
    cloud_call_planned: bool
    cloud_call_invoked: bool
    cloud_used: bool
    candidate_generated: bool
    candidate_source: str
    candidate_raw_output_hash: str
    candidate_normalized_patch_hash: str
    canonical_candidate_available: bool
    blocked_reason: str
    runtime_behavior_changed: bool
    claim_eligible: bool
    public_claim_allowed: bool
    reason: str


def compute_cloud_candidate_stub(
    diagnosis_metadata: dict[str, Any],
    *,
    cloud_provider: str = "none",
    cloud_model: str = "none",
    canonical_candidate: dict[str, Any] | None = None,
) -> CloudCandidateStubResult:
    """Compute cloud candidate stub result from diagnosis metadata.

    Shadow-only mode: no cloud calls, no runtime behavior change.
    """
    cloud_ready = bool(diagnosis_metadata.get("p3_diagnosis_cloud_ready", False))
    diagnosis_reason = str(diagnosis_metadata.get("p3_diagnosis_reason", "") or "")
    compact_prompt_hash = str(diagnosis_metadata.get("p3_diagnosis_compact_prompt_hash", "") or "")
    compact_prompt_token_estimate = int(diagnosis_metadata.get("p3_diagnosis_compact_prompt_token_estimate", 0) or 0)

    cloud_call_planned = cloud_ready
    blocked_reason = "" if cloud_ready else f"cloud_not_ready:{diagnosis_reason}"

    candidate_generated = False
    candidate_raw_output_hash = ""
    candidate_normalized_patch_hash = ""
    canonical_candidate_available = False

    if canonical_candidate:
        candidate_generated = bool(canonical_candidate.get("candidate_patch", ""))
        candidate_raw_output_hash = str(canonical_candidate.get("raw_output_hash", "") or "")
        candidate_normalized_patch_hash = str(canonical_candidate.get("normalized_patch_hash", "") or "")
        canonical_candidate_available = bool(candidate_raw_output_hash)

    reason_parts = []
    if not cloud_ready:
        reason_parts.append("cloud_not_ready")
    if not candidate_generated:
        reason_parts.append("cloud_stub_no_real_call")
    if not reason_parts:
        reason_parts.append("stub_complete")
    reason = ";".join(reason_parts)

    return CloudCandidateStubResult(
        enabled=True,
        authority="shadow_only",
        cloud_provider=cloud_provider,
        cloud_model=cloud_model,
        compact_prompt_hash=compact_prompt_hash,
        compact_prompt_token_estimate=compact_prompt_token_estimate,
        cloud_call_planned=cloud_call_planned,
        cloud_call_invoked=False,
        cloud_used=False,
        candidate_generated=candidate_generated,
        candidate_source="cloud_stub",
        candidate_raw_output_hash=candidate_raw_output_hash,
        candidate_normalized_patch_hash=candidate_normalized_patch_hash,
        canonical_candidate_available=canonical_candidate_available,
        blocked_reason=blocked_reason,
        runtime_behavior_changed=False,
        claim_eligible=False,
        public_claim_allowed=False,
        reason=reason,
    )


def p3_cloud_stub_to_dict(stub: CloudCandidateStubResult) -> dict[str, Any]:
    """Convert CloudCandidateStubResult to JSON-serializable dict."""
    return {
        "p3_cloud_candidate_stub_enabled": stub.enabled,
        "p3_cloud_candidate_authority": stub.authority,
        "p3_cloud_stub_provider": stub.cloud_provider,
        "p3_cloud_stub_model": stub.cloud_model,
        "p3_cloud_stub_compact_prompt_hash": stub.compact_prompt_hash,
        "p3_cloud_stub_compact_prompt_token_estimate": stub.compact_prompt_token_estimate,
        "p3_cloud_stub_call_planned": stub.cloud_call_planned,
        "p3_cloud_stub_call_invoked": stub.cloud_call_invoked,
        "p3_cloud_stub_used": stub.cloud_used,
        "p3_cloud_stub_candidate_generated": stub.candidate_generated,
        "p3_cloud_stub_candidate_source": stub.candidate_source,
        "p3_cloud_stub_candidate_raw_output_hash": stub.candidate_raw_output_hash,
        "p3_cloud_stub_candidate_normalized_patch_hash": stub.candidate_normalized_patch_hash,
        "p3_cloud_stub_canonical_candidate_available": stub.canonical_candidate_available,
        "p3_cloud_stub_blocked_reason": stub.blocked_reason,
        "p3_cloud_stub_runtime_behavior_changed": stub.runtime_behavior_changed,
        "p3_cloud_stub_claim_eligible": stub.claim_eligible,
        "p3_cloud_stub_public_claim_allowed": stub.public_claim_allowed,
        "p3_cloud_stub_reason": stub.reason,
    }
