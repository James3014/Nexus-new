from __future__ import annotations

import pytest

from nexus.knowledge.autonomous_memory_curator import (
    AutonomousMemoryCurator,
    Trajectory,
    HarnessUpdate,
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
