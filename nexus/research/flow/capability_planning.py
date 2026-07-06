from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from nexus.engine.capability_executor_controls import build_executor_controls
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.learning_policy_loader import merge_runtime_learning_policy
from nexus.engine.route_decision_adapter import build_route_decision
from nexus.research.flow.rlm_trace import safe_trace_slug


def compose_capability_plan(
    *,
    task_desc: str,
    task_type: str,
    recommended_flow: str,
    route_features: dict[str, Any],
    research_context: dict[str, Any] | None = None,
    target_file: str | None = None,
) -> dict[str, Any]:
    seed_selected = ["hyper_sprint"] if recommended_flow == "hyper_sprint" else ["baseline"]
    readiness = route_features.get("candidate_factory_readiness_estimate", {})
    readiness = readiness if isinstance(readiness, dict) else {}
    estimated_candidates = int(readiness.get("estimated_candidates", route_features.get("candidate_count", 1)) or 1)
    candidate_factory_ready = bool(readiness.get("ready", estimated_candidates >= 2))
    seed_acceleration = ["ddtree"] if candidate_factory_ready and estimated_candidates >= 3 else []
    research_context = research_context if isinstance(research_context, dict) else {}
    recommended_caps = {str(item) for item in (research_context.get("recommended_capabilities", []) or []) if str(item)}
    seed_route = {
        "recommended_flow": recommended_flow,
        "route_features": route_features,
        "research_context": research_context,
        "route_decision": {
            "selected_capabilities": seed_selected + (["autoreason"] if "autoreason" in recommended_caps else []),
            "acceleration_layers": seed_acceleration,
            "governance_layers": ["ultra_review"] if "ultra_review" in recommended_caps else [],
        },
    }
    plan = CapabilityPlanner().plan(task_desc=task_desc, task_type=task_type, route=seed_route)
    selected = {str(item) for item in plan.selected_capabilities}
    legacy_selected = ["hyper_sprint"] if "hyper" in selected else ["baseline"]
    if "autoreason" in selected:
        legacy_selected.append("autoreason")

    def _reasons(capability: str) -> list[str]:
        for item in plan.decision_trace:
            if item.get("capability") == capability:
                return list(item.get("reasons", []) or [])
        return []

    return {
        "schema_version": "legacy_capability_stack_v2_compat",
        "source": "route_decision_compat",
        "selected_capabilities": legacy_selected,
        "acceleration_layers": ["ddtree"] if "ddtree" in selected else [],
        "governance_layers": ["ultra_review"] if "ultra_review" in selected else [],
        "explain_caps": [
            {
                "capability": "hyper_sprint" if recommended_flow == "hyper_sprint" else "baseline",
                "enabled": True,
                "reasons": [f"recommended_flow:{recommended_flow}"],
                "evidence": ["route.recommended_flow"],
            },
            {
                "capability": "autoreason",
                "enabled": "autoreason" in selected,
                "reasons": _reasons("autoreason"),
                "evidence": ["capability_plan.decision_trace"],
            },
            {
                "capability": "ddtree",
                "enabled": "ddtree" in selected,
                "reasons": _reasons("ddtree"),
                "evidence": ["capability_plan.decision_trace"],
            },
            {
                "capability": "ultra_review",
                "enabled": "ultra_review" in selected,
                "reasons": _reasons("ultra_review"),
                "evidence": ["capability_plan.decision_trace"],
            },
        ],
        "stop_policy": {
            "type": "a_streak" if "autoreason" in selected else "budget",
            "threshold": 2 if "autoreason" in selected else 1,
            "budget_guard": "fail_closed",
        },
        "target_file": target_file or "",
    }


def build_capability_plan_and_decision(
    *,
    task_desc: str,
    task_type: str,
    route: dict[str, Any],
    task_id: str | None = None,
    budget: dict[str, Any] | None = None,
    skills: list[dict[str, Any]] | None = None,
) -> tuple[Any, dict[str, Any]]:
    decision_route = {key: value for key, value in route.items() if key != "capability_stack"}
    plan = CapabilityPlanner().plan(
        task_desc=task_desc,
        task_type=task_type,
        route=decision_route,
        budget=budget,
        skills=skills,
    )
    decision = build_route_decision(
        task_id=task_id or safe_trace_slug(task_desc),
        task_desc=task_desc,
        task_type=task_type,
        recommended_flow=str(route.get("recommended_flow") or ""),
        plan=plan,
    ).to_dict()
    return plan, decision


def benchmark_skill_mount_requests_from_env(*, task_id: str | None) -> list[dict[str, str]]:
    if not task_id:
        return []
    allow_ablation = os.environ.get("NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS", "").strip().lower()
    if allow_ablation in {"0", "false", "no", "off"}:
        return []
    raw = os.environ.get("NEXUS_BENCH_SKILL_MOUNT_REQUESTS", "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in raw.split(",") if item.strip()]
    if not isinstance(parsed, list):
        return []
    requests: list[dict[str, str]] = []
    for item in parsed:
        if isinstance(item, dict):
            skill_id = str(item.get("skill_id") or item.get("task_id") or "").strip()
        else:
            skill_id = str(item).strip()
        if skill_id:
            requests.append({"skill_id": skill_id, "source": "benchmark_env_request"})
    return requests


def runtime_capability_budget(repo_root: Path) -> dict[str, Any]:
    budget = merge_runtime_learning_policy(repo_root)
    status_report = os.environ.get("NEXUS_BENCH_SKILL_STATUS_REPORT", "").strip()
    if status_report:
        budget["skill_status_report"] = status_report
    overlay_path = (
        os.environ.get("NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY", "").strip()
        or os.environ.get("NEXUS_RUNTIME_SKILL_POLICY_OVERLAY", "").strip()
    )
    if overlay_path:
        budget["runtime_skill_policy_overlay_path"] = overlay_path
    if os.environ.get("NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS", "").strip().lower() in {"1", "true", "yes", "on"}:
        budget["allow_ablation_skill_mounts"] = True
    return budget


def runtime_skill_overlay_requested(budget: dict[str, Any]) -> bool:
    return bool(
        budget.get("runtime_skill_policy_overlay")
        or str(budget.get("runtime_skill_policy_overlay_path") or "").strip()
    )


def build_route_executor_flags(*, task_desc: str, task_type: str, route: dict[str, Any]) -> dict[str, Any]:
    route_decision = route.get("route_decision") if isinstance(route, dict) else {}
    route_decision = route_decision if isinstance(route_decision, dict) else {}
    controls = route_decision.get("executor_controls") if isinstance(route_decision.get("executor_controls"), dict) else None
    if controls is None:
        plan_payload = route.get("capability_plan") if isinstance(route, dict) else {}
        controls = build_executor_controls(plan_payload) if isinstance(plan_payload, dict) and plan_payload.get("selected_capabilities") is not None else {}
    return {
        "enable_autoreason_executor": bool(controls.get("enable_autoreason_executor", False)),
        "enable_ddtree_executor": bool(controls.get("enable_ddtree_executor", False)),
        "ddtree_max_candidates": int(controls.get("ddtree_max_candidates", 2) or 2),
        "enable_ultra_review": bool(controls.get("enable_ultra_review", False)),
        "enable_swarm": bool(controls.get("enable_swarm", False)),
        "enable_drone": bool(controls.get("enable_drone", False)),
        "enable_nightshift": bool(controls.get("enable_nightshift", False)),
        "enable_rlm": bool(controls.get("enable_rlm", False)),
    }
