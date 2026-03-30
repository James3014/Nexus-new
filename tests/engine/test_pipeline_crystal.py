import pytest
import os
from unittest.mock import MagicMock, patch
from nexus.engine.pipeline_crystal import PipelineCrystalMixin
from nexus.core.state_contracts import NexusState
from nexus.engine.pipeline_outcome import PipelineTerminalState

class MockPipeline(PipelineCrystalMixin):
    def __init__(self):
        self.engine = MagicMock()
        self.engine.project_root = MagicMock()
        self.engine.run_dir = MagicMock()
        self.engine.state_io = MagicMock()
        self.engine.commander = MagicMock()

    def _register_phase_decision(self, ctx, phase, skill_id):
        return f"dec_{phase.lower()}_mock"

@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.task_id = "test-task"
    ctx.state = NexusState(task_id="test-task")
    ctx.state.metadata = {"trace_id": "tr-123", "span_id": "sp-123"}
    ctx.dry_run = False
    return ctx

@pytest.fixture
def mock_tracer():
    tracer = MagicMock()
    tracer.phase_span.return_value.__enter__.return_value = MagicMock()
    return tracer

def test_collect_crystal_signals_success(mock_ctx, mock_tracer):
    pipeline = MockPipeline()
    pipeline.engine.project_root = "/tmp"
    
    with patch("subprocess.check_output") as mock_git:
        mock_git.return_value = b"sha123\n"
        with patch("nexus.engine.pipeline_crystal.analyze_cycle") as mock_analyze:
            mock_analyze.return_value = {"root_cause": "none"}
            
            signals = pipeline._collect_crystal_signals(mock_ctx, True, mock_tracer)
            
            assert signals["raw_terminal_state"] == "SUCCESS"
            assert mock_ctx.state.metadata["pipeline_terminal_state"] == "SUCCESS"
            assert mock_ctx.state.metadata["nexus_outcome_v2"]["terminal_state"] == "SUCCESS"

def test_stage_crystallize_saves_state(mock_ctx, mock_tracer):
    pipeline = MockPipeline()
    pipeline._collect_crystal_signals = MagicMock(return_value={"raw_terminal_state": "SUCCESS"})
    pipeline._handle_crystallize_success = MagicMock()
    
    pipeline._stage_crystallize(mock_ctx, True, mock_tracer)
    
    assert pipeline.engine.state_io.save_global_state.called
    assert pipeline.engine.commander.next_step.called

@patch("nexus.engine.pipeline_crystal.SkillStore")
@patch("nexus.engine.pipeline_crystal.build_skill_artifact")
@patch("nexus.engine.pipeline_crystal.append_skill_outcome_event")
@patch("nexus.engine.pipeline_crystal.build_outcome_event")
@patch("nexus.engine.pipeline_crystal.SkillExchange")
@patch("nexus.engine.pipeline_crystal.SkillRegistry")
def test_handle_crystallize_success(mock_reg, mock_exch, mock_event, mock_append, mock_build, mock_store_cls, mock_ctx):
    pipeline = MockPipeline()
    mock_store = mock_store_cls.return_value
    mock_build.return_value = "skill content"
    
    pipeline._handle_crystallize_success(mock_ctx, {"raw_terminal_state": "SUCCESS"})
    
    assert mock_append.called
    assert mock_build.called
    assert mock_store.save_skill.called

@patch("nexus.engine.pipeline_crystal.build_outcome_event")
@patch("nexus.engine.pipeline_crystal.append_skill_outcome_event")
def test_handle_crystallize_failure(mock_append, mock_event_fn, mock_ctx):
    pipeline = MockPipeline()
    mock_event = MagicMock()
    mock_event.payload.passed = False
    mock_event_fn.return_value = mock_event
    
    pipeline._handle_crystallize_failure(mock_ctx)
    
    assert mock_append.called
    args, _ = mock_append.call_args
    event = args[1]
    assert event.payload.passed is False
