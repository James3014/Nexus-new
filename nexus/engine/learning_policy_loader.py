from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from nexus.engine.learning_policy_store import DEFAULT_LEARNING_POLICY_STORE, LearningPolicyStore

DEFAULT_PROMOTED_POLICY_PATH = Path(".nexus") / "policy" / "promoted_learning_policy.json"
DEFAULT_DYNAMIC_LEARNING_POLICY_PATH = Path(".nexus") / "memory" / "dynamic_learning_policy.json"
DEFAULT_ROUTE_COST_POLICY_PATH = Path(".nexus") / "policy" / "promoted_route_cost_policy.json"
DEFAULT_S2T_POLICY_DRAFT_PATH = Path(".nexus") / "policy" / "promoted_s2t_policy_draft.json"
_TRUE_VALUES = {"1", "true", "yes", "on"}
EXPECTED_EXECUTOR_CAPABILITIES = frozenset(
    {
        "autoreason",
        "ddtree",
        "drone",
        "nightshift",
        "swarm",
        "ultra_review",
    }
)
EXPECTED_CANDIDATE_FACTORY_CAPABILITIES = frozenset({"autoreason", "ddtree"})
GATE_ONLY_SUPERVISED_CAPABILITIES = frozenset(
    {
        "artifact_gate",
        "belief",
        "claim_gate",
        "delivery_gate",
        "mempalace_gate",
    }
)
PREFLIGHT_SUPERVISED_CAPABILITIES = frozenset({"codeintel", "memory"})
GATE_ONLY_RECEIPT_LITE_LANES = frozenset(
    {
        "feature_reflex",
        "governance_hardened",
        "governance_hardened_capped",
        "hidden_bugfix_supervised",
        "trust_supervised_scope_only",
    }
)
ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES = frozenset({"swarm", "ultra_review"})
DETERMINISTIC_ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES = frozenset(
    {
        "autoreason",
        "bdd_acceptance_skill",
        "ddtree",
        "drone",
        "lancedb",
        "nightshift",
        "research",
        "semantic_failure_sensor",
        "semantic_searcher",
        "swarm_quiet_moment",
    }
)


def load_learning_policy_budget(path: Path, store: LearningPolicyStore | None = None) -> dict[str, Any]:
    policy = (store or DEFAULT_LEARNING_POLICY_STORE).read_promoted_policy(path)
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


def load_dynamic_learning_policy_budget(path: Path, store: LearningPolicyStore | None = None) -> dict[str, Any]:
    try:
        policy = (store or DEFAULT_LEARNING_POLICY_STORE).read_json_policy(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    if policy.get("schema_version") != "nexus_dynamic_learning_policy.v1":
        return {}
    if policy.get("status") != "PASS":
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
            "source": str(path),
            "source_schema": "nexus_dynamic_learning_policy.v1",
        }
    }


def merge_runtime_learning_policy(
    project_root: Path,
    budget: dict[str, Any] | None = None,
    store: LearningPolicyStore | None = None,
) -> dict[str, Any]:
    merged = dict(budget or {})
    if isinstance(merged.get("learning_policy"), dict):
        route_budget = merge_runtime_route_cost_policy(project_root, merged, store=store)
        return merge_runtime_s2t_policy_draft(project_root, route_budget, store=store)
    runtime_budget = load_learning_policy_budget(project_root / DEFAULT_PROMOTED_POLICY_PATH, store=store)
    dynamic_budget = load_dynamic_learning_policy_budget(project_root / DEFAULT_DYNAMIC_LEARNING_POLICY_PATH, store=store)
    if runtime_budget and dynamic_budget:
        runtime_policy = runtime_budget["learning_policy"]
        dynamic_policy = dynamic_budget["learning_policy"]
        runtime_budget["learning_policy"] = {
            **runtime_policy,
            "source_experiences": sorted(
                set((runtime_policy.get("source_experiences", []) or []) + (dynamic_policy.get("source_experiences", []) or []))
            ),
            "promoted_capabilities": sorted(
                set((runtime_policy.get("promoted_capabilities", []) or []) + (dynamic_policy.get("promoted_capabilities", []) or []))
            ),
            "penalized_capabilities": sorted(
                set((runtime_policy.get("penalized_capabilities", []) or []) + (dynamic_policy.get("penalized_capabilities", []) or []))
            ),
            "dynamic_policy_source": dynamic_policy.get("source"),
        }
    elif dynamic_budget:
        runtime_budget = dynamic_budget
    if not runtime_budget:
        route_budget = merge_runtime_route_cost_policy(project_root, merged, store=store)
        return merge_runtime_s2t_policy_draft(project_root, route_budget, store=store)
    merged.update(runtime_budget)
    route_budget = merge_runtime_route_cost_policy(project_root, merged, store=store)
    return merge_runtime_s2t_policy_draft(project_root, route_budget, store=store)


