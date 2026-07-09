from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class P3SyntheticProviderRequest:
    """P3-N2: Synthetic provider contract request.

    Deterministic test infrastructure only. No network, no SDK, no API key.
    """
    synthetic_provider_version: str
    fixture_id: str
    task_difficulty: str
    intended_topology: str
    compact_prompt_hash: str
    env_guard_present: bool
    dry_run_only: bool
    allow_synthetic_candidate: bool
    reason: str


@dataclass(frozen=True)
class P3SyntheticProviderResponse:
    """P3-N2: Synthetic provider contract response.

    Deterministic test infrastructure only. No network, no SDK, no API key.
    """
    synthetic_provider_version: str
    fixture_id: str
    request_accepted: bool
    synthetic_provider_invoked: bool
    real_provider_invoked: bool
    network_invoked: bool
    api_key_used: bool
    candidate_is_synthetic: bool
    synthetic_candidate_id: str
    synthetic_raw_output_hash: str
    canonical_candidate_available: bool
    patch_apply_invoked: bool
    runtime_behavior_changed: bool
    full_verifier_required: bool
    claim_gate_required: bool
    claim_eligible: bool
    public_claim_allowed: bool
    production_ready: bool
    blocked_reasons: list[str]


def _compute_synthetic_candidate_id(fixture_id: str, compact_prompt_hash: str) -> str:
    """Compute deterministic synthetic candidate ID from fixture_id + prompt hash."""
    combined = f"{fixture_id}:{compact_prompt_hash}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:32]


def compute_synthetic_provider_request(
    *,
    fixture_id: str = "default",
    task_difficulty: str = "medium",
    intended_topology: str = "cloud_with_local_assist",
    compact_prompt_hash: str = "",
    env_guard_present: bool = False,
    dry_run_only: bool = True,
    allow_synthetic_candidate: bool = True,
) -> P3SyntheticProviderRequest:
    """Build synthetic provider request."""
    blocked_reasons = []
    if not env_guard_present:
        blocked_reasons.append("env_guard_missing")
    if not compact_prompt_hash:
        blocked_reasons.append("compact_prompt_hash_missing")
    if not dry_run_only:
        blocked_reasons.append("non_dry_run_blocked")
    if not allow_synthetic_candidate:
        blocked_reasons.append("synthetic_candidate_not_allowed")

    reason = ";".join(blocked_reasons) if blocked_reasons else "synthetic_request_valid"

    return P3SyntheticProviderRequest(
        synthetic_provider_version="1.0",
        fixture_id=fixture_id,
        task_difficulty=task_difficulty,
        intended_topology=intended_topology,
        compact_prompt_hash=compact_prompt_hash,
        env_guard_present=env_guard_present,
        dry_run_only=dry_run_only,
        allow_synthetic_candidate=allow_synthetic_candidate,
        reason=reason,
    )


def process_synthetic_provider_request(
    request: P3SyntheticProviderRequest,
) -> P3SyntheticProviderResponse:
    """Process synthetic provider request and return response.

    Deterministic test infrastructure only. No network, no SDK, no API key.
    """
    blocked_reasons = []

    if not request.env_guard_present:
        blocked_reasons.append("env_guard_missing")
    if not request.compact_prompt_hash:
        blocked_reasons.append("compact_prompt_hash_missing")
    if not request.dry_run_only:
        blocked_reasons.append("non_dry_run_blocked")
    if not request.allow_synthetic_candidate:
        blocked_reasons.append("synthetic_candidate_not_allowed")

    request_accepted = len(blocked_reasons) == 0

    synthetic_provider_invoked = request_accepted
    candidate_is_synthetic = request_accepted
    synthetic_candidate_id = ""
    synthetic_raw_output_hash = ""

    if request_accepted:
        synthetic_candidate_id = _compute_synthetic_candidate_id(
            request.fixture_id, request.compact_prompt_hash
        )
        synthetic_raw_output_hash = hashlib.sha256(
            synthetic_candidate_id.encode("utf-8")
        ).hexdigest()

    reason_parts = []
    if not request_accepted:
        reason_parts.append("request_blocked")
    if not candidate_is_synthetic:
        reason_parts.append("no_synthetic_candidate")
    if not reason_parts:
        reason_parts.append("synthetic_provider_complete")
    reason = ";".join(reason_parts)

    return P3SyntheticProviderResponse(
        synthetic_provider_version="1.0",
        fixture_id=request.fixture_id,
        request_accepted=request_accepted,
        synthetic_provider_invoked=synthetic_provider_invoked,
        real_provider_invoked=False,
        network_invoked=False,
        api_key_used=False,
        candidate_is_synthetic=candidate_is_synthetic,
        synthetic_candidate_id=synthetic_candidate_id,
        synthetic_raw_output_hash=synthetic_raw_output_hash,
        canonical_candidate_available=False,
        patch_apply_invoked=False,
        runtime_behavior_changed=False,
        full_verifier_required=True,
        claim_gate_required=True,
        claim_eligible=False,
        public_claim_allowed=False,
        production_ready=False,
        blocked_reasons=blocked_reasons,
    )


def p3_synthetic_request_to_dict(req: P3SyntheticProviderRequest) -> dict[str, Any]:
    """Convert P3SyntheticProviderRequest to JSON-serializable dict."""
    return {
        "p3_n_request_version": req.synthetic_provider_version,
        "p3_n_fixture_id": req.fixture_id,
        "p3_n_task_difficulty": req.task_difficulty,
        "p3_n_intended_topology": req.intended_topology,
        "p3_n_compact_prompt_hash": req.compact_prompt_hash,
        "p3_n_env_guard_present": req.env_guard_present,
        "p3_n_dry_run_only": req.dry_run_only,
        "p3_n_allow_synthetic_candidate": req.allow_synthetic_candidate,
        "p3_n_reason": req.reason,
    }


def p3_synthetic_response_to_dict(resp: P3SyntheticProviderResponse) -> dict[str, Any]:
    """Convert P3SyntheticProviderResponse to JSON-serializable dict."""
    return {
        "p3_n_response_version": resp.synthetic_provider_version,
        "p3_n_fixture_id": resp.fixture_id,
        "p3_n_request_accepted": resp.request_accepted,
        "p3_n_synthetic_provider_invoked": resp.synthetic_provider_invoked,
        "p3_n_real_provider_invoked": resp.real_provider_invoked,
        "p3_n_network_invoked": resp.network_invoked,
        "p3_n_api_key_used": resp.api_key_used,
        "p3_n_candidate_is_synthetic": resp.candidate_is_synthetic,
        "p3_n_synthetic_candidate_id": resp.synthetic_candidate_id,
        "p3_n_synthetic_raw_output_hash": resp.synthetic_raw_output_hash,
        "p3_n_canonical_candidate_available": resp.canonical_candidate_available,
        "p3_n_patch_apply_invoked": resp.patch_apply_invoked,
        "p3_n_runtime_behavior_changed": resp.runtime_behavior_changed,
        "p3_n_full_verifier_required": resp.full_verifier_required,
        "p3_n_claim_gate_required": resp.claim_gate_required,
        "p3_n_claim_eligible": resp.claim_eligible,
        "p3_n_public_claim_allowed": resp.public_claim_allowed,
        "p3_n_production_ready": resp.production_ready,
        "p3_n_blocked_reasons": resp.blocked_reasons,
    }
