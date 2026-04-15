import pytest
from pathlib import Path
from nexus.research.learn.policy_runtime import decide_research_engine

def test_decide_engine_baseline_when_blocked(tmp_path, monkeypatch):
    # Mock LearnModeService to return low pass rate
    from nexus.research.learn_mode import LearnModeService
    monkeypatch.setattr(LearnModeService, "read_phase_slo_summary", lambda self: {"overall_pass_rate": 0.3})
    
    engine = decide_research_engine(tmp_path, "bug", "standard")
    assert engine == "baseline"

def test_decide_engine_hyper_when_allowed(tmp_path, monkeypatch):
    from nexus.research.learn_mode import LearnModeService
    monkeypatch.setattr(LearnModeService, "read_phase_slo_summary", lambda self: {"overall_pass_rate": 0.9})
    
    engine = decide_research_engine(tmp_path, "bug", "standard")
    assert engine == "hyper_sprint"
