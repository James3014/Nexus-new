from __future__ import annotations

import os

from nexus.research.flow.rlm_r_loop import run_rlm_r_loop, RepairSubmission


def test_r_loop_default_stub():
    result = run_rlm_r_loop({"task_id": "r001"})
    assert isinstance(result, RepairSubmission)
    assert result.status == "stub"
    assert len(result.submissions) == 0


def test_r_loop_real_with_env(monkeypatch):
    monkeypatch.setenv("NEXUS_RLM_R_LOOP_ENABLED", "1")
    result = run_rlm_r_loop({"task_id": "r002"}, submit_budget=2)
    assert result.status == "pass"
    assert len(result.submissions) == 2


def test_r_loop_real_default_budget(monkeypatch):
    monkeypatch.setenv("NEXUS_RLM_R_LOOP_ENABLED", "1")
    result = run_rlm_r_loop({"task_id": "r003"})
    assert len(result.submissions) == 3


def test_r_loop_unknown_task_id():
    result = run_rlm_r_loop({})
    assert result.task_id == "unknown"


def test_r_loop_submissions_structure(monkeypatch):
    monkeypatch.setenv("NEXUS_RLM_R_LOOP_ENABLED", "1")
    result = run_rlm_r_loop({"task_id": "r004"}, submit_budget=2)
    for s in result.submissions:
        assert "attempt" in s
        assert "status" in s
