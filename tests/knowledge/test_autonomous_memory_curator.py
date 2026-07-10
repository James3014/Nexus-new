from __future__ import annotations

import os

import pytest

from nexus.knowledge.autonomous_memory_curator import (
    AutonomousMemoryCurator,
    Trajectory,
    HarnessUpdate,
    _parse_automem_response,
)


class TestAutonomousMemoryCurator:

    def test_should_curate_returns_true_every_1000_steps(self):
        curator = AutonomousMemoryCurator(every_n_steps=1000)
        assert curator.should_curate(1000) is True
        assert curator.should_curate(2000) is True
        assert curator.should_curate(5000) is True

    def test_should_curate_returns_false_otherwise(self):
        curator = AutonomousMemoryCurator(every_n_steps=1000)
        assert curator.should_curate(0) is False
        assert curator.should_curate(1) is False
        assert curator.should_curate(500) is False
        assert curator.should_curate(999) is False
        assert curator.should_curate(1001) is False

    def test_curate_returns_empty_harness_update(self):
        curator = AutonomousMemoryCurator()
        result = curator.curate([])
        assert result.recommendations == []
        assert isinstance(result.timestamp, float)

    def test_curate_does_not_call_real_meta_llm(self, monkeypatch):
        called = False

        def fake_meta_llm(*args, **kwargs):
            nonlocal called
            called = True
            return "should not be called"

        monkeypatch.setattr("nexus.knowledge.autonomous_memory_curator.AutonomousMemoryCurator.curate", lambda self, t: HarnessUpdate(recommendations=[], timestamp=0.0))
        curator = AutonomousMemoryCurator()
        result = curator.curate([])
        assert result.recommendations == []

    def test_trajectory_frozen(self):
        t = Trajectory(step_id="s1", action="fix", result="pass", memory_decision="keep")
        with pytest.raises(Exception):
            t.action = "delete"

    def test_harness_update_frozen(self):
        h = HarnessUpdate(recommendations=[], timestamp=1.0)
        with pytest.raises(Exception):
            h.recommendations = ["x"]

    # === L3-D: real AUTOMEM ===

    def test_real_autonomous_memory_curator_disabled_stub(self):
        if "NEXUS_AUTOMEM_LLM" in os.environ:
            del os.environ["NEXUS_AUTOMEM_LLM"]
        curator = AutonomousMemoryCurator()
        result = curator.curate([])
        assert result.recommendations == []

    def test_real_autonomous_memory_curator_calls_llm(self):
        os.environ["NEXUS_AUTOMEM_LLM"] = "qwen2.5-coder:3b"
        curator = AutonomousMemoryCurator()
        traj = [Trajectory("s1", "fix", "pass", "keep")]
        result = curator.curate(traj)
        assert isinstance(result, HarnessUpdate)
        del os.environ["NEXUS_AUTOMEM_LLM"]

    def test_real_autonomous_memory_curator_1000_steps_handling(self):
        os.environ["NEXUS_AUTOMEM_LLM"] = "qwen2.5-coder:3b"
        curator = AutonomousMemoryCurator()
        trajs = [Trajectory(f"s{i}", f"action{i}", f"result{i}", "keep") for i in range(1000)]
        result = curator.curate(trajs)
        assert isinstance(result, HarnessUpdate)
        del os.environ["NEXUS_AUTOMEM_LLM"]

    def test_real_autonomous_memory_curator_recommendations_extraction(self):
        raw = '{"recommendations": ["fix memory leak", "add retry logic"]}'
        recs = _parse_automem_response(raw)
        assert len(recs) == 2
        assert "fix memory leak" in recs

    def test_real_autonomous_memory_curator_fallback(self):
        assert _parse_automem_response("") == []
        assert _parse_automem_response("not json") == []
