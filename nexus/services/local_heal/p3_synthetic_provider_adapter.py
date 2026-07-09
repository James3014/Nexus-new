from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.services.local_heal.p3_synthetic_provider import (
    P3SyntheticProviderRequest,
    P3SyntheticProviderResponse,
    compute_synthetic_provider_request,
    process_synthetic_provider_request,
    p3_synthetic_request_to_dict,
    p3_synthetic_response_to_dict,
)


@dataclass(frozen=True)
class P3SyntheticProviderAdapterResult:
    """P3-N3: Synthetic provider adapter.

    Routes P3 dry-run provider requests into synthetic provider only.
    No real provider, no network, no SDK.
    """
    adapter_version: str
    adapter_authority: str
    synthetic_fixture_enabled: bool
    synthetic_request_built: bool
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


def compute_synthetic_provider_adapter(
    route_metadata: dict[str, Any],
    diagnosis_metadata: dict[str, Any] | None = None,
    synthetic_fixture_enabled: bool = False,
    fixture_id: str = "default",
) -> P3SyntheticProviderAdapterResult:
    """Compute synthetic provider adapter result.

    Pure adapter: no real provider call, no network, no runtime mutation.
    """
    topology = str(route_metadata.get("p3_intended_topology", "") or "")
    difficulty = str(route_metadata.get("p3_task_difficulty", "") or "")
    compact_prompt_hash = str(diagnosis_metadata.get("p3_diagnosis_compact_prompt_hash", "") or "") if diagnosis_metadata else ""

    blocked_reasons = []

    if not synthetic_fixture_enabled:
        blocked_reasons.append("synthetic_fixture_disabled")
        return P3SyntheticProviderAdapterResult(
            adapter_version="1.0",
            adapter_authority="synthetic_fixture_only",
            synthetic_fixture_enabled=False,
            synthetic_request_built=False,
            synthetic_provider_invoked=False,
            real_provider_invoked=False,
            network_invoked=False,
            api_key_used=False,
            candidate_is_synthetic=False,
            synthetic_candidate_id="",
            synthetic_raw_output_hash="",
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

    if topology == "local_only" or not topology:
        blocked_reasons.append("topology_local_only_no_provider_needed")
        return P3SyntheticProviderAdapterResult(
            adapter_version="1.0",
            adapter_authority="synthetic_fixture_only",
            synthetic_fixture_enabled=True,
            synthetic_request_built=False,
            synthetic_provider_invoked=False,
            real_provider_invoked=False,
            network_invoked=False,
            api_key_used=False,
            candidate_is_synthetic=False,
            synthetic_candidate_id="",
            synthetic_raw_output_hash="",
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

    if not compact_prompt_hash:
        blocked_reasons.append("compact_prompt_hash_missing")

    request = compute_synthetic_provider_request(
        fixture_id=fixture_id,
        task_difficulty=difficulty,
        intended_topology=topology,
        compact_prompt_hash=compact_prompt_hash,
        env_guard_present=True,
        dry_run_only=True,
        allow_synthetic_candidate=True,
    )

    response = process_synthetic_provider_request(request)

    if response.blocked_reasons:
        blocked_reasons.extend(response.blocked_reasons)

    return P3SyntheticProviderAdapterResult(
        adapter_version="1.0",
        adapter_authority="synthetic_fixture_only",
        synthetic_fixture_enabled=True,
        synthetic_request_built=True,
        synthetic_provider_invoked=response.synthetic_provider_invoked,
        real_provider_invoked=False,
        network_invoked=False,
        api_key_used=False,
        candidate_is_synthetic=response.candidate_is_synthetic,
        synthetic_candidate_id=response.synthetic_candidate_id,
        synthetic_raw_output_hash=response.synthetic_raw_output_hash,
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


def p3_synthetic_adapter_to_dict(result: P3SyntheticProviderAdapterResult) -> dict[str, Any]:
    """Convert P3SyntheticProviderAdapterResult to JSON-serializable dict."""
    return {
        "p3_n_adapter_version": result.adapter_version,
        "p3_n_adapter_authority": result.adapter_authority,
        "p3_n_synthetic_fixture_enabled": result.synthetic_fixture_enabled,
        "p3_n_synthetic_request_built": result.synthetic_request_built,
        "p3_n_synthetic_provider_invoked": result.synthetic_provider_invoked,
        "p3_n_real_provider_invoked": result.real_provider_invoked,
        "p3_n_network_invoked": result.network_invoked,
        "p3_n_api_key_used": result.api_key_used,
        "p3_n_candidate_is_synthetic": result.candidate_is_synthetic,
        "p3_n_synthetic_candidate_id": result.synthetic_candidate_id,
        "p3_n_synthetic_raw_output_hash": result.synthetic_raw_output_hash,
        "p3_n_canonical_candidate_available": result.canonical_candidate_available,
        "p3_n_patch_apply_invoked": result.patch_apply_invoked,
        "p3_n_runtime_behavior_changed": result.runtime_behavior_changed,
        "p3_n_full_verifier_required": result.full_verifier_required,
        "p3_n_claim_gate_required": result.claim_gate_required,
        "p3_n_claim_eligible": result.claim_eligible,
        "p3_n_public_claim_allowed": result.public_claim_allowed,
        "p3_n_production_ready": result.production_ready,
        "p3_n_blocked_reasons": result.blocked_reasons,
    }
