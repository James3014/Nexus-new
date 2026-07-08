"""P5-I1: Diversity Selection Contract Tests."""
from __future__ import annotations

import json
import pytest

from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate
from nexus.services.local_heal.diversity_selector import (
    DiversityCandidate,
    select_diverse_candidate,
)


def _make_candidate(
    *,
    index: int = 0,
    source_format: str = "UNIFIED_DIFF",
    raw_output: str = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new\n",
    target_file: str = "foo.py",
    safety_flags: tuple[str, ...] = (),
) -> CanonicalPatchCandidate:
    import hashlib
    raw_hash = hashlib.sha256(raw_output.encode("utf-8")).hexdigest()
    norm_patch = raw_output
    norm_hash = raw_hash
    return CanonicalPatchCandidate(
        source_format=source_format,
        raw_output=raw_output,
        raw_output_hash=raw_hash,
        normalized_patch=norm_patch,
        normalized_patch_hash=norm_hash,
        normalization_steps=(),
        safety_flags=safety_flags,
        target_file=target_file,
        target_symbol="",
        line_span="",
        old_block_hash="",
    )


class TestEmptyCandidates:
    def test_fail_closed_on_empty(self):
        result = select_diverse_candidate([])
        assert result.fail_closed is True
        assert result.failure_reasons == ["no_candidates"]
        assert result.selected_index == -1
        assert result.selected_candidate_id == ""
        assert result.selected_candidate_hash == ""

    def test_candidate_count_zero(self):
        result = select_diverse_candidate([])
        assert result.candidate_count == 0
        assert result.diversity_candidate_count == 0
        assert result.duplicate_group_count == 0


class TestSingleCandidate:
    def test_selects_index_zero(self):
        c = _make_candidate(index=0)
        result = select_diverse_candidate([c])
        assert result.selected_index == 0
        assert result.fail_closed is False

    def test_strategy_single_candidate(self):
        c = _make_candidate(index=0)
        result = select_diverse_candidate([c])
        assert result.selection_strategy == "single_candidate"

    def test_candidate_count_one(self):
        c = _make_candidate(index=0)
        result = select_diverse_candidate([c])
        assert result.candidate_count == 1
        assert result.diversity_candidate_count == 1

    def test_no_duplicate_or_popularity_trap(self):
        c = _make_candidate(index=0)
        result = select_diverse_candidate([c])
        assert result.duplicate_group_count == 0
        assert result.popularity_trap_detected is False

    def test_hash_matches_input(self):
        c = _make_candidate(index=0)
        result = select_diverse_candidate([c])
        assert result.selected_candidate_hash == c.raw_output_hash


class TestMultipleCandidates:
    def test_contract_only_first_valid_strategy(self):
        a = _make_candidate(index=0, raw_output="--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new_a\n")
        b = _make_candidate(index=1, raw_output="--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new_b\n")
        result = select_diverse_candidate([a, b])
        assert result.selection_strategy == "contract_only_first_valid"

    def test_selects_first_candidate(self):
        a = _make_candidate(index=0, raw_output="--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+first\n")
        b = _make_candidate(index=1, raw_output="--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+second\n")
        result = select_diverse_candidate([a, b])
        assert result.selected_index == 0
        assert result.selected_candidate_hash == a.raw_output_hash

    def test_candidate_count(self):
        a = _make_candidate(index=0)
        b = _make_candidate(index=1)
        c = _make_candidate(index=2)
        result = select_diverse_candidate([a, b, c])
        assert result.candidate_count == 3
        assert result.diversity_candidate_count == 3

    def test_no_fail_closed_with_valid_candidates(self):
        a = _make_candidate(index=0)
        b = _make_candidate(index=1)
        result = select_diverse_candidate([a, b])
        assert result.fail_closed is False
        assert result.failure_reasons == []


class TestResultSerializable:
    def test_result_to_dict_via_asdict(self):
        from dataclasses import asdict
        c = _make_candidate(index=0)
        result = select_diverse_candidate([c])
        d = asdict(result)
        assert isinstance(d, dict)
        assert d["selected_index"] == 0
        assert d["selection_strategy"] == "single_candidate"
        assert d["fail_closed"] is False

    def test_result_to_json(self):
        c = _make_candidate(index=0)
        result = select_diverse_candidate([c])
        d = {
            "selected_index": result.selected_index,
            "selection_strategy": result.selection_strategy,
            "fail_closed": result.fail_closed,
            "candidate_count": result.candidate_count,
            "score_breakdown": result.score_breakdown,
        }
        payload = json.dumps(d)
        parsed = json.loads(payload)
        assert parsed["selected_index"] == 0
        assert parsed["selection_strategy"] == "single_candidate"

    def test_result_all_fields_serializable(self):
        c = _make_candidate(index=0)
        result = select_diverse_candidate([c])
        json.dumps(result.score_breakdown)
        json.dumps(result.rejected_by_diversity)


class TestNoMutation:
    def test_input_candidates_not_mutated(self):
        c = _make_candidate(index=0)
        orig_hash = c.raw_output_hash
        orig_norm = c.normalized_patch
        _ = select_diverse_candidate([c])
        assert c.raw_output_hash == orig_hash
        assert c.normalized_patch == orig_norm


class TestDiversityCandidateFromCanonical:
    def test_from_canonical_preserves_fields(self):
        c = _make_candidate(index=0)
        dc = DiversityCandidate.from_canonical(c, index=0, source_model="test-model")
        assert dc.candidate_hash == c.raw_output_hash
        assert dc.source_model == "test-model"
        assert dc.source_format == c.source_format
        assert dc.target_file == c.target_file
        assert dc.safety_flags == c.safety_flags
        assert dc.canonical_index == 0

    def test_from_canonical_generates_candidate_id(self):
        c = _make_candidate(index=0)
        dc = DiversityCandidate.from_canonical(c, index=0)
        expected_id = f"{c.raw_output_hash[:16]}#0"
        assert dc.candidate_id == expected_id


class TestSourceModels:
    def test_default_source_models_empty(self):
        a = _make_candidate(index=0)
        b = _make_candidate(index=1)
        result = select_diverse_candidate([a, b])
        assert result.selected_index == 0

    def test_explicit_source_models_passed(self):
        a = _make_candidate(index=0)
        b = _make_candidate(index=1)
        result = select_diverse_candidate(
            [a, b],
            source_models=["model-a", "model-b"],
        )
        assert result.selected_index == 0
