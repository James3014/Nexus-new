from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.p3_shadow_invariants import (
    P3ShadowInvariantResult,
    validate_p3_shadow_invariants,
)


@dataclass(frozen=True)
class P3ShadowReceipt:
    """P3-J3: Consolidated P3 shadow receipt.

    Combines P3-A through P3-F/J2 metadata into one JSON-serializable block.
    Validates through invariant gate.
    """
    p3_shadow_receipt_version: str
    p3_shadow_pipeline_present: bool
    p3_route_skeleton_present: bool
    p3_local_diagnosis_present: bool
    p3_cloud_candidate_stub_present: bool
    p3_cheap_verifier_stub_present: bool
    p3_local_retry_stub_present: bool
    p3_shadow_orchestrator_present: bool
    p3_invariant_gate_present: bool
    p3_invariant_passed: bool
    p3_authority: str
    p3_intended_topology: str
    p3_task_difficulty: str
    p3_cloud_call_invoked: bool
    p3_local_model_call_invoked: bool
    p3_patch_apply_invoked: bool
    p3_runtime_behavior_changed: bool
    p3_full_verifier_required: bool
    p3_claim_gate_required: bool
    p3_claim_eligible: bool
    p3_public_claim_allowed: bool
    p3_solved_claim_allowed: bool
    p3_blocked_reasons: list[str] = field(default_factory=list)
    p3_receipt_complete: bool = False


def consolidate_p3_shadow_receipt(
    component_metadata: dict[str, Any],
    invariant_result: P3ShadowInvariantResult | None = None,
) -> P3ShadowReceipt:
    """Consolidate P3 component metadata into one shadow receipt.

    Validates through invariant gate if provided.
    """
    has_skeleton = "p3_route_skeleton_enabled" in component_metadata or "p3_task_difficulty" in component_metadata
    has_diagnosis = "p3_local_diagnosis_enabled" in component_metadata or "p3_diagnosis_cloud_ready" in component_metadata
    has_cloud_stub = "p3_cloud_candidate_stub_enabled" in component_metadata or "p3_cloud_stub_call_planned" in component_metadata
    has_cheap_verifier = "p3_cheap_verifier_enabled" in component_metadata or "p3_cheap_verifier_planned" in component_metadata
    has_retry = "p3_local_retry_enabled" in component_metadata or "p3_local_retry_planned" in component_metadata
    has_orchestrator = "p3_shadow_orchestrator_enabled" in component_metadata

    authority = "shadow_only"
    for key in ("p3_shadow_authority", "p3_route_authority"):
        if key in component_metadata:
            authority = str(component_metadata[key] or "shadow_only")

    topology = str(component_metadata.get("p3_intended_topology", component_metadata.get("p3_shadow_intended_topology", "")) or "")
    difficulty = str(component_metadata.get("p3_task_difficulty", component_metadata.get("p3_shadow_task_difficulty", "")) or "")

    cloud_call_invoked = bool(component_metadata.get("p3_cloud_call_invoked", False))
    local_model_call_invoked = bool(component_metadata.get("p3_local_model_call_invoked", False))
    patch_apply_invoked = bool(component_metadata.get("p3_patch_apply_invoked", False))
    runtime_behavior_changed = bool(component_metadata.get("p3_runtime_behavior_changed", False))
    full_verifier_required = bool(component_metadata.get("p3_full_verifier_required", True))
    claim_gate_required = bool(component_metadata.get("p3_claim_gate_required", True))
    claim_eligible = bool(component_metadata.get("p3_claim_eligible", False))
    public_claim_allowed = bool(component_metadata.get("p3_public_claim_allowed", False))
    solved_claim_allowed = bool(component_metadata.get("p3_solved_claim_allowed", False))

    blocked_reasons = list(component_metadata.get("p3_blocked_reasons", []) or [])
    if invariant_result and not invariant_result.invariant_passed:
        blocked_reasons.extend(invariant_result.blocked_reasons)

    invariant_passed = invariant_result.invariant_passed if invariant_result else True

    all_present = all([has_skeleton, has_diagnosis, has_cloud_stub, has_cheap_verifier, has_retry, has_orchestrator])
    receipt_complete = all_present and invariant_passed

    return P3ShadowReceipt(
        p3_shadow_receipt_version="1.0",
        p3_shadow_pipeline_present=all_present,
        p3_route_skeleton_present=has_skeleton,
        p3_local_diagnosis_present=has_diagnosis,
        p3_cloud_candidate_stub_present=has_cloud_stub,
        p3_cheap_verifier_stub_present=has_cheap_verifier,
        p3_local_retry_stub_present=has_retry,
        p3_shadow_orchestrator_present=has_orchestrator,
        p3_invariant_gate_present=invariant_result is not None,
        p3_invariant_passed=invariant_passed,
        p3_authority=authority,
        p3_intended_topology=topology,
        p3_task_difficulty=difficulty,
        p3_cloud_call_invoked=cloud_call_invoked,
        p3_local_model_call_invoked=local_model_call_invoked,
        p3_patch_apply_invoked=patch_apply_invoked,
        p3_runtime_behavior_changed=runtime_behavior_changed,
        p3_full_verifier_required=full_verifier_required,
        p3_claim_gate_required=claim_gate_required,
        p3_claim_eligible=claim_eligible,
        p3_public_claim_allowed=public_claim_allowed,
        p3_solved_claim_allowed=solved_claim_allowed,
        p3_blocked_reasons=blocked_reasons,
        p3_receipt_complete=receipt_complete,
    )


def p3_shadow_receipt_to_dict(receipt: P3ShadowReceipt) -> dict[str, Any]:
    """Convert P3ShadowReceipt to JSON-serializable dict."""
    return {
        "p3_shadow_receipt_version": receipt.p3_shadow_receipt_version,
        "p3_shadow_pipeline_present": receipt.p3_shadow_pipeline_present,
        "p3_route_skeleton_present": receipt.p3_route_skeleton_present,
        "p3_local_diagnosis_present": receipt.p3_local_diagnosis_present,
        "p3_cloud_candidate_stub_present": receipt.p3_cloud_candidate_stub_present,
        "p3_cheap_verifier_stub_present": receipt.p3_cheap_verifier_stub_present,
        "p3_local_retry_stub_present": receipt.p3_local_retry_stub_present,
        "p3_shadow_orchestrator_present": receipt.p3_shadow_orchestrator_present,
        "p3_invariant_gate_present": receipt.p3_invariant_gate_present,
        "p3_invariant_passed": receipt.p3_invariant_passed,
        "p3_authority": receipt.p3_authority,
        "p3_intended_topology": receipt.p3_intended_topology,
        "p3_task_difficulty": receipt.p3_task_difficulty,
        "p3_cloud_call_invoked": receipt.p3_cloud_call_invoked,
        "p3_local_model_call_invoked": receipt.p3_local_model_call_invoked,
        "p3_patch_apply_invoked": receipt.p3_patch_apply_invoked,
        "p3_runtime_behavior_changed": receipt.p3_runtime_behavior_changed,
        "p3_full_verifier_required": receipt.p3_full_verifier_required,
        "p3_claim_gate_required": receipt.p3_claim_gate_required,
        "p3_claim_eligible": receipt.p3_claim_eligible,
        "p3_public_claim_allowed": receipt.p3_public_claim_allowed,
        "p3_solved_claim_allowed": receipt.p3_solved_claim_allowed,
        "p3_blocked_reasons": receipt.p3_blocked_reasons,
        "p3_receipt_complete": receipt.p3_receipt_complete,
    }
