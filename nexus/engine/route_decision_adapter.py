from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan, RouteDecision
from nexus.engine.capability_executor_controls import build_execution_plan


def _hash_task_desc(task_desc: str) -> str:
    return hashlib.sha256((task_desc or "").encode("utf-8")).hexdigest()[:16]


def build_route_decision(
    *,
    task_id: str,
    task_desc: str,
    task_type: str,
    recommended_flow: str,
    plan: CapabilityPlan,
    stop_policy: dict[str, Any] | None = None,
    tuning_snapshot: dict[str, Any] | None = None,
) -> RouteDecision:
    execution = build_execution_plan(plan)
    selected = tuple(plan.selected_capabilities)
    acceleration = tuple(item for item in ("ddtree",) if item in selected)
    governance = tuple(item for item in ("ultra_review", "mempalace_gate", "artifact_gate", "claim_gate") if item in selected)
    return RouteDecision(
        schema_version="nexus_route_decision_v1",
        task_id=task_id,
        task_type=task_type,
        task_desc_hash=_hash_task_desc(task_desc),
        recommended_flow=recommended_flow,
        decision_source="capability_planner",
        signal_snapshot=dict(plan.signal_snapshot),
        selected_capabilities=selected,
        required_capabilities=tuple(plan.required_capabilities),
        conditional_capabilities=tuple(plan.conditional_capabilities),
        pending_capabilities=tuple(plan.pending_capabilities),
        forbidden_capabilities=tuple(plan.forbidden_capabilities),
        acceleration_layers=acceleration,
        governance_layers=governance,
        executor_controls=dict(execution.executor_controls),
        constraints=tuple(plan.constraints),
        decision_trace=tuple(plan.decision_trace),
        stop_policy=stop_policy or {"type": "receipt_backed", "budget_guard": "fail_closed"},
        receipt_requirements=("invoked", "evidence_present", "gate_passed", "outcome_contributed"),
        fallback_policy="fail_closed",
        tuning_snapshot=tuning_snapshot or {},
        created_at=datetime.now(timezone.utc).isoformat(),
    )
