from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P3DryRunInvariantResult:
    """P3-L4: Dry-run hook invariant gate.

    Validates LocalModelExecutor dry-run receipt block.
    Fails closed on unsafe metadata.
    """
    invariant_version: str
    invariant_passed: bool
    provider_not_invoked: bool
    network_not_invoked: bool
    api_key_not_used: bool
    local_model_not_invoked_by_p3: bool
    patch_apply_not_invoked: bool
    runtime_behavior_unchanged: bool
    full_verifier_required: bool
    claim_gate_required: bool
    claim_not_eligible: bool
    public_claim_not_allowed: bool
    production_not_ready: bool
    blocked_reasons: list[str] = field(default_factory=list)


def validate_p3_dry_run_receipt(receipt: dict[str, Any]) -> P3DryRunInvariantResult:
    """Validate P3 dry-run receipt block against safety invariants.

    Fails closed: any violation causes invariant_passed=false.
    """
    blocked_reasons: list[str] = []

    def _check(field_name: str, expected: Any, invariant_name: str) -> bool:
        if field_name not in receipt:
            return True
        if receipt[field_name] == expected:
            return True
        blocked_reasons.append(f"{invariant_name}:{field_name}={receipt[field_name]}")
        return False

    provider_not_invoked = _check("p3_l_provider_invoked", False, "provider_invoked")
    network_not_invoked = _check("p3_l_network_invoked", False, "network_invoked")
    api_key_not_used = _check("p3_l_api_key_used", False, "api_key_used")
    local_model_not_invoked = _check("p3_l_local_model_invoked", False, "local_model_invoked")
    patch_apply_not_invoked = _check("p3_l_patch_apply_invoked", False, "patch_apply_invoked")
    runtime_behavior_unchanged = _check("p3_l_runtime_behavior_changed", False, "runtime_behavior_changed")
    full_verifier_required = _check("p3_l_full_verifier_required", True, "full_verifier_required")
    claim_gate_required = _check("p3_l_claim_gate_required", True, "claim_gate_required")
    claim_not_eligible = _check("p3_l_claim_eligible", False, "claim_eligible")
    public_claim_not_allowed = _check("p3_l_public_claim_allowed", False, "public_claim_allowed")
    production_not_ready = _check("p3_l_production_ready", False, "production_ready")

    invariant_passed = all([
        provider_not_invoked,
        network_not_invoked,
        api_key_not_used,
        local_model_not_invoked,
        patch_apply_not_invoked,
        runtime_behavior_unchanged,
        full_verifier_required,
        claim_gate_required,
        claim_not_eligible,
        public_claim_not_allowed,
        production_not_ready,
    ])

    return P3DryRunInvariantResult(
        invariant_version="1.0",
        invariant_passed=invariant_passed,
        provider_not_invoked=provider_not_invoked,
        network_not_invoked=network_not_invoked,
        api_key_not_used=api_key_not_used,
        local_model_not_invoked_by_p3=local_model_not_invoked,
        patch_apply_not_invoked=patch_apply_not_invoked,
        runtime_behavior_unchanged=runtime_behavior_unchanged,
        full_verifier_required=full_verifier_required,
        claim_gate_required=claim_gate_required,
        claim_not_eligible=claim_not_eligible,
        public_claim_not_allowed=public_claim_not_allowed,
        production_not_ready=production_not_ready,
        blocked_reasons=blocked_reasons,
    )


def p3_dry_run_invariant_to_dict(result: P3DryRunInvariantResult) -> dict[str, Any]:
    """Convert P3DryRunInvariantResult to JSON-serializable dict."""
    return {
        "p3_l_invariant_version": result.invariant_version,
        "p3_l_invariant_passed": result.invariant_passed,
        "p3_l_provider_not_invoked": result.provider_not_invoked,
        "p3_l_network_not_invoked": result.network_not_invoked,
        "p3_l_api_key_not_used": result.api_key_not_used,
        "p3_l_local_model_not_invoked_by_p3": result.local_model_not_invoked_by_p3,
        "p3_l_patch_apply_not_invoked": result.patch_apply_not_invoked,
        "p3_l_runtime_behavior_unchanged": result.runtime_behavior_unchanged,
        "p3_l_full_verifier_required": result.full_verifier_required,
        "p3_l_claim_gate_required": result.claim_gate_required,
        "p3_l_claim_not_eligible": result.claim_not_eligible,
        "p3_l_public_claim_not_allowed": result.public_claim_not_allowed,
        "p3_l_production_not_ready": result.production_not_ready,
        "p3_l_blocked_reasons": result.blocked_reasons,
    }
