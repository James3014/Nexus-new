from __future__ import annotations

from typing import Any, Mapping

from nexus.services.local_heal.local_model_armor_receipt_gate import (
    validate_capability_causality,
    validate_local_model_armor_metadata,
)


def _selected_capability_status(
    capability: str,
    metadata: Mapping[str, Any],
    *,
    attempt_gate_passed: bool,
    local_model_called: bool,
    solved: bool,
    evidence_refs: tuple[str, ...],
) -> dict[str, Any]:
    if capability == "local_model_executor":
        return {
            "name": capability,
            "selected": True,
            "invoked": local_model_called,
            "evidence_present": bool(evidence_refs),
            "gate_passed": attempt_gate_passed,
            "outcome_contributed": solved,
            "failure_reason": "" if attempt_gate_passed else "executor_receipt_incomplete",
        }

    if capability == "repair_loop":
        actual_execution = bool(metadata.get("localheal_pipeline_actual_execution", False))
        availability_only = bool(metadata.get("localheal_pipeline_availability_only", False))
        gate_passed = actual_execution and not availability_only
        return {
            "name": capability,
            "selected": True,
            "invoked": actual_execution or bool(metadata.get("localheal_pipeline_run_called", False)),
            "evidence_present": bool(metadata.get("pipeline_final_patch")) or bool(evidence_refs),
            "gate_passed": gate_passed,
            "outcome_contributed": solved,
            "failure_reason": (
                "availability_only"
                if availability_only
                else ("" if gate_passed else "actual_execution_missing")
            ),
        }

    if capability in ("ddtree", "autoreason"):
        result = metadata.get(f"{capability}_result", {}) or {}
        return {
            "name": capability,
            "selected": True,
            "invoked": bool(result.get("invoked", False)),
            "evidence_present": bool(result.get("evidence_present", False) or result.get("evidence_refs")),
            "gate_passed": bool(result.get("gate_passed", False)),
            "outcome_contributed": bool(result.get("outcome_contributed", False)),
            "failure_reason": str(result.get("failure_reason", "") or ""),
        }

    if capability in ("artifact_gate", "claim_gate", "delivery_gate"):
        result = ((metadata.get("gate_results", {}) or {}).get(capability, {}) or {})
        return {
            "name": capability,
            "selected": True,
            "invoked": bool(result.get("invoked", False)),
            "evidence_present": bool(result.get("evidence_present", False) or result.get("evidence_refs")),
            "gate_passed": bool(result.get("gate_passed", False)),
            "outcome_contributed": bool(result.get("outcome_contributed", False)),
            "failure_reason": str(result.get("failure_reason", "") or ""),
        }

    if capability == "memory":
        retrieval_attempted = bool(metadata.get("memory_retrieval_attempted", False))
        prompt_included = bool(metadata.get("memory_prompt_included", False))
        selected_count = int(metadata.get("memory_selected_count", 0) or 0)
        no_match = bool(metadata.get("memory_no_match", False))
        evidence_present = bool(selected_count > 0 or metadata.get("memory_query_text_hash"))
        gate_passed = retrieval_attempted and (prompt_included or no_match)
        failure_reason = ""
        if not retrieval_attempted:
            failure_reason = "memory_query_not_executed"
        elif no_match:
            failure_reason = "no_memory_match"
        elif not prompt_included:
            failure_reason = "memory_prompt_not_included"
        return {
            "name": capability,
            "selected": True,
            "invoked": retrieval_attempted,
            "evidence_present": evidence_present,
            "gate_passed": gate_passed,
            "outcome_contributed": bool(prompt_included and solved),
            "failure_reason": failure_reason,
        }

    return {
        "name": capability,
        "selected": True,
        "invoked": False,
        "evidence_present": False,
        "gate_passed": False,
        "outcome_contributed": False,
        "failure_reason": "selected_without_runtime_receipt_mapping",
    }


