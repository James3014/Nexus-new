"""Verified-subtask canary with isolated application and deterministic verifier."""

from __future__ import annotations

from typing import Any, Mapping

from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService


CANARY_SCHEMA = "nexus.local_assist.verified_subtask_canary.v1"


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "schema": CANARY_SCHEMA,
        "status": "BLOCKED",
        "failure_reason": reason,
        "automatic_verified_subtask_executed": False,
        "local_assist_invoked": False,
        "verifier_reached": False,
        "formal_workspace_mutated": False,
        "agent_review_required": True,
        "fallback_attempted": False,
        "claim_boundary": {
            "output_consumed": False,
            "outcome_contributed": False,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
        },
    }


def run_verified_subtask_canary(
    *,
    request: LocalAssistRequest,
    recommendation: Mapping[str, Any],
    candidate_canary: Mapping[str, Any],
    source_revision: str,
    verifier_known: bool = True,
    rollback_reference_available: bool = True,
    formal_workspace_mutation_allowed: bool = False,
    service: LocalAssistService | None = None,
) -> dict[str, Any]:
    recommendation = dict(recommendation or {})
    if recommendation.get("action") != "verified-subtask":
        return _blocked("action_not_verified_subtask")
    if candidate_canary.get("status") != "SUCCEEDED":
        return _blocked("candidate_canary_not_proven")
    if not verifier_known:
        return _blocked("verifier_command_missing")
    if not rollback_reference_available:
        return _blocked("rollback_reference_missing")
    if formal_workspace_mutation_allowed:
        return _blocked("formal_mutation_enabled")
    if not source_revision or source_revision != request.workspace_revision:
        return _blocked("workspace_revision_stale")
    if recommendation.get("mutation_allowed") is not False:
        return _blocked("mutation_not_allowed")
    verified_request = request.__class__(
        **{**request.__dict__, "action": "verified-subtask", "requested_role": "candidate"}
    )
    response = (service or LocalAssistService()).handle(verified_request)
    candidate = dict(response.candidate_summary or {})
    verifier = dict(response.verifier_summary or {})
    if response.task_id != request.task_id:
        return _blocked("task_identity_mismatch")
    if candidate.get("isolation_status") != "isolated":
        return {
            **_blocked("candidate_not_isolated"),
            "status": "FAILED",
            "automatic_verified_subtask_executed": True,
            "local_assist_invoked": bool(response.local_model_invoked),
        }
    if not candidate.get("selected_candidate_hash_matches_applied", False):
        return {
            **_blocked("candidate_hash_not_proven"),
            "status": "FAILED",
            "automatic_verified_subtask_executed": True,
            "local_assist_invoked": bool(response.local_model_invoked),
        }
    rollback_reference = str(candidate.get("isolated_workspace", ""))
    if not rollback_reference:
        return {
            **_blocked("rollback_reference_missing"),
            "status": "FAILED",
            "automatic_verified_subtask_executed": True,
            "local_assist_invoked": bool(response.local_model_invoked),
        }
    verifier_status = str(verifier.get("verifier_status", "not_run"))
    if response.status != "SUCCEEDED" and verifier_status == "not_run":
        return {
            **_blocked("candidate_execution_failed"),
            "status": "FAILED",
            "automatic_verified_subtask_executed": True,
            "local_assist_invoked": bool(response.local_model_invoked),
        }
    result = {
        "schema": CANARY_SCHEMA,
        "status": "SUCCEEDED" if verifier_status == "pass" else "FAILED",
        "failure_reason": "" if verifier_status == "pass" else "verifier_failed",
        "automatic_verified_subtask_executed": True,
        "local_assist_invoked": bool(response.local_model_invoked),
        "verifier_reached": bool(verifier.get("verifier_reached", False)),
        "verifier_status": verifier_status,
        "verifier_command": list(request.verifier_command),
        "fallback_attempted": False,
        "formal_workspace_mutated": False,
        "agent_review_required": True,
        "task_id": request.task_id,
        "workspace_revision": request.workspace_revision,
        "rollback_reference": rollback_reference,
        "candidate_identity": candidate,
        "verifier_summary": verifier,
        "assist_receipt_path": response.receipt_path,
        "claim_boundary": {
            "output_consumed": False,
            "outcome_contributed": False,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
        },
    }
    return result
