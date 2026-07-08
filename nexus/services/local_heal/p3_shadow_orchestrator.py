from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.services.local_heal.p3_route_skeleton import (
    compute_p3_route_skeleton,
    p3_skeleton_to_dict,
)
from nexus.services.local_heal.p3_local_diagnosis import (
    compute_p3_local_diagnosis,
    p3_diagnosis_to_dict,
)
from nexus.services.local_heal.p3_cloud_candidate_stub import (
    compute_cloud_candidate_stub,
    p3_cloud_stub_to_dict,
)
from nexus.services.local_heal.p3_local_cheap_verifier import (
    compute_p3_cheap_verifier,
    p3_cheap_verifier_to_dict,
)
from nexus.services.local_heal.p3_local_retry_stub import (
    compute_p3_local_retry,
    p3_retry_stub_to_dict,
)


@dataclass(frozen=True)
class P3ShadowReceipt:
    """P3-F: Unified P3 shadow orchestrator receipt.

    Composes P3-A through P3-E into one auditable shadow pipeline.
    """
    enabled: bool
    authority: str
    task_difficulty: str
    intended_topology: str
    route_skeleton_present: bool
    local_diagnosis_present: bool
    cloud_candidate_stub_present: bool
    cheap_verifier_stub_present: bool
    local_retry_stub_present: bool
    assist_stages_planned: list[str]
    assist_stages_invoked: list[str]
    cloud_call_invoked: bool
    local_model_call_invoked: bool
    patch_apply_invoked: bool
    full_verifier_required: bool
    claim_gate_required: bool
    runtime_behavior_changed: bool
    claim_eligible: bool
    public_claim_allowed: bool
    blocked_reason: str
    receipt_complete: bool
    reason: str


def compute_p3_shadow_orchestrator(
    request_metadata: dict[str, Any],
    anchor_metadata: dict[str, Any] | None = None,
    hash_chain_metadata: dict[str, Any] | None = None,
    failure_metadata: dict[str, Any] | None = None,
    cascade_models: list[str] | None = None,
) -> tuple[P3ShadowReceipt, dict[str, Any]]:
    """Compute P3 shadow orchestrator receipt from request metadata.

    Composes all P3 components into one unified receipt.
    Shadow-only mode: no cloud calls, no local model calls, no runtime change.

    Returns (receipt, full_metadata_dict).
    """
    skeleton = compute_p3_route_skeleton(request_metadata)
    skeleton_dict = p3_skeleton_to_dict(skeleton)

    diagnosis = compute_p3_local_diagnosis(
        request_metadata=request_metadata,
        p3_skeleton=skeleton_dict,
        anchor_metadata=anchor_metadata,
        hash_chain_metadata=hash_chain_metadata,
        failure_metadata=failure_metadata,
    )
    diagnosis_dict = p3_diagnosis_to_dict(diagnosis)

    cloud_stub = compute_cloud_candidate_stub(
        diagnosis_metadata=diagnosis_dict,
    )
    cloud_stub_dict = p3_cloud_stub_to_dict(cloud_stub)

    cheap_verifier = compute_p3_cheap_verifier(
        cloud_stub_metadata=cloud_stub_dict,
    )
    cheap_verifier_dict = p3_cheap_verifier_to_dict(cheap_verifier)

    local_retry = compute_p3_local_retry(
        cheap_verifier_metadata=cheap_verifier_dict,
        cascade_models=cascade_models,
    )
    local_retry_dict = p3_retry_stub_to_dict(local_retry)

    blocked_reasons = []
    if skeleton.task_difficulty == "easy":
        blocked_reasons.append("easy_task_local_only")
    if not diagnosis.cloud_ready:
        blocked_reasons.append(f"diagnosis_not_cloud_ready:{diagnosis.reason}")

    receipt = P3ShadowReceipt(
        enabled=True,
        authority="shadow_only",
        task_difficulty=skeleton.task_difficulty,
        intended_topology=skeleton.intended_topology,
        route_skeleton_present=True,
        local_diagnosis_present=True,
        cloud_candidate_stub_present=True,
        cheap_verifier_stub_present=True,
        local_retry_stub_present=True,
        assist_stages_planned=skeleton.assist_stages_activated,
        assist_stages_invoked=[],
        cloud_call_invoked=False,
        local_model_call_invoked=False,
        patch_apply_invoked=False,
        full_verifier_required=True,
        claim_gate_required=True,
        runtime_behavior_changed=False,
        claim_eligible=False,
        public_claim_allowed=False,
        blocked_reason=";".join(blocked_reasons) if blocked_reasons else "",
        receipt_complete=True,
        reason=f"shadow_orchestrator_complete;difficulty={skeleton.task_difficulty}",
    )

    full_metadata = {
        **skeleton_dict,
        **diagnosis_dict,
        **cloud_stub_dict,
        **cheap_verifier_dict,
        **local_retry_dict,
        "p3_shadow_orchestrator_enabled": receipt.enabled,
        "p3_shadow_authority": receipt.authority,
        "p3_shadow_task_difficulty": receipt.task_difficulty,
        "p3_shadow_intended_topology": receipt.intended_topology,
        "p3_shadow_route_skeleton_present": receipt.route_skeleton_present,
        "p3_shadow_local_diagnosis_present": receipt.local_diagnosis_present,
        "p3_shadow_cloud_candidate_stub_present": receipt.cloud_candidate_stub_present,
        "p3_shadow_cheap_verifier_stub_present": receipt.cheap_verifier_stub_present,
        "p3_shadow_local_retry_stub_present": receipt.local_retry_stub_present,
        "p3_shadow_assist_stages_planned": receipt.assist_stages_planned,
        "p3_shadow_assist_stages_invoked": receipt.assist_stages_invoked,
        "p3_shadow_cloud_call_invoked": receipt.cloud_call_invoked,
        "p3_shadow_local_model_call_invoked": receipt.local_model_call_invoked,
        "p3_shadow_patch_apply_invoked": receipt.patch_apply_invoked,
        "p3_shadow_full_verifier_required": receipt.full_verifier_required,
        "p3_shadow_claim_gate_required": receipt.claim_gate_required,
        "p3_shadow_runtime_behavior_changed": receipt.runtime_behavior_changed,
        "p3_shadow_claim_eligible": receipt.claim_eligible,
        "p3_shadow_public_claim_allowed": receipt.public_claim_allowed,
        "p3_shadow_blocked_reason": receipt.blocked_reason,
        "p3_shadow_receipt_complete": receipt.receipt_complete,
        "p3_shadow_reason": receipt.reason,
    }

    return receipt, full_metadata


