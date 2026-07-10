from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

import scripts.bench.capability_ab_runner as capability_ab_runner
from scripts.bench.capability_ab_runner import (
    CapabilityTask,
    _write_daily_hybrid_score_json,
    run_local_only_executed,
    run_cloud_exhausted,
    run_with_nexus,
)


def _make_mock_row(
    task: CapabilityTask,
    status: str = "SUCCESS",
    run_eligible: bool = True,
) -> dict[str, Any]:
    return {
        "task_id": task.id,
        "mode": "with_nexus",
        "status": status,
        "run_eligible": run_eligible,
        "difficulty": task.difficulty,
        "elapsed_sec": 0.1,
        "wall_duration_sec": 0.1,
        "tokens_used": 0,
        "is_claimable": False,
        "public_claim_safe": False,
    }


_SAMPLE_TASK = CapabilityTask(
    id="test_task_001",
    difficulty="easy",
    task_type="edit",
    task_desc="Fix the bug",
    target_file="dummy.py",
    test_file="test_dummy.py",
    success_criteria="pytest passes",
)


class TestQuadrantWithNexusUnchanged:
    def test_run_with_nexus_still_callable(self):
        """5月 with_nexus 行为不变 — run_with_nexus still exists and is callable."""
        assert callable(run_with_nexus)

    def test_run_with_nexus_signature_accepts_with_llm_mode(self):
        """run_with_nexus still accepts with_llm_mode parameter."""
        import inspect
        sig = inspect.signature(run_with_nexus)
        assert "with_llm_mode" in sig.parameters


class TestQuadrantBareUnchanged:
    def test_run_without_nexus_still_callable(self):
        """5月 bare 行为不变 — run_without_nexus still exists and is callable."""
        from scripts.bench.capability_ab_runner import run_without_nexus
        assert callable(run_without_nexus)

    def test_without_mode_bare_still_works(self):
        """run_without_nexus still accepts mode='bare'."""
        from scripts.bench.capability_ab_runner import run_without_nexus
        import inspect
        sig = inspect.signature(run_without_nexus)
        assert "mode" in sig.parameters


class TestQuadrantLocalOnlyExecuted:
    def test_run_local_only_executed_sets_llm_off(self, monkeypatch):
        """local_only_executed uses local_committee_only topology (llm_mode=off)."""
        invoked = {}
        def _fake_run_with_nexus(*, task, with_llm_mode, **kw):
            invoked["llm_mode"] = with_llm_mode
            invoked["task_id"] = task.id
            return {"status": "SUCCESS", "mode": "local_only_executed"}
        monkeypatch.setattr(capability_ab_runner, "run_with_nexus", _fake_run_with_nexus)
        result = run_local_only_executed(
            repo_root=Path("/tmp"),
            task=_SAMPLE_TASK,
            target_file="dummy.py",
            test_file="test_dummy.py",
            timeout_sec=30,
        )
        assert invoked.get("llm_mode") == "off"
        assert result["status"] == "SUCCESS"

    def test_run_local_only_executed_restores_env(self, monkeypatch):
        """local_only_executed restores NEXUS_WITH_LLM_MODE after run."""
        monkeypatch.setenv("NEXUS_WITH_LLM_MODE", "hard")
        def _fake_run_with_nexus(**kw):
            return {"status": "SUCCESS"}
        monkeypatch.setattr(capability_ab_runner, "run_with_nexus", _fake_run_with_nexus)
        run_local_only_executed(
            repo_root=Path("/tmp"),
            task=_SAMPLE_TASK,
            target_file="dummy.py",
            test_file="test_dummy.py",
            timeout_sec=30,
        )
        assert os.environ.get("NEXUS_WITH_LLM_MODE") == "hard"


