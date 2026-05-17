from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RLMRolloutMode(str, Enum):
    DISABLED = "disabled"
    TRACE_ONLY = "trace_only"
    REPAIR_LOOP = "repair_loop"
    RESEARCH_LOOP_CANDIDATE = "research_loop_candidate"


@dataclass(frozen=True)
class RLMRolloutDecision:
    mode: RLMRolloutMode
    reason: str
    required_gates: list[str] = field(default_factory=list)

    @property
    def repair_loop_enabled(self) -> bool:
        return self.mode in {RLMRolloutMode.REPAIR_LOOP, RLMRolloutMode.RESEARCH_LOOP_CANDIDATE}


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _text_has_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def decide_rlm_rollout(
    *,
    task_type: str = "",
    task_desc: str = "",
    metadata: dict[str, Any] | None = None,
    delivery_profile: str = "mock_only",
) -> RLMRolloutDecision:
    meta = metadata or {}
    if _truthy(meta.get("rlm_rollout_disabled")):
        return RLMRolloutDecision(RLMRolloutMode.DISABLED, "metadata_disabled")
    if str(delivery_profile).startswith("live") and not _truthy(meta.get("rlm_allow_live_delivery")):
        return RLMRolloutDecision(RLMRolloutMode.DISABLED, "live_delivery_requires_explicit_approval")

    requested = (
        _truthy(meta.get("rlm_recursive_repair_enabled"))
        or _truthy(meta.get("rlm_recursive_research_enabled"))
        or _truthy(os.getenv("NEXUS_RLM_REPAIR_LOOP"))
        or _truthy(os.getenv("NEXUS_RLM_RESEARCH_LOOP"))
    )
    if not requested:
        return RLMRolloutDecision(RLMRolloutMode.DISABLED, "not_requested")

    combined = f"{task_type} {task_desc}"
    required = ["rlm_trace_present", "submit_not_success", "ac_gate_verified"]
    if _truthy(meta.get("rlm_recursive_research_enabled")) or _truthy(os.getenv("NEXUS_RLM_RESEARCH_LOOP")):
        return RLMRolloutDecision(
            RLMRolloutMode.RESEARCH_LOOP_CANDIDATE,
            "research_loop_requested",
            [*required, "x_loop_budget_observed"],
        )
    if _text_has_any(combined, ("governance", "evidence", "repair", "bug", "refactor", "hidden", "hard")):
        return RLMRolloutDecision(RLMRolloutMode.REPAIR_LOOP, "eligible_repair_task", required)
    return RLMRolloutDecision(RLMRolloutMode.TRACE_ONLY, "low_risk_trace_only", ["rlm_trace_present"])


def decide_rlm_rollout_for_context(ctx: Any) -> RLMRolloutDecision:
    state = getattr(ctx, "state", None)
    metadata = getattr(state, "metadata", {}) or {}
    return decide_rlm_rollout(
        task_type=str(getattr(ctx, "task_type", "") or metadata.get("task_type", "")),
        task_desc=str(getattr(ctx, "task_desc", "") or metadata.get("task_description", "")),
        metadata=metadata,
        delivery_profile=str(metadata.get("delivery_profile", "mock_only")),
    )
