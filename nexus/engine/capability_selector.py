from __future__ import annotations

from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan


class CapabilitySelector:
    """Compatibility selector that makes the planner the single selection seam."""

    def select(
        self,
        *,
        task_desc: str,
        task_type: str,
        route: dict[str, Any],
        pillars: dict[str, Any] | None = None,
        codeintel: dict[str, Any] | None = None,
        phase_trace: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        skills: list[dict[str, Any]] | None = None,
    ) -> CapabilityPlan:
        from nexus.engine.capability_planner import CapabilityPlanner

        return CapabilityPlanner().plan(
            task_desc=task_desc,
            task_type=task_type,
            route=route,
            pillars=pillars,
            codeintel=codeintel,
            phase_trace=phase_trace,
            budget=budget,
            skills=skills,
        )
