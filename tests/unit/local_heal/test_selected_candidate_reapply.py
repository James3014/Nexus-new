from __future__ import annotations

import pytest

from nexus.services.local_heal.candidate_isolation_gate import (
    CandidateIsolationReceipt,
    validate_candidate_isolation_receipt,
)
from nexus.contracts.hybrid_route import VerifierResult


def test_selected_reapply_hash_match_passes():
    receipt = CandidateIsolationReceipt(
        candidate_id="c1",
        selected_candidate_hash="abc123",
        applied_patch_hash="abc123",
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        verifier_result=VerifierResult.PASS,
        evidence_refs=("ref1",),
        local_model_called=True,
        mutation_allowed=True,
    )
    blockers = validate_candidate_isolation_receipt(receipt)
    assert "hash_mismatch" not in blockers
    assert "hash_match_not_proven" not in blockers


def test_selected_reapply_hash_mismatch_fails():
    receipt = CandidateIsolationReceipt(
        candidate_id="c1",
        selected_candidate_hash="abc123",
        applied_patch_hash="def456",
        selected_candidate_hash_matches_applied=False,
        candidate_output_isolated=True,
        verifier_result=VerifierResult.PASS,
        evidence_refs=("ref1",),
        local_model_called=True,
        mutation_allowed=True,
    )
    blockers = validate_candidate_isolation_receipt(receipt)
    assert "hash_mismatch" in blockers


def test_missing_applied_hash_blocks():
    receipt = CandidateIsolationReceipt(
        candidate_id="c1",
        selected_candidate_hash="abc123",
        applied_patch_hash="",
        selected_candidate_hash_matches_applied=False,
        candidate_output_isolated=True,
        verifier_result=VerifierResult.PASS,
        evidence_refs=("ref1",),
        local_model_called=True,
        mutation_allowed=True,
    )
    blockers = validate_candidate_isolation_receipt(receipt)
    assert "missing_applied_patch_hash" in blockers


def test_missing_isolation_blocks():
    receipt = CandidateIsolationReceipt(
        candidate_id="c1",
        selected_candidate_hash="abc123",
        applied_patch_hash="abc123",
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=False,
        verifier_result=VerifierResult.PASS,
        evidence_refs=("ref1",),
        local_model_called=True,
        mutation_allowed=True,
    )
    blockers = validate_candidate_isolation_receipt(receipt)
    assert "missing_candidate_isolation" in blockers


def test_non_selected_apply_blocks():
    """Non-selected candidate apply must fail closed."""
    receipt = CandidateIsolationReceipt(
        candidate_id="c1",
        selected_candidate_hash="abc123",
        applied_patch_hash="abc123",
        selected_candidate_hash_matches_applied=False,
        candidate_output_isolated=True,
        verifier_result=VerifierResult.PASS,
        evidence_refs=("ref1",),
        local_model_called=True,
        mutation_allowed=True,
    )
    blockers = validate_candidate_isolation_receipt(receipt)
    assert "hash_match_not_proven" in blockers
