from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
from typing import Any

from nexus.contracts.hybrid_route import (
    HybridRouteDecision,
    VerifierResult,
    RouteMode,
    Authority,
    build_hybrid_route_decision,
    hybrid_route_decision_from_payload,
)
from nexus.services.local_heal.local_model_patch_envelope import (
    LocalModelPatchEnvelope,
    parse_local_model_patch_envelope,
)
from nexus.services.local_heal.isolated_workspace_apply import (
    IsolatedApplyRequest,
    IsolatedApplyReceipt,
    run_isolated_workspace_apply,
)
from nexus.services.local_heal.isolated_verifier import (
    IsolatedVerifierRequest,
    IsolatedVerifierReceipt,
    run_isolated_verifier,
)
from nexus.services.local_heal.candidate_isolation_gate import (
    CandidateIsolationReceipt,
    candidate_isolation_to_hybrid_route,
)
from nexus.services.local_heal.hybrid_route_bridge import capability_payload_from_hybrid_route


@dataclass(frozen=True)
class IsolatedLocalSolveRequest:
    task_id: str
    source_root: str
    problem_statement: str
    evidence_refs: tuple[str, ...]
    model_output: str
    verifier_command: tuple[str, ...] = ()
    work_dir: str = ""
    local_model_called: bool = False
    mutation_allowed: bool = False
    verifier_allowed: bool = False


@dataclass(frozen=True)
class IsolatedLocalSolveResponse:
    patch_envelope: LocalModelPatchEnvelope
    apply_receipt: IsolatedApplyReceipt
    verifier_receipt: IsolatedVerifierReceipt
    candidate_isolation_receipt: CandidateIsolationReceipt
    hybrid_route: HybridRouteDecision
    capability_payload: dict[str, Any]


def run_isolated_local_solve_loop(request: IsolatedLocalSolveRequest) -> IsolatedLocalSolveResponse:
    envelope = parse_local_model_patch_envelope(request.task_id, request.model_output)
    
    apply_req = IsolatedApplyRequest(
        task_id=request.task_id,
        source_root=request.source_root,
        target_file=envelope.target_file,
        unified_diff=envelope.unified_diff,
        selected_candidate_hash=envelope.candidate_hash,
        work_dir=request.work_dir,
        mutation_allowed=request.mutation_allowed,
    )
    apply_receipt = run_isolated_workspace_apply(apply_req)
    
    workspace_path = apply_receipt.workspace_path if apply_receipt.workspace_path else request.source_root
    
    verifier_req = IsolatedVerifierRequest(
        task_id=request.task_id,
        workspace_path=workspace_path,
        verifier_command=request.verifier_command,
        verifier_allowed=request.verifier_allowed,
    )
    verifier_receipt = run_isolated_verifier(verifier_req)
    
    vr_mapped = VerifierResult.NOT_RUN
    if verifier_receipt.verifier_status == "pass":
        vr_mapped = VerifierResult.PASS
    elif verifier_receipt.verifier_status == "fail":
        vr_mapped = VerifierResult.FAIL
        
    isolation_receipt = CandidateIsolationReceipt(
        candidate_id=envelope.candidate_id,
        selected_candidate_hash=envelope.candidate_hash,
        applied_patch_hash=apply_receipt.applied_patch_hash,
        selected_candidate_hash_matches_applied=apply_receipt.selected_candidate_hash_matches_applied,
        candidate_output_isolated=apply_receipt.candidate_output_isolated,
        verifier_result=vr_mapped,
        evidence_refs=request.evidence_refs,
        local_model_called=request.local_model_called,
        mutation_allowed=request.mutation_allowed and apply_receipt.patch_apply_status == "applied",
    )
    
    hr_decision = candidate_isolation_to_hybrid_route(isolation_receipt)
    
    blockers = []
    if hr_decision.fallback_block_reason:
        blockers.extend(hr_decision.fallback_block_reason.split(";"))
    if envelope.parser_error:
        blockers.append(envelope.parser_error)
    if apply_receipt.patch_apply_error:
        blockers.append(apply_receipt.patch_apply_error)
    if verifier_receipt.verifier_error:
        blockers.append(verifier_receipt.verifier_error)
        
    fallback_block_reason = ";".join(sorted(set([b for b in blockers if b])))
    
    payload = hr_decision.to_dict()
    payload["fallback_block_reason"] = fallback_block_reason
    
    if fallback_block_reason:
        payload["route_mode"] = RouteMode.LOCAL_ONLY_BLOCKED.value
        payload["authority"] = Authority.TRACE_ONLY.value
        
    final_decision = hybrid_route_decision_from_payload(payload)
    
    capability_payload = capability_payload_from_hybrid_route(final_decision)
    
    return IsolatedLocalSolveResponse(
        patch_envelope=envelope,
        apply_receipt=apply_receipt,
        verifier_receipt=verifier_receipt,
        candidate_isolation_receipt=isolation_receipt,
        hybrid_route=final_decision,
        capability_payload=capability_payload,
    )
