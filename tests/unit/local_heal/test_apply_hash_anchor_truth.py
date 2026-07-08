from __future__ import annotations

import hashlib
import pytest
from nexus.services.local_heal.output_understanding import (
    CanonicalPatchCandidate,
    OutputUnderstandingResult,
    OutputFormat,
    understand_output,
    enrich_candidate_with_anchor,
    compute_applied_patch_hash,
    verify_hash_chain,
    verify_selected_candidate_matches_applied,
    check_claim_eligibility,
    _sha256,
)


# ============================================================
# P2-1: All supported output formats map to OutputUnderstandingResult
# ============================================================


def test_search_replace_format():
    raw = (
        "<<<<<<< SEARCH\n"
        "def foo():\n"
        "    pass\n"
        "=======\n"
        "def foo():\n"
        "    return 42\n"
        ">>>>>>> REPLACE"
    )
    result = understand_output(raw)
    assert result.success is True
    assert result.detected_format == "SEARCH_REPLACE"
    assert result.candidate is not None
    assert result.candidate.source_format == "SEARCH_REPLACE"


def test_fenced_search_replace_format():
    raw = (
        "```python\n"
        "<<<<<<< SEARCH\n"
        "def foo():\n"
        "    pass\n"
        "=======\n"
        "def foo():\n"
        "    return 42\n"
        ">>>>>>> REPLACE\n"
        "```"
    )
    result = understand_output(raw)
    assert result.success is True
    assert result.detected_format == "FENCED_SEARCH_REPLACE"
    assert result.candidate is not None
    assert result.candidate.source_format == "FENCED_SEARCH_REPLACE"


def test_unified_diff_format():
    raw = (
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,3 +1,3 @@\n"
        " def foo():\n"
        "-    pass\n"
        "+    return 42\n"
    )
    result = understand_output(raw)
    assert result.success is True
    assert result.detected_format == "UNIFIED_DIFF"
    assert result.candidate is not None
    assert result.candidate.source_format == "UNIFIED_DIFF"


def test_partial_diff_format():
    raw = (
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "-    pass\n"
        "+    return 42\n"
    )
    result = understand_output(raw)
    assert result.success is True
    assert result.detected_format == "PARTIAL_DIFF"
    assert result.candidate is not None
    assert result.candidate.source_format == "PARTIAL_DIFF"


def test_line_span_edit_format():
    raw = (
        "@@ -10,5 +10,5 @@\n"
        "def foo():\n"
        "    return 42\n"
    )
    result = understand_output(raw)
    assert result.success is True
    assert result.detected_format == "LINE_SPAN_EDIT"
    assert result.candidate is not None
    assert result.candidate.source_format == "LINE_SPAN_EDIT"


def test_function_replacement_format():
    raw = (
        "def foo():\n"
        "    return 42\n"
    )
    result = understand_output(raw)
    assert result.success is True
    assert result.detected_format == "FUNCTION_REPLACEMENT"
    assert result.candidate is not None
    assert result.candidate.source_format == "FUNCTION_REPLACEMENT"


def test_natural_language_repair_intent_format():
    raw = "Fix the bug in the login function by adding error handling."
    result = understand_output(raw)
    assert result.success is False
    assert result.detected_format == "NATURAL_LANGUAGE_REPAIR_INTENT"
    assert result.failure_reason == "natural_language_repair_intent_not_actionable"
    assert result.candidate is None


# ============================================================
# P2-2: Empty/refusal/malformed outputs fail closed
# ============================================================


def test_empty_output_fails_closed():
    result = understand_output("")
    assert result.success is False
    assert result.detected_format == "EMPTY_OR_REFUSAL"
    assert result.failure_reason == "empty_or_refusal"
    assert result.candidate is None


def test_refusal_output_fails_closed():
    raw = "I apologize, but I cannot fix this issue."
    result = understand_output(raw)
    assert result.success is False
    assert result.detected_format == "EMPTY_OR_REFUSAL"
    assert result.failure_reason == "empty_or_refusal"
    assert result.candidate is None


def test_malformed_output_fails_closed():
    raw = "Here is some random text that doesn't match any format."
    result = understand_output(raw)
    assert result.success is False
    assert result.detected_format == "MALFORMED_OUTPUT"
    assert result.failure_reason == "malformed_output"
    assert result.candidate is None


# ============================================================
# P2-3: raw_output_hash is stable
# ============================================================


def test_raw_output_hash_stability():
    raw = (
        "<<<<<<< SEARCH\n"
        "x = 1\n"
        "=======\n"
        "x = 2\n"
        ">>>>>>> REPLACE"
    )
    r1 = understand_output(raw)
    r2 = understand_output(raw)
    assert r1.candidate is not None
    assert r2.candidate is not None
    assert r1.candidate.raw_output_hash == r2.candidate.raw_output_hash
    assert r1.candidate.raw_output_hash == _sha256(raw)


# ============================================================
# P2-4: normalized_patch_hash is stable
# ============================================================