def p3_shadow_receipt_to_dict(receipt: P3ShadowReceipt) -> dict[str, Any]:
    """Convert P3ShadowReceipt to JSON-serializable dict."""
    return {
        "p3_shadow_orchestrator_enabled": receipt.enabled,
        "p3_shadow_authority": receipt.authority,
        "p3_shadow_task_difficulty": receipt.task_difficulty,
        "p3_shadow_intended_topology": receipt.intended_topology,
        "p3_shadow_route_skeleton_present": receipt.route_skeleton_present,
        "p3_shadow_local_diagnosis_present": receipt.local_diagnosis_present,
        "p3_shadow_cloud_candidate_stub_present": receipt.cloud_candidate_stub_present,
        "p3_shadow_cheap_verifier_stub_present": receipt.cheap_verifier_stub_present,
        "p3_shadow_local_retry_stub_present": receipt.local_retry_stub_present,
        "p3_shadow_assist_stages_planned": receipt.assist_stages_planned,
        "p3_shadow_assist_stages_invoked": receipt.assist_stages_invoked,
        "p3_shadow_cloud_call_invoked": receipt.cloud_call_invoked,
        "p3_shadow_local_model_call_invoked": receipt.local_model_call_invoked,
        "p3_shadow_patch_apply_invoked": receipt.patch_apply_invoked,
        "p3_shadow_full_verifier_required": receipt.full_verifier_required,
        "p3_shadow_claim_gate_required": receipt.claim_gate_required,
        "p3_shadow_runtime_behavior_changed": receipt.runtime_behavior_changed,
        "p3_shadow_claim_eligible": receipt.claim_eligible,
        "p3_shadow_public_claim_allowed": receipt.public_claim_allowed,
        "p3_shadow_blocked_reason": receipt.blocked_reason,
        "p3_shadow_receipt_complete": receipt.receipt_complete,
        "p3_shadow_reason": receipt.reason,
    }