def load_route_cost_policy_budget(path: Path, store: LearningPolicyStore | None = None) -> dict[str, Any]:
    try:
        policy = (store or DEFAULT_LEARNING_POLICY_STORE).read_promoted_policy(path)
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
    feature_scope = _feature_rule_scope_summary(policy.get("feature_rules", []))
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
        "feature_rule_scope": feature_scope,
        "task_id_runtime_policy_enabled": task_id_runtime_policy_enabled,
        "task_id_runtime_policy_count": active_count,
        "legacy_task_controls_ignored_count": ignored_count,
        "legacy_task_controls_ignored": ignored_counts,
        "failures": failures,
    }


def merge_runtime_route_cost_policy(
    project_root: Path,
    budget: dict[str, Any] | None = None,
    store: LearningPolicyStore | None = None,
) -> dict[str, Any]:
    merged = dict(budget or {})
    if isinstance(merged.get("route_cost_policy"), dict):
        return merged
    env_budget = load_route_cost_policy_budget_from_env()
    if env_budget:
        merged.update(env_budget)
        return merged
    if os.environ.get("NEXUS_DISABLE_PROMOTED_ROUTE_COST_POLICY", "").strip().lower() in {"1", "true", "yes"}:
        return merged
    runtime_budget = load_route_cost_policy_budget(project_root / DEFAULT_ROUTE_COST_POLICY_PATH, store=store)
    if runtime_budget:
        merged.update(runtime_budget)
    return merged


def load_s2t_policy_draft_budget(path: Path, store: LearningPolicyStore | None = None) -> dict[str, Any]:
    try:
        policy = (store or DEFAULT_LEARNING_POLICY_STORE).read_json_policy(path)
    except (OSError, ValueError):
        return {}
    if policy.get("schema") != "nexus_promoted_s2t_policy_draft_v1":
        return {}
    status = str(policy.get("status") or "")
    runtime_promotable = status == "PROMOTED_RUNTIME" and _s2t_promotion_gate_passed(policy)
    if status != "DRAFT_SHADOW_ONLY" and not runtime_promotable:
        return {}
    task_rules = policy.get("task_rules", {})
    task_rules = task_rules if isinstance(task_rules, dict) else {}
    if not task_rules:
        return {}
    return {
        "s2t_policy_draft": {
            "schema": str(policy.get("schema") or ""),
            "status": status,
            "source_schema": str(policy.get("source_schema") or ""),
            "trace_event_schema": str(policy.get("trace_event_schema") or ""),
            "runtime_promotable": runtime_promotable,
            "promotion_gate": policy.get("promotion_gate", {}) if isinstance(policy.get("promotion_gate", {}), dict) else {},
            "task_rules": task_rules,
        }
    }


def merge_runtime_s2t_policy_draft(
    project_root: Path,
    budget: dict[str, Any] | None = None,
    store: LearningPolicyStore | None = None,
) -> dict[str, Any]:
    merged = dict(budget or {})
    if isinstance(merged.get("s2t_policy_draft"), dict):
        return merged
    if os.environ.get("NEXUS_DISABLE_S2T_POLICY_DRAFT", "").strip().lower() in {"1", "true", "yes"}:
        return merged
    runtime_budget = load_s2t_policy_draft_budget(project_root / DEFAULT_S2T_POLICY_DRAFT_PATH, store=store)
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
    if controls.get("allow_high_risk_supervised_bare_first") is True:
        policy["current_allow_high_risk_supervised_bare_first"] = True
    if controls.get("allow_pre_model_deterministic_rescue") is True:
        policy["current_allow_pre_model_deterministic_rescue"] = True
    if controls.get("skip_llm_baseline") is True:
        policy["current_skip_llm_baseline"] = True
    if controls.get("require_llm_baseline") is True:
        policy["current_require_llm_baseline"] = True
    expected = _normalize_expected_capabilities(controls.get("protected_expected_capabilities"))
    if expected:
        policy["protected_expected_capabilities"] = sorted(expected)
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
        "allow_high_risk_supervised_bare_first",
        "allow_pre_model_deterministic_rescue",
        "autoreason_mixed_candidate_pool",
        "ddtree_mixed_candidate_pool",
        "gate_only_receipt_lite",
        "route_oracle_receipt_lite",
        "belief_receipt_lite",
        "hyper_receipt_lite",
        "preflight_receipt_lite",
        "swarm_receipt_executor",
        "expected_capability_protection",
        "protected_expected_capabilities",
    }
    return {key: value for key, value in controls.items() if key in allowed and value not in (None, "", False)}


