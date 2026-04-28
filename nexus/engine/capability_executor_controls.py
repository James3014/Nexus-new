from __future__ import annotations

from typing import Any

from nexus.engine.capability_contracts import CapabilityExecutionPlan, CapabilityPlan, PHASES


def build_executor_controls(plan: CapabilityPlan | dict[str, Any]) -> dict[str, Any]:
    selected = set(plan.selected_capabilities if isinstance(plan, CapabilityPlan) else plan.get("selected_capabilities", []) or [])
    return {
        "enable_autoreason_executor": "autoreason" in selected,
        "enable_ddtree_executor": "ddtree" in selected,
        "ddtree_max_candidates": 2,
        "enable_ultra_review": "ultra_review" in selected,
        "enable_swarm": "swarm" in selected,
        "enable_drone": "drone" in selected,
        "enable_nightshift": "nightshift" in selected,
        "enable_rlm": "rlm" in selected or "repair_loop" in selected,
    }


def build_execution_plan(plan: CapabilityPlan | dict[str, Any]) -> CapabilityExecutionPlan:
    selected = tuple(plan.selected_capabilities if isinstance(plan, CapabilityPlan) else plan.get("selected_capabilities", []) or [])
    return CapabilityExecutionPlan(
        schema_version="nexus_capability_execution_plan_v1",
        phase_order=PHASES,
        selected_capabilities=selected,
        executor_controls=build_executor_controls(plan),
    )
