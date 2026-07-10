from __future__ import annotations

import os

from nexus.research.flow.rlm_x_loop import run_rlm_x_loop, ResearchEvidence


def test_x_loop_default_stub():
    result = run_rlm_x_loop({"task_id": "x001"})
    assert isinstance(result, ResearchEvidence)
    assert result.status == "stub"
    assert result.loop_iterations == 0


def test_x_loop_real_with_env(monkeypatch):
    monkeypatch.setenv("NEXUS_RLM_X_LOOP_ENABLED", "1")
    result = run_rlm_x_loop({"task_id": "x002"}, max_iterations=3)
    assert result.status == "pass"
    assert result.loop_iterations == 3
    assert len(result.findings) == 3


def test_x_loop_real_default_iterations(monkeypatch):
    monkeypatch.setenv("NEXUS_RLM_X_LOOP_ENABLED", "1")
    result = run_rlm_x_loop({"task_id": "x003"})
    assert result.loop_iterations == 5


def test_x_loop_unknown_task_id():
    result = run_rlm_x_loop({})
    assert result.task_id == "unknown"


def test_x_loop_findings_structure(monkeypatch):
    monkeypatch.setenv("NEXUS_RLM_X_LOOP_ENABLED", "1")
    result = run_rlm_x_loop({"task_id": "x004"}, max_iterations=2)
    for f in result.findings:
        assert "iteration" in f
        assert "status" in f
