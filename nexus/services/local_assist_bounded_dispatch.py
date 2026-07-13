"""Compose calibrated Local Assist actions into a bounded dispatch envelope."""

from __future__ import annotations

from typing import Any, Mapping

from nexus.services.local_assist_advisor_canary import run_advisor_canary
from nexus.services.local_assist_candidate_canary import run_candidate_canary
from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService
from nexus.services.local_assist_verified_canary import run_verified_subtask_canary


DISPATCH_SCHEMA = "nexus.local_assist.bounded_dispatch.v1"
_ACTIONS = {"skip", "advisor", "candidate", "verified-subtask"}


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "schema": DISPATCH_SCHEMA,
        "status": "BLOCKED",
        "failure_reason": reason,
        "automatic_dispatch": False,
        "local_assist_invoked": False,
        "formal_workspace_mutated": False,
        "agent_controller": True,
        "claim_boundary": {
            "output_consumed": False,
            "outcome_contributed": False,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
        },
    }


def _with_lineage(
    result: Mapping[str, Any],
    *,
    request: LocalAssistRequest,
    recommendation: Mapping[str, Any],
    agent_actual_choice: str,
    override_reason: str,
) -> dict[str, Any]:
    result = dict(result)
    match = agent_actual_choice == "pending" or agent_actual_choice == recommendation.get("action")
    return {
        **result,
        "schema": DISPATCH_SCHEMA,
        "task_id": request.task_id,
        "workspace_revision": request.workspace_revision,
        "planner_recommendation": dict(recommendation),
        "agent_actual_choice": agent_actual_choice,
        "recommendation_match": match,
        "recommendation_overridden": agent_actual_choice != "pending" and not match,
        "override_reason": override_reason if agent_actual_choice != "pending" and not match else "",
        "automatic_dispatch": bool(result.get("automatic_dispatch", result.get("status") not in {"BLOCKED", "SKIPPED"})),
        "agent_controller": True,
        "formal_workspace_mutated": False,
    }


def dispatch_local_assist(
    *,
    request: LocalAssistRequest,
    recommendation: Mapping[str, Any],
    recommendation_receipt: Mapping[str, Any] | None,
    calibration: Mapping[str, Any],
    agent_actual_choice: str = "pending",
    override_reason: str = "",
    advisor_canary: Mapping[str, Any] | None = None,
    candidate_canary: Mapping[str, Any] | None = None,
    service: LocalAssistService | None = None,
) -> dict[str, Any]:
    """Dispatch only a receipt-backed, calibrated recommendation."""
    recommendation = dict(recommendation or {})
    receipt = dict(recommendation_receipt or {})
    if not receipt:
        return _blocked("recommendation_receipt_missing")
    if receipt.get("task_id") != request.task_id or receipt.get("workspace_revision") != request.workspace_revision:
        return _blocked("task_lineage_mismatch")
    if receipt.get("planner_recommendation") != recommendation:
        return _blocked("recommendation_receipt_mismatch")
    if calibration.get("status") != "CALIBRATED":
        return _blocked("calibration_not_passed")
    action = recommendation.get("action")
    if action not in _ACTIONS:
        return _blocked("invalid_recommendation_action")
    if agent_actual_choice not in _ACTIONS | {"pending"}:
        return _blocked("invalid_agent_actual_choice")
    if agent_actual_choice != "pending" and agent_actual_choice != action and not override_reason.strip():
        return _blocked("override_reason_required")

    if action == "skip":
        result = {
            "status": "SKIPPED",
            "failure_reason": "",
            "local_assist_invoked": False,
            "assist_result": {"status": "not_invoked"},
        }
        return _with_lineage(
            result,
            request=request,
            recommendation=recommendation,
            agent_actual_choice=agent_actual_choice,
            override_reason=override_reason,
        )
    if action == "advisor":
        result = run_advisor_canary(
            request=request,
            recommendation=recommendation,
            calibration=calibration,
            service=service,
        )
    elif action == "candidate":
        result = run_candidate_canary(
            request=request,
            recommendation=recommendation,
            advisor_canary=dict(advisor_canary or {}),
            source_revision=request.workspace_revision,
            service=service,
        )
    else:
        result = run_verified_subtask_canary(
            request=request,
            recommendation=recommendation,
            candidate_canary=dict(candidate_canary or {}),
            source_revision=request.workspace_revision,
            service=service,
        )
    return _with_lineage(
        {"assist_result": result, **result},
        request=request,
        recommendation=recommendation,
        agent_actual_choice=agent_actual_choice,
        override_reason=override_reason,
    )
