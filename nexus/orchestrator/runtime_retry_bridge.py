"""Adapters from the legacy task service to the installed retry runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nexus_runtime.task_retry import (
    CLEAN_SEMANTIC_REJECT,
    RetryService,
    VerifierResidualPacket,
)

from nexus.orchestrator.acceptance_loop import (
    AcceptanceDecision,
    CandidateAcceptanceRequest,
    CandidateAcceptanceResult,
    IndependentReviewReceipt,
    reduce_candidate_acceptance,
)


class _State:
    def __init__(self, owner):
        self.owner = owner

    def read_snapshot(self, task_id):
        return self.owner._read_state_snapshot(task_id)

    def persist(self, task_id, state):
        self.owner._mutate_state(task_id, lambda current: current.update(dict(state)))


class _Contract:
    def __init__(self, owner):
        self.owner = owner

    def maximum_attempts(self, request):
        if "maximum_attempts_per_task" not in request:
            from . import self_hosted_task_service as module

            return module.DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK
        raw = request["maximum_attempts_per_task"]
        try:
            if isinstance(raw, bool):
                raise ValueError("bool")
            value = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"ATTEMPT_BUDGET_INVALID:{raw!r}") from None
        if value < 1:
            raise ValueError(f"ATTEMPT_BUDGET_INVALID:{raw!r}")
        return value

    def build_retry_request(self, state):
        callback = getattr(self.owner, "_retry_request", None)
        if callable(callback):
            return callback(state)
        from . import self_hosted_task_service as module

        return module._retry_request(state)


class _Dispatch:
    def __init__(self, owner):
        self.owner = owner

    def workforce_inputs(self, request):
        from . import self_hosted_task_service as module

        return module._workforce_dispatch_inputs(request)

    def recover_predecessor(self, state, request, failure):
        from . import self_hosted_task_service as module

        return module._recover_pre_provider_cli_envelope_drift(state, request, failure)

    def validate_predecessor(self, request, state):
        from . import self_hosted_task_service as module

        bound = dict(request)
        bound.update(
            task_id=str(state.get("task_id") or ""),
            attempt_id=str(state.get("attempt_id") or ""),
            task_card_path=str(state.get("task_card_path") or request.get("task_card_path") or ""),
            task_card_hash=str(state.get("task_card_hash") or request.get("task_card_hash") or ""),
            canonical_dispatch_envelope=state.get("canonical_dispatch_envelope"),
        )
        return module.validate_workforce_dispatch_binding(bound, require_binding=True)

    def validate_repair(self, request):
        from . import self_hosted_task_service as module

        return module.validate_workforce_dispatch_binding(dict(request), require_binding=True)

    def rebind_fresh_attempt(self, request, dispatch):
        from . import self_hosted_task_service as module

        envelope = module.build_canonical_dispatch_envelope(
            request.get("planner_output"),
            dispatch,
            task_id=str(request.get("task_id") or ""),
            attempt_id=str(request.get("attempt_id") or ""),
            task_card_path=str(request.get("task_card_path") or ""),
            task_card_hash=str(request.get("task_card_hash") or ""),
        ).to_dict()
        result = dict(request)
        result.update({"canonical_dispatch_envelope": envelope})
        bound_request = result.get("bound_action_request")
        action = result.get("action")
        if isinstance(bound_request, Mapping) and isinstance(action, Mapping):
            bound_request = dict(bound_request)
            bound_request["canonical_dispatch_envelope"] = envelope
            request_hash = module.canonical_request_hash(bound_request)
            result["bound_action_request"] = bound_request
            result["action"] = {
                **dict(action),
                "request_hash": request_hash,
            }
            result["action_request_hash"] = request_hash
        return result

    def validate_fresh(self, request, state):
        from . import self_hosted_task_service as module

        return module.validate_workforce_dispatch_binding(request, require_binding=True)


class _Submission:
    def __init__(self, owner):
        self.owner = owner

    def submit(self, request):
        return self.owner.submit_task(dict(request))


_TERMINAL_CLEANUP = frozenset({"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"})
_WAVE20_CLAIM_CEILING = "WAVE20_BOUNDED_RECONCILIATION_PHYSICAL_INTEGRATION_CANARY_ONLY"


def _candidate_field(state: Mapping[str, Any], field: str) -> Any:
    packet = state.get("promotion_packet")
    if not isinstance(packet, Mapping):
        packet = {}
    return state.get(field) or packet.get(field)


def _require_terminal_predecessor(state: Mapping[str, Any]) -> None:
    if state.get("status") != "FINAL_BLOCK" or state.get("terminal_status") != "FINAL_BLOCK":
        raise RuntimeError("BOUNDED_RECONCILIATION_PREDECESSOR_NOT_TERMINAL")
    if state.get("cleanup_decision") not in _TERMINAL_CLEANUP:
        raise RuntimeError("BOUNDED_RECONCILIATION_PREDECESSOR_NOT_CLEANED")
    if state.get("target_present") is True:
        raise RuntimeError("BOUNDED_RECONCILIATION_PREDECESSOR_TARGET_STILL_PRESENT")
    if state.get("lease"):
        raise RuntimeError("BOUNDED_RECONCILIATION_PREDECESSOR_LEASE_ACTIVE")
    if state.get("active_provider"):
        raise RuntimeError("BOUNDED_RECONCILIATION_PREDECESSOR_PROVIDER_ACTIVE")
    if state.get("worker_pid") or state.get("worker_child_pgid"):
        raise RuntimeError("BOUNDED_RECONCILIATION_PREDECESSOR_PROCESS_ACTIVE")
    if state.get("has_unresolved_external_effect") is not False:
        raise RuntimeError("BOUNDED_RECONCILIATION_PREDECESSOR_EFFECT_TRUTH_UNKNOWN")
    active_effect_count = state.get("active_effect_count")
    if (
        isinstance(active_effect_count, bool)
        or not isinstance(active_effect_count, int)
        or active_effect_count != 0
    ):
        raise RuntimeError("BOUNDED_RECONCILIATION_PREDECESSOR_EFFECT_ACTIVE_OR_UNKNOWN")
    execution = state.get("execution")
    if isinstance(execution, Mapping):
        outcome = str(execution.get("outcome") or "").upper()
        if outcome in {"", "UNKNOWN", "OUTCOME_UNKNOWN", "RUNNING", "PENDING"}:
            raise RuntimeError("BOUNDED_RECONCILIATION_PREDECESSOR_EFFECT_UNKNOWN")


def _validate_candidate_binding(
    state: Mapping[str, Any],
    request: CandidateAcceptanceRequest,
) -> str:
    expected = {
        "candidate_commit_sha": request.candidate_commit_sha,
        "candidate_tree_sha": request.candidate_tree_sha,
        "candidate_state_hash": request.candidate_state_hash,
        "verified_receipt_hash": request.verified_receipt_hash,
    }
    for field, value in expected.items():
        if _candidate_field(state, field) != value:
            raise RuntimeError(f"BOUNDED_RECONCILIATION_CANDIDATE_BINDING_MISMATCH:{field}")
    contract = state.get("contract")
    contract = contract if isinstance(contract, Mapping) else {}
    source_revision = str(
        state.get("target_initial_revision") or contract.get("target_base_revision") or ""
    ).strip()
    if not source_revision:
        raise RuntimeError("BOUNDED_RECONCILIATION_SOURCE_REVISION_MISSING")
    return source_revision


def _build_repair_projection(
    state: Mapping[str, Any],
    request: CandidateAcceptanceRequest,
    review: IndependentReviewReceipt,
    acceptance: CandidateAcceptanceResult,
    *,
    repair_target: str,
) -> dict[str, Any]:
    if acceptance.decision is not AcceptanceDecision.REPAIRABLE:
        raise RuntimeError("BOUNDED_RECONCILIATION_ACCEPTANCE_NOT_REPAIRABLE")
    if state.get("task_id") != request.task_id:
        raise RuntimeError("BOUNDED_RECONCILIATION_TASK_BINDING_MISMATCH")
    current_acceptance = state.get("acceptance_decision")
    if current_acceptance not in (None, "NOT_REPAIRABLE", "REPAIRABLE"):
        raise RuntimeError("BOUNDED_RECONCILIATION_ACCEPTANCE_STATE_CONFLICT")
    if state.get("attempt_id") != request.attempt_id:
        raise RuntimeError("BOUNDED_RECONCILIATION_ATTEMPT_BINDING_MISMATCH")
    _require_terminal_predecessor(state)
    source_revision = _validate_candidate_binding(state, request)
    failed_invariants = tuple(acceptance.reasons) or ("independent_review_defect",)
    verifier_receipt_ref = f"sha256:{review.verifier_artifact_hash}"
    residual = VerifierResidualPacket.build(
        task_id=request.task_id,
        predecessor_attempt_id=request.attempt_id,
        candidate_id=request.candidate_commit_sha,
        candidate_sha256=request.candidate_state_hash,
        source_revision=source_revision,
        verifier_id=review.reviewer_id,
        verifier_version=review.schema,
        verifier_receipt_ref=verifier_receipt_ref,
        failure_class=CLEAN_SEMANTIC_REJECT,
        residual_family="INDEPENDENT_REVIEW_DEFECT",
        failed_invariants=failed_invariants,
        counterexample_refs=(verifier_receipt_ref,),
        repair_target=repair_target,
        claim_ceiling=_WAVE20_CLAIM_CEILING,
    )
    return {
        "acceptance_decision": AcceptanceDecision.REPAIRABLE.value,
        "candidate_identity": {
            "candidate_id": request.candidate_commit_sha,
            "candidate_sha256": request.candidate_state_hash,
            "source_revision": source_revision,
        },
        "verifier_identity": {
            "verifier_id": review.reviewer_id,
            "verifier_version": review.schema,
            "receipt_ref": verifier_receipt_ref,
        },
        "verifier_residual": residual.to_dict(),
        "bounded_reconciliation_projection": {
            "schema": "nexus.wave20.bounded_reconciliation_projection.v1",
            "acceptance_binding_hash": acceptance.binding_hash,
            "residual_packet_sha256": residual.packet_sha256,
            "predecessor_attempt_id": request.attempt_id,
            "candidate_commit_sha": request.candidate_commit_sha,
            "candidate_tree_sha": request.candidate_tree_sha,
            "candidate_state_hash": request.candidate_state_hash,
            "verified_receipt_hash": request.verified_receipt_hash,
            "repair_target": repair_target,
            "claim_ceiling": _WAVE20_CLAIM_CEILING,
            "approval_performed": False,
            "integration_performed": False,
            "merge_performed": False,
            "public_claim_allowed": False,
            "production_ready": False,
            "runtime_is_planner_authority": False,
            "runtime_is_completion_authority": False,
        },
    }


def project_candidate_acceptance_for_runtime_repair(
    owner,
    request: CandidateAcceptanceRequest | Mapping[str, Any],
    review: IndependentReviewReceipt | Mapping[str, Any],
    *,
    verified_repair_evidence: Mapping[str, Any] | None = None,
    repair_target: str = "IMPLEMENTATION",
) -> dict[str, Any]:
    request_obj = (
        request
        if isinstance(request, CandidateAcceptanceRequest)
        else CandidateAcceptanceRequest(**dict(request))
    )
    review_obj = (
        review
        if isinstance(review, IndependentReviewReceipt)
        else IndependentReviewReceipt(**dict(review))
    )
    acceptance = reduce_candidate_acceptance(
        request_obj,
        review_obj,
        verified_repair_evidence=verified_repair_evidence,
    )
    acceptance_dict = acceptance.to_dict()
    if acceptance.decision is not AcceptanceDecision.REPAIRABLE:
        return {
            "acceptance": acceptance_dict,
            "repair_projection": None,
            "mutated": False,
        }

    state = owner._read_state_snapshot(request_obj.task_id)
    if state is None:
        raise RuntimeError("BOUNDED_RECONCILIATION_STATE_MISSING")
    projection = _build_repair_projection(
        state,
        request_obj,
        review_obj,
        acceptance,
        repair_target=repair_target,
    )

    mutated = {"value": False}

    def apply(current):
        current_projection = _build_repair_projection(
            current,
            request_obj,
            review_obj,
            acceptance,
            repair_target=repair_target,
        )
        existing = current.get("bounded_reconciliation_projection")
        if existing is not None:
            if existing != current_projection["bounded_reconciliation_projection"]:
                raise RuntimeError("BOUNDED_RECONCILIATION_CONFLICTING_EXISTING_PROJECTION")
            return
        current.update(current_projection)
        mutated["value"] = True

    owner._mutate_state(request_obj.task_id, apply)
    return {
        "acceptance": acceptance_dict,
        "repair_projection": projection["bounded_reconciliation_projection"],
        "residual_packet": projection["verifier_residual"],
        "mutated": mutated["value"],
    }


def retry_task_via_runtime(owner, task_id: str) -> dict[str, Any]:
    return RetryService(
        _State(owner), _Contract(owner), _Dispatch(owner), _Submission(owner)
    ).retry_task(task_id)
