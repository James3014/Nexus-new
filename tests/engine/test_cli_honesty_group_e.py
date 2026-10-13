"""Group E CLI honesty: research:run verification, content:rewrite fail-closed, mission budget."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from nexus.core.mission_contracts import MissionStatus, NexusMission, extract_receipt_tokens
from scripts.engine.commands.research_actions import _scope_test_targets, run_research_run


def _research(tmp_path: Path, runner, **overrides):
    kwargs = dict(
        run_id="run-1",
        candidate_id="candidate-main",
        candidate_count=1,
        hypothesis="fix add",  # no magic "real-run" substring
        scope=("pkg", "tests/test_pkg.py"),
        candidate_src_root=Path("."),
        budget_limit=100.0,
        min_score_threshold=0.5,
        estimated_cost_per_round=1.0,
        dry_run=True,
        report_file=Path(".nexus/reports/research/report.json"),
        max_parallel=1,
        max_retries=0,
        continuation_attempts=0,
        timeout_sec=60,
        retain_last_n=20,
        disk_watermark_gb=0.0,
        research_session_id="",
        research_gate=False,
        task_type="bug",
        root_cause_confidence=1.0,
        findings_query=None,
        disk_usage=lambda root: (0, 0, 10 * 1024**3),
        subprocess_runner=runner,
        completion_handoff_writer=lambda **kw: tmp_path / "handoff.json",
    )
    kwargs.update(overrides)
    return run_research_run(tmp_path, **kwargs)


def _fixture(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_pkg.py").write_text("")


def test_research_run_fails_closed_when_tests_fail(tmp_path: Path):
    _fixture(tmp_path)
    calls = []

    def failing(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=1, stdout="1 failed")

    result = _research(tmp_path, failing)
    assert calls, "verification must actually execute"
    assert "pytest" in calls[0] and "tests/test_pkg.py" in calls[0]
    assert result.exit_code == 1
    assert result.output_payload["status"] == "FAILED_VERIFICATION"
    assert result.output_payload["winner"] is None


def test_research_run_succeeds_only_when_executed_check_passes(tmp_path: Path):
    _fixture(tmp_path)
    ran = []

    def passing(cmd, **kwargs):
        ran.append(cmd)
        return MagicMock(returncode=0, stdout="1 passed")

    result = _research(tmp_path, passing)
    assert ran
    assert result.exit_code == 0
    assert result.output_payload["status"] == "success"
    details = result.report_payload["candidate"]["seed_details"]
    assert details and details[0]["score"] == 1.0


def test_research_run_never_scores_without_executing(tmp_path: Path):
    _fixture(tmp_path)

    def boom(cmd, **kwargs):
        raise OSError("pytest unavailable")

    result = _research(tmp_path, boom)
    assert result.exit_code == 1
    assert result.output_payload["status"] == "FAILED_VERIFICATION"


def test_scope_test_targets_selects_only_tests(tmp_path: Path):
    _fixture(tmp_path)
    assert _scope_test_targets(tmp_path, ["pkg", "tests/test_pkg.py", "missing/test_x.py"]) == [
        "tests/test_pkg.py"
    ]
    assert _scope_test_targets(tmp_path, ["pkg"]) == []


def _rewrite(tmp_path, monkeypatch, *extra):
    monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
    inp = tmp_path / "in.md"
    out = tmp_path / "out.md"
    report = tmp_path / "report.json"
    inp.write_text("a  \n\n\nb\n", encoding="utf-8")
    res = CliRunner().invoke(
        cli_mod.nexus,
        [
            "nexus",
            "content:rewrite",
            "--input-file",
            str(inp),
            "--output-file",
            str(out),
            "--report-file",
            str(report),
            *extra,
        ],
    )
    return res, out, report


def test_rewrite_default_mode_discloses_task_not_applied(tmp_path, monkeypatch):
    res, out, report = _rewrite(tmp_path, monkeypatch)
    assert res.exit_code == 0, res.output
    assert "only normalizes whitespace" in res.output
    assert json.loads(report.read_text())["task_applied"] is False


def test_rewrite_default_mode_with_task_exits_2(tmp_path, monkeypatch):
    res, out, report = _rewrite(tmp_path, monkeypatch, "--task", "make it formal")
    assert res.exit_code == 2
    assert "cannot honour" in res.output
    assert not out.exists()
    assert json.loads(report.read_text())["status"] == "TASK_IGNORED"


def test_rewrite_llm_mode_failure_exits_nonzero_without_fallback(tmp_path, monkeypatch):
    class BrokenGateway:
        oauth_provider = "gemini"

        def __init__(self, *, project_root):
            pass

        def ask_unified(self, *a, **k):
            return {"receipt_complete": False, "online": {}}

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", BrokenGateway)
    res, out, report = _rewrite(tmp_path, monkeypatch, "--llm-mode")
    assert res.exit_code == 1
    assert "unified_runtime_incomplete" in res.output
    assert not out.exists()
    payload = json.loads(report.read_text())
    assert payload["status"] == "FAILED_LLM_UNAVAILABLE"
    assert payload["method"] == "llm_failed"


# --- Mission Control budget breaker ---------------------------------------------------------


def test_wall_time_accumulates_and_trips():
    m = NexusMission(mission_id="M", objective="x", budget={"max_wall_time_sec": 10.0})
    m.begin_wall_clock(now=100.0)
    assert m.wall_time_remaining(now=104.0) == 6.0
    m.settle_wall_clock(now=105.0)
    assert m.accumulated_usage["wall_time_sec"] == 5.0
    assert m.check_telemetry_budget() is True
    m.begin_wall_clock(now=200.0)  # resume
    m.settle_wall_clock(now=205.0)
    assert m.accumulated_usage["wall_time_sec"] == 10.0
    assert m.check_telemetry_budget() is False


def test_tokens_accumulate_from_receipt_and_trip(tmp_path: Path):
    receipt = tmp_path / "r.json"
    receipt.write_text(
        json.dumps({
            "online": {"usage": {"input_tokens": 300, "output_tokens": 100}},
            "local": {"response": {"usage": {"total_tokens": 250}}},
        })
    )
    assert extract_receipt_tokens(json.loads(receipt.read_text())) == 650
    m = NexusMission(mission_id="M", objective="x", budget={"max_tokens": 600.0})
    assert m.add_tokens_from_receipt_file(receipt) == 650
    assert m.check_telemetry_budget() is False
    assert m.add_tokens_from_receipt_file(tmp_path / "missing.json") == 0.0


def test_retries_still_trip():
    m = NexusMission(mission_id="M", objective="x", budget={"max_retries": 2.0})
    m.accumulated_usage["retries"] = 2.0
    assert m.check_telemetry_budget() is False


def _start(tmp_path: Path, mission: NexusMission, fake_run):
    mission.persist(tmp_path)
    with (
        patch.object(cli_mod, "repo_root", tmp_path),
        patch.object(cli_mod.subprocess, "run", fake_run),
        patch.object(NexusMission, "run_fingerprint_preflight", return_value=True),
    ):
        return CliRunner().invoke(cli_mod.nexus, ["nexus", "mission", "start"])


def test_mission_start_token_limit_blocks_after_successful_run(tmp_path: Path):
    def fake_run(cmd, *a, **k):
        report = Path(cmd[cmd.index("--report-file") + 1])
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"online": {"usage": {"total_tokens": 900}}}))
        return MagicMock(returncode=0)

    res = _start(
        tmp_path,
        NexusMission(mission_id="M", objective="o", budget={"max_tokens": 500.0}),
        fake_run,
    )
    assert res.exit_code == 1, res.output
    loaded = NexusMission.load(tmp_path)
    assert loaded.status == MissionStatus.BLOCKED
    assert loaded.accumulated_usage["tokens"] == 900


def test_mission_start_wall_time_limit_blocks(tmp_path: Path):
    def fake_run(cmd, *a, **k):
        assert k["timeout"] is not None  # remaining wall budget bounds the run
        raise subprocess.TimeoutExpired(cmd, k["timeout"])

    m = NexusMission(mission_id="M", objective="o", budget={"max_wall_time_sec": 5.0})
    res = _start(tmp_path, m, fake_run)
    assert res.exit_code == 1
    assert "wall-time" in res.output
    loaded = NexusMission.load(tmp_path)
    assert loaded.active_since is None
    assert loaded.accumulated_usage["wall_time_sec"] >= 0.0


def test_pause_resume_accumulate_wall_time(tmp_path: Path):
    m = NexusMission(
        mission_id="M",
        objective="o",
        status=MissionStatus.ACTIVE,
        active_since=time.time() - 30.0,
    )
    m.persist(tmp_path)
    with patch.object(cli_mod, "repo_root", tmp_path):
        res = CliRunner().invoke(cli_mod.nexus, ["nexus", "mission", "pause"])
    assert res.exit_code == 0, res.output
    loaded = NexusMission.load(tmp_path)
    assert loaded.active_since is None
    assert loaded.accumulated_usage["wall_time_sec"] >= 30.0
