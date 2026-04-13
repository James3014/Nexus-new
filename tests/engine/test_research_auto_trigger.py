import pytest
import dataclasses
from unittest.mock import MagicMock, patch
from nexus.engine.pipeline_stages import PipelineStagesMixin
from nexus.core.state_contracts import NexusState
from nexus.engine.policies.research_policy import ResearchDecision

class MockPipeline(PipelineStagesMixin):
    def __init__(self):
        self.engine = MagicMock()
        self.engine.project_root = "/tmp"
        self.engine.run_dir = MagicMock()
        self.engine._add_step_to_history = MagicMock()

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
    ctx.research_policy = MagicMock()
    ctx.kwargs = {}
    ctx.bayesian_params = {"nas_aggression": 0.5}
    ctx.prediction = None
    ctx.dry_run = False
    return ctx

@pytest.fixture
def mock_tracer():
    tracer = MagicMock()
    tracer.phase_span.return_value.__enter__.return_value = MagicMock()
    return tracer

@patch("nexus.engine.pipeline_stages.KnowledgeIndex")
def test_p_stage_precomputes_research_route(mock_ki_cls, mock_ctx, mock_tracer):
    """測試 P 階段結束時會預計算 research_route"""
    mock_ki = mock_ki_cls.return_value
    mock_ki.search_similar.return_value = []
    
    mock_ctx.prediction = {"candidate_count": 2, "root_cause_confidence": 0.5}
    mock_ctx.planner.run.return_value = mock_ctx.prediction
    
    # 模擬研究決策：需要研究
    res_decision = ResearchDecision(should_research=True, mode="external", reason="low_confidence", rounds=5, stable_wins=3)
    mock_ctx.research_policy.route.return_value = res_decision
    
    pipeline = MockPipeline()
    pipeline._stage_plan(mock_ctx, mock_tracer)
    
    # 驗證 metadata 中已存入 research_route
    assert "research_route" in mock_ctx.state.metadata
    assert mock_ctx.state.metadata["research_route"]["should_research"] is True
    assert mock_ctx.state.metadata["research_route"]["reason"] == "low_confidence"
    assert mock_ctx.research_policy.route.called

@patch("nexus.engine.pipeline_stages.KnowledgeIndex")
def test_x_stage_reuses_precomputed_route(mock_ki_cls, mock_ctx, mock_tracer):
    """測試 X 階段會重用預計算的 research_route"""
    # 預先存入研究決策
    res_dict = {"should_research": True, "mode": "external", "reason": "precomputed_reason", "rounds": 5, "stable_wins": 3}
    mock_ctx.state.metadata["research_route"] = res_dict
    
    mock_ctx.researcher = MagicMock()
    mock_ctx.researcher.run.return_value = {"status": "SUCCESS"}
    
    pipeline = MockPipeline()
    pipeline._stage_research(mock_ctx, mock_tracer)
    
    # 驗證並未再次呼叫 research_policy.route
    assert not mock_ctx.research_policy.route.called
    assert mock_ctx.researcher.run.called

@patch("nexus.engine.pipeline_stages.KnowledgeIndex")
def test_x_stage_skips_when_route_says_false(mock_ki_cls, mock_ctx, mock_tracer):
    """測試當路由說不需要研究且未強制時，X 階段不會執行研究器"""
    # 預先存入研究決策：不需要研究
    res_dict = {"should_research": False, "mode": "skip", "reason": "clear_root_cause", "rounds": 0, "stable_wins": 0}
    mock_ctx.state.metadata["research_route"] = res_dict
    
    mock_ctx.researcher = MagicMock()
    
    pipeline = MockPipeline()
    pipeline._stage_research(mock_ctx, mock_tracer)
    
    # 驗證並未執行研究器
    assert not mock_ctx.researcher.run.called
