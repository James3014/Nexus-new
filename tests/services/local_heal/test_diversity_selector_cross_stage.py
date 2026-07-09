from __future__ import annotations

import pytest

from nexus.services.local_heal.diversity_selector import DiversitySelectionResult, select_from_cascade
from nexus.services.local_heal.local_cascade_orchestrator import LocalCascadeReceipt
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


def _make_candidate(hash_suffix: str) -> CanonicalPatchCandidate:
    return CanonicalPatchCandidate(
        source_format="unified_diff",
        raw_output=f"patch-{hash_suffix}",
        raw_output_hash=f"hash-{hash_suffix}",
        normalized_patch=f"diff --git a/x.py b/x.py\n@@ -1 +1 @@\n-old\n+new-{hash_suffix}",
        normalized_patch_hash=f"norm-{hash_suffix}",
        normalization_steps=(),
        safety_flags=(),
        target_file="x.py",
        target_symbol="foo",
    )


def _make_receipt(winner_hash: str = "") -> LocalCascadeReceipt:
    return LocalCascadeReceipt(
        task_id="t1",
        stages_run=("model_a", "model_b"),
        stages_failed=(),
        winner_model="model_b" if winner_hash else "",
        winner_candidate_hash=winner_hash,
        failed_at_final_stage=not bool(winner_hash),
        fail_closed=not bool(winner_hash),
    )


def test_select_from_cascade_empty_returns_empty():
    receipt = _make_receipt(winner_hash="hash-winner")
    result = select_from_cascade(receipt, [])
    assert result.cascade_aware
    assert result.selected_candidate_hash == "hash-winner"
    assert result.selected_index == -1


def test_select_from_cascade_single_candidate():
    receipt = _make_receipt(winner_hash="hash-single")
    candidates = [_make_candidate("single")]
    result = select_from_cascade(receipt, candidates)
    assert result.cascade_aware
    assert result.selected_candidate_hash == "hash-single"
    assert result.selected_index == 0


def test_select_from_cascade_two_candidates_borda():
    receipt = _make_receipt(winner_hash="hash-first")
    candidates = [_make_candidate("a"), _make_candidate("b")]
    result = select_from_cascade(receipt, candidates)
    assert result.cascade_aware
    assert result.selection_strategy == "cascade_aware_diversity"
    assert result.candidate_count == 2


def test_select_from_cascade_cascade_aware_flag_true():
    receipt = _make_receipt(winner_hash="hash-flag")
    candidates = [_make_candidate("flag")]
    result = select_from_cascade(receipt, candidates)
    assert result.cascade_aware is True


def test_select_from_cascade_default_winner_on_tie():
    candidates = [
        _make_candidate("x"),
        _make_candidate("x"),
    ]
    tied_receipt = _make_receipt(winner_hash="hash-tie-default")
    result = select_from_cascade(tied_receipt, candidates)
    assert result.cascade_aware
    assert result.selected_index >= 0
