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
