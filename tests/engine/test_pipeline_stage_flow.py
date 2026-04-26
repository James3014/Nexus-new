from unittest.mock import MagicMock

from nexus.core.state_contracts import NexusState
from nexus.engine.pipeline import NexusPipeline


def _build_engine():
    engine = MagicMock()
    engine.phases = {}
    return engine


def test_pipeline_initializes_seven_stage_flow_metadata():
    pipeline = NexusPipeline(_build_engine())
    state = NexusState(task_id="t-1")
    pipeline._init_stage_status(state)
    assert state.metadata["stage_flow"] == ["S", "P", "X", "D", "R", "A", "C"]
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
