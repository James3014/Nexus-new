from __future__ import annotations

from typing import Any

from nexus.engine.autoreason_service import AutoreasonService
from nexus.engine.llm_judge_providers import build_judge_providers_from_env


def _existing_autoreason_payload(hyper_learning_trace: dict[str, Any]) -> dict[str, Any]:
    payload = hyper_learning_trace.get("autoreason", {}) if isinstance(hyper_learning_trace, dict) else {}
    return dict(payload) if isinstance(payload, dict) else {}


def _stop_threshold(route: dict[str, Any]) -> int:
    stack = route.get("capability_stack", {}) if isinstance(route, dict) else {}
    if not isinstance(stack, dict):
        return 2
    stop_policy = stack.get("stop_policy", {})
    if not isinstance(stop_policy, dict):
        return 2
    try:
        return int(stop_policy.get("threshold", 2) or 2)
    except (TypeError, ValueError):
        return 2


def _list_values(payload: dict[str, Any], key: str) -> set[str]:
    values = payload.get(key, []) if isinstance(payload, dict) else []
    if not isinstance(values, list):
        return set()
    return {str(item) for item in values}


def _autoreason_route_enabled(route: dict[str, Any]) -> bool:
    """Fail closed unless the planner explicitly selected autoreason."""
    if not isinstance(route, dict):
        return False
    route_decision = route.get("route_decision", {})
    if isinstance(route_decision, dict):
        controls = route_decision.get("executor_controls", {})
        if isinstance(controls, dict) and controls.get("enable_autoreason_executor") is True:
            return True
        if "autoreason" in _list_values(route_decision, "selected_capabilities"):
            return True
    capability_plan = route.get("capability_plan", {})
    if isinstance(capability_plan, dict):
        selected = _list_values(capability_plan, "selected_capabilities")
        pending = _list_values(capability_plan, "pending_capabilities")
        if "autoreason" in selected and "autoreason" not in pending:
            return True
    capability_stack = route.get("capability_stack", {})
    if "autoreason" in _list_values(capability_stack, "selected_capabilities"):
        return True
    return False


def skipped_autoreason_payload(*, stop_reason: str, candidate_factory: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "nexus_autoreason_result_v1",
        "enabled": False,
        "status": "SKIPPED",
        "winner": None,
        "stop_reason": stop_reason,
        "judge_votes": [],
        "borda_scores": {},
    }
    if candidate_factory is not None:
        payload["candidate_factory"] = candidate_factory
    return payload


def build_autoreason_payload(
    *,
    result: dict[str, Any],
    result_report: dict[str, Any],
    hyper_learning_trace: dict[str, Any],
    route: dict[str, Any],
    task_desc: str,
    service: AutoreasonService | None = None,
) -> dict[str, Any]:
    """Build the runtime autoreason payload without leaking orchestration details.

    Existing hyper sprint learning traces remain authoritative when the sprint did
    not emit enough candidate summaries for a fresh A/B/AB tournament.
    """
    existing = _existing_autoreason_payload(hyper_learning_trace)
    summaries = result_report.get("candidate_summaries", []) if isinstance(result_report, dict) else []
    should_run = str(result.get("flow", "")) == "hyper_sprint" and isinstance(summaries, list) and bool(summaries)
    if not should_run:
        return existing or skipped_autoreason_payload(stop_reason="candidate_summaries_missing")
    if not _autoreason_route_enabled(route):
        return existing or skipped_autoreason_payload(stop_reason="route_autoreason_disabled")

    autoreason_service = service or AutoreasonService(judge_providers=build_judge_providers_from_env())
    factory_payload = autoreason_service.candidate_factory_from_summaries(summaries, task_desc=task_desc)
    candidates = factory_payload.get("candidates", []) if isinstance(factory_payload.get("candidates"), list) else []
    if not candidates:
        return skipped_autoreason_payload(stop_reason="candidate_factory_skipped", candidate_factory=factory_payload)

    payload = autoreason_service.run(
        candidates=candidates,
        task_desc=task_desc,
        stop_threshold=_stop_threshold(route),
    )
    payload["candidate_factory"] = factory_payload
    return payload
