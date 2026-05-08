from __future__ import annotations

from collections import Counter
from typing import Any


HIGH_COST_CAPABILITIES = {
    "research",
    "external_doc_scout",
    "llm_judge_panel",
    "ultra_review",
    "nightshift",
    "swarm",
    "drone",
}


def _number(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _bool(row: dict[str, Any], key: str) -> bool:
    return bool(row.get(key, False))


def _selected_capabilities(row: dict[str, Any]) -> list[str]:
    raw = row.get("capability_plan_selected") or row.get("capability_stack_selected") or []
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return [str(item) for item in raw or [] if str(item).strip()]


def build_s2t_trace_event(row: dict[str, Any]) -> dict[str, Any]:
    """Build a launchable-style S2T event without changing runtime decisions."""

    selected = _selected_capabilities(row)
    model_calls = int(_number(row, "model_calls"))
    tokens = int(_number(row, "total_tokens", "model_total_tokens"))
    verified = str(row.get("semantic_status") or "").upper() == "VERIFIED" or str(row.get("status") or "").upper() == "SUCCESS"
    high_cost_selected = [cap for cap in selected if cap in HIGH_COST_CAPABILITIES]
    self_heal = _bool(row, "capability_self_heal_used") or str(row.get("nexus_winner_source") or "").startswith("llm_self_heal")
    route_decision_present = bool(str(row.get("route_decision_schema_version") or "").strip())
    risk_score = int(_number(row, "route_risk_score", "codeintel_risk_score"))
    model_id = str(row.get("model_name") or "")
    mode = str(row.get("mode") or "")
    task_type = str(row.get("task_type") or "")
    fixture_kind = str(row.get("fixture_kind") or "")

    selector_profile = "lite"
    selector_reasons: list[str] = []
    if risk_score >= 70 or self_heal or model_calls > 1:
        selector_profile = "strict"
        selector_reasons.append("high_risk_or_second_pass_observed")
    elif high_cost_selected or "evidence" in task_type or "governance" in task_type or route_decision_present:
        selector_profile = "standard"
        selector_reasons.append("governed_or_evidence_route")
    else:
        selector_reasons.append("low_risk_single_pass")

    token_efficiency = "unknown"
    if verified and model_calls <= 1 and tokens <= 50000:
        token_efficiency = "efficient_verified"
    elif verified and (model_calls > 1 or tokens > 80000):
        token_efficiency = "verified_but_expensive"
    elif not verified and model_calls > 0:
        token_efficiency = "spent_without_verified_delivery"

    return {
        "schema": "nexus_s2t_trace_event_v1",
        "task_id": str(row.get("task_id") or ""),
        "trial_index": int(_number(row, "trial_index")),
        "mode": mode,
        "model_id": model_id,
        "task_type": task_type,
        "fixture_kind": fixture_kind,
        "route": {
            "recommended_flow": str(row.get("route_recommended_flow") or ""),
            "chosen_flow": str(row.get("chosen_flow") or ""),
            "strategy_path": str(row.get("strategy_path") or ""),
            "risk_score": risk_score,
            "decision_present": route_decision_present,
        },
        "candidate": {
            "selected_capabilities": selected,
            "high_cost_selected": high_cost_selected,
            "candidate_count": int(_number(row, "route_decision_selected_count", "capability_plan_selected_count")),
        },
        "repair": {
            "self_heal_used": self_heal,
            "winner_source": str(row.get("nexus_winner_source") or row.get("source") or ""),
            "model_calls": model_calls,
        },
        "gate": {
            "claim_verified": _bool(row, "capability_claim_verified"),
            "trust_mismatch": _bool(row, "report_trust_mismatch"),
            "run_eligible": bool(row.get("run_eligible", True)),
        },
        "cost": {
            "wall_time_sec": round(_number(row, "wall_duration_sec", "duration_sec"), 4),
            "tokens": tokens,
            "model_calls": model_calls,
            "token_efficiency": token_efficiency,
        },
        "outcome": {
            "status": str(row.get("status") or ""),
            "semantic_status": str(row.get("semantic_status") or ""),
            "verified": verified,
        },
        "selector_shadow": {
            "profile": selector_profile,
            "reasons": selector_reasons,
            "training_eligible": bool(row.get("run_eligible", True)) and not _bool(row, "report_trust_mismatch"),
        },
    }


def build_s2t_shadow_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    events = [build_s2t_trace_event(row) for row in rows]
    with_events = [event for event in events if event["mode"] == "with_nexus"]
    profile_counts = Counter(event["selector_shadow"]["profile"] for event in with_events)
    efficiency_counts = Counter(event["cost"]["token_efficiency"] for event in with_events)
    expensive_verified = [
        event["task_id"]
        for event in with_events
        if event["outcome"]["verified"] and event["cost"]["token_efficiency"] == "verified_but_expensive"
    ]
    self_heal_wins = [
        event["task_id"]
        for event in with_events
        if event["outcome"]["verified"] and event["repair"]["self_heal_used"]
    ]
    training_events = [event for event in events if event["selector_shadow"]["training_eligible"]]
    return {
        "schema": "nexus_s2t_shadow_report_v1",
        "scope": "shadow_only_no_runtime_decision_change",
        "trace_event_schema": "nexus_s2t_trace_event_v1",
        "events": events,
        "summary": {
            "rows": len(events),
            "with_nexus_rows": len(with_events),
            "training_eligible_rows": len(training_events),
            "selector_profile_counts": dict(sorted(profile_counts.items())),
            "token_efficiency_counts": dict(sorted(efficiency_counts.items())),
            "expensive_verified_task_ids": expensive_verified,
            "self_heal_win_task_ids": self_heal_wins,
        },
        "promotion_gate": {
            "status": "SHADOW_ONLY",
            "requires_before_after_ab": True,
            "minimum_trace_coverage": 0.95,
            "must_not_reduce_verified_delivery": True,
            "must_not_increase_trust_mismatch": True,
            "must_not_increase_high_cost_waste": True,
        },
        "claim_boundary": [
            "S2T shadow report is telemetry for policy learning, not proof of runtime improvement.",
            "Selector profiles are recommendations until promoted by same-model before/after A/B.",
        ],
    }


def build_promoted_s2t_policy(report: dict[str, Any]) -> dict[str, Any]:
    """Draft a Launchable-style policy artifact from shadow traces.

    The artifact is intentionally not active. Runtime promotion still requires
    same-model before/after A/B because shadow traces only explain past runs.
    """

    all_events = list(report.get("events", []) or [])
    events = [event for event in all_events if event.get("mode") == "with_nexus"]
    bare_verified = {
        str(event.get("task_id") or "")
        for event in all_events
        if event.get("mode") == "without_nexus" and bool(event.get("outcome", {}).get("verified", False))
    }
    profile_counts = Counter(event.get("selector_shadow", {}).get("profile", "lite") for event in events)
    task_rules: dict[str, dict[str, Any]] = {}
    for event in events:
        task_id = str(event.get("task_id") or "")
        if not task_id:
            continue
        selector = event.get("selector_shadow", {})
        cost = event.get("cost", {})
        outcome = event.get("outcome", {})
        candidate = event.get("candidate", {})
        repair = event.get("repair", {})
        task_rules[task_id] = {
            "selector_profile": selector.get("profile", "lite"),
            "training_eligible": bool(selector.get("training_eligible", False)),
            "token_efficiency": cost.get("token_efficiency", "unknown"),
            "verified": bool(outcome.get("verified", False)),
            "paired_bare_verified": task_id in bare_verified,
            "high_cost_selected": list(candidate.get("high_cost_selected") or []),
            "self_heal_used": bool(repair.get("self_heal_used", False)),
            "recommended_action": _recommended_action(event, paired_bare_verified=task_id in bare_verified),
        }

    return {
        "schema": "nexus_promoted_s2t_policy_draft_v1",
        "status": "DRAFT_SHADOW_ONLY",
        "source_schema": report.get("schema", ""),
        "trace_event_schema": report.get("trace_event_schema", ""),
        "profile_counts": dict(sorted(profile_counts.items())),
        "task_rules": task_rules,
        "promotion_requirements": {
            "same_model_before_after_ab": True,
            "defensive_run_required": True,
            "minimum_trace_coverage": report.get("promotion_gate", {}).get("minimum_trace_coverage", 0.95),
            "must_not_reduce_verified_delivery": True,
            "must_not_increase_trust_mismatch": True,
            "must_not_increase_high_cost_waste": True,
        },
        "claim_boundary": [
            "Draft policy is a candidate for route planning, not an active runtime policy.",
            "Promotion requires after-run evidence because Launchable-style selection depends on historical validity.",
        ],
    }


def _recommended_action(event: dict[str, Any], *, paired_bare_verified: bool = False) -> str:
    efficiency = event.get("cost", {}).get("token_efficiency", "unknown")
    verified = bool(event.get("outcome", {}).get("verified", False))
    self_heal = bool(event.get("repair", {}).get("self_heal_used", False))
    high_cost = bool(event.get("candidate", {}).get("high_cost_selected") or [])
    trust_mismatch = bool(event.get("gate", {}).get("trust_mismatch", False))
    if trust_mismatch:
        return "hold_for_defensive_run"
    if not verified:
        return "do_not_promote"
    if paired_bare_verified and efficiency == "verified_but_expensive":
        return "try_lite_with_defensive_gate"
    if self_heal:
        return "keep_strict_repair_selector"
    if efficiency == "verified_but_expensive" and high_cost:
        return "try_standard_with_cost_cap"
    if efficiency == "efficient_verified":
        return "prefer_lite_or_standard"
    return "observe_more"
