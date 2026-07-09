from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.p3_synthetic_provider_adapter import (
    P3SyntheticProviderAdapterResult,
    compute_synthetic_provider_adapter,
    p3_synthetic_adapter_to_dict,
)


@dataclass(frozen=True)
class P3SyntheticProviderReceipt:
    """P3-N4: Synthetic provider receipt extension.

    Extends P3 dry-run receipt to optionally include synthetic provider fixture metadata.
    """
    p3_n_receipt_version: str
    p3_n_synthetic_fixture_enabled: bool
    p3_n_synthetic_provider_invoked: bool
    p3_n_real_provider_invoked: bool
    p3_n_network_invoked: bool
    p3_n_api_key_used: bool
    p3_n_candidate_is_synthetic: bool
    p3_n_synthetic_candidate_id: str
    p3_n_synthetic_raw_output_hash: str
    p3_n_patch_apply_invoked: bool
    p3_n_runtime_behavior_changed: bool
    p3_n_full_verifier_required: bool
    p3_n_claim_gate_required: bool
    p3_n_claim_eligible: bool
    p3_n_public_claim_allowed: bool
    p3_n_production_ready: bool
    p3_n_blocked_reasons: list[str] = field(default_factory=list)


def compute_synthetic_provider_receipt(
    route_metadata: dict[str, Any],
    diagnosis_metadata: dict[str, Any] | None = None,
    synthetic_fixture_enabled: bool = False,
    fixture_id: str = "default",
) -> P3SyntheticProviderReceipt:
    """Compute synthetic provider receipt.

    Extends dry-run receipt with optional synthetic fixture metadata.
    """
    adapter = compute_synthetic_provider_adapter(
        route_metadata=route_metadata,
        diagnosis_metadata=diagnosis_metadata,
        synthetic_fixture_enabled=synthetic_fixture_enabled,
        fixture_id=fixture_id,
    )

    return P3SyntheticProviderReceipt(
        p3_n_receipt_version="1.0",
        p3_n_synthetic_fixture_enabled=adapter.synthetic_fixture_enabled,
        p3_n_synthetic_provider_invoked=adapter.synthetic_provider_invoked,
        p3_n_real_provider_invoked=False,
        p3_n_network_invoked=False,
        p3_n_api_key_used=False,
        p3_n_candidate_is_synthetic=adapter.candidate_is_synthetic,
        p3_n_synthetic_candidate_id=adapter.synthetic_candidate_id,
        p3_n_synthetic_raw_output_hash=adapter.synthetic_raw_output_hash,
        p3_n_patch_apply_invoked=False,
        p3_n_runtime_behavior_changed=False,
        p3_n_full_verifier_required=True,
        p3_n_claim_gate_required=True,
        p3_n_claim_eligible=False,
        p3_n_public_claim_allowed=False,
        p3_n_production_ready=False,
        p3_n_blocked_reasons=adapter.blocked_reasons,
    )


def p3_synthetic_receipt_to_dict(receipt: P3SyntheticProviderReceipt) -> dict[str, Any]:
    """Convert P3SyntheticProviderReceipt to JSON-serializable dict."""
    return {
        "p3_n_receipt_version": receipt.p3_n_receipt_version,
        "p3_n_synthetic_fixture_enabled": receipt.p3_n_synthetic_fixture_enabled,
        "p3_n_synthetic_provider_invoked": receipt.p3_n_synthetic_provider_invoked,
        "p3_n_real_provider_invoked": receipt.p3_n_real_provider_invoked,
        "p3_n_network_invoked": receipt.p3_n_network_invoked,
        "p3_n_api_key_used": receipt.p3_n_api_key_used,
        "p3_n_candidate_is_synthetic": receipt.p3_n_candidate_is_synthetic,
        "p3_n_synthetic_candidate_id": receipt.p3_n_synthetic_candidate_id,
        "p3_n_synthetic_raw_output_hash": receipt.p3_n_synthetic_raw_output_hash,
        "p3_n_patch_apply_invoked": receipt.p3_n_patch_apply_invoked,
        "p3_n_runtime_behavior_changed": receipt.p3_n_runtime_behavior_changed,
        "p3_n_full_verifier_required": receipt.p3_n_full_verifier_required,
        "p3_n_claim_gate_required": receipt.p3_n_claim_gate_required,
        "p3_n_claim_eligible": receipt.p3_n_claim_eligible,
        "p3_n_public_claim_allowed": receipt.p3_n_public_claim_allowed,
        "p3_n_production_ready": receipt.p3_n_production_ready,
        "p3_n_blocked_reasons": receipt.p3_n_blocked_reasons,
    }
