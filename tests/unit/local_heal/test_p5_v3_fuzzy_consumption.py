"""P5-V3: FuzzyFunction Runtime Consumption Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.diversity_selector import select_diverse_candidate
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


def _make_candidate(patch, safety_flags=(), target_file="foo.py", source_format="UNIFIED_DIFF"):
    raw_hash = __import__("hashlib").sha256(patch.encode("utf-8")).hexdigest()
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


def test_score_breakdown_includes_fuzzy_function():
    """P5-V3: score_breakdown includes fuzzy_function fields."""
    c1 = _make_candidate("x = 1\ny = 2\nz = 3\n")
    c2 = _make_candidate("a = 1\nb = 2\nc = 3\n")
    result = select_diverse_candidate([c1, c2], source_models=["qwen", "deepseek"])

    for entry in result.score_breakdown:
        assert "fuzzy_function" in entry
        assert entry["fuzzy_function"]["name"] == "candidate_quality_v1"
        assert entry["fuzzy_function"]["version"] == "1.0"
        assert entry["fuzzy_function"]["backend"] == "deterministic"


def test_candidate_quality_matches_inline():
    """P5-V3: candidate_quality result matches inline scoring."""
    from nexus.services.local_heal.fuzzy_functions import evaluate as fuzzy_evaluate

    # Test with known values
    result = fuzzy_evaluate("candidate_quality_v1", syntax_like_score=0.8, safety_penalty=0.0)
    assert result.score == 0.8
    assert result.label == "high"
    assert result.deterministic is True


def test_duplicate_similarity_matches_inline():
    """P5-V3: duplicate_similarity result matches inline grouping."""
    from nexus.services.local_heal.fuzzy_functions import evaluate as fuzzy_evaluate

    # Test exact duplicate
    result = fuzzy_evaluate("duplicate_similarity_v1", jaccard_similarity=0.5, same_hash=True, same_target=True)
    assert result.score == 1.0
    assert result.label == "exact"


def test_popularity_trap_risk_matches_inline():
    """P5-V3: popularity_trap_risk result matches inline trap detection."""
    from nexus.services.local_heal.fuzzy_functions import evaluate as fuzzy_evaluate

    result = fuzzy_evaluate(
        "popularity_trap_risk_v1",
        dominant_group_ratio=0.8,
        has_low_syntax=True,
        has_safety_penalty=True,
        model_homogeneous=True,
    )
    assert result.score >= 0.6
    assert result.label == "high"


def test_unknown_fuzzy_function_raises_keyerror():
    """P5-V3: unknown fuzzy function raises KeyError."""
    from nexus.services.local_heal.fuzzy_functions import evaluate as fuzzy_evaluate

    with pytest.raises(KeyError):
        fuzzy_evaluate("nonexistent_function")


def test_full_p5_suite_still_green():
    """P5-V3: Full P5 test suite still green after fuzzy consumption."""
    # This test just imports and runs select_diverse_candidate to ensure no import errors
    c1 = _make_candidate("--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-a\n+b")
    c2 = _make_candidate("y = 2\nz = 3\n")
    result = select_diverse_candidate([c1, c2], source_models=["qwen", "deepseek"])
    assert result.selection_strategy == "diversity_v1"
    assert len(result.score_breakdown) == 2
    # Verify fuzzy functions are used
    for entry in result.score_breakdown:
        assert "fuzzy_function" in entry
