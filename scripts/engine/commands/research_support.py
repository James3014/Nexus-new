from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexus.app import research_flow_service
from nexus.engine.completion_contract import build_completion_envelope
from nexus.research.session_loop_service import ResearchSessionLoopService


def read_json_file(repo_root: Path, path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.is_absolute():
        path = repo_root / path
    return json.loads(path.read_text(encoding="utf-8"))


def research_session_preflight(
    repo_root: Path,
    *,
    session_id: str,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    target_file: str | None = None,
    scope: list[str] | None = None,
    enforce_gate: bool = False,
) -> dict[str, Any]:
    route = research_flow_service.build_route(
        repo_root=repo_root,
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
        target_file=target_file,
    )
    svc = ResearchSessionLoopService(repo_root)
    manifest = svc.load_manifest(session_id)
    if not manifest.get("goal"):
        manifest = svc.onboarding(
            session_id=session_id,
            goal=task_desc,
            scope=list(scope or ([target_file] if target_file else [])),
        )
    recommendation = svc.recommend_next(session_id=session_id, route=route)
    research_context = route.get("research_context", {}) if isinstance(route.get("research_context"), dict) else {}
    risk_flags = set(research_context.get("risk_flags", []) or [])
    blocked_assumptions = set(research_context.get("blocked_assumptions", []) or [])
    blocked = bool(
        enforce_gate
        and (
            "claim_uncertainty" in risk_flags
            or "api_contract_not_verified" in blocked_assumptions
        )
    )
    next_action = str(
        research_context.get("next_action_hint")
        or recommendation["nextStep"]["nextAction"].get("reason")
        or "recommend-next"
    )
    return {
        "schema": "nexus_research_preflight_v1",
        "session_id": manifest["session_id"],
        "blocked": blocked,
        "block_reasons": ["claim_uncertainty_requires_research"] if blocked else [],
        "next_action": next_action,
        "route": route,
        "recommendation": recommendation,
    }


def research_preflight_block_payload(*, command_name: str, task_name: str, preflight: dict[str, Any]) -> dict[str, Any]:
    payload = build_completion_envelope(
        command_name=command_name,
        task_name=task_name,
        runtime_ok=False,
        execution_path=f"cli->{command_name}->research_session_preflight",
        semantic_failures=preflight.get("block_reasons", []),
        blocker_type="research_preflight",
        semantic_status="BLOCKED",
        retryable=False,
        next_action=str(preflight.get("next_action") or "recommend-next"),
    )
    payload.update(
        {
            "status": "blocked",
            "research_preflight": preflight,
        }
    )
    return payload


def attach_research_session_result(
    repo_root: Path,
    *,
    session_id: str,
    report_payload: dict[str, Any],
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    svc = ResearchSessionLoopService(repo_root)
    route = preflight.get("route", {}) if isinstance(preflight, dict) else {}
    packet = svc.packet(session_id=session_id, report=report_payload, route=route)
    status = "keep" if report_payload.get("semantic_status") == "VERIFIED" else "checks_failed"
    logged = svc.log_from_last(
        session_id=session_id,
        status=status,
        description=str(report_payload.get("task_name") or report_payload.get("run_id") or "research session result"),
        asi={
            "hypothesis": str(report_payload.get("task_name") or report_payload.get("run_id") or ""),
            "evidence": str(report_payload.get("semantic_status") or ""),
            "rollback_reason": "" if status == "keep" else str(report_payload.get("blocker_type") or "not_verified"),
            "next_action_hint": str(report_payload.get("next_action") or "none"),
        },
    )
    return {
        "session_id": session_id,
        "packet_id": packet.get("packet_id"),
        "status": status,
        "logged": bool(logged.get("logged")),
    }
