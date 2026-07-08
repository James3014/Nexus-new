"""P5-I2: Candidate Feature Extraction Tests."""
from __future__ import annotations

import hashlib
import pytest
from nexus.services.local_heal.diversity_selector import (
    CandidateFeatures,
    extract_features,
)
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


def _make_candidate(patch="", target_file="foo.py", safety_flags=(), source_format="UNIFIED_DIFF"):
    raw_hash = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    return CanonicalPatchCandidate(
        source_format=source_format,
        raw_output=patch,
        raw_output_hash=raw_hash,
        normalized_patch=patch,
        normalized_patch_hash="",
        normalization_steps=(),
        safety_flags=safety_flags,
        target_file=target_file,
    )


def test_unified_diff_features():
    """P5-I2: Unified diff extracts line_count / patch_length / syntax_like_score."""
    patch = "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n def foo():\n-    pass\n+    return 42\n"
    candidate = _make_candidate(patch=patch)
    features = extract_features(candidate, model="qwen")

    assert features.patch_length == len(patch)
    assert features.line_count == len(patch.splitlines())
    assert features.syntax_like_score == 1.0
    assert features.source_model == "qwen"
    assert features.source_format == "UNIFIED_DIFF"
    assert features.target_file_match is True
    assert features.safety_penalty == 0.0


def test_search_replace_features():
    """P5-I2: SEARCH/REPLACE format feature extraction."""
    patch = "<<<<<<< SEARCH\nold code\n=======\nnew code\n>>>>>>> REPLACE"
    candidate = _make_candidate(patch=patch, source_format="SEARCH_REPLACE", target_file="")
    features = extract_features(candidate)

    assert features.syntax_like_score == 0.9
    assert features.source_format == "SEARCH_REPLACE"
    assert features.patch_length == len(patch)


def test_empty_patch_features():
    """P5-I2: Empty patch → syntax_like_score = 0, line_count = 0."""
    candidate = _make_candidate(patch="")
    features = extract_features(candidate)

    assert features.syntax_like_score == 0.0
    assert features.line_count == 0
    assert features.patch_length == 0
    assert features.token_set == frozenset()


def test_nonempty_no_markers():
    """P5-I2: Non-empty patch with code tokens → syntax_like_score = 0.6."""
    patch = "def calculate_sum(a, b):\n    result = a + b\n    return result\n"
    candidate = _make_candidate(patch=patch, target_file="")
    features = extract_features(candidate)

    assert features.syntax_like_score == 0.6
    assert features.line_count == 3
    assert features.patch_length == len(patch)


def test_target_file_empty():
    """P5-I2: Empty target_file → target_file_match = False."""
    candidate = _make_candidate(patch="x = 1", target_file="")
    features = extract_features(candidate)

    assert features.target_file_match is False


def test_target_file_present():
    """P5-I2: target_file referenced in patch → target_file_match = True."""
    candidate = _make_candidate(patch="fix foo.py function", target_file="foo.py")
    features = extract_features(candidate)

    assert features.target_file_match is True


def test_safety_flags_empty():
    """P5-I2: Empty safety_flags → safety_penalty = 0."""
    candidate = _make_candidate(patch="x = 1", safety_flags=())
    features = extract_features(candidate)

    assert features.safety_penalty == 0.0


def test_safety_flags_nonempty():
    """P5-I2: Non-empty safety_flags → safety_penalty > 0."""
    candidate = _make_candidate(patch="x = 1", safety_flags=("target_file_mismatch",))
    features = extract_features(candidate)

    assert features.safety_penalty == 0.3


def test_safety_flags_multiple():
    """P5-I2: Multiple safety_flags → safety_penalty capped at 1.0."""
    candidate = _make_candidate(patch="x = 1", safety_flags=("flag1", "flag2", "flag3", "flag4"))
    features = extract_features(candidate)

    assert features.safety_penalty == 1.0


def test_token_set_is_frozenset():
    """P5-I2: token_set is frozenset and hashable."""
    candidate = _make_candidate(patch="x = 42\ny = x + 1")
    features = extract_features(candidate)

    assert isinstance(features.token_set, frozenset)
    # Should be hashable
    hash(features.token_set)


def test_token_set_content():
    """P5-I2: token_set contains expected tokens."""
    patch = "x = 42"
    candidate = _make_candidate(patch=patch)
    features = extract_features(candidate)

    assert "x" in features.token_set
    assert "=" in features.token_set
    assert "42" in features.token_set


def test_no_mutation():
    """P5-I2: extract_features does not mutate input candidate."""
    patch = "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n old\n-new\n+new\n"
    candidate = _make_candidate(patch=patch)
    original_hash = candidate.raw_output_hash
    original_patch = candidate.normalized_patch

    features = extract_features(candidate)

    assert candidate.raw_output_hash == original_hash
    assert candidate.normalized_patch == original_patch
