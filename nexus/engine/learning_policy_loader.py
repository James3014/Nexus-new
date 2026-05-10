from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from nexus.contracts.learning_experience import load_promoted_learning_policy

DEFAULT_PROMOTED_POLICY_PATH = Path(".nexus") / "policy" / "promoted_learning_policy.json"
DEFAULT_ROUTE_COST_POLICY_PATH = Path(".nexus") / "policy" / "promoted_route_cost_policy.json"
DEFAULT_S2T_POLICY_DRAFT_PATH = Path(".nexus") / "policy" / "promoted_s2t_policy_draft.json"
_TRUE_VALUES = {"1", "true", "yes", "on"}


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
        return merge_runtime_s2t_policy_draft(project_root, merge_runtime_route_cost_policy(project_root, merged))
    runtime_budget = load_learning_policy_budget(project_root / DEFAULT_PROMOTED_POLICY_PATH)
    if not runtime_budget:
        return merge_runtime_s2t_policy_draft(project_root, merge_runtime_route_cost_policy(project_root, merged))
    merged.update(runtime_budget)
    return merge_runtime_s2t_policy_draft(project_root, merge_runtime_route_cost_policy(project_root, merged))


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
    feature_rules = policy.get("feature_rules", [])
    feature_rules = feature_rules if isinstance(feature_rules, list) else []
    lite_route_tasks = [str(item) for item in policy.get("lite_route_tasks", []) or [] if str(item).strip()]
    hold_tasks = [str(item) for item in policy.get("hold_tasks", []) or [] if str(item).strip()]
    task_id_policy_enabled = _task_id_route_cost_policy_enabled(policy)
    active_task_controls = bool(candidate_cap_overrides or lite_route_tasks or hold_tasks)
    if not active_task_controls and not feature_rules:
        return {}
    route_policy: dict[str, Any] = {
        "source": str(policy.get("source") or path),
        "feature_rules": [rule for rule in feature_rules if isinstance(rule, dict)],
        "task_id_runtime_policy_enabled": task_id_policy_enabled,
    }
    if task_id_policy_enabled:
        route_policy.update(
            {
                "candidate_cap_overrides": {
                    str(task_id): max(1, int(value))
                    for task_id, value in candidate_cap_overrides.items()
                    if str(task_id).strip() and _is_positive_int(value)
                },
                "lite_route_tasks": lite_route_tasks,
                "hold_tasks": hold_tasks,
            }
        )
    elif active_task_controls:
        route_policy["legacy_task_controls_ignored"] = {
            "candidate_cap_overrides": len(candidate_cap_overrides),
            "lite_route_tasks": len(lite_route_tasks),
            "hold_tasks": len(hold_tasks),
        }
    return {"route_cost_policy": route_policy}


