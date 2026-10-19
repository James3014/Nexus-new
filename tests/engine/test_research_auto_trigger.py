import pytest
import dataclasses
from unittest.mock import MagicMock, patch
from nexus.engine.pipeline_stages import PipelineStagesMixin
from nexus.core.state_contracts import NexusState
from nexus.engine.policies.research_policy import ResearchDecision

class MockPipeline(PipelineStagesMixin):
    # Set per test by _isolate_run_dir; a MagicMock run_dir is path-like and
    # made stages write "MagicMock/mock.run_dir/..." into the current directory.
    default_run_dir = None

    def __init__(self):
        self.engine = MagicMock()
        self.engine.project_root = "/tmp"
        self.engine.run_dir = MockPipeline.default_run_dir
        self.engine._add_step_to_history = MagicMock()

@pytest.fixture(autouse=True)
def _isolate_run_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(MockPipeline, "default_run_dir", tmp_path)


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


def _write_slo_summary(root, *, phase_slo_pass, required_done_ratio):
    import json
    path = root / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "SUCCESS",
                "phase_slo_pass": phase_slo_pass,
                "global": {"required_done_ratio": required_done_ratio},
            }
        ),
        encoding="utf-8",
    )


@patch("nexus.engine.pipeline_stages.KnowledgeIndex")
def test_p_stage_missing_slo_summary_closes_research_route_2702(
    mock_ki_cls, mock_ctx, mock_tracer, tmp_path, monkeypatch
):
    """#2702: no phase_slo_summary.json is not ready (as in nightshift), so X is skipped."""
    monkeypatch.delenv("NEXUS_STATE_ROOT", raising=False)
    mock_ki_cls.return_value.search_similar.return_value = []
    mock_ctx.prediction = {"candidate_count": 2, "root_cause_confidence": 0.5}
    mock_ctx.planner.run.return_value = mock_ctx.prediction
    mock_ctx.research_policy.route.return_value = ResearchDecision(
        should_research=True, mode="external", reason="low_confidence", rounds=5, stable_wins=3
    )
    pipeline = MockPipeline()
    pipeline.engine.project_root = str(tmp_path)

    guard = pipeline._load_learn_phase_slo_guard(mock_ctx)
    assert guard["ready"] is False and guard["active"] is True
    assert guard["phase_slo_pass"] is False
    assert guard["reason"] == "phase_slo_summary_missing"

    pipeline._stage_plan(mock_ctx, mock_tracer)
    route = mock_ctx.state.metadata["research_route"]
    assert route["should_research"] is False
    assert route["reason"] == "learn_phase_slo_not_ready"

@patch("nexus.engine.pipeline_stages.KnowledgeIndex")
def test_p_stage_precomputes_research_route(mock_ki_cls, mock_ctx, mock_tracer, tmp_path):
    """測試 P 階段結束時會預計算 research_route"""
    mock_ki = mock_ki_cls.return_value
    mock_ki.search_similar.return_value = []
    
    mock_ctx.prediction = {"candidate_count": 2, "root_cause_confidence": 0.5}
    mock_ctx.planner.run.return_value = mock_ctx.prediction
    
    # 模擬研究決策：需要研究
    res_decision = ResearchDecision(should_research=True, mode="external", reason="low_confidence", rounds=5, stable_wins=3)
    mock_ctx.research_policy.route.return_value = res_decision
    
    pipeline = MockPipeline()
    # #2702: a missing summary now closes X, so this test supplies a passing one.
    pipeline.engine.project_root = str(tmp_path)
    _write_slo_summary(tmp_path, phase_slo_pass=True, required_done_ratio=1.0)
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


@patch("nexus.engine.pipeline_stages.KnowledgeIndex")
def test_p_stage_learn_slo_can_force_research_skip(mock_ki_cls, mock_ctx, mock_tracer, tmp_path):
    """若 Learn phase-SLO 未達標，P 階段應覆寫 research_route 為 skip。"""
    mock_ki = mock_ki_cls.return_value
    mock_ki.search_similar.return_value = []
    mock_ctx.prediction = {"candidate_count": 3, "root_cause_confidence": 0.2}
    mock_ctx.planner.run.return_value = mock_ctx.prediction
    res_decision = ResearchDecision(should_research=True, mode="external", reason="low_confidence", rounds=5, stable_wins=3)
    mock_ctx.research_policy.route.return_value = res_decision

    slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    slo.parent.mkdir(parents=True, exist_ok=True)
    slo.write_text('{"phase_slo_pass": false, "global": {"required_done_ratio": 0.2}}', encoding="utf-8")

    pipeline = MockPipeline()
    pipeline.engine.project_root = tmp_path
    pipeline._stage_plan(mock_ctx, mock_tracer)

    route = mock_ctx.state.metadata["research_route"]
    assert route["should_research"] is False
    assert route["mode"] == "skip"
    assert route["reason"] == "learn_phase_slo_not_ready"
    assert route["learn_guard_forced_skip"] is True


@patch("nexus.engine.pipeline_stages.KnowledgeIndex")
def test_x_stage_skips_when_learn_guard_not_ready(mock_ki_cls, mock_ctx, mock_tracer):
    """X 階段在 Learn guard 未就緒時，需跳過 researcher。"""
    mock_ctx.state.metadata["research_route"] = {
        "should_research": True,
        "mode": "external",
        "reason": "precomputed",
        "rounds": 5,
        "stable_wins": 3,
    }
    mock_ctx.state.metadata["learn_phase_slo"] = {
        "active": True,
        "ready": False,
        "phase_slo_pass": False,
        "required_done_ratio": 0.4,
        "reason": "learn_phase_slo_not_ready",
    }
    mock_ctx.researcher = MagicMock()

    pipeline = MockPipeline()
    pipeline._stage_research(mock_ctx, mock_tracer)

    assert mock_ctx.state.metadata["research_skipped_by_learn_guard"] is True
    assert not mock_ctx.researcher.run.called


# ARCHIVED 2026-10-13 legacy-engine: this file tests (in whole or in part) modules archived with
# the legacy NexusEngine (nexus.engine.pipeline_stages); see ARCHIVED_2026-10-13-legacy-engine.md.
# It keeps running with unchanged node ids until the deletion PR removes it with those modules.
