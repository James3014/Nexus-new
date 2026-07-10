from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.diversity_selector import (
    DiversitySelectionResult,
    select_diverse_candidate,
    select_with_diversity,
)
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


def _make_candidate(raw_output: str) -> CanonicalPatchCandidate:
    import hashlib
    h = hashlib.sha256(raw_output.encode()).hexdigest()
    return CanonicalPatchCandidate(
        source_format="SEARCH_REPLACE",
        raw_output=raw_output,
        raw_output_hash=h,
        normalized_patch=raw_output,
        normalized_patch_hash=h,
        normalization_steps=(),
        safety_flags=(),
        target_file="a.py",
        target_symbol="foo",
    )


class TestOrchestratorDiversityAware:
    def test_orchestrator_default_uses_borda(self) -> None:
        candidates = [_make_candidate("def foo(): pass")]
        result = select_diverse_candidate(candidates)
        assert result.selection_strategy != "diversity_aware"
        assert result.selected_index == 0

    def test_orchestrator_diversity_aware_uses_select_with_diversity(self) -> None:
        candidates = [_make_candidate("def foo(): pass")]
        result = select_with_diversity(candidates)
        assert result.selection_strategy == "diversity_aware"
        assert result.diversity_aware is True

    def test_orchestrator_log_which_mode(self) -> None:
        borda = select_diverse_candidate([_make_candidate("x")])
        assert borda.selection_strategy in ("single_candidate", "diversity_v1", "contract_only_first_valid")
        aware = select_with_diversity([_make_candidate("x")])
        assert aware.selection_strategy == "diversity_aware"

    def test_existing_orchestrator_tests_unchanged(self) -> None:
        result = select_diverse_candidate([_make_candidate("def foo(): return 1")])
        assert result.selected_index == 0
        assert not result.fail_closed

    def test_orchestrator_same_result_shape_both_modes(self) -> None:
        candidates = [_make_candidate("def foo(): pass")]
        r1 = select_diverse_candidate(candidates)
        r2 = select_with_diversity(candidates)
        assert type(r1) is type(r2)
        for field in ("selected_index", "selected_candidate_hash", "candidate_count", "fail_closed"):
            assert hasattr(r2, field)