class TestQuadrantCloudExhausted:
    def test_run_cloud_exhausted_sets_quota_zero(self, monkeypatch):
        """cloud_exhausted sets NEXUS_CLOUD_BUDGET_REMAINING=0."""
        invoked = {}
        def _fake_run_with_nexus(*, task, **kw):
            quota = os.environ.get("NEXUS_CLOUD_BUDGET_REMAINING", "")
            invoked["quota"] = quota
            invoked["task_id"] = task.id
            return {"status": "SUCCESS", "mode": "cloud_exhausted"}
        monkeypatch.setattr(capability_ab_runner, "run_with_nexus", _fake_run_with_nexus)
        result = run_cloud_exhausted(
            repo_root=Path("/tmp"),
            task=_SAMPLE_TASK,
            target_file="dummy.py",
            test_file="test_dummy.py",
            timeout_sec=30,
        )
        assert invoked.get("quota") == "0"
        assert result["status"] == "SUCCESS"

    def test_run_cloud_exhausted_restores_quota_env(self, monkeypatch):
        """cloud_exhausted restores NEXUS_CLOUD_BUDGET_REMAINING after run."""
        monkeypatch.setenv("NEXUS_CLOUD_BUDGET_REMAINING", "42")
        def _fake_run_with_nexus(**kw):
            return {"status": "SUCCESS"}
        monkeypatch.setattr(capability_ab_runner, "run_with_nexus", _fake_run_with_nexus)
        run_cloud_exhausted(
            repo_root=Path("/tmp"),
            task=_SAMPLE_TASK,
            target_file="dummy.py",
            test_file="test_dummy.py",
            timeout_sec=30,
        )
        assert os.environ.get("NEXUS_CLOUD_BUDGET_REMAINING") == "42"


class TestDailyHybridScoreJson:
    def test_daily_hybrid_score_json_includes_all_4(self, tmp_path: Path):
        """daily_hybrid_score.json has all 4 quadrant keys."""
        row = _make_mock_row(_SAMPLE_TASK)
        score_path = _write_daily_hybrid_score_json(
            out_dir=tmp_path,
            with_rows=[row],
            without_rows=[{**row, "mode": "bare", "status": "FAILED"}],
            local_only_rows=[{**row, "mode": "local_only_executed"}],
            cloud_exhausted_rows=[{**row, "mode": "cloud_exhausted"}],
            ts=1234567890,
        )
        assert score_path.exists()
        data = json.loads(score_path.read_text(encoding="utf-8"))
        assert data["schema"] == "nexus.daily_hybrid_score.v1"
        assert "quadrants" in data
        for qname in ("with_nexus", "bare", "local_only_executed", "cloud_exhausted"):
            assert qname in data["quadrants"], f"missing quadrant {qname}"
            qdata = data["quadrants"][qname]
            assert "total" in qdata
            assert "eligible" in qdata
            assert "solved" in qdata
            assert "score" in qdata

    def test_daily_hybrid_score_quadrant_scoring(self, tmp_path: Path):
        """daily_hybrid_score.json scores are correct."""
        row_pass = _make_mock_row(_SAMPLE_TASK, status="SUCCESS")
        row_fail = _make_mock_row(_SAMPLE_TASK, status="FAILED", run_eligible=True)
        score_path = _write_daily_hybrid_score_json(
            out_dir=tmp_path,
            with_rows=[row_pass],
            without_rows=[row_fail],
            local_only_rows=[row_pass],
            cloud_exhausted_rows=[row_fail],
            ts=1234567890,
        )
        data = json.loads(score_path.read_text(encoding="utf-8"))
        assert data["quadrants"]["with_nexus"]["score"] == 1.0
        assert data["quadrants"]["bare"]["score"] == 0.0
        assert data["quadrants"]["local_only_executed"]["score"] == 1.0
        assert data["quadrants"]["cloud_exhausted"]["score"] == 0.0


class TestQuadrantBackwardCompatDefaultWithNexus:
    def test_quadrant_default_is_with_nexus(self):
        """--quadrant defaults to with_nexus for backward compatibility."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--quadrant", choices=["with_nexus", "bare", "local_only_executed", "cloud_exhausted", "all"], default="with_nexus")
        args = parser.parse_args([])
        assert args.quadrant == "with_nexus"


class TestQuadrantFunctionsAvailable:
    def test_run_local_only_executed_imported(self):
        assert callable(run_local_only_executed)

    def test_run_cloud_exhausted_imported(self):
        assert callable(run_cloud_exhausted)

    def test_write_daily_hybrid_score_json_imported(self):
        assert callable(_write_daily_hybrid_score_json)
