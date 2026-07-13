"""Narrow, read-only automatic advisor canary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService


CANARY_SCHEMA = "nexus.local_assist.advisor_canary.v1"


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "schema": CANARY_SCHEMA,
        "status": "BLOCKED",
        "failure_reason": reason,
        "automatic_advisor_executed": False,
        "local_assist_invoked": False,
        "candidate_generation": False,
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


def _write(path: str | Path | None, payload: Mapping[str, Any]) -> None:
    if path is None:
        return
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def run_advisor_canary(
    *,
    request: LocalAssistRequest,
    recommendation: Mapping[str, Any],
    calibration: Mapping[str, Any],
    provider_available: bool = True,
    formal_workspace_mutation_possible: bool = False,
    current_workspace_revision: str | None = None,
    service: LocalAssistService | None = None,
    receipt_path: str | Path | None = None,
) -> dict[str, Any]:
    """Execute advisor only after every canary precondition passes."""
    recommendation = dict(recommendation or {})
    calibration = dict(calibration or {})
    if not recommendation:
        result = _blocked("recommendation_absent")
        _write(receipt_path, result)
        return result
    if recommendation.get("action") != "advisor":
        result = _blocked("action_not_advisor")
        _write(receipt_path, result)
        return result
    if calibration.get("status") != "CALIBRATED":
        result = _blocked("shadow_calibration_not_passed")
        _write(receipt_path, result)
        return result
    if recommendation.get("mutation_allowed") is not False:
        result = _blocked("mutation_not_allowed")
        _write(receipt_path, result)
        return result
    if recommendation.get("task_risk") not in {"low", "medium"}:
        result = _blocked("risk_above_canary_limit")
        _write(receipt_path, result)
        return result
    if not provider_available:
        result = _blocked("provider_unavailable")
        _write(receipt_path, result)
        return result
    if formal_workspace_mutation_possible:
        result = _blocked("formal_workspace_mutation_possible")
        _write(receipt_path, result)
        return result
    if current_workspace_revision is not None and current_workspace_revision != request.workspace_revision:
        result = _blocked("workspace_revision_stale")
        _write(receipt_path, result)
        return result
    try:
        recommendation_budget = float(recommendation.get("time_budget_sec", 0) or 0)
        if recommendation_budget <= 0 or request.time_budget <= 0:
            raise ValueError
    except (TypeError, ValueError):
        result = _blocked("invalid_time_budget")
        _write(receipt_path, result)
        return result

    advisor_request = request.__class__(**{**request.__dict__, "action": "advisor", "requested_role": "advisor"})
    response = (service or LocalAssistService()).handle(advisor_request)
    try:
        receipt = json.loads(Path(response.receipt_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        receipt = {}
    if response.task_id != request.task_id:
        failure_reason = "task_identity_mismatch"
    elif not receipt.get("receipt_complete", False):
        failure_reason = "incomplete_receipt"
    elif not response.output_delivered:
        failure_reason = "advisor_output_not_delivered"
    else:
        failure_reason = ""
    status = "SUCCEEDED" if not failure_reason and response.status == "SUCCEEDED" else "FAILED"
    result = {
        "schema": CANARY_SCHEMA,
        "status": status,
        "failure_reason": failure_reason,
        "automatic_advisor_executed": True,
        "local_assist_invoked": bool(response.local_model_invoked),
        "output_delivered": bool(response.output_delivered),
        "candidate_generation": False,
        "formal_workspace_mutated": False,
        "agent_controller": True,
        "task_id": request.task_id,
        "workspace_revision": request.workspace_revision,
        "assist_receipt_path": response.receipt_path,
        "assist_response": response.to_dict(),
        "claim_boundary": {
            "output_consumed": False,
            "outcome_contributed": False,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
        },
    }
    _write(receipt_path, result)
    return result
