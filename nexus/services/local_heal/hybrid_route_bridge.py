from __future__ import annotations

from typing import Any, Mapping

from nexus.contracts.hybrid_route import (
    HybridRouteDecision,
    RouteMode,
    VerifierResult,
    Authority,
    build_hybrid_route_decision,
)
from nexus.services.local_heal.local_model_adapter_contract import LocalModelAdapterReceipt
from nexus.services.local_heal.first_solve_harness import SolveAttemptReceipt
from nexus.services.local_heal.native_validation_bridge import ValidationReceipt


def hybrid_route_from_local_model_receipt(receipt: LocalModelAdapterReceipt) -> HybridRouteDecision:
    # 由於 LocalModelAdapterReceipt 本身不含有獨立的 applied_patch_hash 或 selected re-apply 證明，
    # 絕對不能發布為 LOCAL_ONLY_EXECUTED，必須強制設為 LOCAL_ONLY_BLOCKED。
    route_mode = RouteMode.LOCAL_ONLY_BLOCKED
    authority = Authority.TRACE_ONLY
    verifier_result = _map_verifier_result(receipt.verifier_result)
    applied_patch_hash = ""
    selected_candidate_hash_matches_applied = False
    
    blockers = ["missing_applied_patch_hash"]
    if receipt.verifier_result != "pass":
        blockers.append("verifier_fail_or_not_run")
    if not receipt.evidence_refs:
        blockers.append("missing_evidence_refs")
    if not receipt.candidate_output_isolated:
        blockers.append("missing_candidate_isolation")
    if not receipt.selected_candidate_hash:
        blockers.append("missing_candidate_hash")
    
    fallback_block_reason = ";".join(sorted(blockers))

    payload = build_hybrid_route_decision(
        route_mode=route_mode,
        public_claim_allowed=False,
        production_ready=False,
        adapter_output_is_route_truth=False,
        route_truth_source="CapabilityPlanner",
        behavior_changed=False,
        authority=authority,
        local_model_called=receipt.local_model_called,
        candidate_output_isolated=receipt.candidate_output_isolated,
        selected_candidate_hash=receipt.selected_candidate_hash,
        applied_patch_hash=applied_patch_hash,
        selected_candidate_hash_matches_applied=selected_candidate_hash_matches_applied,
        verifier_result=verifier_result,
        evidence_refs=receipt.evidence_refs,
        fallback_block_reason=fallback_block_reason,
    )
    return hybrid_route_decision_from_payload_direct(payload)


def hybrid_route_from_solve_attempt_receipt(receipt: SolveAttemptReceipt) -> HybridRouteDecision:
    # 由於 SolveAttemptReceipt 本身不含有獨立的 applied_patch_hash，
    # 絕對不能發布為 LOCAL_ONLY_EXECUTED，必須設為 LOCAL_ONLY_BLOCKED。
    route_mode = RouteMode.LOCAL_ONLY_BLOCKED
    authority = Authority.TRACE_ONLY
    verifier_result = _map_verifier_result(receipt.verifier_result)
    applied_patch_hash = ""
    selected_candidate_hash_matches_applied = False
    
    blockers = ["missing_applied_patch_hash"]
    if receipt.verifier_result != "pass":
        blockers.append("verifier_fail_or_not_run")
    if not receipt.evidence_refs:
        blockers.append("missing_evidence_refs")
    if not receipt.candidate_output_isolated:
        blockers.append("missing_candidate_isolation")
    if not receipt.selected_candidate_hash:
        blockers.append("missing_candidate_hash")
    if not receipt.patch_applied:
        blockers.append("selected_reapply_not_proven")
        
    fallback_block_reason = ";".join(sorted(blockers))

    payload = build_hybrid_route_decision(
        route_mode=route_mode,
        public_claim_allowed=False,
        production_ready=False,
        adapter_output_is_route_truth=False,
        route_truth_source="CapabilityPlanner",
        behavior_changed=False,
        authority=authority,
        local_model_called=receipt.local_model_called,
        candidate_output_isolated=receipt.candidate_output_isolated,
        selected_candidate_hash=receipt.selected_candidate_hash,
        applied_patch_hash=applied_patch_hash,
        selected_candidate_hash_matches_applied=selected_candidate_hash_matches_applied,
        verifier_result=verifier_result,
        evidence_refs=receipt.evidence_refs,
        fallback_block_reason=fallback_block_reason,
    )
    return hybrid_route_decision_from_payload_direct(payload)


