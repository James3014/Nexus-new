from __future__ import annotations

import pytest
from nexus.services.local_heal.diversity_selector import (
    PopularityTrapResult,
    select_diverse_candidate,
    select_from_cascade,
    select_with_diversity,
)
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


def _make_candidate(raw_output: str, hash_suffix: str = "") -> CanonicalPatchCandidate:
    import hashlib
    raw = raw_output
    h = hashlib.sha256(raw.encode()).hexdigest()
    return CanonicalPatchCandidate(
        source_format="SEARCH_REPLACE",
        raw_output=raw,
        raw_output_hash=h[:16] + hash_suffix,
        normalized_patch=raw,
        normalized_patch_hash=h,
        normalization_steps=(),
        safety_flags=(),
        target_file="a.py",
        target_symbol="foo",
    )


class TestSelectWithDiversity:
    def test_all_unique(self) -> None:
        candidates = [
            _make_candidate("def foo(): return 1"),
            _make_candidate("def foo(): return 2"),
            _make_candidate("def foo(): return 3"),
            _make_candidate("def foo(): return 4"),
        ]
        result = select_with_diversity(candidates)
        assert result.fail_closed is False
        assert result.selected_index >= 0
        assert result.selection_strategy == "diversity_aware"

    def test_all_similar(self) -> None:
        candidates = [
            _make_candidate("fix the bug by adding a check"),
            _make_candidate("fix the bug by adding a check"),
            _make_candidate("fix the bug by adding a check"),
            _make_candidate("fix the bug by adding a check"),
        ]
        result = select_with_diversity(candidates)
        assert result.popularity_trap_detected is True
        assert result.selected_index >= 0

    def test_one_dissimilar(self) -> None:
        candidates = [
            _make_candidate("fix the bug by adding a null check"),
            _make_candidate("fix the bug by adding a null check here"),
            _make_candidate("fix the bug by adding a null check there"),
            _make_candidate("completely different: rewrite the whole module"),
        ]
        result = select_with_diversity(candidates)
        dissimilar_idx = 3
        assert result.selected_index == dissimilar_idx

    def test_similarity_threshold(self) -> None:
        candidates = [
            _make_candidate("some similar text here"),
            _make_candidate("some similar text over there"),
            _make_candidate("some similar text right here"),
            _make_candidate("completely unrelated: different module approach"),
        ]
        result_low = select_with_diversity(candidates, similarity_threshold=0.1)
        assert result_low.popularity_trap_detected is True
        result_high = select_with_diversity(candidates, similarity_threshold=0.99)
        assert result_high.popularity_trap_detected is False

    def test_popularity_trap_detected_flag(self) -> None:
        candidates = [
            _make_candidate("identical output here"),
            _make_candidate("identical output here"),
            _make_candidate("identical output here"),
            _make_candidate("identical output here"),
        ]
        result = select_with_diversity(candidates)
        assert result.popularity_trap_detected is True

    def test_existing_select_diverse_candidates_unchanged(self) -> None:
        candidates = [_make_candidate("test")]
        result = select_diverse_candidate(candidates)
        assert result.fail_closed is False
        assert result.selected_index == 0

    def test_existing_select_from_cascade_unchanged(self) -> None:
        candidates = [_make_candidate("test")]
        result = select_from_cascade(
            type("FakeReceipt", (), {"winner_candidate_hash": candidates[0].raw_output_hash})(),
            candidates,
        )
        assert result.cascade_aware is True

    def test_popularity_trap_result_frozen(self) -> None:
        r = PopularityTrapResult(
            trapped_candidate_ids=("a", "b"),
            similarity_scores={"a": 0.9},
        )
        with pytest.raises(AttributeError):
            r.trapped_candidate_ids = ("c",)
