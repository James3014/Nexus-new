"""P4-I3: Candidate Provider Adapter Tests."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.committee_candidate_adapter import (
    adapt_committee_candidate,
    adapt_committee_candidates,
)
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate
from nexus.services.local_heal.receipt import build_repair_receipt


def test_adapt_search_replace_to_canonical():
    """P4-I3: SEARCH/REPLACE format adapts to canonical."""
    raw = {
        "candidate_patch": "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
        "format": "SEARCH_REPLACE",
        "model": "qwen",
        "candidate_id": "c1",
    }
    candidate, warnings = adapt_committee_candidate(raw, "foo.py")
    assert candidate is not None
    assert isinstance(candidate, CanonicalPatchCandidate)
    assert candidate.source_format == "SEARCH_REPLACE"
    assert candidate.normalized_patch == "new"
    assert candidate.target_file == "foo.py"


def test_adapt_unified_diff_to_canonical():
    """P4-I3: UNIFIED_DIFF format adapts to canonical."""
    raw = {
        "candidate_patch": "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n old\n-new\n+new\n",
        "format": "UNIFIED_DIFF",
        "model": "qwen",
        "candidate_id": "c2",
    }
    candidate, warnings = adapt_committee_candidate(raw, "foo.py")
    assert candidate is not None
    assert candidate.source_format == "UNIFIED_DIFF"
    assert candidate.target_file == "foo.py"


def test_adapt_malformed_rejected():
    """P4-I3: Malformed candidate is rejected."""
    raw = {
        "candidate_patch": "random text with no structure",
        "model": "qwen",
        "candidate_id": "c3",
    }
    candidate, errors = adapt_committee_candidate(raw, "foo.py")
    assert candidate is None
    assert len(errors) > 0


def test_adapt_empty_rejected():
    """P4-I3: Empty candidate is rejected."""
    raw = {
        "candidate_patch": "",
        "model": "qwen",
        "candidate_id": "c4",
    }
    candidate, errors = adapt_committee_candidate(raw, "foo.py")
    assert candidate is None
    assert "empty_candidate" in errors


def test_adapt_refusal_rejected():
    """P4-I3: Refusal candidate is rejected."""
    raw = {
        "candidate_patch": "I apologize, but I cannot fix this issue.",
        "model": "qwen",
        "candidate_id": "c5",
    }
    candidate, errors = adapt_committee_candidate(raw, "foo.py")
    assert candidate is None
    assert "refusal_detected" in errors


def test_adapt_target_file_mismatch_flagged():
    """P4-I3: Target file mismatch is flagged in safety_flags."""
    raw = {
        "candidate_patch": "--- a/bar.py\n+++ b/bar.py\n@@ -1,3 +1,3 @@\n old\n-new\n+new\n",
        "format": "UNIFIED_DIFF",
        "model": "qwen",
        "candidate_id": "c6",
    }
    candidate, warnings = adapt_committee_candidate(raw, "foo.py")
    assert candidate is not None
    assert "target_file_mismatch" in candidate.safety_flags
    assert "target_file_not_in_patch" in warnings


def test_adapt_batch_all_valid():
    """P4-I3: Batch adapt with all valid candidates."""
    raw_candidates = [
        {"candidate_patch": "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n old\n-new\n+new\n", "format": "UNIFIED_DIFF", "model": "a", "candidate_id": "c1"},
        {"candidate_patch": "--- a/bar.py\n+++ b/bar.py\n@@ -1,3 +1,3 @@\n old\n-new\n+new\n", "format": "UNIFIED_DIFF", "model": "b", "candidate_id": "c2"},
    ]
    valid, rejections = adapt_committee_candidates(raw_candidates, "foo.py")
    assert len(valid) == 2
    assert len(rejections) == 0


def test_adapt_batch_partial_rejection():
    """P4-I3: Batch adapt with some rejections."""
    raw_candidates = [
        {"candidate_patch": "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n old\n-new\n+new\n", "format": "UNIFIED_DIFF", "model": "a", "candidate_id": "c1"},
        {"candidate_patch": "", "model": "b", "candidate_id": "c2"},
    ]
    valid, rejections = adapt_committee_candidates(raw_candidates, "foo.py")
    assert len(valid) == 1
    assert len(rejections) == 1
    assert rejections[0]["reason"] == "empty_candidate"


def test_adapt_batch_all_rejected():
    """P4-I3: Batch adapt with all rejected."""
    raw_candidates = [
        {"candidate_patch": "", "model": "a", "candidate_id": "c1"},
        {"candidate_patch": "random", "model": "b", "candidate_id": "c2"},
    ]
    valid, rejections = adapt_committee_candidates(raw_candidates, "foo.py")
    assert len(valid) == 0
    assert len(rejections) == 2


def test_canonical_candidate_has_required_fields():
    """P4-I3: Canonical candidate has all required fields."""
    raw = {
        "candidate_patch": "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n old\n-new\n+new\n",
        "format": "UNIFIED_DIFF",
        "model": "qwen",
        "candidate_id": "c7",
    }
    candidate, _ = adapt_committee_candidate(raw, "foo.py", "bar")
    assert candidate is not None
    assert candidate.raw_output_hash != ""
    assert candidate.target_file == "foo.py"
    assert candidate.target_symbol == "bar"


def test_no_raw_text_only_candidate_enters_selection():
    """P4-I3: Candidate with only raw_text (no candidate_patch) still adapts."""
    raw = {
        "raw_text": "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n old\n-new\n+new\n",
        "model": "qwen",
        "candidate_id": "c8",
    }
    candidate, warnings = adapt_committee_candidate(raw, "foo.py")
    assert candidate is not None
    assert candidate.raw_output == raw["raw_text"]


def test_adapt_results_in_receipt():
    """P4-I3: Adapt results appear in receipt."""
    class FakeCtx:
        instance_id = "p4-adapter-test"
        p4_raw_candidate_count = 3
        p4_rejected_candidate_count = 1
        p4_rejected_candidate_reasons = ["empty_candidate"]

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p4_raw_candidate_count"] == 3
    assert receipt["p4_rejected_candidate_count"] == 1
    assert receipt["p4_rejected_candidate_reasons"] == ["empty_candidate"]
