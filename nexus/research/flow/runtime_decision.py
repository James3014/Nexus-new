from __future__ import annotations

from typing import Any

from nexus.research.flow.rlm_trace import safe_trace_slug


def nexus_tier(route_features: dict[str, Any], *, force_flow: str | None) -> dict[str, Any]:
    risk_score = int(route_features.get("risk_score", 0) or 0)
    high_risk = bool(
        risk_score >= 50
        or route_features.get("has_hard_signal")
        or route_features.get("is_cross_module_task")
        or force_flow == "hyper_sprint"
    )
    return {
        "tier": "full" if high_risk else "light",
        "reason": "high_risk_or_forced_hyper" if high_risk else "low_risk_light_governance",
        "risk_score": risk_score,
    }


def claim_check_summary(
    *,
    task_desc: str,
    tests_passed: bool,
    artifact_summary: dict[str, Any],
    route: dict[str, Any],
) -> dict[str, Any]:
    changed = bool(artifact_summary.get("changed", False))
    verification_only = bool(artifact_summary.get("verification_only", False))
    results = [
        {
            "claim_id": "tests_passed",
            "status": "PASS" if tests_passed else "FAIL",
            "evidence_refs": [str(artifact_summary.get("pytest_cmd", ""))],
            "reason": "target tests execution",
        },
        {
            "claim_id": "artifact_or_verification",
            "status": "PASS" if (changed or verification_only) else "FAIL",
            "evidence_refs": [f"changed:{changed}", f"verification_only:{verification_only}"],
            "reason": "artifact mutation or verification-only rescue",
        },
    ]
    claim_text = str(task_desc or "").lower()
    if "claim" in claim_text or "evidence" in claim_text or "verify" in claim_text:
        results.append(
            {
                "claim_id": "claim_keyword_requires_evidence",
                "status": "PASS" if tests_passed else "FAIL",
                "evidence_refs": [f"route_reason:{route.get('recommended_reason', '')}"],
                "reason": "claim-bearing task must retain executable evidence",
            }
        )
    return {"passed": all(str(item.get("status", "")).upper() == "PASS" for item in results), "results": results}


def hitl_payload(*, route_confidence: float, route: dict[str, Any], task_id: str | None) -> dict[str, Any]:
    if route_confidence >= 0.6:
        return {"attach_session": "", "strategic_guidance": "", "reason": "not_required"}
    confidence_text = f"{route_confidence:.2f}"
    hint_mode = ((route.get("route_features", {}) if isinstance(route, dict) else {}) or {}).get("router_hint_mode", "")
    return {
        "attach_session": f"hitl-{safe_trace_slug(task_id or 'task')}",
        "strategic_guidance": (
            f"Low confidence route ({confidence_text}); prioritize reversible steps, "
            f"preserve test evidence, and prefer bounded edits. hint_mode={hint_mode}"
        ),
        "reason": "low_confidence_route",
    }


def asi_record(
    *,
    run_id: int,
    task_desc: str,
    recommended_flow: str,
    chosen_flow: str,
    status: str,
    error: str,
    route_confidence: float,
    execution_family: str = "",
) -> dict[str, Any]:
    metric = 1.0 if str(status).upper() == "SUCCESS" else 0.0
    family = execution_family or f"flow:{recommended_flow or chosen_flow or 'unknown'}"
    return {
        "run_id": run_id,
        "hypothesis": task_desc[:240],
        "family": family,
        "metric_name": "success_rate",
        "metric": metric,
        "status": "keep" if metric >= 1.0 else "discard",
        "decision": "keep" if metric >= 1.0 else "discard",
        "evidence": "artifact_verified" if metric >= 1.0 else "run_failed",
        "rollback_reason": "" if metric >= 1.0 else (error or "failed"),
        "next_action_hint": "consider_distant_scout" if metric < 1.0 else "continue",
        "route_confidence": round(float(route_confidence), 4),
        "schema_version": "nexus_asi_record_v1",
    }


def detect_plateau(asi_ledger: list[dict[str, Any]]) -> dict[str, Any]:
    window = [item for item in asi_ledger[-5:] if isinstance(item, dict)]
    if len(window) < 4:
        return {"detected": False, "reason": "insufficient_window"}
    recent4 = window[-4:]
    statuses = [str(item.get("status", "")).lower() for item in recent4]
    if not all(status == "discard" for status in statuses):
        return {"detected": False, "reason": "status_not_all_discard"}
    families = [str(item.get("family", "")).strip() for item in recent4]
    if len(set(families)) != 1:
        return {"detected": False, "reason": "family_not_stable"}
    metrics = [float(item.get("metric", 0.0) or 0.0) for item in recent4]
    metric_span = max(metrics) - min(metrics)
    if metric_span >= 0.05:
        return {"detected": False, "reason": "metric_variance_too_high", "metric_span": metric_span}
    return {
        "detected": True,
        "reason": "discard_streak_same_family_low_variance",
        "family": families[0],
        "metric_span": metric_span,
        "next_lane": "DISTANT_SCOUT",
    }
