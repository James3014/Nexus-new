from __future__ import annotations

import logging
from typing import Any

from nexus.events.transport import NexusEventBus
from nexus.learning.cycle_analyzer import analyze_cycle


logger = logging.getLogger(__name__)


def handle_escalation(
    owner: Any,
    ctx: Any,
    repair_attempts: int,
    review_status_raw: str,
    phantom_reason: str,
    *,
    cycle_analyzer: Any = analyze_cycle,
) -> tuple[bool, bool]:
    rejection_history = list(ctx.state.metadata.get("rejection_history", []))
    reason_tag = phantom_reason if phantom_reason else f"rejected:{review_status_raw}"
    rejection_history.append(reason_tag)
    ctx.state.metadata["rejection_history"] = rejection_history

    ctx.state.metadata["last_audit_failure"] = (
        f"phantom success: {phantom_reason}" if phantom_reason else f"rejected: {review_status_raw}"
    )
    ctx.pack["audit_feedback"] = ctx.state.metadata["last_audit_failure"]

    if repair_attempts >= 3:
        try:
            mid_cycle = cycle_analyzer(rejection_history)
            mid_root = mid_cycle.get("root_cause", "")
            if mid_root in ("scope_drift", "insufficient_diag"):
                return owner._perform_escalation(ctx, mid_root, repair_attempts)
        except Exception as esc_exc:
            logger.debug("escalation_analysis_failed: %s", esc_exc)
    return False, False


def perform_escalation(owner: Any, ctx: Any, mid_root: str, repair_attempts: int) -> tuple[bool, bool]:
    owner._update_meta_counter(ctx, "escalation_count")
    esc_count = ctx.state.metadata.get("escalation_count", 0)

    if esc_count > 2:
        logger.error("Max escalation reached (%d). Entering HUMAN_REVIEW.", esc_count)
        ctx.state.metadata["human_review_required"] = True
        ctx.state.metadata["human_review_reason"] = f"max_escalation:{mid_root}"
        NexusEventBus.publish(
            "human_review_required",
            {"task_id": ctx.state.task_id, "root_cause": mid_root, "escalation_count": esc_count},
        )
        return True, False

    logger.warning("Escalation to actual replan (root_cause=%s)", mid_root)
    ctx.state.metadata["escalation_triggered"] = True
    ctx.state.metadata["escalation_root_cause"] = mid_root
    NexusEventBus.publish(
        "escalation_to_plan",
        {"task_id": ctx.state.task_id, "root_cause": mid_root, "attempt": repair_attempts},
    )

    try:
        logger.info("Executing actual P-Stage for replan due to escalation.")
        p_plugin = next((p for p in owner.engine.registry.get_ordered_plugins() if p.name == "P"), None)
        if not p_plugin:
            raise RuntimeError("P-Stage plugin not found")

        replan_feedback = {
            "root_cause": mid_root,
            "rejection_history": ctx.state.metadata.get("rejection_history", []),
            "repair_attempts": repair_attempts,
        }
        ctx.kwargs["plan_feedback"] = replan_feedback
        try:
            p_plugin.execute(owner.engine, ctx)
        finally:
            ctx.kwargs.pop("plan_feedback", None)

        logger.info("Escalation replan succeeded, resetting repair cycle.")
        return False, True
    except Exception as exc:
        logger.error("Replan failed during escalation: %s", exc)
        return True, False
