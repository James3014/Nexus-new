"""P5-I4: Popularity Trap Guard Tests."""
from __future__ import annotations

import hashlib
import pytest
from nexus.services.local_heal.diversity_selector import (
    CandidateFeatures,
    DuplicateGroup,
    PopularityTrapDecision,
    detect_popularity_trap,
)


def _make_features(patch="x = 1", target_file="foo.py", safety_flags=(), model="qwen", syntax_score=1.0):
    raw_hash = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    return CandidateFeatures(
        candidate_hash=raw_hash,
        source_model=model,
        source_format="UNIFIED_DIFF",
        patch_length=len(patch),
        line_count=len(patch.splitlines()),
        token_set=frozenset(patch.split()),
        target_file_match=bool(target_file),
        syntax_like_score=syntax_score,
        safety_penalty=min(1.0, len(safety_flags) * 0.3) if safety_flags else 0.0,
    )


def _make_group(indices, kind="exact", sim=1.0):
    return DuplicateGroup(
        group_id=f"dup-{min(indices)}",
        candidate_indices=tuple(indices),
        representative_index=min(indices),
        duplicate_kind=kind,
        similarity_score=sim,
    )


def test_low_quality_trap_detected():
    """P5-I4: 3 low-quality candidates → trap detected, action=penalize."""
    # Mix: 2 low quality + 1 high quality → not all unsafe → penalize
    features = [
        _make_features(patch="x", syntax_score=0.3, target_file="", model="qwen"),  # low syntax
        _make_features(patch="x", syntax_score=0.3, target_file="", model="deepseek"),  # low syntax
        _make_features(patch="x = 1\ny = 2", syntax_score=1.0, target_file="foo.py", model="llama"),  # high quality
    ]
    groups = [_make_group([0, 1, 2])]

    decision = detect_popularity_trap(features, groups)
    assert decision.detected is True
    assert decision.dominant_group_size == 3
    assert decision.candidate_count == 3
    assert decision.recommended_action == "penalize_dominant_group"
    assert "low_syntax_score" in decision.reason


def test_high_quality_no_trap():
    """P5-I4: 3 high-quality candidates → no trap."""
    features = [
        _make_features(patch="x = 1\ny = 2", syntax_score=1.0, target_file="foo.py", model="qwen"),
        _make_features(patch="x = 1\ny = 2", syntax_score=1.0, target_file="foo.py", model="deepseek"),
        _make_features(patch="x = 1\ny = 2", syntax_score=1.0, target_file="foo.py", model="llama"),
    ]
    groups = [_make_group([0, 1, 2])]

    decision = detect_popularity_trap(features, groups)
    assert decision.detected is False
    assert decision.recommended_action == "none"


def test_model_homogeneity_trap():
    """P5-I4: majority same model family → reason includes model_homogeneity."""
    features = [
        _make_features(patch="x", model="qwen"),
        _make_features(patch="x", model="qwen"),
        _make_features(patch="x", model="qwen"),
        _make_features(patch="y", model="deepseek"),
    ]
    groups = [_make_group([0, 1, 2])]

    decision = detect_popularity_trap(features, groups)
    assert decision.detected is True
    assert "model_homogeneity" in decision.reason


def test_no_groups_no_trap():
    """P5-I4: no groups → no trap."""
    features = [_make_features(patch="x"), _make_features(patch="y")]
    groups = []

    decision = detect_popularity_trap(features, groups)
    assert decision.detected is False
    assert decision.reason == "no_groups"


def test_all_candidates_unsafe_fail_closed():
    """P5-I4: all candidates unsafe → action=fail_closed."""
    features = [
        _make_features(patch="x", safety_flags=("flag1",), syntax_score=0.3),
        _make_features(patch="x", safety_flags=("flag2",), syntax_score=0.3),
    ]
    groups = [_make_group([0, 1])]

    decision = detect_popularity_trap(features, groups)
    assert decision.detected is True
    assert decision.recommended_action == "fail_closed"


def test_no_mutation():
    """P5-I4: Input features and groups are never mutated."""
    features = [
        _make_features(patch="x", syntax_score=0.3),
        _make_features(patch="x", syntax_score=0.3),
    ]
    groups = [_make_group([0, 1])]
    original_hashes = [f.candidate_hash for f in features]
    original_indices = groups[0].candidate_indices

    detect_popularity_trap(features, groups)

    assert [f.candidate_hash for f in features] == original_hashes
    assert groups[0].candidate_indices == original_indices
