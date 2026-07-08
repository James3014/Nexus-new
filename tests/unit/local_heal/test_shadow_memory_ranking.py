"""EA-R4: Copyability Telemetry Tests."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.shadow_memory_ranking import (
    ShadowScore,
    ShadowRankingResult,
    compute_copyability_score,
    shadow_score_lessons,
)


def test_copyability_score_high_verified():
    """EA-R4: High copyability + verified → decision_eligible."""
    lesson = {
        "summary": "fix database connection",
        "classification": "bug fix verifier_pass",
        "provenance": "receipt:verified",
    }
    score, eligibility, reason = compute_copyability_score(lesson, verified_outcome=True)
    assert score >= 0.80
    assert eligibility == "decision_eligible"
    assert reason == "high_copyability_verified"


def test_copyability_score_medium():
    """EA-R4: Medium copyability → audit_only."""
    lesson = {
        "summary": "fix something",
        "classification": "bug fix",
        "provenance": "receipt:pending",
    }
    score, eligibility, reason = compute_copyability_score(lesson, verified_outcome=False)
    assert 0.50 <= score < 0.80
    assert eligibility == "audit_only"


def test_copyability_score_low():
    """EA-R4: Low copyability → ignore_for_selection."""
    lesson = {
        "summary": "",
        "classification": "",
        "provenance": "",
    }
    score, eligibility, reason = compute_copyability_score(lesson, verified_outcome=False)
    assert score < 0.50
    assert eligibility == "ignore_for_selection"


def test_shadow_score_includes_copyability():
    """EA-R4: ShadowScore includes copyability fields."""
    lessons = [
        {"lesson_id": "l1", "summary": "fix bug", "classification": "bug fix", "relevance_score": 1.0},
        {"lesson_id": "l2", "summary": "add feature", "classification": "feature", "relevance_score": 0.8},
    ]
    result = shadow_score_lessons(lessons, task_classification="bug")
    for score in result.scores:
        assert hasattr(score, "copyability_score")
        assert hasattr(score, "decision_eligibility")
        assert hasattr(score, "audit_only_reason")


def test_shadow_ranking_unchanged():
    """EA-R4: Shadow ranking runtime order unchanged."""
    lessons = [
        {"lesson_id": "l1", "summary": "fix bug", "classification": "bug fix", "relevance_score": 1.0},
        {"lesson_id": "l2", "summary": "add feature", "classification": "feature", "relevance_score": 0.8},
    ]
    result = shadow_score_lessons(lessons, task_classification="bug")
    # Ranking should still work correctly
    assert result.shadow_scored_count == 2
    assert len(result.top_proposed_ids) == 2
