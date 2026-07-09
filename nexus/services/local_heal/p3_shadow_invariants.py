from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P3ShadowInvariantResult:
    """P3-J2: Shadow pipeline invariant gate.

    Fails closed if any P3 shadow component accidentally claims runtime authority.
    """
    invariant_version: str
    invariant_passed: bool
    authority_is_shadow_only: bool
    cloud_call_not_invoked: bool
    local_model_not_invoked: bool
    patch_apply_not_invoked: bool
    runtime_behavior_unchanged: bool
    full_verifier_required: bool
    claim_gate_required: bool
    claim_not_eligible: bool
    public_claim_not_allowed: bool
    solved_not_claimed: bool
    p5_not_promoted: bool
    p6_not_overridden: bool
    blocked_reasons: list[str] = field(default_factory=list)


def _check_field(
    metadata: dict[str, Any],
    field_name: str,
    expected_safe_value: Any,
    invariant_name: str,
    blocked_reasons: list[str],
) -> bool:
    """Check a field against its safe value. Returns True if safe."""
    if field_name not in metadata:
        return True
    value = metadata[field_name]
    if value == expected_safe_value:
        return True
    blocked_reasons.append(f"{invariant_name}:{field_name}={value}")
    return False


def validate_p3_shadow_invariants(metadata: dict[str, Any]) -> P3ShadowInvariantResult:
    """Validate P3 shadow metadata against safety invariants.

    Fails closed: any violation causes invariant_passed=false.
    """
    blocked_reasons: list[str] = []

    authority_is_shadow_only = True
    for key in ("p3_route_authority", "p3_local_diagnosis_authority", "p3_cloud_candidate_authority",
                "p3_cheap_verifier_authority", "p3_local_retry_authority", "p3_shadow_authority"):
        if key in metadata:
            val = str(metadata[key] or "").lower()
            if val not in ("shadow_only", ""):
                authority_is_shadow_only = False
                blocked_reasons.append(f"authority_violation:{key}={val}")

    cloud_call_not_invoked = _check_field(metadata, "p3_cloud_call_invoked", False, "cloud_call_invoked", blocked_reasons)
    if "cloud_call_invoked" not in metadata:
        for key in ("p3_diagnosis_cloud_call_invoked", "p3_cloud_stub_call_invoked"):
            if key in metadata and metadata[key] is True:
                cloud_call_not_invoked = False
                blocked_reasons.append(f"cloud_call_invoked:{key}=True")

    local_model_not_invoked = _check_field(metadata, "p3_local_model_call_invoked", False, "local_model_call_invoked", blocked_reasons)
    patch_apply_not_invoked = _check_field(metadata, "p3_patch_apply_invoked", False, "patch_apply_invoked", blocked_reasons)
    runtime_behavior_unchanged = _check_field(metadata, "p3_runtime_behavior_changed", False, "runtime_behavior_changed", blocked_reasons)
    if "p3_runtime_behavior_changed" not in metadata:
        for key in ("p3_diagnosis_runtime_behavior_changed", "p3_cloud_stub_runtime_behavior_changed",
                     "p3_cheap_verifier_runtime_behavior_changed", "p3_local_retry_runtime_behavior_changed"):
            if key in metadata and metadata[key] is True:
                runtime_behavior_unchanged = False
                blocked_reasons.append(f"runtime_behavior_changed:{key}=True")

    full_verifier_required = _check_field(metadata, "p3_full_verifier_required", True, "full_verifier_required", blocked_reasons)
    if "p3_full_verifier_required" not in metadata:
        for key in ("p3_cheap_verifier_full_verifier_required", "p3_local_retry_full_verifier_required"):
            if key in metadata and metadata[key] is False:
                full_verifier_required = False
                blocked_reasons.append(f"full_verifier_required:{key}=False")

    claim_gate_required = _check_field(metadata, "p3_claim_gate_required", True, "claim_gate_required", blocked_reasons)
    if "p3_claim_gate_required" not in metadata:
        for key in ("p3_cheap_verifier_claim_gate_required", "p3_local_retry_claim_gate_required"):
            if key in metadata and metadata[key] is False:
                claim_gate_required = False
                blocked_reasons.append(f"claim_gate_required:{key}=False")

    claim_not_eligible = _check_field(metadata, "p3_claim_eligible", False, "claim_eligible", blocked_reasons)
    if "p3_claim_eligible" not in metadata:
        for key in ("p3_diagnosis_claim_eligible", "p3_cloud_stub_claim_eligible"):
            if key in metadata and metadata[key] is True:
                claim_not_eligible = False
                blocked_reasons.append(f"claim_eligible:{key}=True")

    public_claim_not_allowed = _check_field(metadata, "p3_public_claim_allowed", False, "public_claim_allowed", blocked_reasons)
    if "p3_public_claim_allowed" not in metadata:
        for key in ("p3_diagnosis_public_claim_allowed", "p3_cloud_stub_public_claim_allowed",
                     "p3_cheap_verifier_public_claim_allowed", "p3_local_retry_public_claim_allowed"):
            if key in metadata and metadata[key] is True:
                public_claim_not_allowed = False
                blocked_reasons.append(f"public_claim_allowed:{key}=True")

    solved_not_claimed = True
    if "solved" in metadata and metadata["solved"] is True:
        solved_not_claimed = False
        blocked_reasons.append("solved=True")

    p5_not_promoted = True
    for key in ("p5_promoted", "p5_diversity_selector_used"):
        if key in metadata and metadata[key] is True:
            p5_not_promoted = False
            blocked_reasons.append(f"p5_promoted:{key}=True")

    p6_not_overridden = True
    for key in ("p6_override", "p6_runtime_mutation_allowed"):
        if key in metadata and metadata[key] is True:
            p6_not_overridden = False
            blocked_reasons.append(f"p6_override:{key}=True")

    invariant_passed = all([
        authority_is_shadow_only,
        cloud_call_not_invoked,
        local_model_not_invoked,
        patch_apply_not_invoked,
        runtime_behavior_unchanged,
        full_verifier_required,
        claim_gate_required,
        claim_not_eligible,
        public_claim_not_allowed,
        solved_not_claimed,
        p5_not_promoted,
        p6_not_overridden,
    ])

    return P3ShadowInvariantResult(
        invariant_version="1.0",
        invariant_passed=invariant_passed,
        authority_is_shadow_only=authority_is_shadow_only,
        cloud_call_not_invoked=cloud_call_not_invoked,
        local_model_not_invoked=local_model_not_invoked,
        patch_apply_not_invoked=patch_apply_not_invoked,
        runtime_behavior_unchanged=runtime_behavior_unchanged,
        full_verifier_required=full_verifier_required,
        claim_gate_required=claim_gate_required,
        claim_not_eligible=claim_not_eligible,
        public_claim_not_allowed=public_claim_not_allowed,
        solved_not_claimed=solved_not_claimed,
        p5_not_promoted=p5_not_promoted,
        p6_not_overridden=p6_not_overridden,
        blocked_reasons=blocked_reasons,
    )
