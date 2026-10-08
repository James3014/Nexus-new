"""#1632: canonical lesson retrieval and authoritative applied-lesson attribution."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from nexus_learning.lessons import LessonStore, build_lesson
from nexus_learning.state_root import LearningStateRoot

from nexus.services.local_heal.learning_closure_bridge import (
    LearningClosureBridge,
    write_learning_closure,
)
from nexus.services.local_heal.memory_retrieval_adapter import (
    CanonicalLessonStore,
    MemoryRetrievalAdapter,
    NexusCompositeLessonStore,
)
from nexus.services.local_heal.memory_trace import MemoryTrace
from nexus.services.local_heal.orchestrator import HealOrchestrator


def _write(root: Path, origin: str, title: str) -> str:
    lesson = build_lesson(
        title=title,
        lesson_body="Guard the empty sequence before indexing the first element.",
        source_episode_ids=["ep-1"],
        outcome_polarity="success",
        applies_when=["indexing empty list"],
        avoid_when=["list is validated upstream"],
        source_task_ids=["task-a"],
        evidence_refs=["receipt://r1"],
        evidence_origin=origin,
    )
    LessonStore(LearningStateRoot.from_project_root(root)).append(lesson)
    return lesson["lesson_id"]


def _orch() -> HealOrchestrator:
    return object.__new__(HealOrchestrator)


def _op(lesson_id: str, **over):
    base = dict(
        instance_id="task-1",
        attempt_id="a1",
        action_id="act1",
        idempotency_key="idem-1",
        terminal_outcome="SUCCEEDED",
        solve_eligible=True,
        failure_reason="",
        receipt_path="receipt://verifier",
        memory_enabled=True,
        retrieved_lesson_ids=[lesson_id],
        applied_patch_hash="abc123",
        selected_candidate_hash_matches_applied=True,
        verifier_receipt={"verifier_status": "pass", "receipt_id": "r1"},
        _memory_influence_trace=MemoryTrace(
            available=True,
            selected_ids=[lesson_id],
            memory_evidence_ids=[lesson_id],
            prompt_included=True,
        ),
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_canonical_store_returns_physical_excludes_simulated(tmp_path):
    phys = _write(tmp_path, "physical", "Empty list indexing guard")
    sim = _write(tmp_path, "simulated", "Empty list indexing simulated guard")
    rows = CanonicalLessonStore(project_root=tmp_path).query(
        query_text="empty list indexing", limit=3
    )
    ids = [r["lesson_id"] for r in rows]
    assert ids == [phys]
    assert sim not in ids
    assert rows[0]["title"] and rows[0]["applies_when"] and rows[0]["avoid_when"]


def test_canonical_store_fail_open_and_missing_ledger(tmp_path):
    store = CanonicalLessonStore(project_root=tmp_path)
    assert store.query(query_text="anything", limit=3) == []
    assert store.last_error == ""


def test_composite_default_includes_canonical_store():
    stores = NexusCompositeLessonStore().stores
    assert isinstance(stores[-1], CanonicalLessonStore)


def test_adapter_turns_canonical_rows_into_lessons(tmp_path):
    lid = _write(tmp_path, "physical", "Empty list indexing guard")
    adapter = MemoryRetrievalAdapter(store=CanonicalLessonStore(project_root=tmp_path))
    lessons = adapter.retrieve(query_text="empty list indexing", limit=3)
    assert [l.finding_id for l in lessons] == [lid]
    assert lessons[0].provenance
    assert lessons[0].pattern_type == "success"


def test_adoption_sets_applied_and_closure_reinforces(tmp_path, monkeypatch):
    lid = _write(tmp_path, "physical", "Empty list indexing guard")
    op = _op(lid)
    ctx = SimpleNamespace(op=op)
    _orch()._record_authoritative_memory_adoption(ctx)
    assert op.applied_lesson_ids == [lid]

    import nexus.learning.outcome_memory as om

    monkeypatch.setattr(om.OutcomeMemoryManager, "save_episode_and_tune_sync", lambda *a, **k: None)
    bridge = LearningClosureBridge(
        path=tmp_path / "c.jsonl", project_root=tmp_path, enable_findings=False
    )
    row = bridge.write_lesson(ctx)
    assert row["applied_lesson_ids"] == [lid]
    assert row["lesson_disposition"] == "reinforce"
    result = write_learning_closure(ctx, bridge)
    assert result["lesson"]["applied_lesson_ids"] == [lid]
    assert result["lesson"]["lesson_disposition"] == "reinforce"


@pytest.mark.parametrize(
    "over",
    [
        {"verifier_receipt": {"verifier_status": "fail", "receipt_id": "r1"}},
        {"selected_candidate_hash_matches_applied": False},
        {"applied_patch_hash": ""},
    ],
)
def test_not_applied_when_authority_missing(over):
    op = _op("L1", **over)
    _orch()._record_authoritative_memory_adoption(SimpleNamespace(op=op))
    assert op.applied_lesson_ids == []
    assert op.applied_lesson_attribution == {}


def test_not_applied_when_prompt_not_included():
    op = _op(
        "L1",
        _memory_influence_trace=MemoryTrace(
            available=True, selected_ids=["L1"], prompt_included=False
        ),
    )
    _orch()._record_authoritative_memory_adoption(SimpleNamespace(op=op))
    assert op.applied_lesson_ids == []


def test_memory_off_leaves_retrieved_and_applied_empty():
    op = SimpleNamespace(
        instance_id="t",
        memory_enabled=False,
        final_patch="",
        problem_statement="p",
        repo_dir=Path("."),
        retrieved_lesson_ids=[],
    )
    orch = _orch()
    orch._attach_memory_influence_trace(SimpleNamespace(op=op))
    orch._record_authoritative_memory_adoption(SimpleNamespace(op=op))
    assert op.applied_lesson_ids == []
    from nexus.services.local_heal.learning_closure_bridge import _lineage

    lin = _lineage(op)
    assert lin["retrieved_lesson_ids"] == [] and lin["applied_lesson_ids"] == []


def test_success_path_hook_populates_inputs_and_enables_adoption():
    patch = "--- a/f.py\n+++ b/f.py\n@@\n-x\n+y\n"
    op = SimpleNamespace(
        instance_id="task-1",
        attempt=1,
        final_patch=patch,
        solve_eligible=True,
        evaluation_report="ok",
        retrieved_lesson_ids=["L1"],
        _memory_influence_trace=MemoryTrace(
            available=True, selected_ids=["L1"], prompt_included=True
        ),
    )
    ctx = SimpleNamespace(op=op, gov=SimpleNamespace(gate_exit="verification"))
    orch = _orch()
    orch._bind_applied_attribution_inputs(ctx)
    assert op.applied_patch_hash == hashlib.sha256(patch.encode()).hexdigest()
    assert op.selected_candidate_hash_matches_applied is True
    assert op.verifier_receipt["verifier_status"] == "pass"
    assert op.verifier_receipt["receipt_id"]
    orch._record_authoritative_memory_adoption(ctx)
    assert op.applied_lesson_ids == ["L1"]


def test_success_path_hook_fail_closed_without_verifier_pass():
    op = SimpleNamespace(
        instance_id="t",
        attempt=1,
        final_patch="diff",
        solve_eligible=True,
        retrieved_lesson_ids=["L1"],
        _memory_influence_trace=MemoryTrace(
            available=True, selected_ids=["L1"], prompt_included=True
        ),
    )
    ctx = SimpleNamespace(op=op, gov=SimpleNamespace(gate_exit=""))
    orch = _orch()
    orch._bind_applied_attribution_inputs(ctx)
    assert getattr(op, "verifier_receipt", None) is None
    orch._record_authoritative_memory_adoption(ctx)
    assert op.applied_lesson_ids == []


def _verifier_fail_op(**over):
    base = dict(
        instance_id="task-1",
        attempt=2,
        final_patch="--- a/f.py\n+++ b/f.py\n@@\n-x\n+y\n",
        solve_eligible=False,
        evaluation_report="",
        failure_reason="verifier rejected patch",
        last_failure_class="VERIFIER_FAIL",
        verifier_failure_kind="test_failed",
        verifier_exit_code=1,
        retrieved_lesson_ids=["L1"],
        _memory_influence_trace=MemoryTrace(
            available=True, selected_ids=["L1"], prompt_included=True
        ),
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_verifier_fail_with_patch_binds_fail_receipt_without_applied():
    op = _verifier_fail_op()
    ctx = SimpleNamespace(op=op, gov=SimpleNamespace(gate_exit="verification"))
    orch = _orch()
    orch._bind_applied_attribution_inputs(ctx)
    receipt = op.verifier_receipt
    assert receipt["verifier_status"] == "fail"
    assert receipt["receipt_id"].startswith("verifier:task-1:attempt2:")
    assert receipt["failure_kind"] == "test_failed"
    assert receipt["exit_code"] == 1
    assert op.applied_patch_hash == hashlib.sha256(op.final_patch.encode()).hexdigest()
    orch._record_authoritative_memory_adoption(ctx)
    assert op.applied_lesson_ids == []


def test_verifier_fail_without_patch_still_binds_fail_receipt():
    op = _verifier_fail_op(final_patch="")
    ctx = SimpleNamespace(op=op, gov=SimpleNamespace(gate_exit="verification"))
    _orch()._bind_applied_attribution_inputs(ctx)
    assert op.verifier_receipt["verifier_status"] == "fail"
    assert op.verifier_receipt["receipt_id"].startswith("verifier:task-1:attempt2:")
    assert not getattr(op, "applied_patch_hash", "")
    _orch()._record_authoritative_memory_adoption(ctx)
    assert op.applied_lesson_ids == []


def test_no_fail_receipt_outside_verification_gate():
    op = _verifier_fail_op()
    ctx = SimpleNamespace(op=op, gov=SimpleNamespace(gate_exit="patch_synthesis"))
    _orch()._bind_applied_attribution_inputs(ctx)
    assert getattr(op, "verifier_receipt", None) is None


def test_existing_pass_receipt_not_overwritten_by_fail_path():
    pass_receipt = {"verifier_status": "pass", "receipt_id": "verifier:keep"}
    op = _verifier_fail_op(verifier_receipt=pass_receipt)
    ctx = SimpleNamespace(op=op, gov=SimpleNamespace(gate_exit="verification"))
    _orch()._bind_applied_attribution_inputs(ctx)
    assert op.verifier_receipt is pass_receipt
