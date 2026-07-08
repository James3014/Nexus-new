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
