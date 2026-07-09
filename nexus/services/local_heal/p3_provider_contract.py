from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class P3ProviderRequest:
    """P3-K3: Provider interface contract request.

    Pure contract: no network call, no API key, no SDK import.
    """
    provider_request_version: str
    provider_kind: str
    model_name: str
    compact_prompt_hash: str
    compact_prompt_token_estimate: int
    task_difficulty: str
    intended_topology: str
    env_guard_present: bool
    dry_run: bool
    network_allowed: bool
    api_key_required: bool
    reason: str


@dataclass(frozen=True)
class P3ProviderResponse:
    """P3-K3: Provider interface contract response.

    Pure contract: no network call, no API key, no SDK import.
    """
    provider_response_version: str
    provider_kind: str
    model_name: str
    request_accepted: bool
    provider_invoked: bool
    network_invoked: bool
    api_key_used: bool
    candidate_generated: bool
    candidate_raw_output_hash: str
    canonical_candidate_available: bool
    blocked_reason: str
    full_verifier_required: bool
    claim_gate_required: bool
    public_claim_allowed: bool
    production_ready: bool
    reason: str


def build_p3_provider_request(
    *,
    provider_kind: str = "none",
    model_name: str = "none",
    compact_prompt_hash: str = "",
    compact_prompt_token_estimate: int = 0,
    task_difficulty: str = "medium",
    intended_topology: str = "cloud_with_local_assist",
    env_guard_present: bool = False,
    dry_run: bool = True,
) -> P3ProviderRequest:
    """Build a P3 provider request contract object.

    Pure contract: no network call, no API key, no SDK import.
    """
    blocked_reasons = []

    if not env_guard_present:
        blocked_reasons.append("env_guard_missing")

    if not compact_prompt_hash:
        blocked_reasons.append("compact_prompt_hash_missing")

    if not dry_run:
        blocked_reasons.append("non_dry_run_not_allowed")

    reason = ";".join(blocked_reasons) if blocked_reasons else "contract_valid"

    return P3ProviderRequest(
        provider_request_version="1.0",
        provider_kind=provider_kind,
        model_name=model_name,
        compact_prompt_hash=compact_prompt_hash,
        compact_prompt_token_estimate=compact_prompt_token_estimate,
        task_difficulty=task_difficulty,
        intended_topology=intended_topology,
        env_guard_present=env_guard_present,
        dry_run=dry_run,
        network_allowed=False,
        api_key_required=False,
        reason=reason,
    )


def process_p3_provider_request(
    request: P3ProviderRequest,
    *,
    deterministic_candidate: dict[str, Any] | None = None,
) -> P3ProviderResponse:
    """Process a P3 provider request and return response.

    Pure contract: no network call, no API key, no SDK import.
    """
    blocked_reasons = []

    if not request.dry_run:
        blocked_reasons.append("non_dry_run_blocked")

    if not request.env_guard_present:
        blocked_reasons.append("env_guard_missing")

    if not request.compact_prompt_hash:
        blocked_reasons.append("compact_prompt_hash_missing")

    request_accepted = len(blocked_reasons) == 0

    candidate_generated = False
    candidate_raw_output_hash = ""
    canonical_candidate_available = False

    if deterministic_candidate and request_accepted:
        candidate_generated = bool(deterministic_candidate.get("candidate_patch", ""))
        candidate_raw_output_hash = str(deterministic_candidate.get("raw_output_hash", "") or "")
        canonical_candidate_available = bool(candidate_raw_output_hash)

    blocked_reason = ";".join(blocked_reasons) if blocked_reasons else ""

    reason_parts = []
    if not request_accepted:
        reason_parts.append("request_blocked")
    if not candidate_generated:
        reason_parts.append("no_candidate_generated")
    if not reason_parts:
        reason_parts.append("contract_dry_run_complete")
    reason = ";".join(reason_parts)

    return P3ProviderResponse(
        provider_response_version="1.0",
        provider_kind=request.provider_kind,
        model_name=request.model_name,
        request_accepted=request_accepted,
        provider_invoked=False,
        network_invoked=False,
        api_key_used=False,
        candidate_generated=candidate_generated,
        candidate_raw_output_hash=candidate_raw_output_hash,
        canonical_candidate_available=canonical_candidate_available,
        blocked_reason=blocked_reason,
        full_verifier_required=True,
        claim_gate_required=True,
        public_claim_allowed=False,
        production_ready=False,
        reason=reason,
    )


def p3_provider_request_to_dict(req: P3ProviderRequest) -> dict[str, Any]:
    """Convert P3ProviderRequest to JSON-serializable dict."""
    return {
        "p3_provider_request_version": req.provider_request_version,
        "p3_provider_kind": req.provider_kind,
        "p3_provider_model_name": req.model_name,
        "p3_provider_compact_prompt_hash": req.compact_prompt_hash,
        "p3_provider_compact_prompt_token_estimate": req.compact_prompt_token_estimate,
        "p3_provider_task_difficulty": req.task_difficulty,
        "p3_provider_intended_topology": req.intended_topology,
        "p3_provider_env_guard_present": req.env_guard_present,
        "p3_provider_dry_run": req.dry_run,
        "p3_provider_network_allowed": req.network_allowed,
        "p3_provider_api_key_required": req.api_key_required,
        "p3_provider_reason": req.reason,
    }


def p3_provider_response_to_dict(resp: P3ProviderResponse) -> dict[str, Any]:
    """Convert P3ProviderResponse to JSON-serializable dict."""
    return {
        "p3_provider_response_version": resp.provider_response_version,
        "p3_provider_resp_kind": resp.provider_kind,
        "p3_provider_resp_model_name": resp.model_name,
        "p3_provider_resp_request_accepted": resp.request_accepted,
        "p3_provider_resp_invoked": resp.provider_invoked,
        "p3_provider_resp_network_invoked": resp.network_invoked,
        "p3_provider_resp_api_key_used": resp.api_key_used,
        "p3_provider_resp_candidate_generated": resp.candidate_generated,
        "p3_provider_resp_candidate_raw_output_hash": resp.candidate_raw_output_hash,
        "p3_provider_resp_canonical_candidate_available": resp.canonical_candidate_available,
        "p3_provider_resp_blocked_reason": resp.blocked_reason,
        "p3_provider_resp_full_verifier_required": resp.full_verifier_required,
        "p3_provider_resp_claim_gate_required": resp.claim_gate_required,
        "p3_provider_resp_public_claim_allowed": resp.public_claim_allowed,
        "p3_provider_resp_production_ready": resp.production_ready,
        "p3_provider_resp_reason": resp.reason,
    }
