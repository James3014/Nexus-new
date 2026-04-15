import pytest
from pathlib import Path
from unittest.mock import MagicMock
from nexus.engine.pipeline_stages import PipelineStagesMixin

class MockEngine: 
    def __init__(self, root): self.project_root = root

class MockCtx:
    def __init__(self):
        self.task_id = "t"
        self.task_type = "bug"
        self.task_desc = "test"
        self.decision_counter = 0
        self.state = MagicMock()
        self.state.metadata = {}
        self.event_store = None
        self.bayesian_params = {}
        self.kwargs = {}
        self.hub = MagicMock()
        self.hub.make_pre_routing_decision.return_value = {"external_needed": False}
        self.planner = MagicMock()
        self.researcher = MagicMock()
        self.research_policy = MagicMock()
        self.prediction = {}; self.dry_run = False

def test_planner_stage_injects_policy(tmp_path: Path, monkeypatch):
    from nexus.research.learn_mode import LearnModeService
    monkeypatch.setattr(LearnModeService, "read_phase_slo_summary", lambda self: {"overall_pass_rate": 0.9})
    
    stage = PipelineStagesMixin()
    stage.engine = MockEngine(tmp_path)
    ctx = MockCtx()
    tracer = MagicMock()
    
    # We use try/except because we only care about the injection before it hits the real business logic
    try:
        stage._stage_plan(ctx, tracer)
    except:
        pass
        
    assert "phase_policy" in ctx.state.metadata
    assert ctx.state.metadata["phase_policy"]["allow_research"] is True

def test_research_stage_skips_when_forced_baseline(tmp_path: Path, monkeypatch):
    from nexus.research.learn.policy_runtime import decide_research_engine
    monkeypatch.setattr("nexus.engine.pipeline_stages.decide_research_engine", lambda root, t, r: "baseline")
    
    stage = PipelineStagesMixin()
    stage.engine = MockEngine(tmp_path)
    ctx = MockCtx()
    # Ensure guard doesn't block before our policy check
    ctx.state.metadata["learn_phase_slo"] = {"active": True, "ready": True}
    tracer = MagicMock()
    
    stage._stage_research(ctx, tracer)
    assert ctx.state.metadata["chosen_research_engine"] == "baseline"
