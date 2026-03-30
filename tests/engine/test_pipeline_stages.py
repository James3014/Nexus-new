import pytest
import dataclasses
from unittest.mock import MagicMock, patch
from nexus.engine.pipeline_stages import PipelineStagesMixin
from nexus.core.state_contracts import NexusState

class MockPipeline(PipelineStagesMixin):
    def __init__(self):
        self.engine = MagicMock()
        self.engine.project_root = "/tmp"
        self.engine.run_dir = MagicMock()

@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.task_id = "test-task"
    ctx.task_desc = "test description"
    ctx.task_type = "bug"
    ctx.decision_counter = 0
    ctx.state = NexusState(task_id="test-task")
    ctx.event_store = MagicMock()
    ctx.hub = MagicMock()
    ctx.planner = MagicMock()
    ctx.accumulator = MagicMock()
    ctx.kwargs = {}
    ctx.prediction = None
    ctx.dry_run = False
    ctx.pack = {}
    return ctx

@pytest.fixture
def mock_tracer():
    tracer = MagicMock()
    tracer.phase_span.return_value.__enter__.return_value = MagicMock()
    return tracer

def test_register_phase_decision(mock_ctx):
    pipeline = MockPipeline()
    decision_id = pipeline._register_phase_decision(mock_ctx, "P", "planner")
    
    assert decision_id.startswith("dec_p_test-task_")
    assert mock_ctx.decision_counter == 1
    assert mock_ctx.event_store.append.called
    assert mock_ctx.state.metadata["phase_decisions"]["P"] == decision_id

@patch("nexus.engine.pipeline_stages.KnowledgeIndex")
def test_stage_plan(mock_ki_cls, mock_ctx, mock_tracer):
    mock_ki = mock_ki_cls.return_value
    mock_ki.search_similar.return_value = []
    
    pipeline = MockPipeline()
    pipeline._stage_plan(mock_ctx, mock_tracer)
    
    assert mock_ctx.state.current_phase == "P"
    assert mock_ctx.planner.run.called
    assert mock_ctx.accumulator.record.called
    assert pipeline.engine._add_step_to_history.called

@patch("nexus.engine.pipeline_stages.KnowledgeIndex")
def test_stage_research_standard(mock_ki_cls, mock_ctx, mock_tracer):
    mock_ctx.research_policy = MagicMock()
    res_decision = MagicMock()
    res_decision.should_research = True
    res_decision.mode = "standard"
    mock_ctx.research_policy.route.return_value = res_decision
    
    mock_ctx.researcher = MagicMock()
    mock_ctx.researcher.run.return_value = {"status": "SUCCESS", "findings": ["found something"]}
    
    pipeline = MockPipeline()
    pipeline._stage_research(mock_ctx, mock_tracer)
    
    assert mock_ctx.state.current_phase == "X"
    assert mock_ctx.state.metadata["research_route"] is not None
    assert mock_ctx.researcher.run.called

def test_stage_diagnose(mock_ctx, mock_tracer):
    mock_ctx.prediction = {"plan": "do something"}
    mock_ctx.research_pack = {"data": "..."}
    
    mock_ctx.hub.assemble_diag_pack.return_value = {}
    mock_ctx.hub.assemble_feature_pack.return_value = {}
    
    pipeline = MockPipeline()
    pipeline._stage_diagnose(mock_ctx, mock_tracer)
    
    assert mock_ctx.state.current_phase == "D"
    assert mock_ctx.pack["research_pack"] == mock_ctx.research_pack
    assert pipeline.engine._add_step_to_history.called