def hybrid_route_from_validation_receipt(receipt: ValidationReceipt) -> HybridRouteDecision:
    # ValidationReceipt 也不能直接發布為 LOCAL_ONLY_EXECUTED，因為它沒有證明 applied_patch_hash。
    # 必須強制設為 LOCAL_ONLY_BLOCKED。
    route_mode = RouteMode.LOCAL_ONLY_BLOCKED
    authority = Authority.TRACE_ONLY
    verifier_result = VerifierResult.PASS if receipt.verifier_status == "pass" else VerifierResult.FAIL
    applied_patch_hash = ""
    selected_candidate_hash_matches_applied = False
    
    blockers = ["missing_applied_patch_hash"]
    if receipt.verifier_status != "pass":
        blockers.append("verifier_fail_or_not_run")
    if not receipt.candidate_id:
        blockers.append("missing_candidate_id")
    if receipt.patch_apply_status != "applied":
        blockers.append("patch_not_applied")
    if receipt.parser_status != "pass":
        blockers.append("parser_not_pass")
    if receipt.compliance_status != "pass":
        blockers.append("compliance_not_pass")
    if not receipt.route_id:
        blockers.append("missing_route_id")
    if not receipt.evidence_packet_id:
        blockers.append("missing_evidence_packet_id")
        
    fallback_block_reason = ";".join(sorted(blockers))

    payload = build_hybrid_route_decision(
        route_mode=route_mode,
        public_claim_allowed=False,
        production_ready=False,
        adapter_output_is_route_truth=False,
        route_truth_source="CapabilityPlanner",
        behavior_changed=False,
        authority=authority,
        local_model_called=True,
        candidate_output_isolated=True,
        selected_candidate_hash=receipt.candidate_id,
        applied_patch_hash=applied_patch_hash,
        selected_candidate_hash_matches_applied=selected_candidate_hash_matches_applied,
        verifier_result=verifier_result,
        evidence_refs=(receipt.route_id, receipt.evidence_packet_id) if receipt.route_id and receipt.evidence_packet_id else (),
        fallback_block_reason=fallback_block_reason,
    )
    return hybrid_route_decision_from_payload_direct(payload)


def capability_payload_from_hybrid_route(decision: HybridRouteDecision) -> dict[str, Any]:
    return {
        "invoked": decision.local_model_called,
        "gate_passed": decision.route_mode == RouteMode.LOCAL_ONLY_EXECUTED,
        "evidence_present": bool(decision.evidence_refs),
        "evidence_refs": list(decision.evidence_refs),
        "hybrid_route": decision.to_dict(),
        "telemetries": {
            "route_mode": decision.route_mode.value,
            "authority": decision.authority.value,
            "verifier_result": decision.verifier_result.value,
            "fallback_block_reason": decision.fallback_block_reason,
        },
    }


def build_local_heal_hybrid_receipt(
    *,
    task_id: str,
    route_mode: RouteMode,
    verifier_result: VerifierResult,
    evidence_refs: tuple[str, ...],
    candidate_output_isolated: bool,
    selected_candidate_hash: str = "",
    applied_patch_hash: str = "",
) -> HybridRouteDecision:
    # 只有當 caller 明確提供一致且有效的屬性時，才允許 LOCAL_ONLY_EXECUTED
    is_executed_eligible = (
        verifier_result == VerifierResult.PASS
        and bool(evidence_refs)
        and candidate_output_isolated
        and bool(selected_candidate_hash)
        and bool(applied_patch_hash)
        and selected_candidate_hash == applied_patch_hash
    )
    
    if route_mode == RouteMode.LOCAL_ONLY_EXECUTED:
        if not is_executed_eligible:
            route_mode = RouteMode.LOCAL_ONLY_BLOCKED
            blockers = []
            if verifier_result != VerifierResult.PASS:
                blockers.append("verifier_fail_or_not_run")
            if not evidence_refs:
                blockers.append("missing_evidence_refs")
            if not candidate_output_isolated:
                blockers.append("missing_candidate_isolation")
            if not selected_candidate_hash:
                blockers.append("missing_selected_candidate_hash")
            if not applied_patch_hash:
                blockers.append("missing_applied_patch_hash")
            elif selected_candidate_hash != applied_patch_hash:
                blockers.append("hash_mismatch")
            fallback_block_reason = ";".join(blockers)
        else:
            fallback_block_reason = ""
    else:
        fallback_block_reason = ""

    authority = Authority.INTERNAL_ONLY if route_mode == RouteMode.LOCAL_ONLY_EXECUTED else Authority.TRACE_ONLY

    payload = build_hybrid_route_decision(
        route_mode=route_mode,
        public_claim_allowed=False,
        production_ready=False,
        adapter_output_is_route_truth=False,
        route_truth_source="CapabilityPlanner",
        behavior_changed=False,
        authority=authority,
        local_model_called=True,
        candidate_output_isolated=candidate_output_isolated,
        selected_candidate_hash=selected_candidate_hash,
        applied_patch_hash=applied_patch_hash,
        selected_candidate_hash_matches_applied=selected_candidate_hash == applied_patch_hash and bool(selected_candidate_hash),
        verifier_result=verifier_result,
        evidence_refs=evidence_refs,
        fallback_block_reason=fallback_block_reason,
        metadata={"task_id": task_id},
    )
    return hybrid_route_decision_from_payload_direct(payload)


def _map_verifier_result(val: str) -> VerifierResult:
    if val == "pass":
        return VerifierResult.PASS
    if val == "fail":
        return VerifierResult.FAIL
    if val == "blocked":
        return VerifierResult.BLOCKED
    return VerifierResult.NOT_RUN


def hybrid_route_decision_from_payload_direct(payload: dict[str, Any]) -> HybridRouteDecision:
    from nexus.contracts.hybrid_route import hybrid_route_decision_from_payload
    return hybrid_route_decision_from_payload(payload)
