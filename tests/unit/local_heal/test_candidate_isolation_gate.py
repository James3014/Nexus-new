from __future__ import annotations

from nexus.contracts.hybrid_route import RouteMode, Authority, VerifierResult
from nexus.services.local_heal.candidate_isolation_gate import (
    CandidateIsolationReceipt,
    validate_candidate_isolation_receipt,
    candidate_isolation_to_hybrid_route,
)


def test_candidate_isolation_gate_success() -> None:
    receipt = CandidateIsolationReceipt(
        candidate_id="c1",
        selected_candidate_hash="hash1",
        applied_patch_hash="hash1",
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        verifier_result=VerifierResult.PASS,
        evidence_refs=("ref1",),
        local_model_called=True,
        mutation_allowed=True,
        public_claim_allowed=False,
        production_ready=False,
    )
    
    blockers = validate_candidate_isolation_receipt(receipt)
    assert not blockers
    
    decision = candidate_isolation_to_hybrid_route(receipt)
    assert decision.route_mode == RouteMode.LOCAL_ONLY_EXECUTED
    assert decision.authority == Authority.INTERNAL_ONLY
    assert decision.selected_candidate_hash_matches_applied is True
    assert decision.local_model_called is True
    assert decision.fallback_block_reason == ""


def test_candidate_isolation_gate_blocked_due_to_mismatch() -> None:
    receipt = CandidateIsolationReceipt(
        candidate_id="c1",
        selected_candidate_hash="hash1",
        applied_patch_hash="hash2",
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        verifier_result="pass",
        evidence_refs=("ref1",),
        local_model_called=True,
        mutation_allowed=True,
    )
    
    blockers = validate_candidate_isolation_receipt(receipt)
    assert "hash_mismatch" in blockers
    
    decision = candidate_isolation_to_hybrid_route(receipt)
    assert decision.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert decision.authority == Authority.TRACE_ONLY
    assert decision.selected_candidate_hash_matches_applied is False
    assert "hash_mismatch" in decision.fallback_block_reason


def test_candidate_isolation_gate_blocked_due_to_various_fails() -> None:
    receipt = CandidateIsolationReceipt(
        candidate_id="c1",
        selected_candidate_hash="",
        applied_patch_hash="",
        selected_candidate_hash_matches_applied=False,
        candidate_output_isolated=False,
        verifier_result="fail",
        evidence_refs=(),
        local_model_called=False,
        mutation_allowed=False,
        public_claim_allowed=True,
        production_ready=True,
    )
    
    blockers = validate_candidate_isolation_receipt(receipt)
    assert "local_model_not_called" in blockers
    assert "mutation_not_allowed" in blockers
    assert "missing_candidate_isolation" in blockers
    assert "missing_selected_candidate_hash" in blockers
    assert "missing_applied_patch_hash" in blockers
    assert "hash_match_not_proven" in blockers
    assert "verifier_fail_or_not_run" in blockers
    assert "missing_evidence_refs" in blockers
    assert "public_claim_allowed_must_be_false" in blockers
    assert "production_ready_must_be_false" in blockers
    
    decision = candidate_isolation_to_hybrid_route(receipt)
    assert decision.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "missing_candidate_isolation" in decision.fallback_block_reason
    assert decision.local_model_called is False


def test_candidate_isolation_gate_blocked_due_to_local_model_not_called() -> None:
    receipt = CandidateIsolationReceipt(
        candidate_id="c1",
        selected_candidate_hash="hash1",
        applied_patch_hash="hash1",
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        verifier_result="pass",
        evidence_refs=("ref1",),
        local_model_called=False,
        mutation_allowed=True,
    )
    blockers = validate_candidate_isolation_receipt(receipt)
    assert "local_model_not_called" in blockers
    
    decision = candidate_isolation_to_hybrid_route(receipt)
    assert decision.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "local_model_not_called" in decision.fallback_block_reason
    assert decision.local_model_called is False


def test_candidate_isolation_gate_blocked_due_to_mutation_not_allowed() -> None:
    receipt = CandidateIsolationReceipt(
        candidate_id="c1",
        selected_candidate_hash="hash1",
        applied_patch_hash="hash1",
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        verifier_result="pass",
        evidence_refs=("ref1",),
        local_model_called=True,
        mutation_allowed=False,
    )
    blockers = validate_candidate_isolation_receipt(receipt)
    assert "mutation_not_allowed" in blockers
    
    decision = candidate_isolation_to_hybrid_route(receipt)
    assert decision.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "mutation_not_allowed" in decision.fallback_block_reason
