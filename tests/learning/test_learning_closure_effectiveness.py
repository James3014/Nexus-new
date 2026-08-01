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


def test_learning_closure_tracks_retrieved_applied_lessons_and_terminal_disposition(tmp_path: Path):
    from types import SimpleNamespace
    from nexus.services.local_heal.learning_closure_bridge import LearningClosureBridge

    op = SimpleNamespace(
        instance_id="task-1",
        attempt_id="attempt-1",
        action_id="action-1",
        idempotency_key="idem-1",
        solve_eligible=True,
        failure_reason="",
        final_patch="diff --git a/x b/x",
        receipt_path="receipt://1",
        retrieved_lesson_ids=["lesson-old"],
        applied_lesson_ids=["lesson-old"],
        terminal_outcome="SUCCEEDED",
        uncertain_mutation=False,
    )
    ctx = SimpleNamespace(op=op)
    result = LearningClosureBridge(path=tmp_path / "closure.jsonl", project_root=tmp_path, enable_findings=False).write_lesson(ctx)
    assert result["attempt_id"] == "attempt-1"
    assert result["retrieved_lesson_ids"] == ["lesson-old"]
    assert result["applied_lesson_ids"] == ["lesson-old"]
    assert result["lesson_disposition"] == "reinforce"
    assert result["auto_replay_allowed"] is False
    assert result["qualification_evidence_present"] is True


def test_failed_without_terminal_decision_is_parked(tmp_path: Path):
    from types import SimpleNamespace
    from nexus.services.local_heal.learning_closure_bridge import LearningClosureBridge

    op = SimpleNamespace(instance_id="task-park", failure_reason="provider failed", final_patch="")
    result = LearningClosureBridge(path=tmp_path / "closure.jsonl", project_root=tmp_path, enable_findings=False).write_lesson(
        SimpleNamespace(op=op)
    )
    assert result["terminal_outcome"] == "PARKED"
    assert result["qualification_status"] == "UNQUALIFIED"
    assert result["auto_replay_allowed"] is False
    assert result["qualification_evidence_present"] is False


def test_terminal_outcomes_can_contradict_or_retire_applied_lessons(tmp_path: Path):
    from types import SimpleNamespace
    from nexus.services.local_heal.learning_closure_bridge import LearningClosureBridge

    bridge = LearningClosureBridge(path=tmp_path / "closure.jsonl", project_root=tmp_path, enable_findings=False)
    for terminal, expected in (("FAILED", "contradict"), ("RETIRED", "retire")):
        op = SimpleNamespace(
            instance_id=f"task-{terminal.lower()}",
            failure_reason="" if terminal == "RETIRED" else "verifier failed",
            final_patch="diff --git a/x b/x",
            terminal_outcome=terminal,
            applied_lesson_ids=["lesson-1"],
        )
        result = bridge.write_lesson(SimpleNamespace(op=op))
        assert result["lesson_disposition"] == expected
