from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from nexus.contracts.learning_experience import load_promoted_learning_policy

DEFAULT_PROMOTED_POLICY_PATH = Path(".nexus") / "policy" / "promoted_learning_policy.json"
DEFAULT_ROUTE_COST_POLICY_PATH = Path(".nexus") / "policy" / "promoted_route_cost_policy.json"


def load_learning_policy_budget(path: Path) -> dict[str, Any]:
    policy = load_promoted_learning_policy(path)
    if policy.get("schema_version") != "nexus_promoted_learning_policy.v1":
        return {}
    promoted = [str(item) for item in policy.get("promoted_capabilities", []) or [] if str(item).strip()]
    penalized = [str(item) for item in policy.get("penalized_capabilities", []) or [] if str(item).strip()]
    if not promoted and not penalized:
        return {}
    return {
        "learning_policy": {
            "source_experiences": [str(item) for item in policy.get("source_experiences", []) or []],
            "promoted_capabilities": promoted,
            "penalized_capabilities": penalized,
            "enforce_penalties": bool(policy.get("enforce_penalties", False)),
            "penalty_candidates": [str(item) for item in policy.get("penalty_candidates", []) or []],
        }
    }


def merge_runtime_learning_policy(project_root: Path, budget: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(budget or {})
    if isinstance(merged.get("learning_policy"), dict):
        return merge_runtime_route_cost_policy(project_root, merged)
    runtime_budget = load_learning_policy_budget(project_root / DEFAULT_PROMOTED_POLICY_PATH)
    if not runtime_budget:
        return merge_runtime_route_cost_policy(project_root, merged)
    merged.update(runtime_budget)
    return merge_runtime_route_cost_policy(project_root, merged)


def load_route_cost_policy_budget(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        policy = load_promoted_learning_policy(path)
    except (OSError, ValueError):
        return {}
    if policy.get("schema_version") != "nexus_promoted_route_cost_policy.v1":
        return {}
    candidate_cap_overrides = policy.get("candidate_cap_overrides", {})
    candidate_cap_overrides = candidate_cap_overrides if isinstance(candidate_cap_overrides, dict) else {}
    lite_route_tasks = [str(item) for item in policy.get("lite_route_tasks", []) or [] if str(item).strip()]
    hold_tasks = [str(item) for item in policy.get("hold_tasks", []) or [] if str(item).strip()]
    if not candidate_cap_overrides and not lite_route_tasks and not hold_tasks:
        return {}
    return {
        "route_cost_policy": {
            "source": str(policy.get("source") or path),
            "candidate_cap_overrides": {
                str(task_id): max(1, int(value))
                for task_id, value in candidate_cap_overrides.items()
                if str(task_id).strip() and _is_positive_int(value)
            },
            "lite_route_tasks": lite_route_tasks,
            "hold_tasks": hold_tasks,
        }
    }


def merge_runtime_route_cost_policy(project_root: Path, budget: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(budget or {})
    if isinstance(merged.get("route_cost_policy"), dict):
        return merged
    env_budget = load_route_cost_policy_budget_from_env()
    if env_budget:
        merged.update(env_budget)
        return merged
    if os.environ.get("NEXUS_DISABLE_PROMOTED_ROUTE_COST_POLICY", "").strip().lower() in {"1", "true", "yes"}:
        return merged
    runtime_budget = load_route_cost_policy_budget(project_root / DEFAULT_ROUTE_COST_POLICY_PATH)
    if runtime_budget:
        merged.update(runtime_budget)
    return merged


def load_route_cost_policy_budget_from_env() -> dict[str, Any]:
    raw = os.environ.get("NEXUS_ROUTE_COST_CONTROLS", "").strip()
    if not raw:
        return {}
    try:
        controls = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(controls, dict):
        return {}
    policy: dict[str, Any] = {"source": str(controls.get("policy_source") or "env:NEXUS_ROUTE_COST_CONTROLS")}
    if controls.get("lite_route") is True:
        policy["current_lite_route"] = True
    if controls.get("hold") is True:
        policy["current_hold"] = True
    if _is_positive_int(controls.get("candidate_cap")):
        policy["current_candidate_cap"] = int(controls["candidate_cap"])
    if len(policy) <= 1:
        return {}
    return {"route_cost_policy": policy}


def route_cost_controls_for_task(project_root: Path, task_id: str, budget: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = merge_runtime_route_cost_policy(project_root, budget)
    policy = merged.get("route_cost_policy", {})
    policy = policy if isinstance(policy, dict) else {}
    overrides = policy.get("candidate_cap_overrides", {})
    overrides = overrides if isinstance(overrides, dict) else {}
    task_id = str(task_id)
    controls: dict[str, Any] = {
        "candidate_cap": overrides.get(task_id),
        "lite_route": task_id in set(policy.get("lite_route_tasks", []) or []),
        "hold": task_id in set(policy.get("hold_tasks", []) or []),
    }
    if any(value not in (None, "", False) for value in controls.values()):
        controls["policy_source"] = str(policy.get("source") or "")
    return {key: value for key, value in controls.items() if value not in (None, "", False)}


def _is_positive_int(value: Any) -> bool:
    try:
        return int(value) >= 1
    except (TypeError, ValueError):
        return False
