from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan, RouteDecision
from nexus.engine.capability_executor_controls import build_execution_plan
from nexus.engine.route_forecast_policy import build_forecast_gate_shadow, build_pillar_signal_summary
from nexus.engine.route_tactical_policy import build_tactical_stop_policy
from nexus.engine.route_tier_policy import build_route_derivation_meta, resolve_route_tier


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
    signal_snapshot = dict(plan.signal_snapshot)
    signal_snapshot["pillar_signals"] = build_pillar_signal_summary(plan)
    forecast_gate_shadow = build_forecast_gate_shadow(plan)
    resolved_tier = resolve_route_tier(signal_snapshot=signal_snapshot, forecast_gate_shadow=forecast_gate_shadow)
    hazard_hits = tuple(str(item) for item in (signal_snapshot.get("hazard_hits", []) or []) if str(item))
    hazard_forced_l3 = bool(signal_snapshot.get("hazard_forced_l3", False))
    policy_loaded_count = int(signal_snapshot.get("policy_loaded_count", 0) or 0)
    policy_pruned_count = int(signal_snapshot.get("policy_pruned_count", 0) or 0)
    derivation_meta = build_route_derivation_meta(
        signal_snapshot=signal_snapshot,
        recommended_flow=recommended_flow,
        routing_tier_fallback_used=resolved_tier.routing_tier_fallback_used,
    )
    resolved_stop_policy = build_tactical_stop_policy(
        plan=plan,
        recommended_flow=recommended_flow,
        base_policy=stop_policy,
    )
    return RouteDecision(
        schema_version="nexus_route_decision_v1",
        plan_schema_version=plan.schema_version,
        plan_mode=plan.planner_mode,
        plan_score=int(plan.score),
        task_id=task_id,
        task_type=task_type,
        task_desc_hash=_hash_task_desc(task_desc),
        recommended_flow=recommended_flow,
        decision_source="capability_planner",
        signal_snapshot=signal_snapshot,
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
        stop_policy=resolved_stop_policy,
        receipt_requirements=("invoked", "evidence_present", "gate_passed", "outcome_contributed"),
        fallback_policy="fail_closed",
        forecast_gate_shadow=forecast_gate_shadow,
        routing_tier=resolved_tier.routing_tier,
        routing_tier_reason=resolved_tier.routing_tier_reason,
        hazard_hits=hazard_hits,
        hazard_forced_l3=hazard_forced_l3,
        early_exit_used=resolved_tier.early_exit_used,
        policy_loaded_count=policy_loaded_count,
        policy_pruned_count=policy_pruned_count,
        tuning_snapshot=tuning_snapshot or {},
        derivation_meta=derivation_meta,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def write_route_decision_report(path: Path, decision: RouteDecision) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(decision.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
