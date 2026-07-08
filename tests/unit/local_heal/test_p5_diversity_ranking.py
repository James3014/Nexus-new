"""P5-I5: Diversity-Aware Ranking and Selection Tests."""
from __future__ import annotations

import hashlib
import json
import pytest
from nexus.services.local_heal.diversity_selector import (
    select_diverse_candidate,
    extract_features,
)
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


def _make_candidate(patch, target_file="foo.py", safety_flags=(), source_format="UNIFIED_DIFF"):
    raw_hash = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    return CanonicalPatchCandidate(
        source_format=source_format,
        raw_output=patch,
        raw_output_hash=raw_hash,
        normalized_patch=patch,
        normalized_patch_hash=raw_hash,
        normalization_steps=(),
        safety_flags=safety_flags,
        target_file=target_file,
    )


def test_best_quality_selected():
    """P5-I5: Best quality candidate selected."""
    c1 = _make_candidate("--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-a\n+b", source_format="UNIFIED_DIFF")  # syntax_like_score=1.0
    c2 = _make_candidate("random text no markers", source_format="PLAIN_TEXT")  # syntax_like_score=0.5
    result = select_diverse_candidate([c1, c2], source_models=["qwen", "deepseek"])

    # c1 has syntax_like_score=1.0, c2 has 0.5 → c1 wins
    assert result.selected_index == 0
    assert result.selection_strategy == "diversity_v1"


def test_duplicate_majority_penalized():
    """P5-I5: Duplicate majority penalized when risky."""
    c1 = _make_candidate("x = 1", safety_flags=("flag",))  # safety_penalty=0.3
    c2 = _make_candidate("x = 1", safety_flags=("flag",))  # same hash, safety
    c3 = _make_candidate("y = 2", target_file="bar.py")  # different, no safety
    result = select_diverse_candidate([c1, c2, c3], source_models=["qwen", "qwen", "deepseek"])

    # c3 should win: different from duplicate group, no safety penalty
    assert result.selected_index == 2


def test_unique_safer_beats_duplicated_unsafe():
    """P5-I5: Unique safer candidate beats duplicated unsafe candidate."""
    c1 = _make_candidate("x = 1", safety_flags=("flag",))  # safety_penalty=0.3
    c2 = _make_candidate("y = 2")  # no safety penalty
    result = select_diverse_candidate([c1, c2], source_models=["qwen", "deepseek"])

    assert result.selected_index == 1


def test_tiebreak_stable():
    """P5-I5: Tie-break stable (same score → lower index wins)."""
    c1 = _make_candidate("--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-a\n+b")
    c2 = _make_candidate("--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-a\n+b")
    result = select_diverse_candidate([c1, c2], source_models=["qwen", "deepseek"])

    assert result.selected_index == 0


def test_single_candidate():
    """P5-I5: Single candidate still selected with strategy='single_candidate'."""
    c1 = _make_candidate("x = 1")
    result = select_diverse_candidate([c1])

    assert result.selected_index == 0
    assert result.selection_strategy == "single_candidate"


def test_contract_only_unchanged():
    """P5-I5: contract_only_first_valid strategy still returns index 0."""
    c1 = _make_candidate("x = 1")
    c2 = _make_candidate("y = 2")
    result = select_diverse_candidate([c1, c2], strategy="contract_only_first_valid")

    assert result.selected_index == 0
    assert result.selection_strategy == "contract_only_first_valid"


def test_all_unsafe_fail_closed():
    """P5-I5: All candidates with final_score <= 0 → fail_closed."""
    c1 = _make_candidate("x", safety_flags=("f1", "f2", "f3", "f4"), target_file="")
    c2 = _make_candidate("y", safety_flags=("f1", "f2", "f3", "f4"), target_file="")
    result = select_diverse_candidate([c1, c2], source_models=["qwen", "deepseek"])

    assert result.fail_closed is True
    assert "all_candidates_unsafe" in result.failure_reasons


def test_score_breakdown_serializable():
    """P5-I5: score_breakdown is JSON-serializable."""
    c1 = _make_candidate("--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-a\n+b")
    c2 = _make_candidate("y = 2")
    result = select_diverse_candidate([c1, c2], source_models=["qwen", "deepseek"])

    # Should be serializable to JSON
    json_str = json.dumps(result.score_breakdown)
    assert len(json_str) > 0


def test_no_mutation():
    """P5-I5: Input candidates are not mutated."""
    c1 = _make_candidate("x = 1")
    c2 = _make_candidate("y = 2")
    original_hash = c1.raw_output_hash

    select_diverse_candidate([c1, c2], source_models=["qwen", "deepseek"])

    assert c1.raw_output_hash == original_hash
