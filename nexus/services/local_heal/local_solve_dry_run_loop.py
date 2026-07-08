from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from nexus.contracts.hybrid_route import (
    HybridRouteDecision,
    build_hybrid_route_decision,
    hybrid_route_decision_from_payload,
)
from nexus.services.local_heal.local_model_patch_envelope import (
    LocalModelPatchEnvelope,
    parse_local_model_patch_envelope,
)
from nexus.services.local_heal.local_model_apply_dry_run import (
    LocalModelApplyDryRunReceipt,
    run_local_model_apply_dry_run,
)
from nexus.services.local_heal.candidate_isolation_gate import (
    CandidateIsolationReceipt,
    candidate_isolation_to_hybrid_route,
)
from nexus.services.local_heal.hybrid_route_bridge import capability_payload_from_hybrid_route


@dataclass(frozen=True)
class LocalSolveDryRunRequest:
    task_id: str
    problem_statement: str
    evidence_refs: tuple[str, ...]
    model_output: str
    verifier_result: str = "not_run"
    local_model_called: bool = False
    mutation_allowed: bool = False


@dataclass(frozen=True)
class LocalSolveDryRunResponse:
    patch_envelope: LocalModelPatchEnvelope
    apply_receipt: LocalModelApplyDryRunReceipt
    candidate_isolation_receipt: CandidateIsolationReceipt
    hybrid_route: HybridRouteDecision
    capability_payload: dict[str, Any]


def run_local_solve_dry_run_loop(
    request: LocalSolveDryRunRequest,
    *,
    apply_fn: Callable[[LocalModelPatchEnvelope], str] | None = None,
) -> LocalSolveDryRunResponse:
    
    envelope = parse_local_model_patch_envelope(request.task_id, request.model_output)
    
    apply_receipt = run_local_model_apply_dry_run(envelope, apply_fn=apply_fn)
    
    # 建立隔離憑證，安全旗標使用來自 Request 且對應 apply 狀態
    isolation_receipt = CandidateIsolationReceipt(
        candidate_id=envelope.candidate_id,
        selected_candidate_hash=envelope.candidate_hash,
        applied_patch_hash=apply_receipt.applied_patch_hash,
        selected_candidate_hash_matches_applied=apply_receipt.selected_candidate_hash_matches_applied,
        candidate_output_isolated=apply_receipt.candidate_output_isolated,
        verifier_result=request.verifier_result,
        evidence_refs=request.evidence_refs,
        local_model_called=request.local_model_called,
        mutation_allowed=request.mutation_allowed and apply_receipt.patch_apply_status == "applied",
        candidate_target_file=envelope.target_file,
    )
    
    hr_decision = candidate_isolation_to_hybrid_route(isolation_receipt)
    
    blockers = []
    if hr_decision.fallback_block_reason:
        blockers.extend(hr_decision.fallback_block_reason.split(";"))
    if envelope.parser_error:
        blockers.append(envelope.parser_error)
    if apply_receipt.patch_apply_error:
        blockers.append(apply_receipt.patch_apply_error)
        
    fallback_block_reason = ";".join(sorted(set([b for b in blockers if b])))
    
    payload = hr_decision.to_dict()
    payload["fallback_block_reason"] = fallback_block_reason
    
    final_decision = hybrid_route_decision_from_payload(payload)
    
    capability_payload = capability_payload_from_hybrid_route(final_decision)
    
    return LocalSolveDryRunResponse(
        patch_envelope=envelope,
        apply_receipt=apply_receipt,
        candidate_isolation_receipt=isolation_receipt,
        hybrid_route=final_decision,
        capability_payload=capability_payload,
    )
