"""P5-V4: Selected Candidate Metadata Consistency Tests.

Verifies that when P5 enables diversity selection and picks a candidate,
the selected_candidate_source_model and hash match the P5-selected raw candidate,
not the first non-rejected candidate.
"""
from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    evaluate_and_execute,
)


def _valid_request(**overrides):
    defaults = {
        "task_id": "t1",
        "repo_root": "/tmp",
        "target_file": "foo.py",
        "difficulty": "hard",
        "execution_topology": "cloud_with_local_assist",
        "p3_route_status": "shadow_stage5_escalation_recommended",
        "hard_case_escalation_reason": "retry_failed",
        "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        "judge_model": "judge",
    }
    defaults.update(overrides)
    return CommitteeRoutedToolRequest(**defaults)


def _producer_first_bad_second_good(request):
    """candidate 0: bad-model, short meaningless patch
       candidate 1: good-model, proper unified diff (target file in patch)."""
    return [
        {
            "model": "bad-model",
            "candidate_patch": "x",
            "format": "SEARCH_REPLACE",
        },
        {
            "model": "good-model",
            "candidate_patch": "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-x\n+y\n",
            "format": "UNIFIED_DIFF",
        },
    ]


def _producer_duplicate_majority_unique(request):
    """candidate 0: qwen, short
       candidate 1: qwen, short (duplicate)
       candidate 2: deepseek, proper unified diff."""
    return [
        {
            "model": "qwen",
            "candidate_patch": "x",
            "format": "SEARCH_REPLACE",
        },
        {
            "model": "qwen",
            "candidate_patch": "x",
            "format": "SEARCH_REPLACE",
            "candidate_id": "dup",
        },
        {
            "model": "deepseek",
            "candidate_patch": "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-x\n+y\n",
            "format": "UNIFIED_DIFF",
        },
    ]


def _producer_rejected_first(request):
    """First raw candidate is rejected by adapter,
       P5 must still map selected index correctly."""
    return [
        {
            "model": "rejected-model",
            "candidate_patch": "",
            "format": "UNIFIED_DIFF",
        },
        {
            "model": "good-model",
            "candidate_patch": "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-x\n+y\n",
            "format": "UNIFIED_DIFF",
        },
    ]


class TestP5MetadataConsistency:
    """P5-V4: Metadata consistency across selection scenarios."""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
        os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
        yield
        os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
        os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)

    # ------- Scenario A: first bad, second good -------

    def test_p5_disabled_first_bad_selected(self):
        os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=_producer_first_bad_second_good)
        assert result.winner_found is True
        assert result.selected_candidate_source_model == "bad-model"

    def test_p5_on_selects_good_model(self):
        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=_producer_first_bad_second_good)
        assert result.winner_found is True
        p5_idx = result.receipt_fragment.get("p5_selected_candidate_index", -1)
        assert p5_idx == 1, f"P5 should select index 1, got {p5_idx}"
        assert result.selected_candidate_source_model == "good-model", (
            f"expected good-model, got {result.selected_candidate_source_model}"
        )

    def test_p5_on_model_matches_p5_index(self):
        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=_producer_first_bad_second_good)
        p5_idx = result.receipt_fragment.get("p5_selected_candidate_index", -1)
        p5_model = result.receipt_fragment.get("p4_selected_candidate_model", "")
        idx_to_model = {0: "bad-model", 1: "good-model"}
        expected = idx_to_model.get(p5_idx, "unknown")
        assert p5_model == expected, (
            f"p5 index {p5_idx} should map to model '{expected}', got '{p5_model}'"
        )

    # ------- Scenario B: duplicate majority + unique safer -------

    def test_p5_on_duplicate_majority_selects_unique(self):
        req = _valid_request(target_file="foo.py")
        result = evaluate_and_execute(req, candidate_producer=_producer_duplicate_majority_unique)
        assert result.winner_found is True
        p5_idx = result.receipt_fragment.get("p5_selected_candidate_index", -1)
        assert p5_idx == 2, f"P5 should select index 2 (deepseek), got {p5_idx}"
        assert result.selected_candidate_source_model == "deepseek", (
            f"expected deepseek, got {result.selected_candidate_source_model}"
        )
        assert result.receipt_fragment.get("p5_popularity_trap_detected") is True

    # ------- Scenario C: hash consistency -------

    def test_p5_hash_consistent_with_selected_index(self):
        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=_producer_first_bad_second_good)
        p5_hash = result.receipt_fragment.get("p5_selected_candidate_hash", "")
        p4_hash = result.receipt_fragment.get("p4_selected_candidate_hash", "")
        assert p5_hash, "p5_selected_candidate_hash should be non-empty"
        assert p5_hash == p4_hash, (
            f"p5 hash '{p5_hash}' != p4 hash '{p4_hash}'"
        )

    # ------- Scenario D: raw_index != canonical_index (rejected first) -------

    def test_p5_on_model_after_first_rejected(self):
        req = _valid_request(target_file="foo.py")
        result = evaluate_and_execute(req, candidate_producer=_producer_rejected_first)
        assert result.winner_found is True
        assert result.selected_candidate_source_model == "good-model", (
            f"after first rejected, expected good-model, got {result.selected_candidate_source_model}"
        )

    # ------- P5 receipt fields still present -------

    def test_p5_trace_and_fuzzy_still_present(self):
        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=_producer_first_bad_second_good)
        frag = result.receipt_fragment
        assert frag.get("p5_trace_event_count", 0) > 0, "trace events should be present"
        assert frag.get("p5_score_breakdown"), "score breakdown should be present"
        # Check that at least one score_breakdown entry has fuzzy_function
        scores = frag.get("p5_score_breakdown", [])
        has_fuzzy = any(
            "fuzzy_function" in s.get("breakdown", {}) or "fuzzy_functions_used" in s.get("breakdown", {})
            for s in scores
        ) or any("fuzzy_function" in s for s in scores)
        assert has_fuzzy, "fuzzy_function should be present in score_breakdown"
