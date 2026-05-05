from unittest.mock import MagicMock

from nexus.core.state_contracts import NexusState
from nexus.engine.pipeline import CANONICAL_STAGE_FLOW, PipelineContext, NexusPipeline


def _build_engine():
    engine = MagicMock()
    engine.phases = {}
    return engine


def test_pipeline_initializes_seven_stage_flow_metadata():
    pipeline = NexusPipeline(_build_engine())
    state = NexusState(task_id="t-1")
    pipeline._init_stage_status(state)
    assert state.metadata["stage_flow"] == CANONICAL_STAGE_FLOW
    assert state.metadata["stage_descriptions"]["S"] == "cold_start_seed"
    assert state.metadata["stage_status"]["S"] == "pending"
    assert state.metadata["stage_status"]["C"] == "pending"


def test_pipeline_mark_stage_updates_status():
    pipeline = NexusPipeline(_build_engine())
    state = NexusState(task_id="t-2")
    pipeline._init_stage_status(state)
    pipeline._mark_stage(state, "S", "success")
    pipeline._mark_stage(state, "P", "skipped_direct_mode")
    assert state.metadata["stage_status"]["S"] == "success"
    assert state.metadata["stage_status"]["P"] == "skipped_direct_mode"


def test_pipeline_context_appends_immutable_decision_journal_event():
    state = NexusState(task_id="t-3")
    ctx = PipelineContext(
        state=state,
        task_desc="task",
        task_type="test",
        task_id="t-3",
        kwargs={},
        dry_run=True,
        hub=None,
        accumulator=None,
        health_evaluator=None,
        research_policy=None,
    )

    event = ctx.append_journal(origin_phase="S", event_type="cold_start_loaded", payload={"docs": 2})

    assert ctx.decision_journal == [event]
    assert event["origin_phase"] == "S"
    assert event["event_type"] == "cold_start_loaded"
    assert event["payload"] == {"docs": 2}
    assert "timestamp" in event
