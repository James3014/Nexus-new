from __future__ import annotations

import hashlib
import pytest
from nexus.services.local_heal.output_understanding import (
    CanonicalPatchCandidate,
    OutputUnderstandingResult,
    understand_output,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_search_replace_returns_canonical_candidate():
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
    assert isinstance(result.candidate, CanonicalPatchCandidate)
    assert result.candidate.source_format == "SEARCH_REPLACE"
    assert result.candidate.raw_output == raw
    assert result.candidate.raw_output_hash == _sha256(raw)


def test_fenced_search_replace_unwraps_and_records_normalization_step():
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
    assert "unwrap_outer_markdown_fence" in result.candidate.normalization_steps
    assert "extract_replacement_from_search_replace" in result.candidate.normalization_steps


def test_unified_diff_returns_canonical_candidate():
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
    assert result.candidate.raw_output == raw


def test_empty_output_returns_failure_result():
    result = understand_output("")
    assert result.success is False
    assert result.detected_format == "EMPTY_OR_REFUSAL"
    assert result.failure_reason == "empty_or_refusal"
    assert result.candidate is None


def test_refusal_output_returns_failure_result():
    raw = "I apologize, but I cannot fix this issue as it requires more context."
    result = understand_output(raw)
    assert result.success is False
    assert result.detected_format == "EMPTY_OR_REFUSAL"
    assert result.failure_reason == "empty_or_refusal"
    assert result.candidate is None


def test_malformed_output_returns_failure_result():
    raw = "Here is some random text that doesn't match any known format."
    result = understand_output(raw)
    assert result.success is False
    assert result.detected_format == "MALFORMED_OUTPUT"
    assert result.failure_reason == "malformed_output"
    assert result.candidate is None


def test_raw_output_hash_is_stable():
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


def test_normalized_patch_hash_present_when_candidate_exists():
    raw = (
        "```python\n"
        "<<<<<<< SEARCH\n"
        "a = 1\n"
        "=======\n"
        "a = 2\n"
        ">>>>>>> REPLACE\n"
        "```"
    )
    result = understand_output(raw)
    assert result.success is True
    assert result.candidate is not None
    assert result.candidate.normalized_patch_hash != ""
    assert result.candidate.normalized_patch_hash == _sha256(result.candidate.normalized_patch)


def test_protocol_compatibility_for_existing_search_replace_path():
    raw = (
        "<<<<<<< SEARCH\n"
        "old code\n"
        "=======\n"
        "new code\n"
        ">>>>>>> REPLACE"
    )
    result = understand_output(raw)
    assert result.success is True
    assert result.candidate is not None
    assert result.candidate.normalized_patch == "new code"
    assert result.failure_reason == ""


# ============================================================
# P2-1: Anchor Fields Tests
# ============================================================


def test_canonical_candidate_anchor_fields_default_empty():
    """P2-1: New candidate has empty anchor fields by default."""
    raw = (
        "<<<<<<< SEARCH\n"
        "x = 1\n"
        "=======\n"
        "x = 2\n"
        ">>>>>>> REPLACE"
    )
    result = understand_output(raw)
    assert result.candidate is not None
    assert result.candidate.target_file == ""
    assert result.candidate.target_symbol == ""
    assert result.candidate.line_span == ""
    assert result.candidate.old_block_hash == ""


def test_enrich_candidate_with_anchor_fills_fields():
    """P2-1: Enrich with target_file, target_symbol, old_block_hash."""
    from nexus.services.local_heal.output_understanding import enrich_candidate_with_anchor, CanonicalPatchCandidate

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
    """P2-1: Original fields unchanged after enrichment."""
    from nexus.services.local_heal.output_understanding import enrich_candidate_with_anchor, CanonicalPatchCandidate

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


def test_enrich_candidate_with_empty_fields_noop():
    """P2-1: Enrich with all empty fields leaves candidate unchanged."""
    from nexus.services.local_heal.output_understanding import enrich_candidate_with_anchor, CanonicalPatchCandidate

    candidate = CanonicalPatchCandidate(
        source_format="SEARCH_REPLACE",
        raw_output="raw",
        raw_output_hash="hash1",
        normalized_patch="patch",
        normalized_patch_hash="hash2",
        normalization_steps=(),
        safety_flags=(),
    )
    enriched = enrich_candidate_with_anchor(candidate)
    assert enriched == candidate


def test_executor_injects_anchor_into_candidate():
    """P2-1: Integration — understand_output + enrich fills anchor fields."""
    from nexus.services.local_heal.output_understanding import understand_output, enrich_candidate_with_anchor

    raw = (
        "<<<<<<< SEARCH\n"
        "x = 1\n"
        "=======\n"
        "x = 2\n"
        ">>>>>>> REPLACE"
    )
    result = understand_output(raw)
    assert result.candidate is not None

    enriched = enrich_candidate_with_anchor(
        result.candidate,
        target_file="test.py",
        target_symbol="my_func",
        old_block_hash="abc123",
    )
    assert enriched.target_file == "test.py"
    assert enriched.target_symbol == "my_func"
    assert enriched.old_block_hash == "abc123"
    assert enriched.source_format == "SEARCH_REPLACE"


def test_understanding_meta_contains_anchor_fields_when_candidate_present():
    """P2-2: After understand_output + enrich, simulated meta contains anchor keys."""
    from nexus.services.local_heal.output_understanding import understand_output, enrich_candidate_with_anchor

    raw = (
        "<<<<<<< SEARCH\n"
        "x = 1\n"
        "=======\n"
        "x = 2\n"
        ">>>>>>> REPLACE"
    )
    result = understand_output(raw)
    assert result.candidate is not None

    enriched = enrich_candidate_with_anchor(
        result.candidate,
        target_file="foo.py",
        target_symbol="bar",
        old_block_hash="hash123",
    )

    # Simulate what executor builds in _understanding_meta
    meta = {
        "output_understanding_format": result.detected_format,
        "output_understanding_success": result.success,
    }
    if enriched:
        meta["output_understanding_candidate_target_file"] = enriched.target_file
        meta["output_understanding_candidate_target_symbol"] = enriched.target_symbol
        meta["output_understanding_candidate_old_block_hash"] = enriched.old_block_hash

    assert meta["output_understanding_candidate_target_file"] == "foo.py"
    assert meta["output_understanding_candidate_target_symbol"] == "bar"
    assert meta["output_understanding_candidate_old_block_hash"] == "hash123"
