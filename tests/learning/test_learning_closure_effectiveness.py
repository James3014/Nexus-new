from __future__ import annotations

import json
from pathlib import Path

from nexus.learning.learning_closure_effectiveness import (
    EffectivenessReport,
    classify_closure_effectiveness,
    evaluate_effectiveness,
    generate_effectiveness_report,
    load_learning_closures,
)


def test_real_learning_closure_loaded():
    entries = load_learning_closures(Path(".nexus/reports/learn/learning_closure.jsonl"))
    assert len(entries) > 0


def test_real_learning_closure_12_task_evaluation():
    entries = [
        {"status": "ok", "classification": "verifier_pass", "task_id": "task_001"},
        {"status": "failed_non_blocking", "classification": "verifier_fail", "task_id": "task_002"},
        {"status": "ok", "classification": "correct_abstain", "task_id": "task_003"},
    ]
    report = evaluate_effectiveness(entries)
    assert report.total_entries == 3
    assert report.improved_count == 2
    assert report.no_change_count == 1


def test_real_learning_closure_improvement_rate():
    entries = [
        {"status": "ok", "classification": "verifier_pass", "task_id": f"task_{i:03d}"}
        for i in range(10)
    ] + [
        {"status": "failed_non_blocking", "classification": "verifier_fail", "task_id": f"task_{i:03d}"}
        for i in range(10, 15)
    ]
    report = evaluate_effectiveness(entries)
    assert report.total_entries == 15
    assert report.improved_count == 10
    assert report.improvement_rate == round(10 / 15, 4)


def test_classify_closure_effectiveness():
    assert classify_closure_effectiveness({"status": "ok"}) == "improved"
    assert classify_closure_effectiveness({"status": "failed_non_blocking"}) == "no_change"
    assert classify_closure_effectiveness({"status": "fail"}) == "degraded"
    assert classify_closure_effectiveness({"writeback_status": "ok"}) == "improved"
    assert classify_closure_effectiveness({}) == "no_change"


def test_generate_effectiveness_report(tmp_path: Path):
    entries = [
        {"status": "ok", "classification": "verifier_pass", "task_id": "t1"},
        {"status": "fail", "classification": "verifier_fail", "task_id": "t2"},
    ]
    out = tmp_path / "report.md"
    generate_effectiveness_report(entries, out)
    assert out.exists()
    content = out.read_text()
    assert "improved" in content.lower()
    assert "degraded" in content.lower()
