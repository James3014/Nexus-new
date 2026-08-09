from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import pytest

from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
from nexus.services.local_heal.learning_closure_bridge import (
    LearningClosureBridge,
    write_candidate_learning_closures,
    write_learning_closure,
)


def test_write_candidate_learning_closures_writes_all_models(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_LOCAL_HEAL_LEARNING_WRITEBACK", raising=False)
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "learning_closure.jsonl"
        bridge = LearningClosureBridge(path=path, enable_findings=False)

        c_judge = CandidateEnvelope(
            candidate_id="cand-judge",
            task_id="task-1",
            source="local",
            model="qwen-3b",
            role="judge",
            patch_protocol="none",
            target_file="app.py",
            target_symbol="run",
            source_anchor_hash="hash-1",
            candidate_patch_hash="hash-empty",
            evidence_refs=("ref-1",),
            candidate_patch="",
        )

        c_primary = CandidateEnvelope(
            candidate_id="cand-primary",
            task_id="task-1",
            source="local",
            model="qwen-7b",
            role="primary_proposer",
            patch_protocol="anchored_edit",
            target_file="app.py",
            target_symbol="run",
            source_anchor_hash="hash-1",
            candidate_patch_hash="hash-2",
            evidence_refs=("ref-1",),
            candidate_patch="print('hello')",
        )

        c_secondary = CandidateEnvelope(
            candidate_id="cand-secondary",
            task_id="task-1",
            source="local",
            model="ds-6.7b",
            role="secondary_proposer",
            patch_protocol="anchored_edit",
            target_file="app.py",
            target_symbol="run",
            source_anchor_hash="hash-1",
            candidate_patch_hash="hash-3",
            evidence_refs=("ref-1",),
            candidate_patch="print('world')",
        )

        ctx = {"task_id": "task-1", "instance_id": "task-1"}

        lessons = write_candidate_learning_closures(
            ctx=ctx,
            envelopes=[c_judge, c_primary, c_secondary],
            selected_id="cand-primary",
            selected_by="candidate_policy",
            verifier_result="pass",
            bridge=bridge,
        )

        assert len(lessons) == 3

        # Read back jsonl file
        with path.open("r", encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle]

        assert len(lines) == 3

        # 3B judge check
        judge_line = next(line for line in lines if line["model"] == "qwen-3b")
        assert judge_line["selected"] is False
        assert judge_line["selected_by"] == "none"
        assert judge_line["verifier_result"] == "not_run"
        assert judge_line["failure_class"] == "not_selected"

        # Primary proposer check
        primary_line = next(line for line in lines if line["model"] == "qwen-7b")
        assert primary_line["selected"] is True
        assert primary_line["selected_by"] == "candidate_policy"
        assert primary_line["verifier_result"] == "pass"
        assert primary_line["failure_class"] == "none"
        assert primary_line["future_weight_delta"] == 1.0


def _candidate(candidate_id: str = "candidate-1") -> CandidateEnvelope:
    return CandidateEnvelope(
        candidate_id=candidate_id,
        task_id="task-1",
        source="local",
        model="qwen-7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="app.py",
        target_symbol="run",
        source_anchor_hash="hash-1",
        candidate_patch_hash="hash-2",
        evidence_refs=("ref-1",),
        candidate_patch="print('hello')",
    )


def test_learning_writeback_is_default_on(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_LOCAL_HEAL_LEARNING_WRITEBACK", raising=False)
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "learning_closure.jsonl"
        bridge = LearningClosureBridge(path=path, enable_findings=False)

        lesson = bridge.write_lesson(SimpleNamespace(task_id="task-1", failure_reason="parser"))

        assert lesson["classification"] == "parser_fail"
        assert path.exists()


def test_learning_writeback_disabled_is_stable_and_does_not_write(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_LOCAL_HEAL_LEARNING_WRITEBACK", "off")
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "learning_closure.jsonl"
        bridge = LearningClosureBridge(path=path, enable_findings=False)
        ctx = SimpleNamespace(task_id="task-1", instance_id="task-1", failure_reason="parser")
        candidate = _candidate()

        lesson = bridge.write_lesson(ctx)
        envelope_lesson = bridge.write_envelope_lesson(ctx, candidate, True, "policy", "pass")
        candidate_lessons = write_candidate_learning_closures(
            ctx, [candidate], candidate.candidate_id, "policy", "pass", bridge
        )
        closure = write_learning_closure(ctx, bridge)

        expected = {
            "schema": "nexus.local_heal.learning_closure.v1",
            "writeback_status": "disabled",
            "writeback_disabled": True,
            "disabled_by": "NEXUS_LOCAL_HEAL_LEARNING_WRITEBACK",
            "training_export_allowed": False,
            "internal_only": True,
        }
        for evidence in [lesson, envelope_lesson, candidate_lessons[0], closure]:
            assert {key: evidence[key] for key in expected} == expected
        assert not path.exists()
        assert not hasattr(ctx, "outcome_memory_writeback")


def test_learning_episode_preserves_receipts_and_rejects_unattributed_applied(tmp_path):
    op = SimpleNamespace(
        instance_id="task-episode",
        attempt_id="attempt-1",
        action_id="action-1",
        idempotency_key="idem-episode",
        terminal_outcome="SUCCEEDED",
        solve_eligible=True,
        failure_reason="",
        receipt_path="receipt://verifier",
        retrieved_lesson_ids=["lesson-1"],
        applied_lesson_ids=["lesson-1"],
        capability_receipts=[{"name": "repair_loop", "selected": True, "invoked": True, "evidence_present": True}],
    )
    result = LearningClosureBridge(path=tmp_path / "closure.jsonl", project_root=tmp_path, enable_findings=False).write_lesson(SimpleNamespace(op=op))
    assert result["schema"] == "nexus.local_heal.learning_closure.v1"
    assert result["source_schema"] == "nexus.learning_episode.v1"
    assert result["capability_receipts"]
    assert result["retrieved_lesson_ids"] == ["lesson-1"]
    assert result["applied_lesson_ids"] == []
    assert result["idempotency_key"] == "idem-episode"


def test_learning_episode_write_is_idempotent(tmp_path):
    op = SimpleNamespace(
        instance_id="task-idem",
        attempt_id="attempt-1",
        action_id="action-1",
        idempotency_key="idem-fixed",
        terminal_outcome="FAILED",
        failure_reason="verifier failed",
        receipt_path="receipt://verifier",
        capability_receipts=[{"name": "repair_loop", "selected": True}],
    )
    bridge = LearningClosureBridge(path=tmp_path / "closure.jsonl", project_root=tmp_path, enable_findings=False)
    first = bridge.write_lesson(SimpleNamespace(op=op))
    second = bridge.write_lesson(SimpleNamespace(op=op))
    assert first["episode_id"] == second["episode_id"]
    ledger = tmp_path / ".nexus" / "memory" / "learning_episodes.jsonl"
    assert len(ledger.read_text().splitlines()) == 1


def test_candidate_projection_is_idempotent(tmp_path):
    op = SimpleNamespace(
        instance_id="task-candidate-idem",
        attempt_id="attempt-1",
        action_id="action-1",
        idempotency_key="candidate-idem",
    )
    bridge = LearningClosureBridge(
        path=tmp_path / "closure.jsonl", project_root=tmp_path, enable_findings=False
    )
    candidate = _candidate()
    first = bridge.write_envelope_lesson(op, candidate, True, "policy", "pass")
    second = bridge.write_envelope_lesson(op, candidate, True, "policy", "pass")
    assert first["episode_id"] == second["episode_id"]
    assert len((tmp_path / "closure.jsonl").read_text().splitlines()) == 1


def test_canonical_ledger_failure_is_explicit_and_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "nexus.learning.learning_closure_effectiveness.append_learning_episode",
        lambda path, episode: False,
    )
    op = SimpleNamespace(instance_id="task-ledger-fail", failure_reason="parser")
    result = LearningClosureBridge(path=tmp_path / "closure.jsonl", project_root=tmp_path, enable_findings=False).write_lesson(op)
    assert result["learning_write_succeeded"] is False
    assert result["learning_write_status"] == "canonical_ledger_write_failed"
    assert result["learning_blocker"] == "canonical_ledger_write_failed"


def test_learning_closure_does_not_project_outcome_memory_after_canonical_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "nexus.learning.learning_closure_effectiveness.append_learning_episode",
        lambda path, episode: False,
    )
    monkeypatch.setattr(
        "nexus.learning.outcome_memory.OutcomeMemoryManager.save_episode_and_tune_sync",
        lambda *args, **kwargs: pytest.fail("outcome memory must not outrun canonical ledger"),
    )
    op = SimpleNamespace(instance_id="task-ledger-fail", failure_reason="parser")
    bridge = LearningClosureBridge(
        path=tmp_path / "closure.jsonl", project_root=tmp_path, enable_findings=False
    )

    result = write_learning_closure(op, bridge)

    assert result["writeback_status"] == "failed_non_blocking"
    assert result["learning_write_succeeded"] is False
    assert result["outcome_memory_writeback"] == "skipped"
