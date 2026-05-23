from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.core.event_bus import NexusEventBus
from nexus.research.flow.rlm_trace import safe_trace_slug
from nexus.research.research_stack_contract import research_stack_contract, research_stack_source_projects


RESEARCH_SOURCE_PROJECTS = tuple(research_stack_source_projects())


def research_preflight_packet(*, route: dict[str, Any], route_confidence: float, task_id: str | None) -> dict[str, Any]:
    context = route.get("research_context", {}) if isinstance(route.get("research_context"), dict) else {}
    risk_flags = list(context.get("risk_flags", []) or [])
    blocked_assumptions = list(context.get("blocked_assumptions", []) or [])
    requires_evidence = bool("claim_uncertainty" in risk_flags or blocked_assumptions)
    return {
        "schema": "nexus_research_preflight_v1",
        "task_id": task_id or safe_trace_slug(str(route.get("recommended_reason") or "task")),
        "present": True,
        "blocked": False,
        "requires_evidence": requires_evidence,
        "source_projects": list(RESEARCH_SOURCE_PROJECTS),
        "research_stack": research_stack_contract(),
        "route": {
            "recommended_flow": str(route.get("recommended_flow") or ""),
            "recommended_reason": str(route.get("recommended_reason") or ""),
            "research_context": context,
        },
        "route_confidence": round(float(route_confidence), 4),
        "decision": "requires_evidence" if requires_evidence else "allow_with_research_receipt",
    }


def research_session_packet(
    *,
    task_id: str | None,
    status: str,
    asi_record: dict[str, Any],
    route: dict[str, Any],
    research_preflight: dict[str, Any],
) -> dict[str, Any]:
    context = route.get("research_context", {}) if isinstance(route.get("research_context"), dict) else {}
    return {
        "schema": "nexus_research_session_v1",
        "logged": True,
        "task_id": task_id or safe_trace_slug(str(asi_record.get("hypothesis") or "task")),
        "status": str(asi_record.get("status") or ("keep" if str(status).upper() == "SUCCESS" else "discard")),
        "hypothesis": str(asi_record.get("hypothesis") or ""),
        "family": str(asi_record.get("family") or ""),
        "evidence": str(asi_record.get("evidence") or ""),
        "rollback_reason": str(asi_record.get("rollback_reason") or ""),
        "next_action_hint": str(asi_record.get("next_action_hint") or context.get("next_action_hint") or ""),
        "lane": "distant-scout" if "plateau_detected" in set(context.get("risk_flags", []) or []) else "research-runtime",
        "preflight_decision": str(research_preflight.get("decision") or ""),
        "source_projects": list(RESEARCH_SOURCE_PROJECTS),
        "research_stack": research_stack_contract(),
    }


def governance_events_packet(
    *,
    repo_root: Path,
    task_id: str | None,
    receipt_slug: str,
    artifact_verified: bool,
    claim_probe: dict[str, Any],
) -> dict[str, Any]:
    task_ref = task_id or receipt_slug
    events: list[dict[str, Any]] = []
    reasons: list[str] = []
    if not artifact_verified:
        reasons.append("artifact_unverified")
    if bool(claim_probe.get("eligible")) and not bool(claim_probe.get("gate_passed")):
        reasons.append("claim_probe_gate_failed")

    if artifact_verified:
        events.append(
            {
                "event_type": "evidence_accepted",
                "task_id": task_ref,
                "evidence_id": f"artifact:{receipt_slug}:tests_passed",
                "evidence_type": "artifact",
            }
        )
    else:
        events.append(
            {
                "event_type": "audit_failed",
                "task_id": task_ref,
                "reason": ",".join(reasons) or "artifact_unverified",
                "evidence_id": "",
            }
        )
    events.append(
        {
            "event_type": "learning_decision",
            "task_id": task_ref,
            "action": "INGEST" if artifact_verified else "DISCARD",
            "reasons": reasons,
        }
    )

    try:
        NexusEventBus.configure(repo_root)
        for event in events:
            event_type = str(event.get("event_type") or "")
            if event_type == "evidence_accepted":
                NexusEventBus.emit_evidence_accepted(
                    task_id=task_ref,
                    evidence_id=str(event.get("evidence_id") or ""),
                    evidence_type=str(event.get("evidence_type") or ""),
                )
            elif event_type == "audit_failed":
                NexusEventBus.emit_audit_failure(
                    task_id=task_ref,
                    reason=str(event.get("reason") or ""),
                    evidence_id=str(event.get("evidence_id") or ""),
                )
            elif event_type == "learning_decision":
                NexusEventBus.emit_learning_decision(
                    task_id=task_ref,
                    action=str(event.get("action") or ""),
                    reasons=list(event.get("reasons", []) or []),
                )
    except Exception:
        pass

    return {
        "events": events,
        "summary": {
            "event_count": len(events),
            "event_types": sorted({str(item.get("event_type") or "") for item in events if item.get("event_type")}),
        },
    }
