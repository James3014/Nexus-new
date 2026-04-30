from __future__ import annotations

from typing import Any

from nexus.engine.capability_contracts import CapabilityExecutionPlan, CapabilityPlan, PHASES


def build_executor_controls(plan: CapabilityPlan | dict[str, Any]) -> dict[str, Any]:
    selected = set(plan.selected_capabilities if isinstance(plan, CapabilityPlan) else plan.get("selected_capabilities", []) or [])
    pending = set(plan.pending_capabilities if isinstance(plan, CapabilityPlan) else plan.get("pending_capabilities", []) or [])
    executable = selected - pending
    return {
        "enable_autoreason_executor": "autoreason" in executable,
        "enable_ddtree_executor": "ddtree" in executable,
        "ddtree_max_candidates": 2,
        "enable_ultra_review": "ultra_review" in executable,
        "enable_swarm": "swarm" in executable,
        "enable_drone": "drone" in executable,
        "enable_nightshift": "nightshift" in executable,
        "enable_rlm": "rlm" in executable or "repair_loop" in executable,
    }


def build_execution_plan(plan: CapabilityPlan | dict[str, Any]) -> CapabilityExecutionPlan:
    selected = tuple(plan.selected_capabilities if isinstance(plan, CapabilityPlan) else plan.get("selected_capabilities", []) or [])
    return CapabilityExecutionPlan(
        schema_version="nexus_capability_execution_plan_v1",
        phase_order=PHASES,
        selected_capabilities=selected,
        executor_controls=build_executor_controls(plan),
    )
