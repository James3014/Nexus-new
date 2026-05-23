from __future__ import annotations

from scripts.bench.evidence_bundle_rows import build_evidence_bundle_row_sets, row_key_counts


def test_build_evidence_bundle_row_sets_splits_modes_and_eligibility():
    rows = [
        {"mode": "with_nexus", "task_id": "a", "trial_index": 0},
        {"mode": "with_nexus", "task_id": "b", "trial_index": 0, "run_eligible": False},
        {"mode": "without_nexus", "task_id": "a", "trial_index": 0},
        {"mode": "without_nexus", "task_id": "b", "trial_index": 0, "run_eligible": False},
    ]

    row_sets = build_evidence_bundle_row_sets(rows)

    assert row_sets.with_rows == rows[:2]
    assert row_sets.without_rows == rows[2:]
    assert row_sets.eligible_with == [rows[0]]
    assert row_sets.eligible_without == [rows[2]]
    assert row_sets.row_counts == {
        "with_nexus": 2,
        "without_nexus": 2,
        "total": 4,
        "eligible_with_nexus": 1,
        "eligible_without_nexus": 1,
        "infra_invalid_with_nexus": 1,
        "infra_invalid_without_nexus": 1,
    }


def test_build_evidence_bundle_row_sets_keeps_same_task_trial_contract():
    matching = [
        {"mode": "with_nexus", "task_id": "a", "trial_index": 0},
        {"mode": "without_nexus", "task_id": "a", "trial_index": 0},
    ]
    mismatched = [
        {"mode": "with_nexus", "task_id": "a", "trial_index": 2},
        {"mode": "without_nexus", "task_id": "a", "trial_index": 1},
    ]

    assert build_evidence_bundle_row_sets(matching).same_task_trials is True
    assert build_evidence_bundle_row_sets(mismatched).same_task_trials is False


def test_row_key_counts_preserves_existing_default_trial_index_semantics():
    assert row_key_counts(
        [
            {"task_id": "a"},
            {"task_id": "a", "trial_index": ""},
            {"task_id": "a", "trial_index": 0},
        ]
    ) == {("a", "1"): 3}
