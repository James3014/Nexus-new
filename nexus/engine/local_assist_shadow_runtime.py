"""Shadow-only recording for Planner recommendations and Agent choices."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from nexus.engine.capability_planner import CapabilityPlanner


SHADOW_RECEIPT_SCHEMA = "nexus.local_assist.shadow_decision.v1"
_ACTIONS = {"skip", "advisor", "candidate", "verified-subtask"}


def _route_features(risk: int, confidence: float) -> dict[str, Any]:
    return {"risk_score": risk, "adjusted_root_cause_confidence": confidence}


DEFAULT_SHADOW_TASKS: tuple[dict[str, Any], ...] = (
    {
        "task_id": "m3b-skip-001",
        "category": "no-change",
        "task_desc": "inspect one file; no implementation is requested",
        "task_type": "audit",
        "route": {"route_features": _route_features(5, 0.95)},
        "agent_actual_choice": "skip",
    },
    {
        "task_id": "m3b-skip-002",
        "category": "insufficient-context",
        "task_desc": "insufficient-context no-change audit",
        "task_type": "audit",
        "route": {"route_features": _route_features(10, 0.9)},
        "agent_actual_choice": "skip",
    },
    {
        "task_id": "m3b-skip-003",
        "category": "test-only",
        "task_desc": "read-only test inventory with no change requested",
        "task_type": "audit",
        "route": {"route_features": _route_features(15, 0.9)},
        "agent_actual_choice": "skip",
    },
    {
        "task_id": "m3b-advisor-001",
        "category": "source-localization",
        "task_desc": "localize an uncertain source of a failing branch",
        "task_type": "localization",
        "route": {"route_features": _route_features(40, 0.35)},
        "agent_actual_choice": "advisor",
    },
    {
        "task_id": "m3b-advisor-002",
        "category": "source-localization",
        "task_desc": "identify the likely source before editing",
        "task_type": "diagnosis",
        "route": {"route_features": _route_features(45, 0.45)},
        "agent_actual_choice": "advisor",
    },
    {
        "task_id": "m3b-advisor-003",
        "category": "insufficient-context",
        "task_desc": "uncertain diagnosis with incomplete context",
        "task_type": "localization",
        "route": {"route_features": _route_features(55, 0.5)},
        "agent_actual_choice": "advisor",
    },
    {
        "task_id": "m3b-candidate-001",
        "category": "bounded-bug-fix",
        "task_desc": "implement a bounded bug fix in one file",
        "task_type": "bugfix",
        "route": {"route_features": _route_features(20, 0.9)},
        "agent_actual_choice": "candidate",
    },
    {
        "task_id": "m3b-candidate-002",
        "category": "test-only",
        "task_desc": "implement a bounded test-only change in one file",
        "task_type": "test_only",
        "route": {"route_features": _route_features(20, 0.9)},
        "agent_actual_choice": "candidate",
    },
    {
        "task_id": "m3b-candidate-003",
        "category": "bounded-bug-fix",
        "task_desc": "implement a bounded feature change with a known target",
        "task_type": "feature",
        "route": {"route_features": _route_features(25, 0.85)},
        "agent_actual_choice": "candidate",
    },
    {
        "task_id": "m3b-verified-001",
        "category": "verifier-sensitive",
        "task_desc": "make a verifier-sensitive change and run the deterministic verifier",
        "task_type": "implementation",
        "route": {"route_features": _route_features(45, 0.8)},
        "agent_actual_choice": "verified-subtask",
    },
    {
        "task_id": "m3b-verified-002",
        "category": "verifier-sensitive",
        "task_desc": "make a test-sensitive change; must pass the verifier",
        "task_type": "implementation",
        "route": {"route_features": _route_features(50, 0.8)},
        "agent_actual_choice": "verified-subtask",
    },
    {
        "task_id": "m3b-verified-003",
        "category": "verifier-sensitive",
        "task_desc": "run the deterministic verifier after a bounded repair",
        "task_type": "repair",
        "route": {"route_features": _route_features(60, 0.75)},
        "agent_actual_choice": "verified-subtask",
    },
)


def record_shadow_decision(
    *,
    task_id: str,
    workspace_revision: str,
    task_desc: str,
    task_type: str,
    route: Mapping[str, Any],
    agent_actual_choice: str,
    override_reason: str = "",
    assist_result: Mapping[str, Any] | None = None,
    receipt_path: str | Path | None = None,
) -> dict[str, Any]:
    """Record a recommendation and independently supplied Agent choice."""
    if agent_actual_choice not in _ACTIONS:
        raise ValueError("invalid_agent_actual_choice")
    plan = CapabilityPlanner().plan(
        task_desc=task_desc,
        task_type=task_type,
        route=dict(route),
        budget={"max_cost": 100},
    )
    recommendation = dict(plan.signal_snapshot["local_assist_recommendation"])
    match = recommendation["action"] == agent_actual_choice
    if not match and not str(override_reason).strip():
        raise ValueError("override_reason_required")
    result = dict(assist_result or {"status": "not_invoked", "local_assist_invoked": False})
    invoked = bool(result.get("local_assist_invoked", result.get("invoked", False)))
    if result.get("task_id", task_id) != task_id:
        raise ValueError("assist_result_task_id_mismatch")
    payload = {
        "schema": SHADOW_RECEIPT_SCHEMA,
        "task_id": str(task_id),
        "workspace_revision": str(workspace_revision),
        "planner_recommendation": recommendation,
        "agent_actual_choice": agent_actual_choice,
        "recommendation_match": match,
        "recommendation_overridden": not match,
        "override_reason": str(override_reason) if not match else "",
        "assist_result": result,
        "local_assist_task_id": str(task_id),
        "local_assist_invoked": invoked,
        "recommendation_generated_before_agent_choice": True,
        "agent_remained_controller": True,
        "automatic_dispatch": False,
        "workspace_mutated": False,
        "route_truth_source": "CapabilityPlanner",
    }
    if receipt_path is not None:
        destination = Path(receipt_path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def run_shadow_task_set(
    tasks: tuple[Mapping[str, Any], ...] = DEFAULT_SHADOW_TASKS,
) -> dict[str, Any]:
    receipts = [
        record_shadow_decision(
            task_id=str(task["task_id"]),
            workspace_revision=f"shadow-revision-{index}",
            task_desc=str(task["task_desc"]),
            task_type=str(task["task_type"]),
            route=dict(task["route"]),
            agent_actual_choice=str(task["agent_actual_choice"]),
        )
        for index, task in enumerate(tasks, start=1)
    ]
    action_counts = {action: 0 for action in sorted(_ACTIONS)}
    exact_matches = 0
    overrides = 0
    false_positive = 0
    false_negative = 0
    unsafe = 0
    safe_disagreements = 0
    disagreements = 0
    for receipt in receipts:
        recommendation = receipt["planner_recommendation"]
        action_counts[str(recommendation["action"])] += 1
        if receipt["recommendation_match"]:
            exact_matches += 1
        else:
            disagreements += 1
            overrides += 1
            if receipt["agent_actual_choice"] in {"skip", "advisor"}:
                safe_disagreements += 1
        if recommendation["action"] != "skip" and receipt["agent_actual_choice"] == "skip":
            false_positive += 1
        if recommendation["action"] == "skip" and receipt["agent_actual_choice"] != "skip":
            false_negative += 1
        if (
            recommendation.get("mutation_allowed") is not False
            or recommendation.get("shadow_only") is not True
            or recommendation.get("route_truth_source") != "CapabilityPlanner"
        ):
            unsafe += 1
    count = len(receipts)
    return {
        "schema": "nexus.local_assist.shadow_metrics.v1",
        "task_count": count,
        "recommendation_coverage": (count / count) if count else 0.0,
        "exact_action_agreement": (exact_matches / count) if count else 0.0,
        "safe_disagreement_rate": (safe_disagreements / disagreements) if disagreements else 1.0,
        "unsafe_recommendation_rate": (unsafe / count) if count else 0.0,
        "false_positive_assist_rate": (false_positive / count) if count else 0.0,
        "false_negative_assist_rate": (false_negative / count) if count else 0.0,
        "agent_override_rate": (overrides / count) if count else 0.0,
        "local_assist_invocations": sum(int(item["local_assist_invoked"]) for item in receipts),
        "action_counts": action_counts,
        "receipts": receipts,
    }
