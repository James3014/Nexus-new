"""Pure CanonicalTaskContext -> CapabilityPlanner -> projection seam."""

from __future__ import annotations

from nexus.contracts.canonical_execution import (
    CanonicalExecutionProjection,
    CanonicalTaskContext,
    ExecutionDecision,
    validate_canonical_execution_binding,
)
from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_planner import CapabilityPlanner


def plan_canonical_task(
    context: CanonicalTaskContext,
) -> tuple[ExecutionDecision, CanonicalExecutionProjection]:
    """Invoke the sole planner once and project only its immutable decision."""
    if not isinstance(context, CanonicalTaskContext):
        raise TypeError("context_must_be_CanonicalTaskContext")
    plan = CapabilityPlanner().plan(**context.planner_inputs())
    if not isinstance(plan, CapabilityPlan):
        raise TypeError("capability_planner_must_return_CapabilityPlan")
    if plan.signal_snapshot.get("route_truth_source") != "CapabilityPlanner":
        raise ValueError("plan_route_truth_source_must_be_CapabilityPlanner")
    decision = ExecutionDecision.from_plan(context, plan)
    projection = CanonicalExecutionProjection.from_decision(decision)
    validate_canonical_execution_binding(context, decision, projection)
    return decision, projection