def test_normalized_patch_hash_stability():
    raw = (
        "```python\n"
        "<<<<<<< SEARCH\n"
        "a = 1\n"
        "=======\n"
        "a = 2\n"
        ">>>>>>> REPLACE\n"
        "```"
    )
    r1 = understand_output(raw)
    r2 = understand_output(raw)
    assert r1.candidate is not None
    assert r2.candidate is not None
    assert r1.candidate.normalized_patch_hash == r2.candidate.normalized_patch_hash
    assert r1.candidate.normalized_patch_hash == _sha256(r1.candidate.normalized_patch)


def test_normalized_patch_hash_always_computed():
    raw = (
        "<<<<<<< SEARCH\n"
        "x = 1\n"
        "=======\n"
        "x = 2\n"
        ">>>>>>> REPLACE"
    )
    result = understand_output(raw)
    assert result.candidate is not None
    assert result.candidate.normalized_patch_hash != ""
    assert result.candidate.normalized_patch_hash == _sha256(result.candidate.normalized_patch)


# ============================================================
# P2-5: applied_patch_hash is stable
# ============================================================


def test_applied_patch_hash_stability():
    diff1 = "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n def foo():\n-    pass\n+    return 42"
    diff2 = "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n def foo():\n-    pass\n+    return 42"
    h1 = compute_applied_patch_hash(diff1)
    h2 = compute_applied_patch_hash(diff2)
    assert h1 == h2
    assert h1 == _sha256(diff1)


# ============================================================
# P2-6: selected candidate hash matches applied patch
# ============================================================


def test_selected_candidate_matches_applied():
    candidate_hash = _sha256("some_patch")
    applied_hash = _sha256("some_patch")
    assert verify_selected_candidate_matches_applied(candidate_hash, applied_hash) is True


def test_selected_candidate_mismatches_applied():
    candidate_hash = _sha256("patch_a")
    applied_hash = _sha256("patch_b")
    assert verify_selected_candidate_matches_applied(candidate_hash, applied_hash) is False


def test_selected_candidate_empty_hash_blocks_match():
    assert verify_selected_candidate_matches_applied("", "some_hash") is False
    assert verify_selected_candidate_matches_applied("some_hash", "") is False


# ============================================================
# P2-7: verifier pass + hash mismatch does not become solved
# ============================================================


def test_hash_mismatch_blocks_solved():
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state
    
    state = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=False,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_b",
        verifier_result="pass",
        solved=True,
    )
    assert state == "isolation_applied_hash_mismatch"


def test_hash_match_with_verifier_pass_succeeds():
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state
    
    state = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="pass",
        solved=True,
    )
    assert state == "verifier_passed"


# ============================================================
# P2-8: hash mismatch blocks claim_eligible
# ============================================================


def test_hash_chain_completeness_blocks_claim():
    candidate = CanonicalPatchCandidate(
        source_format="SEARCH_REPLACE",
        raw_output="raw",
        raw_output_hash="hash1",
        normalized_patch="patch",
        normalized_patch_hash="hash2",
        normalization_steps=(),
        safety_flags=(),
    )
    assert check_claim_eligibility(candidate) is True
    
    candidate_incomplete = CanonicalPatchCandidate(
        source_format="SEARCH_REPLACE",
        raw_output="raw",
        raw_output_hash="",
        normalized_patch="patch",
        normalized_patch_hash="",
        normalization_steps=(),
        safety_flags=(),
    )
    assert check_claim_eligibility(candidate_incomplete) is False


def test_hash_mismatch_blocks_claim_eligibility():
    candidate = CanonicalPatchCandidate(
        source_format="SEARCH_REPLACE",
        raw_output="raw",
        raw_output_hash="hash1",
        normalized_patch="patch",
        normalized_patch_hash="hash2",
        normalization_steps=(),
        safety_flags=(),
        claim_eligible=True,
    )
    result = check_claim_eligibility(
        candidate,
        selected_candidate_hash="hash_a",
        applied_patch_hash="hash_b",
        selected_candidate_hash_matches_applied=False,
    )
    assert result is False


def test_hash_match_preserves_claim_eligibility():
    candidate = CanonicalPatchCandidate(
        source_format="SEARCH_REPLACE",
        raw_output="raw",
        raw_output_hash="hash1",
        normalized_patch="patch",
        normalized_patch_hash="hash2",
        normalization_steps=(),
        safety_flags=(),
        claim_eligible=True,
    )
    result = check_claim_eligibility(
        candidate,
        selected_candidate_hash="hash_a",
        applied_patch_hash="hash_a",
        selected_candidate_hash_matches_applied=True,
    )
    assert result is True


# ============================================================
# P2-9: missing anchor is explicit in metadata
# ============================================================


def test_missing_anchor_explicit_in_metadata():
    candidate = CanonicalPatchCandidate(
        source_format="SEARCH_REPLACE",
        raw_output="raw",
        raw_output_hash="hash1",
        normalized_patch="patch",
        normalized_patch_hash="hash2",
        normalization_steps=(),
        safety_flags=(),
    )
    assert candidate.target_file == ""
    assert candidate.target_symbol == ""
    assert candidate.line_span == ""
    assert candidate.old_block_hash == ""


