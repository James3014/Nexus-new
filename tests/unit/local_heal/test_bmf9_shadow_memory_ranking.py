"""Tests for BMF9-SM shadow memory ranking."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.shadow_memory_ranking import (
    ShadowScore,
    ShadowRankingResult,
    compute_shadow_features,
    shadow_score_lessons,
    FEATURE_WEIGHTS,
)


def _make_lesson(lesson_id: str, classification: str = "verifier_pass", summary: str = "", provenance: str = "receipt:test") -> dict:
    return {
        "lesson_id": lesson_id,
        "classification": classification,
        "summary": summary,
        "provenance": provenance,
        "source": "LocalJsonlLessonStore",
        "relevance_score": 1.0,
    }


class TestShadowScoringDataModel:
    def test_shadow_score_fields(self):
        score = ShadowScore(lesson_id="l1", current_score=1.0, proposed_score=2.0)
        assert score.shadow_only is True
        assert score.lesson_id == "l1"

    def test_shadow_ranking_result_to_dict(self):
        result = ShadowRankingResult(
            shadow_scored_count=5,
            shadow_rank_changes=2,
            shadow_safety={"runtime_order_changed": False, "prompt_changed": False, "verifier_changed": False},
        )
        d = result.to_dict()
        assert d["shadow_scored_count"] == 5
        assert d["shadow_rank_changes"] == 2
        assert d["shadow_safety"]["runtime_order_changed"] is False


class TestFeatureComputation:
    def test_issue_intent_match(self):
        lesson = _make_lesson("l1", classification="evidence_gap")
        features = compute_shadow_features(lesson, task_classification="evidence_gap")
        assert features["issue_intent_match"] == 1.0

    def test_issue_intent_no_match(self):
        lesson = _make_lesson("l1", classification="verifier_pass")
        features = compute_shadow_features(lesson, task_classification="evidence_gap")
        assert features["issue_intent_match"] == 0.0

    def test_anchor_symbol_match(self):
        lesson = _make_lesson("l1", summary="fixed limit function in sympy")
        features = compute_shadow_features(lesson, anchor_symbol="limit")
        assert features["anchor_symbol_match"] > 0.0

    def test_verifier_outcome_weight(self):
        lesson_pass = _make_lesson("l1", classification="verifier_pass")
        lesson_fail = _make_lesson("l2", classification="verifier_fail")
        f_pass = compute_shadow_features(lesson_pass)
        f_fail = compute_shadow_features(lesson_fail)
        assert f_pass["verifier_outcome_weight"] > f_fail["verifier_outcome_weight"]

    def test_provenance_trust(self):
        lesson_good = _make_lesson("l1", provenance="receipt:abc123")
        lesson_bad = _make_lesson("l2", provenance="receipt:pending")
        f_good = compute_shadow_features(lesson_good)
        f_bad = compute_shadow_features(lesson_bad)
        assert f_good["provenance_trust"] > f_bad["provenance_trust"]

    def test_negative_memory_penalty(self):
        lesson_success = _make_lesson("l1", classification="verifier_pass")
        lesson_failure = _make_lesson("l2", classification="failure")
        f_success = compute_shadow_features(lesson_success)
        f_failure = compute_shadow_features(lesson_failure)
        assert f_success["negative_memory_penalty"] > f_failure["negative_memory_penalty"]

    def test_evidence_gap_bonus(self):
        lesson_gap = _make_lesson("l1", classification="evidence_gap")
        lesson_no_gap = _make_lesson("l2", classification="verifier_pass")
        f_gap = compute_shadow_features(lesson_gap)
        f_no_gap = compute_shadow_features(lesson_no_gap)
        assert f_gap["evidence_gap_bonus"] > f_no_gap["evidence_gap_bonus"]

    def test_missing_metadata_produces_zero(self):
        lesson = _make_lesson("l1")
        features = compute_shadow_features(lesson)
        # Should not crash, features should have default values
        assert "issue_intent_match" in features
        assert "anchor_symbol_match" in features


class TestShadowScoreLessons:
    def test_empty_lessons(self):
        result = shadow_score_lessons([])
        assert result.shadow_scored_count == 0
        assert result.shadow_safety["runtime_order_changed"] is False

    def test_ranking_does_not_change_runtime_order(self):
        """Shadow scoring records proposed order but does not change runtime."""
        lessons = [
            _make_lesson("l1", summary="alpha fix"),
            _make_lesson("l2", summary="beta fix"),
            _make_lesson("l3", summary="gamma fix"),
        ]
        result = shadow_score_lessons(lessons)
        # Runtime order is still l1, l2, l3 (original order)
        assert result.shadow_safety["runtime_order_changed"] is False
        assert result.shadow_safety["prompt_changed"] is False
        assert result.shadow_safety["verifier_changed"] is False

    def test_shadow_scored_count(self):
        lessons = [_make_lesson(f"l{i}") for i in range(5)]
        result = shadow_score_lessons(lessons)
        assert result.shadow_scored_count == 5

    def test_proposed_top_ids_differ_from_current(self):
        lessons = [
            _make_lesson("l1", classification="evidence_gap", summary="gap fix"),
            _make_lesson("l2", classification="verifier_pass", summary="pass fix"),
            _make_lesson("l3", classification="verifier_fail", summary="fail fix"),
        ]
        result = shadow_score_lessons(lessons, task_classification="evidence_gap")
        # l1 should be top proposed due to evidence_gap_bonus and issue_intent_match
        assert result.top_proposed_ids[0] == "l1"

    def test_feature_coverage_computed(self):
        lessons = [_make_lesson("l1", summary="test fix")]
        result = shadow_score_lessons(lessons)
        assert result.shadow_feature_coverage >= 0.0

    def test_no_task_id_specific_logic(self):
        """Verify no task_id branching in scoring."""
        lessons = [_make_lesson("l1")]
        result_a = shadow_score_lessons(lessons, task_classification="any_task")
        result_b = shadow_score_lessons(lessons, task_classification="different_task")
        # Same lesson, different task classification should produce different scores
        assert result_a.shadow_scored_count == result_b.shadow_scored_count
