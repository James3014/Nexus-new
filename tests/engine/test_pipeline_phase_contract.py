from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nexus.core.state_contracts import NexusState
from nexus.engine.pipeline import CANONICAL_STAGE_FLOW, PipelineContext, NexusPipeline
from nexus.engine.runtime_phase_contract import RuntimeTransitionError


def _context() -> PipelineContext:
    state = NexusState(task_id="phase-contract")
    state.metadata["runtime_phase"] = "S"
    return PipelineContext(
        state=state,
        task_desc="phase contract",
        task_type="test",
        task_id="phase-contract",
        kwargs={},
        dry_run=True,
        hub=None,
        accumulator=None,
        health_evaluator=None,
        research_policy=None,
    )


def test_pipeline_stage_identity_comes_from_runtime_contract():
    assert CANONICAL_STAGE_FLOW == ["S", "P", "D", "X", "R", "A", "C"]


def test_pipeline_records_the_approved_runtime_transition_path():
    pipeline = NexusPipeline(SimpleNamespace(phases={}, phase_executors={}))
    ctx = _context()

    for phase in ("P", "D", "X", "D", "R", "A"):
        pipeline._advance_runtime_phase(ctx, phase)
    pipeline._advance_runtime_phase(ctx, "C", audit_passed=True)

    assert ctx.state.metadata["runtime_phase"] == "C"
    assert [(item["from"], item["to"]) for item in ctx.state.metadata["runtime_phase_transitions"]] == [
        ("S", "P"),
        ("P", "D"),
        ("D", "X"),
        ("X", "D"),
        ("D", "R"),
        ("R", "A"),
        ("A", "C"),
    ]


def test_illegal_transition_is_rejected_before_executor_entry():
    pipeline = NexusPipeline(SimpleNamespace(phases={}, phase_executors={}))
    ctx = _context()
    pipeline._advance_runtime_phase(ctx, "P")
    executor = MagicMock()

    with pytest.raises(RuntimeTransitionError, match="illegal_runtime_transition"):
        pipeline._advance_runtime_phase(ctx, "X")

    executor.assert_not_called()


def test_audit_rejection_can_return_to_repair_or_diagnose():
    pipeline = NexusPipeline(SimpleNamespace(phases={}, phase_executors={}))
    for target in ("R", "D"):
        ctx = _context()
        for phase in ("P", "D", "R", "A"):
            pipeline._advance_runtime_phase(ctx, phase)
        pipeline._advance_runtime_phase(ctx, target, reason="audit_rejection")
        assert ctx.state.metadata["runtime_phase"] == target


def test_formulation_order_places_diagnose_before_optional_research_resume():
    ctx = _context()
    research = SimpleNamespace(should_run=lambda _ctx: True)
    assert NexusPipeline._formulation_phase_order({"X": research}, ctx) == ["P", "D", "X"]
    assert NexusPipeline._formulation_phase_order({}, ctx) == ["P", "D"]
