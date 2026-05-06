from __future__ import annotations

from nexus.engine.autodata_forge import classify_trajectory_quality


def test_autodata_forge_marks_gold_only_for_audited_strong_weak_gap():
    label = classify_trajectory_quality(strong_score=0.82, weak_score=0.55, audit_passed=True)

    assert label.label == "GOLD"
    assert label.gap == 0.27
    assert label.reason == "strong_weak_gap_passed"


def test_autodata_forge_rejects_failed_audit_even_with_large_gap():
    label = classify_trajectory_quality(strong_score=0.9, weak_score=0.1, audit_passed=False)

    assert label.label == "REJECTED"
    assert label.reason == "audit_failed"


def test_autodata_forge_keeps_low_gap_as_silver():
    label = classify_trajectory_quality(strong_score=0.66, weak_score=0.51, audit_passed=True)

    assert label.label == "SILVER"
    assert label.reason == "strong_weak_gap_below_threshold"