def route_cost_controls_for_task(
    project_root: Path,
    task_id: str,
    budget: dict[str, Any] | None = None,
    route_features: dict[str, Any] | None = None,
    expected_capabilities: Any | None = None,
) -> dict[str, Any]:
    merged = merge_runtime_route_cost_policy(project_root, budget)
    policy = merged.get("route_cost_policy", {})
    policy = policy if isinstance(policy, dict) else {}
    overrides = policy.get("candidate_cap_overrides", {})
    overrides = overrides if isinstance(overrides, dict) else {}
    feature_controls = _controls_from_feature_rules(policy.get("feature_rules", []), route_features or {})
    task_id = str(task_id)
    lane = feature_controls.get("route_lane") or policy.get("current_route_lane")
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
        "allow_high_risk_supervised_bare_first": bool(
            policy.get("current_allow_high_risk_supervised_bare_first", False)
        )
        or bool(feature_controls.get("allow_high_risk_supervised_bare_first", False)),
        "allow_pre_model_deterministic_rescue": bool(
            policy.get("current_allow_pre_model_deterministic_rescue", False)
        )
        or bool(feature_controls.get("allow_pre_model_deterministic_rescue", False))
        or (lane == "hidden_bugfix_supervised"),
        "skip_llm_baseline": bool(policy.get("current_skip_llm_baseline", False))
        or bool(feature_controls.get("skip_llm_baseline", False))
        or (lane in {"governance_hardened", "governance_hardened_capped"}),
        "disable_research": bool(policy.get("current_disable_research", False))
        or bool(feature_controls.get("disable_research", False)),
        "max_rounds": feature_controls.get("max_rounds") or policy.get("current_max_rounds"),
        "context_mode": feature_controls.get("context_mode") or policy.get("current_context_mode"),
        "route_lane": lane,
        "require_llm_baseline": bool(policy.get("current_require_llm_baseline", False))
        or bool(feature_controls.get("require_llm_baseline", False)),
    }
    if any(value not in (None, "", False) for value in controls.values()):
        controls["policy_source"] = str(feature_controls.get("policy_source") or policy.get("source") or "")
    controls = {key: value for key, value in controls.items() if value not in (None, "", False)}
    if expected_capabilities is None:
        expected_capabilities = policy.get("protected_expected_capabilities")
    controls, _ = protect_expected_capability_controls(controls, expected_capabilities)
    return controls


def build_route_cost_policy_usage_ledger(policy: dict[str, Any], rows: Any) -> dict[str, Any]:
    """Summarize which promoted feature rules are still earning their keep."""
    feature_rules = policy.get("feature_rules", []) if isinstance(policy, dict) else []
    feature_rules = feature_rules if isinstance(feature_rules, list) else []
    source_rows = [row for row in (rows or []) if isinstance(row, dict)]
    rules: list[dict[str, Any]] = []
    for rule in feature_rules:
        if not isinstance(rule, dict):
            continue
        rule_id = str(rule.get("id") or "")
        match = rule.get("match", {}) if isinstance(rule.get("match"), dict) else {}
        matched = [row for row in source_rows if _feature_rule_matches(match, {str(k): v for k, v in row.items()})]
        rules.append(
            {
                "id": rule_id,
                "matched_count": len(matched),
                "status": "active" if matched else "dehydrate_candidate",
                "match": match,
            }
        )
    return {
        "schema_version": "nexus_route_cost_policy_usage_ledger.v1",
        "rule_count": len(rules),
        "active_count": sum(1 for rule in rules if rule["status"] == "active"),
        "dehydrate_candidate_count": sum(1 for rule in rules if rule["status"] == "dehydrate_candidate"),
        "rules": rules,
    }


