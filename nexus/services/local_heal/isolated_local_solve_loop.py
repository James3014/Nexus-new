from __future__ import annotations

from dataclasses import dataclass
import os
import re
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
from nexus.services.local_heal.local_model_source_anchor import build_local_model_source_anchor


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
    target_file: str = ""
    target_symbol: str = ""
    locked_search: str = ""


@dataclass(frozen=True)
class IsolatedLocalSolveResponse:
    patch_envelope: LocalModelPatchEnvelope
    apply_receipt: IsolatedApplyReceipt
    verifier_receipt: IsolatedVerifierReceipt
    candidate_isolation_receipt: CandidateIsolationReceipt
    hybrid_route: HybridRouteDecision
    capability_payload: dict[str, Any]


def is_patch_outside_span(unified_diff: str, span_start: int, span_end: int) -> bool:
    pattern = re.compile(r"@@ -(\d+),?(\d+)? \+\d+,?\d* @@")
    matches = list(pattern.finditer(unified_diff))
    if not matches:
        return False
    for match in matches:
        hunk_start = int(match.group(1))
        hunk_len = int(match.group(2)) if match.group(2) else 1
        hunk_end = hunk_start + hunk_len - 1
        if hunk_start < span_start or hunk_end > span_end:
            return True
    return False


def run_isolated_local_solve_loop(request: IsolatedLocalSolveRequest) -> IsolatedLocalSolveResponse:
    envelope = parse_local_model_patch_envelope(request.task_id, request.model_output)
    
    from nexus.services.local_heal.diff_repair import RepairReceipt
    repair_receipt = RepairReceipt(False, False, "none", "", "", "none", False)
    
    from nexus.services.local_heal.diff_normalizer import normalize_diff_header
    normalized_diff, normalizer_receipt = normalize_diff_header(envelope.unified_diff, request.target_file)
    
    if normalizer_receipt.normalized:
        import hashlib
        from dataclasses import replace
        new_hash = hashlib.sha256(normalized_diff.encode("utf-8")).hexdigest()
        envelope = replace(
            envelope,
            target_file=request.target_file,
            unified_diff=normalized_diff,
            candidate_hash=new_hash,
        )
        
    anchor = build_local_model_source_anchor(
        source_root=request.source_root,
        target_file=request.target_file,
        target_symbol=request.target_symbol,
        patch_diff=envelope.unified_diff,
        locked_search=request.locked_search,
    )
    
    has_constraint_blockers = False
    loop_blockers = []
    
    if "source_anchor_missing" in anchor.blockers:
        loop_blockers.append("SOURCE_ANCHOR_MISSING")
        has_constraint_blockers = True
        
    if envelope.parser_status == "blocked":
        loop_blockers.append(envelope.parser_error)
        has_constraint_blockers = True
        
    if envelope.parser_status == "pass":
        orig_file = normalizer_receipt.original_target_file if getattr(normalizer_receipt, "normalized", False) else envelope.target_file
        normalized = os.path.normpath(orig_file or "")
        if normalized.startswith("/") or normalized.startswith("..") or ".." in normalized.split(os.sep):
            loop_blockers.append("path_traversal_detected")
            loop_blockers.append("SEARCH_MISMATCH")
            has_constraint_blockers = True
            
        if not has_constraint_blockers:
            if not envelope.target_file or os.path.normpath(envelope.target_file) != os.path.normpath(request.target_file):
                loop_blockers.append("target_file_mismatch")
                loop_blockers.append("SEARCH_MISMATCH")
                has_constraint_blockers = True
                
        # De-escalate is_patch_outside_span check to downstream to allow deterministic repair to resolve malformed spans
        pass
                
    if has_constraint_blockers:
        apply_receipt = IsolatedApplyReceipt(
            task_id=request.task_id,
            workspace_path="",
            target_file=request.target_file,
            patch_apply_status="blocked",
            patch_apply_error="constraint_violation",
            selected_candidate_hash=envelope.candidate_hash,
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=False,
            candidate_output_isolated=False,
            mutation_allowed=False,
        )
        verifier_receipt = IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            verifier_error="constraint_violation",
            verifier_allowed=False,
        )
    else:
        from nexus.services.local_heal.diff_repair import repair_malformed_diff
        
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
        
        orig_outside = False
        if anchor.span_start > 0 and anchor.span_end > 0:
            orig_outside = is_patch_outside_span(envelope.unified_diff, anchor.span_start, anchor.span_end)
            
        if (apply_receipt.patch_apply_status == "failed" or orig_outside) and request.locked_search:
            from dataclasses import replace
            repaired_diff, rep_receipt = repair_malformed_diff(
                envelope.unified_diff,
                request.target_file,
                request.locked_search,
                span_start=anchor.span_start if anchor.span_start > 0 else 1,
                source_root=request.source_root,
            )
            repair_receipt = rep_receipt
            if repair_receipt.repair_success:
                envelope = replace(
                    envelope,
                    unified_diff=repaired_diff,
                    candidate_hash=repair_receipt.repaired_patch_hash,
                )
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
        mutation_allowed=request.mutation_allowed,
        repaired_by_rule=repair_receipt.repaired_by_rule,
    )
    
    hr_decision = candidate_isolation_to_hybrid_route(isolation_receipt)
    
    blockers = list(loop_blockers)
    if hr_decision.fallback_block_reason:
        blockers.extend(hr_decision.fallback_block_reason.split(";"))
        
    if anchor.span_start > 0 and anchor.span_end > 0:
        if is_patch_outside_span(envelope.unified_diff, anchor.span_start, anchor.span_end):
            blockers.append("patch_outside_locked_span")
            blockers.append("SEARCH_MISMATCH")
            
    if apply_receipt.patch_apply_status == "failed":
        blockers.append("PATCH_APPLY_FAILED")
        if apply_receipt.patch_apply_error:
            blockers.append(apply_receipt.patch_apply_error)
            
    if verifier_receipt.verifier_status == "fail":
        blockers.append("VERIFIER_FAIL")
        
    if (
        apply_receipt.patch_apply_status == "applied"
        and not apply_receipt.selected_candidate_hash_matches_applied
        and repair_receipt.repaired_by_rule == "none"
    ):
        blockers.append("HASH_MISMATCH")
        
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
    
    metadata = dict(capability_payload.get("metadata", {}))
    metadata.update({
        "canonical_span_source": anchor.canonical_span_source,
        "fallback_used": anchor.fallback_used,
        "target_symbol": request.target_symbol,
        "selected_candidate_hash": envelope.candidate_hash,
        "applied_patch_hash": apply_receipt.applied_patch_hash,
        "applied_patch_hash_source": apply_receipt.applied_patch_hash_source,
        "verifier_status": verifier_receipt.verifier_status,
        "original_target_file": normalizer_receipt.original_target_file,
        "normalized_target_file": normalizer_receipt.normalized_target_file,
        "normalization_reason": normalizer_receipt.normalization_reason,
        "normalized_by_rule": normalizer_receipt.normalized_by_rule,
        "normalized": normalizer_receipt.normalized,
        "repair_attempted": repair_receipt.repair_attempted,
        "repair_success": repair_receipt.repair_success,
        "repair_reason": repair_receipt.repair_reason,
        "repaired_by_rule": repair_receipt.repaired_by_rule,
        "still_within_locked_span": repair_receipt.still_within_locked_span,
    })
    capability_payload["metadata"] = metadata
    
    return IsolatedLocalSolveResponse(
        patch_envelope=envelope,
        apply_receipt=apply_receipt,
        verifier_receipt=verifier_receipt,
        candidate_isolation_receipt=isolation_receipt,
        hybrid_route=final_decision,
        capability_payload=capability_payload,
    )
