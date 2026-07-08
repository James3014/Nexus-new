from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class P3RouteSkeleton:
    """P3-A: Route skeleton for cloud_with_local_assist topology planning.

    Shadow-only: computes intended topology without executing cloud calls.
    No runtime behavior change. No cloud API client. No network call.
    """
    enabled: bool
    authority: str
    task_difficulty: str
    intended_topology: str
    cloud_used: bool
    cloud_call_invoked: bool
    local_diagnosis_planned: bool
    cloud_candidate_generation_planned: bool
    local_cheap_verifier_planned: bool
    local_retry_planned: bool
    hybrid_committee_planned: bool
    assist_stages_activated: list[str]
    runtime_behavior_changed: bool
    claim_eligible: bool
    public_claim_allowed: bool
    reason: str


def _classify_task_difficulty(request_metadata: dict[str, Any]) -> tuple[str, str]:
    """Classify task difficulty from request metadata.

    Priority:
    1. Explicit difficulty in request_metadata
    2. Task ID or route_context marks
    3. Default to "medium" (shadow-only acceptable)

    Returns (difficulty, reason).
    """
    explicit = str(request_metadata.get("difficulty", "") or "").lower()
    if explicit in ("easy", "medium", "hard"):
        return explicit, f"difficulty_explicit_{explicit}"

    task_id = str(request_metadata.get("task_id", "") or "").lower()
    if "easy" in task_id or "simple" in task_id:
        return "easy", "difficulty_from_task_id_easy"
    if "hard" in task_id or "complex" in task_id:
        return "hard", "difficulty_from_task_id_hard"
    if "medium" in task_id:
        return "medium", "difficulty_from_task_id_medium"

    route_ctx = request_metadata.get("route_context", {}) or {}
    if isinstance(route_ctx, dict):
        signal = route_ctx.get("signal_snapshot", {}) or {}
        if isinstance(signal, dict):
            signal_difficulty = str(signal.get("task_difficulty", "") or "").lower()
            if signal_difficulty in ("easy", "medium", "hard"):
                return signal_difficulty, f"difficulty_from_signal_snapshot_{signal_difficulty}"

    return "medium", "difficulty_unknown_default_medium_shadow_only"


def _plan_topology(difficulty: str) -> tuple[str, list[str], str]:
    """Plan intended topology and assist stages from difficulty.

    Returns (topology, assist_stages, reason).
    """
    if difficulty == "easy":
        return "local_only", [], "easy_task_local_only"

    stages = [
        "stage1_local_diagnosis",
        "stage2_cloud_candidate_generation",
        "stage3_local_cheap_verifier",
        "stage4_local_retry",
    ]
    topology = "cloud_with_local_assist"

    if difficulty == "hard":
        stages.append("stage5_hybrid_committee")
        return topology, stages, "hard_task_cloud_with_local_assist_hybrid_planned"

    return topology, stages, "medium_task_cloud_with_local_assist"


def compute_p3_route_skeleton(
    request_metadata: dict[str, Any],
) -> P3RouteSkeleton:
    """Compute P3 route skeleton from request metadata.

    Shadow-only mode: no cloud calls, no runtime behavior change.
    This is a planning-only function that answers:
    - Is this task easy, medium, or hard?
    - Would the intended topology be local_only or cloud_with_local_assist?
    - Which assist stages would be planned?
    - Is this decision shadow-only or runtime-authoritative?
    - Did this task change runtime behavior? Must be false.
    """
    difficulty, difficulty_reason = _classify_task_difficulty(request_metadata)
    topology, stages, topology_reason = _plan_topology(difficulty)

    hybrid_planned = "stage5_hybrid_committee" in stages

    reason = f"{difficulty_reason};{topology_reason}"

    return P3RouteSkeleton(
        enabled=True,
        authority="shadow_only",
        task_difficulty=difficulty,
        intended_topology=topology,
        cloud_used=False,
        cloud_call_invoked=False,
        local_diagnosis_planned="stage1_local_diagnosis" in stages,
        cloud_candidate_generation_planned="stage2_cloud_candidate_generation" in stages,
        local_cheap_verifier_planned="stage3_local_cheap_verifier" in stages,
        local_retry_planned="stage4_local_retry" in stages,
        hybrid_committee_planned=hybrid_planned,
        assist_stages_activated=stages,
        runtime_behavior_changed=False,
        claim_eligible=False,
        public_claim_allowed=False,
        reason=reason,
    )


def p3_skeleton_to_dict(skeleton: P3RouteSkeleton) -> dict[str, Any]:
    """Convert P3RouteSkeleton to JSON-serializable dict for receipt metadata."""
    return {
        "p3_route_skeleton_enabled": skeleton.enabled,
        "p3_route_authority": skeleton.authority,
        "p3_task_difficulty": skeleton.task_difficulty,
        "p3_intended_topology": skeleton.intended_topology,
        "p3_cloud_used": skeleton.cloud_used,
        "p3_cloud_call_invoked": skeleton.cloud_call_invoked,
        "p3_local_diagnosis_planned": skeleton.local_diagnosis_planned,
        "p3_cloud_candidate_generation_planned": skeleton.cloud_candidate_generation_planned,
        "p3_local_cheap_verifier_planned": skeleton.local_cheap_verifier_planned,
        "p3_local_retry_planned": skeleton.local_retry_planned,
        "p3_hybrid_committee_planned": skeleton.hybrid_committee_planned,
        "p3_assist_stages_activated": skeleton.assist_stages_activated,
        "p3_runtime_behavior_changed": skeleton.runtime_behavior_changed,
        "p3_claim_eligible": skeleton.claim_eligible,
        "p3_public_claim_allowed": skeleton.public_claim_allowed,
        "p3_reason": skeleton.reason,
    }