def _build_profile_transition(
    metadata: Mapping[str, Any],
    planner_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    explicit_initial = str(metadata.get("initial_execution_profile", "") or "")
    explicit_final = str(metadata.get("final_execution_profile", "") or "")
    explicit_history = list(metadata.get("profile_transition_history", []) or [])
    explicit_escalation_count = int(metadata.get("profile_escalation_count", 0) or 0)
    explicit_escalation_reasons = list(metadata.get("profile_escalation_reasons", []) or [])

    planner_selected = str(
        planner_snapshot.get("local_armor_execution_profile")
        or planner_snapshot.get("local_armor_profile")
        or planner_snapshot.get("profile_selected")
        or planner_snapshot.get("execution_profile")
        or planner_snapshot.get("armor_profile")
        or ""
    )
    initial_profile = explicit_initial or planner_selected
    final_profile = explicit_final or planner_selected

    history = [str(item) for item in explicit_history if str(item).strip()]
    if not history:
        if initial_profile and final_profile and initial_profile != final_profile:
            history = [initial_profile, final_profile]
        elif final_profile:
            history = [final_profile]
        elif initial_profile:
            history = [initial_profile]

    transition_present = bool(history)
    transition_evidence_complete = bool(final_profile) and bool(history)
    if initial_profile and final_profile and initial_profile != final_profile and len(history) < 2:
        transition_evidence_complete = False

    return {
        "planner_selected_profile": planner_selected,
        "initial_profile": initial_profile,
        "final_profile": final_profile,
        "transition_history": history,
        "escalation_count": explicit_escalation_count,
        "escalation_reasons": explicit_escalation_reasons,
        "transition_present": transition_present,
        "transition_evidence_complete": transition_evidence_complete,
    }


def _build_attempt_xray(
    metadata: Mapping[str, Any],
    planner_snapshot: Mapping[str, Any],
    *,
    local_model_called: bool,
    evidence_refs: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "planner_snapshot": {
            "execution_topology": str(
                planner_snapshot.get("executor_topology")
                or planner_snapshot.get("execution_topology", "")
                or ""
            ),
            "selected_executor": str(planner_snapshot.get("selected_executor", "") or ""),
            "executor_model": str(planner_snapshot.get("executor_model", "") or ""),
            "protocol_mode": str(planner_snapshot.get("protocol_mode", "") or ""),
            "difficulty": str(
                planner_snapshot.get("difficulty", "")
                or metadata.get("p3_task_difficulty", "")
                or ""
            ),
            "routing_tier": str(planner_snapshot.get("routing_tier", "") or ""),
        },
        "runtime_trace": {
            "provider_invoked": bool(
                metadata.get("actual_provider_invoked", metadata.get("provider_invoked", False))
            ),
            "local_model_called": local_model_called,
            "model_name": str(metadata.get("actual_model_name_used", "") or metadata.get("patch_synthesis_model_name", "") or ""),
            "output_len": int(
                metadata.get("actual_model_output_len", metadata.get("patch_synthesis_output_len", 0)) or 0
            ),
            "candidate_hash": str(metadata.get("selected_candidate_hash", "") or ""),
            "applied_hash": str(metadata.get("applied_patch_hash", "") or ""),
            "hash_match": bool(
                metadata.get("selected_candidate_hash_matches_applied", metadata.get("hash_match", False))
            ),
            "patch_lifecycle_state": str(metadata.get("patch_lifecycle_state", "") or ""),
            "failure_class": str(metadata.get("failure_class", "") or ""),
            "verifier_result": str(metadata.get("verifier_result", "") or ""),
            "verifier_failure_kind": str(metadata.get("verifier_failure_kind", "") or ""),
            "retry_available": bool(metadata.get("retry_available", False)),
            "retry_not_invoked_reason": str(metadata.get("retry_not_invoked_reason", "") or ""),
            "delegated_retry_stage": str(metadata.get("delegated_retry_stage", "") or ""),
            "delegated_retry_provider_called": bool(metadata.get("delegated_retry_provider_called", False)),
            "delegated_retry_status": str(metadata.get("delegated_retry_status", "") or ""),
            "evidence_ref_count": len(evidence_refs),
            "memory_retrieval_attempted": bool(metadata.get("memory_retrieval_attempted", False)),
            "memory_prompt_included": bool(metadata.get("memory_prompt_included", False)),
            "memory_selected_count": int(metadata.get("memory_selected_count", 0) or 0),
            "memory_trace_status": str(metadata.get("memory_trace_status", "") or ""),
            "memory_retrieval_sources": list(metadata.get("memory_retrieval_sources", []) or []),
            "memory_backend_receipts": list(metadata.get("memory_backend_receipts", []) or []),
            "memory_lancedb_query_attempted": bool(metadata.get("memory_lancedb_query_attempted", False)),
            "memory_lancedb_query_succeeded": bool(metadata.get("memory_lancedb_query_succeeded", False)),
            "solved": bool(metadata.get("solved", False)),
        },
    }


def _build_committee_candidate_receipts(metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose candidate-level runtime truth without changing committee policy."""
    receipts: list[dict[str, Any]] = []
    for candidate in metadata.get("committee_candidates", []) or []:
        if not isinstance(candidate, Mapping):
            continue
        receipts.append(
            {
                "candidate_id": str(candidate.get("candidate_id", "") or ""),
                "selected": bool(candidate.get("selected", False)),
                "invoked": bool(candidate.get("invoked", candidate.get("provider_called", False))),
                "evidence_present": bool(candidate.get("evidence_present", False)),
                "gate_passed": bool(candidate.get("gate_passed", False)),
                "outcome_contributed": bool(candidate.get("outcome_contributed", False)),
                "apply_status": str(candidate.get("apply_status", "") or ""),
                "verifier_result": str(candidate.get("isolated_verifier_result", "") or ""),
                "rejection_reason": str(candidate.get("rejection_reason", "") or ""),
            }
        )
    return receipts


def build_local_armor_attempt_receipt(
    *,
    task_id: str,
    metadata: Mapping[str, Any],
    local_model_called: bool,
    evidence_refs: tuple[str, ...],
    provider: str,
    model_name: str,
    planner_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    planner_snapshot = planner_snapshot or {}
    armor_ok, armor_missing = validate_local_model_armor_metadata(metadata)
    causality_ok, causality_issues = validate_capability_causality(metadata)

    selected_candidate_hash = str(metadata.get("selected_candidate_hash", "") or "")
    applied_patch_hash = str(metadata.get("applied_patch_hash", "") or "")
    hash_match = bool(metadata.get("selected_candidate_hash_matches_applied", metadata.get("hash_match", False)))
    candidate_output_isolated = bool(metadata.get("candidate_output_isolated", False))
    verifier_result = str(metadata.get("verifier_result", "") or "not_run")
    solved = bool(metadata.get("solved", False))

    blocked_reasons: list[str] = []
    if not local_model_called:
        blocked_reasons.append("local_model_not_called")
    if not evidence_refs:
        blocked_reasons.append("missing_evidence_refs")
    if not selected_candidate_hash:
        blocked_reasons.append("missing_selected_candidate_hash")
    if not applied_patch_hash:
        blocked_reasons.append("missing_applied_patch_hash")
    if selected_candidate_hash and applied_patch_hash and not hash_match:
        blocked_reasons.append("hash_mismatch")
    if not candidate_output_isolated:
        blocked_reasons.append("candidate_not_isolated")
    if verifier_result != "pass":
        blocked_reasons.append(f"verifier_result:{verifier_result}")
    if not solved:
        blocked_reasons.append("not_solved")
    blocked_reasons.extend(f"metadata:{field}" for field in armor_missing)
    blocked_reasons.extend(f"causality:{field}" for field in causality_issues)

    attempt_gate_passed = not blocked_reasons and armor_ok and causality_ok
    selected_capabilities = tuple(metadata.get("selected_capabilities_used", ()) or ())
    capability_receipts = [
        _selected_capability_status(
            capability,
            metadata,
            attempt_gate_passed=attempt_gate_passed,
            local_model_called=local_model_called,
            solved=solved,
            evidence_refs=evidence_refs,
        )
        for capability in selected_capabilities
    ]
    if "local_model_executor" not in selected_capabilities:
        capability_receipts.insert(
            0,
            _selected_capability_status(
                "local_model_executor",
                metadata,
                attempt_gate_passed=attempt_gate_passed,
                local_model_called=local_model_called,
                solved=solved,
                evidence_refs=evidence_refs,
            ),
        )

    profile_transition = _build_profile_transition(metadata, planner_snapshot)
    attempt_xray = _build_attempt_xray(
        metadata,
        planner_snapshot,
        local_model_called=local_model_called,
        evidence_refs=evidence_refs,
    )
    committee_candidate_receipts = _build_committee_candidate_receipts(metadata)

    return {
        "schema": "nexus.local_heal.local_armor_attempt_receipt.v1",
        "task_id": task_id,
        "execution_topology": str(metadata.get("execution_topology", "") or ""),
        "provider": provider,
        "model_name": model_name,
        "selected_capabilities": list(selected_capabilities),
        "capability_receipts": capability_receipts,
        "committee_candidate_receipts": committee_candidate_receipts,
        "local_model_called": local_model_called,
        "candidate_output_isolated": candidate_output_isolated,
        "selected_candidate_hash": selected_candidate_hash,
        "applied_patch_hash": applied_patch_hash,
        "selected_candidate_hash_matches_applied": hash_match,
        "verifier_result": verifier_result,
        "evidence_refs": list(evidence_refs),
        "solved": solved,
        "attempt_gate_passed": attempt_gate_passed,
        "armor_receipt_complete": armor_ok,
        "armor_receipt_missing_fields": list(armor_missing),
        "capability_causality_complete": causality_ok,
        "capability_causality_issues": list(causality_issues),
        "profile_transition": profile_transition,
        "attempt_xray": attempt_xray,
        "blocked_reasons": blocked_reasons,
        "claim_eligible": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "internal_only": True,
    }
