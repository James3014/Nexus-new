from __future__ import annotations

from typing import Any


def feature_rule_matches(match: dict[str, Any], features: dict[str, Any]) -> bool:
    for key, expected in match.items():
        actual = features.get(str(key))
        if isinstance(expected, list):
            if str(actual) not in {str(item) for item in expected}:
                return False
            continue
        if str(actual) != str(expected):
            return False
    return bool(match)


def controls_from_feature_rules(rules: Any, route_features: dict[str, Any]) -> dict[str, Any]:
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
        if feature_rule_matches(match, normalized):
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


def _is_positive_int(value: Any) -> bool:
    try:
        return int(value) >= 1
    except (TypeError, ValueError):
        return False
