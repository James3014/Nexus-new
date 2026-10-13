from __future__ import annotations

from typing import Any

from nexus.contracts.planner_snapshot_binding import register_planner_snapshot
from nexus.engine.capability_contracts import CapabilityExecutionPlan, CapabilityPlan, PHASES


def build_executor_controls(plan: CapabilityPlan | dict[str, Any]) -> dict[str, Any]:
    selected = set(plan.selected_capabilities if isinstance(plan, CapabilityPlan) else plan.get("selected_capabilities", []) or [])
    pending = set(plan.pending_capabilities if isinstance(plan, CapabilityPlan) else plan.get("pending_capabilities", []) or [])
    executable = selected - pending

    controls = {
        "enable_autoreason_executor": "autoreason" in executable,
        "enable_ddtree_executor": "ddtree" in executable,
        "ddtree_max_candidates": 2,
        "enable_ultra_review": "ultra_review" in executable,
        "enable_swarm": "swarm" in executable,
        "enable_drone": "drone" in executable,
        "enable_nightshift": "nightshift" in executable,
        "enable_rlm": "rlm" in executable or "repair_loop" in executable,
    }

    if "local_heal" in executable:
        controls.update({
            "enable_local_heal": True,
            "local_heal_mode": "shadow_only",
            "local_heal_mutation_allowed": False,
            "local_heal_receipt_required": True,
            "hybrid_route_mode": "cloud_assisted_by_local_trace_only",
            "hybrid_route_authority": "trace_only",
            "hybrid_route_public_claim_allowed": False,
            "hybrid_route_production_ready": False,
        })
    elif "local_heal" in pending:
        controls.update({
            "enable_local_heal": False,
            "local_heal_mode": "pending",
        })
    else:
        controls.update({
            "enable_local_heal": False,
            "local_heal_mode": "disabled",
        })

    return controls


# Capabilities whose executors (LocalHealCapabilityAdapter) read the planner's
# signal_snapshot from ``executor_controls["route_context"]`` (#1924).
_ROUTE_CONTEXT_CONSUMERS = frozenset({"local_heal", "local_model_executor"})


def _planner_route_context(plan: CapabilityPlan | dict[str, Any]) -> dict[str, Any] | None:
    """Pass CapabilityPlanner's signal_snapshot through unchanged (a copy, never augmented)."""
    if isinstance(plan, CapabilityPlan):
        selected, pending, snapshot = plan.selected_capabilities, plan.pending_capabilities, plan.signal_snapshot
    else:
        selected = plan.get("selected_capabilities", []) or []
        pending = plan.get("pending_capabilities", []) or []
        snapshot = plan.get("signal_snapshot") or {}
    if not (set(selected) - set(pending)) & _ROUTE_CONTEXT_CONSUMERS:
        return None
    if not isinstance(snapshot, dict) or not snapshot:
        return None
    passed_snapshot = dict(snapshot)
    # In-process origin binding: consumers reject route_context snapshots not registered here.
    register_planner_snapshot(passed_snapshot)
    return {"signal_snapshot": passed_snapshot}


def build_execution_plan(plan: CapabilityPlan | dict[str, Any]) -> CapabilityExecutionPlan:
    selected = tuple(plan.selected_capabilities if isinstance(plan, CapabilityPlan) else plan.get("selected_capabilities", []) or [])
    controls = build_executor_controls(plan)
    route_context = _planner_route_context(plan)
    if route_context is not None:
        controls["route_context"] = route_context
    return CapabilityExecutionPlan(
        schema_version="nexus_capability_execution_plan_v1",
        phase_order=PHASES,
        selected_capabilities=selected,
        executor_controls=controls,
    )