def expected_capability_executor_flags(expected_capabilities: Any) -> dict[str, bool]:
    expected = _normalize_expected_capabilities(expected_capabilities)
    return {
        "enable_autoreason_executor": "autoreason" in expected,
        "enable_ddtree_executor": "ddtree" in expected,
        "enable_ultra_review_dry_gate": "ultra_review" in expected,
    }


def protect_expected_capability_controls(
    route_cost_controls: dict[str, Any] | None,
    expected_capabilities: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep route-cost slimming from disconnecting explicitly audited capabilities."""

    controls = dict(route_cost_controls or {})
    expected = _normalize_expected_capabilities(expected_capabilities)
    gate_only_receipt_lite = bool(
        expected
        and expected <= GATE_ONLY_SUPERVISED_CAPABILITIES
        and controls.get("route_lane") in GATE_ONLY_RECEIPT_LITE_LANES
        and controls.get("context_mode") == "compact"
        and int(controls.get("max_rounds", 0) or 0) == 1
        and controls.get("disable_research") is True
    )
    if gate_only_receipt_lite:
        controls["gate_only_receipt_lite"] = True
        controls["supervised_bare_first"] = True
        controls["allow_medium_risk_supervised_bare_first"] = True
        controls["allow_pre_model_deterministic_rescue"] = True
    route_oracle_receipt_lite = bool(
        expected
        and expected <= (ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES | DETERMINISTIC_ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES)
        and controls.get("route_lane")
        in (
            GATE_ONLY_RECEIPT_LITE_LANES
            | {"context_sync_capped", "feature_reflex", "hidden_lite", "memory_contract_compact"}
        )
        and controls.get("context_mode") == "compact"
        and int(controls.get("max_rounds", 0) or 0) == 1
        and controls.get("disable_research") is True
    )
    if route_oracle_receipt_lite:
        controls["route_oracle_receipt_lite"] = True
        controls["allow_pre_model_deterministic_rescue"] = True
    belief_receipt_lite = bool(
        expected == {"belief"}
        and controls.get("route_lane") == "belief_budget_hardened_capped"
        and controls.get("context_mode") == "compact"
        and int(controls.get("max_rounds", 0) or 0) == 1
        and controls.get("disable_research") is True
    )
    if belief_receipt_lite:
        controls["belief_receipt_lite"] = True
        controls["allow_pre_model_deterministic_rescue"] = True
    hyper_receipt_lite = bool(
        expected == {"hyper", "delivery_gate"}
        and controls.get("route_lane") == "repair_capped"
        and controls.get("context_mode") == "compact"
        and int(controls.get("max_rounds", 0) or 0) == 1
        and controls.get("disable_research") is True
    )
    if hyper_receipt_lite:
        controls["hyper_receipt_lite"] = True
        controls["allow_pre_model_deterministic_rescue"] = True
    if (
        "swarm" in expected
        and controls.get("route_lane") in GATE_ONLY_RECEIPT_LITE_LANES
        and controls.get("context_mode") == "compact"
        and int(controls.get("max_rounds", 0) or 0) == 1
        and controls.get("disable_research") is True
    ):
        controls["swarm_receipt_executor"] = True
    preflight_supervised = bool(
        controls.get("route_lane") in (GATE_ONLY_RECEIPT_LITE_LANES | {"context_sync_capped", "memory_contract_compact"})
        and expected
        and expected - GATE_ONLY_SUPERVISED_CAPABILITIES <= PREFLIGHT_SUPERVISED_CAPABILITIES
    )
    if preflight_supervised:
        controls["preflight_receipt_lite"] = True
        controls["allow_pre_model_deterministic_rescue"] = True
    receipt_lite_baseline = (
        ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES | DETERMINISTIC_ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES
        if route_oracle_receipt_lite
        else frozenset()
    )
    supervised_baseline = (
        GATE_ONLY_SUPERVISED_CAPABILITIES
        | receipt_lite_baseline
        | (PREFLIGHT_SUPERVISED_CAPABILITIES if preflight_supervised else frozenset())
    )
    protected = sorted(expected - supervised_baseline)
    if not protected:
        return controls, {}

    overrides: dict[str, Any] = {"protected_expected_capabilities": protected}

    if expected & EXPECTED_CANDIDATE_FACTORY_CAPABILITIES:
        candidate_cap = _positive_int_or_zero(controls.get("candidate_cap"))
        if "ddtree" in expected and candidate_cap < 3:
            overrides["candidate_cap"] = controls.pop("candidate_cap", None)
            controls["candidate_cap"] = 3
        if (
            "ddtree" in expected
            and controls.get("disable_research") is True
            and controls.get("context_mode") == "compact"
        ):
            controls["ddtree_mixed_candidate_pool"] = True
        if (
            "autoreason" in expected
            and controls.get("disable_research") is True
            and controls.get("context_mode") == "compact"
        ):
            if candidate_cap < 2:
                overrides["candidate_cap"] = controls.pop("candidate_cap", None)
            controls["autoreason_mixed_candidate_pool"] = True
        elif "ddtree" not in expected and candidate_cap < 2:
            overrides["candidate_cap"] = controls.pop("candidate_cap", None)
        if controls.get("lite_route") is True:
            overrides["lite_route"] = True
            controls["lite_route"] = False

    if expected - supervised_baseline and controls.get("supervised_bare_first") is True:
        overrides["supervised_bare_first"] = True
        controls["supervised_bare_first"] = False

    if "research" in expected and controls.get("disable_research") is True:
        overrides["disable_research"] = True
        controls["disable_research"] = False

    if controls.get("skip_llm_baseline") is True and not (
        controls.get("route_oracle_receipt_lite") is True
        or controls.get("belief_receipt_lite") is True
        or controls.get("gate_only_receipt_lite") is True
        or controls.get("hyper_receipt_lite") is True
        or controls.get("preflight_receipt_lite") is True
    ):
        overrides["skip_llm_baseline"] = True
        controls.pop("skip_llm_baseline", None)
        controls["require_llm_baseline"] = True

    if len(overrides) > 1:
        controls["expected_capability_protection"] = protected
        return controls, overrides
    return controls, {}


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
            if controls.get("allow_high_risk_supervised_bare_first") is True:
                out["allow_high_risk_supervised_bare_first"] = True
            if controls.get("allow_pre_model_deterministic_rescue") is True:
                out["allow_pre_model_deterministic_rescue"] = True
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


def _normalize_expected_capabilities(value: Any) -> set[str]:
    if value in (None, "", False):
        return set()
    items: list[Any]
    if isinstance(value, str):
        items = re.split(r"[,\\s]+", value)
    elif isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
    else:
        items = [value]
    normalized: set[str] = set()
    for item in items:
        text = str(item).strip().lower().replace("-", "_").replace(" ", "_")
        if text:
            normalized.add(text)
    return normalized


def _positive_int_or_zero(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 1 else 0


def _feature_rule_scope_summary(rules: Any) -> dict[str, Any]:
    valid_rules = [rule for rule in (rules or []) if isinstance(rule, dict)]
    fixture_locked = 0
    generic = 0
    ids: list[str] = []
    for rule in valid_rules:
        match = rule.get("match", {})
        match = match if isinstance(match, dict) else {}
        rule_id = str(rule.get("id") or "")
        if rule_id:
            ids.append(rule_id)
        if str(match.get("repo_kind") or "") == "neutral_fixture":
            fixture_locked += 1
        else:
            generic += 1
    return {
        "total": len(valid_rules),
        "fixture_locked": fixture_locked,
        "generic": generic,
        "fixture_only": bool(valid_rules) and fixture_locked == len(valid_rules),
        "ids": ids,
    }


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


def _s2t_promotion_gate_passed(policy: dict[str, Any]) -> bool:
    gate = policy.get("promotion_gate", {})
    if not isinstance(gate, dict) or gate.get("passed") is not True:
        return False
    try:
        trust_mismatch_rate = float(gate.get("trust_mismatch_rate", 1.0))
        sample_count = int(gate.get("sample_count", 0))
    except (TypeError, ValueError):
        return False
    rollback_policy = str(gate.get("rollback_policy") or "").strip()
    return trust_mismatch_rate == 0.0 and sample_count >= 1 and bool(rollback_policy)


def _is_positive_int(value: Any) -> bool:
    try:
        return int(value) >= 1
    except (TypeError, ValueError):
        return False