def audit_route_cost_policy(project_root: Path, budget: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = merge_runtime_route_cost_policy(project_root, budget)
    policy = merged.get("route_cost_policy", {})
    policy = policy if isinstance(policy, dict) else {}
    ignored_counts = policy.get("legacy_task_controls_ignored", {})
    ignored_counts = ignored_counts if isinstance(ignored_counts, dict) else {}
    ignored_count = sum(int(value) for value in ignored_counts.values() if _is_positive_int(value) or value == 0)
    active_count = _task_id_policy_count(policy)
    feature_rule_count = len([rule for rule in policy.get("feature_rules", []) or [] if isinstance(rule, dict)])
    task_id_runtime_policy_enabled = bool(policy.get("task_id_runtime_policy_enabled", False))
    failures: list[dict[str, Any]] = []
    if task_id_runtime_policy_enabled and active_count:
        failures.append(
            {
                "reason": "task_id_runtime_route_cost_controls_enabled",
                "task_id_runtime_policy_count": active_count,
            }
        )
    return {
        "schema_version": "nexus_route_cost_policy_audit.v1",
        "passed": not failures,
        "policy_present": bool(policy),
        "source": str(policy.get("source") or ""),
        "feature_rule_count": feature_rule_count,
        "task_id_runtime_policy_enabled": task_id_runtime_policy_enabled,
        "task_id_runtime_policy_count": active_count,
        "legacy_task_controls_ignored_count": ignored_count,
        "legacy_task_controls_ignored": ignored_counts,
        "failures": failures,
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


def load_s2t_policy_draft_budget(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if policy.get("schema") != "nexus_promoted_s2t_policy_draft_v1":
        return {}
    if policy.get("status") != "DRAFT_SHADOW_ONLY":
        return {}
    task_rules = policy.get("task_rules", {})
    task_rules = task_rules if isinstance(task_rules, dict) else {}
    if not task_rules:
        return {}
    return {
        "s2t_policy_draft": {
            "schema": str(policy.get("schema") or ""),
            "status": str(policy.get("status") or ""),
            "source_schema": str(policy.get("source_schema") or ""),
            "trace_event_schema": str(policy.get("trace_event_schema") or ""),
            "task_rules": task_rules,
        }
    }


def merge_runtime_s2t_policy_draft(project_root: Path, budget: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(budget or {})
    if isinstance(merged.get("s2t_policy_draft"), dict):
        return merged
    if os.environ.get("NEXUS_DISABLE_S2T_POLICY_DRAFT", "").strip().lower() in {"1", "true", "yes"}:
        return merged
    runtime_budget = load_s2t_policy_draft_budget(project_root / DEFAULT_S2T_POLICY_DRAFT_PATH)
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
    if controls.get("supervised_bare_first") is True:
        policy["current_supervised_bare_first"] = True
    if controls.get("skip_llm_baseline") is True:
        policy["current_skip_llm_baseline"] = True
    if controls.get("require_llm_baseline") is True:
        policy["current_require_llm_baseline"] = True
    if controls.get("disable_research") is True:
        policy["current_disable_research"] = True
    if _is_positive_int(controls.get("candidate_cap")):
        policy["current_candidate_cap"] = int(controls["candidate_cap"])
    if _is_positive_int(controls.get("max_rounds")):
        policy["current_max_rounds"] = int(controls["max_rounds"])
    context_mode = str(controls.get("context_mode") or "").strip()
    if context_mode:
        policy["current_context_mode"] = context_mode
    route_lane = str(controls.get("route_lane") or "").strip()
    if route_lane:
        policy["current_route_lane"] = route_lane
    if len(policy) <= 1:
        return {}
    return {"route_cost_policy": policy}


def route_cost_controls_from_env() -> dict[str, Any]:
    raw = os.environ.get("NEXUS_ROUTE_COST_CONTROLS", "").strip()
    if not raw:
        return {}
    try:
        controls = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(controls, dict):
        return {}
    allowed = {
        "candidate_cap",
        "context_mode",
        "disable_research",
        "hold",
        "lite_route",
        "max_rounds",
        "policy_source",
        "route_lane",
        "require_llm_baseline",
        "skip_llm_baseline",
        "supervised_bare_first",
        "allow_medium_risk_supervised_bare_first",
    }
    return {key: value for key, value in controls.items() if key in allowed and value not in (None, "", False)}


def route_cost_controls_for_task(
    project_root: Path,
    task_id: str,
    budget: dict[str, Any] | None = None,
    route_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = merge_runtime_route_cost_policy(project_root, budget)
    policy = merged.get("route_cost_policy", {})
    policy = policy if isinstance(policy, dict) else {}
    overrides = policy.get("candidate_cap_overrides", {})
    overrides = overrides if isinstance(overrides, dict) else {}
    feature_controls = _controls_from_feature_rules(policy.get("feature_rules", []), route_features or {})
    task_id = str(task_id)
    controls: dict[str, Any] = {
        "candidate_cap": overrides.get(task_id) or feature_controls.get("candidate_cap") or policy.get("current_candidate_cap"),
        "lite_route": bool(policy.get("current_lite_route", False))
        or bool(feature_controls.get("lite_route", False))
        or task_id in set(policy.get("lite_route_tasks", []) or []),
        "hold": bool(policy.get("current_hold", False))
        or bool(feature_controls.get("hold", False))
        or task_id in set(policy.get("hold_tasks", []) or []),
        "supervised_bare_first": bool(policy.get("current_supervised_bare_first", False))
        or bool(feature_controls.get("supervised_bare_first", False)),
        "allow_medium_risk_supervised_bare_first": bool(
            policy.get("current_allow_medium_risk_supervised_bare_first", False)
        )
        or bool(feature_controls.get("allow_medium_risk_supervised_bare_first", False)),
        "skip_llm_baseline": bool(policy.get("current_skip_llm_baseline", False))
        or bool(feature_controls.get("skip_llm_baseline", False)),
        "disable_research": bool(policy.get("current_disable_research", False))
        or bool(feature_controls.get("disable_research", False)),
        "max_rounds": feature_controls.get("max_rounds") or policy.get("current_max_rounds"),
        "context_mode": feature_controls.get("context_mode") or policy.get("current_context_mode"),
        "route_lane": feature_controls.get("route_lane") or policy.get("current_route_lane"),
        "require_llm_baseline": bool(policy.get("current_require_llm_baseline", False))
        or bool(feature_controls.get("require_llm_baseline", False)),
    }
    if any(value not in (None, "", False) for value in controls.values()):
        controls["policy_source"] = str(feature_controls.get("policy_source") or policy.get("source") or "")
    return {key: value for key, value in controls.items() if value not in (None, "", False)}


def _controls_from_feature_rules(rules: Any, route_features: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rules, list) or not route_features:
        return {}
    normalized = {str(key): value for key, value in route_features.items()}
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        match = rule.get("match", {})
        controls = rule.get("controls", {})
        if not isinstance(match, dict) or not isinstance(controls, dict):
            continue
        if _feature_rule_matches(match, normalized):
            out: dict[str, Any] = {}
            if _is_positive_int(controls.get("candidate_cap")):
                out["candidate_cap"] = int(controls["candidate_cap"])
            if controls.get("lite_route") is True:
                out["lite_route"] = True
            if controls.get("hold") is True:
                out["hold"] = True
            if controls.get("supervised_bare_first") is True:
                out["supervised_bare_first"] = True
            if controls.get("allow_medium_risk_supervised_bare_first") is True:
                out["allow_medium_risk_supervised_bare_first"] = True
            if controls.get("skip_llm_baseline") is True:
                out["skip_llm_baseline"] = True
            if controls.get("require_llm_baseline") is True:
                out["require_llm_baseline"] = True
            if controls.get("disable_research") is True:
                out["disable_research"] = True
            if _is_positive_int(controls.get("max_rounds")):
                out["max_rounds"] = int(controls["max_rounds"])
            context_mode = str(controls.get("context_mode") or "").strip()
            if context_mode:
                out["context_mode"] = context_mode
            route_lane = str(controls.get("route_lane") or "").strip()
            if route_lane:
                out["route_lane"] = route_lane
            out["policy_source"] = str(rule.get("id") or "")
            return out
    return {}


def _feature_rule_matches(match: dict[str, Any], features: dict[str, Any]) -> bool:
    for key, expected in match.items():
        actual = features.get(str(key))
        if isinstance(expected, list):
            if str(actual) not in {str(item) for item in expected}:
                return False
            continue
        if str(actual) != str(expected):
            return False
    return bool(match)


def _task_id_route_cost_policy_enabled(policy: dict[str, Any]) -> bool:
    env_value = os.environ.get("NEXUS_ENABLE_TASK_ID_ROUTE_COST_POLICY", "").strip().lower()
    if env_value in _TRUE_VALUES:
        return True
    return bool(policy.get("allow_task_id_runtime_controls", False))


def _task_id_policy_count(policy: dict[str, Any]) -> int:
    overrides = policy.get("candidate_cap_overrides", {})
    overrides = overrides if isinstance(overrides, dict) else {}
    lite_route_tasks = policy.get("lite_route_tasks", [])
    lite_route_tasks = lite_route_tasks if isinstance(lite_route_tasks, list) else []
    hold_tasks = policy.get("hold_tasks", [])
    hold_tasks = hold_tasks if isinstance(hold_tasks, list) else []
    return len(overrides) + len(lite_route_tasks) + len(hold_tasks)


def _is_positive_int(value: Any) -> bool:
    try:
        return int(value) >= 1
    except (TypeError, ValueError):
        return False
