from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nexus.contracts.learning_experience import (
    build_runtime_learning_closure,
    validate_runtime_learning_closure,
)
from nexus.contracts.local_memory_hub import build_memory_learning_lineage
from nexus.core.state_contracts import NexusState
from nexus.engine.pipeline_crystal import PipelineCrystalMixin


def test_learning_closure_keeps_uncertain_mutation_non_replayable():
    episode = build_runtime_learning_closure(
        task_id="t-1",
        attempt_id="a-1",
        action_id="x-1",
        phase_receipts=[{"phase": "R", "status": "FAILED"}],
        outcome="FAILED",
        terminal_evidence={"receipt": "r-1"},
        uncertain_mutation=True,
        lesson_disposition="shadow",
    )
    assert episode["auto_replay_allowed"] is False
    assert episode["primary_task_success"] is False


def test_failed_attempt_cannot_graduate_as_stable_lesson():
    with pytest.raises(ValueError, match="FAILED_ATTEMPT_CANNOT_GRADUATE"):
        build_runtime_learning_closure(
            task_id="t-1",
            attempt_id="a-1",
            action_id="x-1",
            phase_receipts=[{"phase": "A", "status": "FAILED"}],
            outcome="FAILED",
            terminal_evidence={"receipt": "r-1"},
            lesson_disposition="graduated",
            qualification={
                "repeatability": True,
                "prevention_rule": "rule",
                "authority_qualification": True,
            },
        )


def test_learning_write_failure_blocks_primary_success_claim():
    episode = build_runtime_learning_closure(
        task_id="t-1",
        attempt_id="a-1",
        action_id="x-1",
        phase_receipts=[{"phase": "C", "status": "SUCCESS"}],
        outcome="SUCCESS",
        terminal_evidence={"receipt": "r-1"},
        primary_task_success=True,
        learning_write_succeeded=False,
    )
    assert episode["primary_task_success"] is False
    assert episode["learning_blocker"] == "LEARNING_WRITE_FAILED"
    validate_runtime_learning_closure(episode)


def test_runtime_learning_closure_rejects_unretrieved_applied_lessons():
    episode = build_runtime_learning_closure(
        task_id="t-1",
        attempt_id="a-1",
        action_id="x-1",
        phase_receipts=[],
        outcome="SUCCESS",
        terminal_evidence={"receipt": "r-1"},
        retrieved_lesson_ids=["known"],
        applied_lesson_ids=["known", "forged"],
    )
    assert episode["applied_lesson_ids"] == ["known"]


def test_memory_lineage_preserves_existing_writer_boundaries():
    lineage = build_memory_learning_lineage(
        task_id="t-1",
        attempt_id="a-1",
        action_id="x-1",
        retrieved_lesson_ids=["lesson-2", "lesson-1"],
        applied_lesson_ids=["lesson-1"],
    )
    assert lineage["retrieved_lesson_ids"] == ["lesson-1", "lesson-2"]
    assert lineage["auto_replay_allowed"] is False
    with pytest.raises(ValueError, match="OVERWRITE_FORBIDDEN"):
        build_memory_learning_lineage(
            task_id="t-1", attempt_id="a-1", action_id="x-1", stable_knowledge_overwrite=True
        )


def test_crystallize_stage_persists_runtime_learning_closure(monkeypatch):
    class Pipeline(PipelineCrystalMixin):
        def __init__(self):
            self.engine = SimpleNamespace(
                project_root="/tmp",
                state_io=MagicMock(),
                commander=MagicMock(),
            )

    pipeline = Pipeline()
    ctx = SimpleNamespace(
        task_id="t-1",
        state=NexusState(task_id="t-1"),
        bayesian_params={},
    )
    ctx.state.metadata["phase_receipts"] = [{"phase": "C", "status": "SUCCESS"}]
    pipeline._collect_crystal_signals = lambda *_args: {"raw_terminal_state": "SUCCESS"}
    pipeline._handle_crystallize_success = lambda *_args: None
    monkeypatch.setattr("nexus.engine.pipeline_crystal.finalize_learning_loop", lambda *_args, **_kwargs: {"status": "PASS"})

    pipeline._stage_crystallize(ctx, True, MagicMock())

    closure = ctx.state.metadata["learning_closure"]
    assert closure["schema"] == "nexus.runtime_learning_closure.v1"
    assert closure["memory_lineage"]["auto_replay_allowed"] is False


def test_crystallize_stage_blocks_success_when_canonical_episode_write_fails(monkeypatch):
    class Pipeline(PipelineCrystalMixin):
        def __init__(self):
            self.engine = SimpleNamespace(
                project_root="/tmp",
                state_io=MagicMock(),
                commander=MagicMock(),
            )

    pipeline = Pipeline()
    ctx = SimpleNamespace(
        task_id="t-write-fail",
        state=NexusState(task_id="t-write-fail"),
        bayesian_params={},
    )
    pipeline._collect_crystal_signals = lambda *_args: {"raw_terminal_state": "SUCCESS"}
    pipeline._handle_crystallize_success = lambda *_args: None
    monkeypatch.setattr(
        "nexus.engine.pipeline_crystal.finalize_learning_loop",
        lambda *_args, **_kwargs: {"learning_episode_write_succeeded": False},
    )

    pipeline._stage_crystallize(ctx, True, MagicMock())

    closure = ctx.state.metadata["learning_closure"]
    assert closure["learning_write_succeeded"] is False
    assert closure["primary_task_success"] is False
    assert ctx.state.metadata["learning_closure_failed"] is True