def test_enrich_candidate_with_anchor_fills_fields():
    candidate = CanonicalPatchCandidate(
        source_format="SEARCH_REPLACE",
        raw_output="raw",
        raw_output_hash="hash1",
        normalized_patch="patch",
        normalized_patch_hash="hash2",
        normalization_steps=(),
        safety_flags=(),
    )
    enriched = enrich_candidate_with_anchor(
        candidate,
        target_file="foo.py",
        target_symbol="bar",
        old_block_hash="anchor_hash",
    )
    assert enriched.target_file == "foo.py"
    assert enriched.target_symbol == "bar"
    assert enriched.old_block_hash == "anchor_hash"
    assert enriched.line_span == ""


def test_enrich_candidate_preserves_original_fields():
    candidate = CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output="raw output",
        raw_output_hash="abc123",
        normalized_patch="normalized",
        normalized_patch_hash="def456",
        normalization_steps=("step1",),
        safety_flags=("flag1",),
    )
    enriched = enrich_candidate_with_anchor(
        candidate,
        target_file="bar.py",
        target_symbol="baz",
    )
    assert enriched.source_format == "UNIFIED_DIFF"
    assert enriched.raw_output == "raw output"
    assert enriched.raw_output_hash == "abc123"
    assert enriched.normalized_patch == "normalized"
    assert enriched.normalized_patch_hash == "def456"
    assert enriched.normalization_steps == ("step1",)
    assert enriched.safety_flags == ("flag1",)


# ============================================================
# P2-10: hash chain verification
# ============================================================


def test_verify_hash_chain_complete():
    assert verify_hash_chain("h1", "h2", "h3") is True


def test_verify_hash_chain_incomplete():
    assert verify_hash_chain("", "h2", "h3") is False
    assert verify_hash_chain("h1", "", "h3") is False
    assert verify_hash_chain("h1", "h2", "") is False


# ============================================================
# P2-11: CandidateIsolationReceipt validation
# ============================================================


def test_candidate_isolation_receipt_blocks_on_hash_mismatch():
    from nexus.services.local_heal.candidate_isolation_gate import (
        CandidateIsolationReceipt,
        validate_candidate_isolation_receipt,
    )
    
    receipt = CandidateIsolationReceipt(
        candidate_id="test#1",
        selected_candidate_hash="hash_a",
        applied_patch_hash="hash_b",
        selected_candidate_hash_matches_applied=False,
        candidate_output_isolated=True,
        verifier_result="pass",
        evidence_refs=("ref1",),
        local_model_called=True,
        mutation_allowed=True,
        candidate_target_file="foo.py",
    )
    blockers = validate_candidate_isolation_receipt(receipt)
    assert "hash_mismatch" in blockers
    assert "hash_match_not_proven" in blockers


def test_candidate_isolation_receipt_passes_on_hash_match():
    from nexus.services.local_heal.candidate_isolation_gate import (
        CandidateIsolationReceipt,
        validate_candidate_isolation_receipt,
    )
    
    receipt = CandidateIsolationReceipt(
        candidate_id="test#1",
        selected_candidate_hash="hash_a",
        applied_patch_hash="hash_a",
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        verifier_result="pass",
        evidence_refs=("ref1",),
        local_model_called=True,
        mutation_allowed=True,
        candidate_target_file="foo.py",
    )
    blockers = validate_candidate_isolation_receipt(receipt)
    assert "hash_mismatch" not in blockers
    assert "hash_match_not_proven" not in blockers


# ============================================================
# P2-12: IsolatedApplyReceipt hash chain
# ============================================================


def test_isolated_apply_receipt_hash_chain():
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    
    receipt = IsolatedApplyReceipt(
        task_id="test",
        workspace_path="/tmp",
        target_file="foo.py",
        patch_apply_status="applied",
        patch_apply_error="",
        selected_candidate_hash="hash_a",
        applied_patch_hash="hash_a",
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        mutation_allowed=True,
        applied_patch_hash_source="git_diff",
    )
    assert receipt.selected_candidate_hash == receipt.applied_patch_hash
    assert receipt.selected_candidate_hash_matches_applied is True


# ============================================================
# P2-13: public_claim_allowed and production_ready defaults
# ============================================================


def test_public_claim_allowed_default_false():
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    
    receipt = IsolatedApplyReceipt(
        task_id="test",
        workspace_path="/tmp",
        target_file="foo.py",
        patch_apply_status="applied",
        patch_apply_error="",
        selected_candidate_hash="hash_a",
        applied_patch_hash="hash_a",
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        mutation_allowed=True,
    )
    assert receipt.public_claim_allowed is False
    assert receipt.production_ready is False


def test_candidate_isolation_receipt_public_claim_default_false():
    from nexus.services.local_heal.candidate_isolation_gate import CandidateIsolationReceipt
    
    receipt = CandidateIsolationReceipt(
        candidate_id="test#1",
        selected_candidate_hash="hash_a",
        applied_patch_hash="hash_a",
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        verifier_result="pass",
        evidence_refs=("ref1",),
        local_model_called=True,
        mutation_allowed=True,
    )
    assert receipt.public_claim_allowed is False
    assert receipt.production_ready is False
