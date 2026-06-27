from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from nexus.contracts.hybrid_route import (
    HybridRouteDecision,
    RouteMode,
    VerifierResult,
    Authority,
    build_hybrid_route_decision,
    hybrid_route_decision_from_payload,
)


@dataclass(frozen=True)
class CandidateIsolationReceipt:
    candidate_id: str
    selected_candidate_hash: str
    applied_patch_hash: str
    selected_candidate_hash_matches_applied: bool
    candidate_output_isolated: bool
    verifier_result: VerifierResult | str
    evidence_refs: tuple[str, ...]
    local_model_called: bool = False
    mutation_allowed: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False


def validate_candidate_isolation_receipt(receipt: CandidateIsolationReceipt) -> list[str]:
    blockers: list[str] = []
    
    if not receipt.local_model_called:
        blockers.append("local_model_not_called")
    if not receipt.mutation_allowed:
        blockers.append("mutation_not_allowed")
    if not receipt.candidate_output_isolated:
        blockers.append("missing_candidate_isolation")
    if not receipt.selected_candidate_hash.strip():
        blockers.append("missing_selected_candidate_hash")
    if not receipt.applied_patch_hash.strip():
        blockers.append("missing_applied_patch_hash")
    if (
        receipt.selected_candidate_hash.strip()
        and receipt.applied_patch_hash.strip()
        and receipt.selected_candidate_hash != receipt.applied_patch_hash
    ):
        blockers.append("hash_mismatch")
    if not receipt.selected_candidate_hash_matches_applied:
        blockers.append("hash_match_not_proven")
        
    vr = receipt.verifier_result
    if isinstance(vr, VerifierResult):
        verifier_passed = vr == VerifierResult.PASS
    else:
        verifier_passed = str(vr).lower() == "pass"
        
    if not verifier_passed:
        blockers.append("verifier_fail_or_not_run")
        
    if not receipt.evidence_refs:
        blockers.append("missing_evidence_refs")
    if receipt.public_claim_allowed:
        blockers.append("public_claim_allowed_must_be_false")
    if receipt.production_ready:
        blockers.append("production_ready_must_be_false")
        
    return sorted(set(blockers))


def candidate_isolation_to_hybrid_route(receipt: CandidateIsolationReceipt) -> HybridRouteDecision:
    blockers = validate_candidate_isolation_receipt(receipt)
    
    if not blockers:
        route_mode = RouteMode.LOCAL_ONLY_EXECUTED
        authority = Authority.INTERNAL_ONLY
        selected_candidate_hash_matches_applied = True
        fallback_block_reason = ""
    else:
        route_mode = RouteMode.LOCAL_ONLY_BLOCKED
        authority = Authority.TRACE_ONLY
        selected_candidate_hash_matches_applied = (
            receipt.selected_candidate_hash_matches_applied
            and receipt.selected_candidate_hash == receipt.applied_patch_hash
            and bool(receipt.selected_candidate_hash)
        )
        fallback_block_reason = ";".join(blockers)
        
    vr = receipt.verifier_result
    if isinstance(vr, VerifierResult):
        verifier_res = vr
    else:
        val = str(vr).lower()
        if val == "pass":
            verifier_res = VerifierResult.PASS
        elif val == "fail":
            verifier_res = VerifierResult.FAIL
        elif val == "blocked":
            verifier_res = VerifierResult.BLOCKED
        else:
            verifier_res = VerifierResult.NOT_RUN

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
        applied_patch_hash=receipt.applied_patch_hash,
        selected_candidate_hash_matches_applied=selected_candidate_hash_matches_applied,
        verifier_result=verifier_res,
        evidence_refs=receipt.evidence_refs,
        fallback_block_reason=fallback_block_reason,
    )
    return hybrid_route_decision_from_payload(payload)
