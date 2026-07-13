"""Bounded automatic candidate generation with Agent-controlled adoption."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService


CANARY_SCHEMA = "nexus.local_assist.candidate_canary.v1"
_ADOPTION_DECISIONS = {"pending", "adopted", "partially_adopted", "rejected"}


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "schema": CANARY_SCHEMA,
        "status": "BLOCKED",
        "failure_reason": reason,
        "automatic_candidate_executed": False,
        "local_assist_invoked": False,
        "candidate_generated": False,
        "formal_workspace_mutated": False,
        "agent_controller": True,
        "adoption_decision": "pending",
        "claim_boundary": {
            "output_consumed": False,
            "outcome_contributed": False,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
        },
    }


def run_candidate_canary(
    *,
    request: LocalAssistRequest,
    recommendation: Mapping[str, Any],
    advisor_canary: Mapping[str, Any],
    source_revision: str,
    candidate_isolation_available: bool = True,
    formal_workspace_mutation_allowed: bool = False,
    target_bounded: bool = True,
    verifier_known: bool = True,
    service: LocalAssistService | None = None,
) -> dict[str, Any]:
    """Generate an isolated candidate only after the bounded preconditions pass."""
    recommendation = dict(recommendation or {})
    if recommendation.get("action") != "candidate":
        return _blocked("action_not_candidate")
    if advisor_canary.get("status") != "SUCCEEDED":
        return _blocked("advisor_canary_not_proven")
    if not candidate_isolation_available:
        return _blocked("candidate_isolation_unavailable")
    if formal_workspace_mutation_allowed:
        return _blocked("formal_mutation_enabled")
    if not target_bounded:
        return _blocked("target_scope_unbounded")
    if not verifier_known:
        return _blocked("verifier_command_missing")
    if not source_revision or source_revision != request.workspace_revision:
        return _blocked("workspace_revision_stale")
    if recommendation.get("mutation_allowed") is not False:
        return _blocked("mutation_not_allowed")
    candidate_request = request.__class__(**{**request.__dict__, "action": "candidate", "requested_role": "candidate"})
    response = (service or LocalAssistService()).handle(candidate_request)
    candidate = dict(response.candidate_summary or {})
    if response.task_id != request.task_id:
        return _blocked("task_identity_mismatch")
    if response.status != "SUCCEEDED" or candidate.get("isolation_status") != "isolated":
        return {
            **_blocked("candidate_not_isolated"),
            "status": "FAILED",
            "automatic_candidate_executed": True,
            "local_assist_invoked": bool(response.local_model_invoked),
            "candidate_response": response.to_dict(),
        }
    if not candidate.get("selected_candidate_hash_matches_applied", False):
        return {
            **_blocked("candidate_hash_not_proven"),
            "status": "FAILED",
            "automatic_candidate_executed": True,
            "local_assist_invoked": bool(response.local_model_invoked),
            "candidate_response": response.to_dict(),
        }
    return {
        "schema": CANARY_SCHEMA,
        "status": "SUCCEEDED",
        "failure_reason": "",
        "automatic_candidate_executed": True,
        "local_assist_invoked": bool(response.local_model_invoked),
        "candidate_generated": bool(response.output_delivered),
        "formal_workspace_mutated": False,
        "agent_controller": True,
        "task_id": request.task_id,
        "workspace_revision": request.workspace_revision,
        "candidate_identity": candidate,
        "candidate_response": response.to_dict(),
        "candidate_receipt_path": response.receipt_path,
        "adoption_decision": "pending",
        "claim_boundary": {
            "output_consumed": False,
            "outcome_contributed": False,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
        },
    }


def record_candidate_adoption(
    canary_result: Mapping[str, Any],
    *,
    decision: str,
    consumed_candidate_hash: str = "",
) -> dict[str, Any]:
    """Record Agent adoption without applying anything to the formal workspace."""
    result = dict(canary_result)
    normalized = "partially_adopted" if decision == "partial" else decision
    if normalized not in _ADOPTION_DECISIONS:
        raise ValueError("invalid_adoption_decision")
    if result.get("status") != "SUCCEEDED":
        return {**result, "adoption_decision": "rejected", "failure_reason": "candidate_not_usable"}
    identity = dict(result.get("candidate_identity", {}) or {})
    expected = str(identity.get("selected_candidate_hash", ""))
    if normalized in {"adopted", "partially_adopted"} and (
        not consumed_candidate_hash or consumed_candidate_hash != expected
    ):
        return {
            **result,
            "adoption_decision": "rejected",
            "failure_reason": "candidate_hash_mismatch",
            "formal_workspace_mutated": False,
        }
    return {
        **result,
        "adoption_decision": normalized,
        "consumed_candidate_hash": consumed_candidate_hash,
        "adoption_evidence": {
            "agent_controller": True,
            "formal_workspace_mutated": False,
            "candidate_hash_verified": normalized == "rejected" or consumed_candidate_hash == expected,
        },
    }
