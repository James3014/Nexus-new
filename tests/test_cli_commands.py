import pytest
from click.testing import CliRunner
from scripts.engine.nexus_cli import nexus
import os
from unittest.mock import patch, MagicMock


@pytest.mark.parametrize("cmd", [
    ["nexus:status"],
    ["nexus:hud"],
    ["nexus:spec-lock"],
    ["nexus:governance-check"],
    ["nexus:acceptance-check"],
    ["nexus:closeout"]
])
def test_cli_deprecated_commands_blocked(cmd):
    runner = CliRunner()
    result = runner.invoke(nexus, cmd)
    assert result.exit_code == 2
    assert "DEPRECATED_BLOCKED" in result.output

def test_cli_invalid_command():
    runner = CliRunner()
    # 測試無效指令
    result = runner.invoke(nexus, ["nexus:invalid-cmd"])
    assert result.exit_code != 0

import json


def test_research_run_success(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    target = tmp_path / "docs" / "sample.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ok", encoding="utf-8")

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "r-success",
            "--scope",
            "docs/sample.txt",
            "--candidate-src-root",
            ".",
            "--report-file",
            ".nexus/reports/research/report-success.json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["status"] == "success"
    assert payload["semantic_status"] == "VERIFIED"
    report_path = tmp_path / ".nexus" / "reports" / "research" / "report-success.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["run_id"] == "r-success"
    assert report["status"] == "success"
    assert report["semantic_status"] == "VERIFIED"
    assert report["winner"] == "candidate-main"
    assert isinstance(report["top_k"], list) and report["top_k"]
    assert "budget_summary" in report
    assert "timestamps" in report


def test_research_run_rollback_on_failed_gate(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    target = tmp_path / "docs" / "sample.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ok", encoding="utf-8")

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "r-fail",
            "--scope",
            "docs/sample.txt",
            "--candidate-src-root",
            ".",
            "--budget-limit",
            "0",
            "--estimated-cost-per-round",
            "1",
            "--report-file",
            ".nexus/reports/research/report-fail.json",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output.strip())
    assert payload["status"] == "failed"
    assert payload["semantic_status"] == "UNVERIFIED"
    assert payload["retryable"] is True
    assert payload["next_action_file"]
    report_path = tmp_path / ".nexus" / "reports" / "research" / "report-fail.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["semantic_status"] == "UNVERIFIED"
    assert report["next_action_file"]
    assert "below_threshold" in report["rejected_reasons"]
    assert report["rollback_trace"]


def test_research_run_continuation_attempts_retryable_failures(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    target = tmp_path / "docs" / "sample.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ok", encoding="utf-8")

    captured = {}

    class _Res:
        returncode = 0
        stdout = json.dumps({"status": "success", "semantic_status": "VERIFIED"})
        stderr = ""

    def _fake_subprocess_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        return _Res()

    monkeypatch.setattr("scripts.engine.nexus_cli.subprocess.run", _fake_subprocess_run)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "r-cont",
            "--scope",
            "docs/sample.txt",
            "--candidate-src-root",
            ".",
            "--budget-limit",
            "0",
            "--estimated-cost-per-round",
            "1",
            "--continuation-attempts",
            "1",
            "--report-file",
            ".nexus/reports/research/report-cont.json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["status"] == "success"
    assert payload["semantic_status"] == "VERIFIED"
    cmd = captured["cmd"]
    idx = cmd.index("--continuation-attempts")
    assert cmd[idx + 1] == "0"


def test_research_run_blocked_does_not_attempt_continuation(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)

    import shutil

    def mock_disk_usage(path):
        return (100 * 1024**3, 99 * 1024**3, 1 * 1024**3)

    monkeypatch.setattr(shutil, "disk_usage", mock_disk_usage)

    called = {"count": 0}

    class _Res:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def _fake_subprocess_run(*_args, **_kwargs):
        called["count"] += 1
        return _Res()

    monkeypatch.setattr("scripts.engine.nexus_cli.subprocess.run", _fake_subprocess_run)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "gov-low-disk-no-cont",
            "--disk-watermark-gb",
            "5.0",
            "--continuation-attempts",
            "2",
            "--report-file",
            ".nexus/reports/research/gov-low-disk-no-cont.json",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output.strip())
    assert payload["semantic_status"] == "BLOCKED"
    assert called["count"] == 0


def test_research_governance_success(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    target = tmp_path / "docs" / "sample.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ok", encoding="utf-8")

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "gov-ok",
            "--scope",
            "docs/sample.txt",
            "--max-parallel",
            "2",
            "--timeout-sec",
            "300",
            "--report-file",
            ".nexus/reports/research/gov-ok.json",
        ],
    )
    assert result.exit_code == 0
    report_path = tmp_path / ".nexus" / "reports" / "research" / "gov-ok.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "success"
    assert report["semantic_status"] == "VERIFIED"


def test_research_governance_low_disk(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)

    # Monkeypatch shutil.disk_usage to return low free space
    import shutil
    def mock_disk_usage(path):
        return (100 * 1024**3, 99 * 1024**3, 1 * 1024**3)  # 1GB free
    monkeypatch.setattr(shutil, "disk_usage", mock_disk_usage)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "gov-low-disk",
            "--disk-watermark-gb",
            "5.0",
            "--report-file",
            ".nexus/reports/research/gov-low-disk.json",
        ],
    )
    assert result.exit_code != 0
    report_path = tmp_path / ".nexus" / "reports" / "research" / "gov-low-disk.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["semantic_status"] == "BLOCKED"
    assert report["blocker_type"] == "governance"
    assert "low_disk_space" in report["rejected_reasons"]


def test_research_governance_invalid_parallelism(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "gov-inv-par",
            "--max-parallel",
            "0",
            "--report-file",
            ".nexus/reports/research/gov-inv-par.json",
        ],
    )
    assert result.exit_code != 0
    report_path = tmp_path / ".nexus" / "reports" / "research" / "gov-inv-par.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["semantic_status"] == "BLOCKED"
    assert "invalid_parallelism" in report["rejected_reasons"]


def test_research_governance_invalid_timeout(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "gov-inv-timeout",
            "--timeout-sec",
            "-1",
            "--report-file",
            ".nexus/reports/research/gov-inv-timeout.json",
        ],
    )
    assert result.exit_code != 0
    report_path = tmp_path / ".nexus" / "reports" / "research" / "gov-inv-timeout.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["semantic_status"] == "BLOCKED"
    assert "invalid_timeout" in report["rejected_reasons"]


def test_research_governance_invalid_retries(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "gov-inv-retries",
            "--max-retries",
            "-1",
            "--report-file",
            ".nexus/reports/research/gov-inv-retries.json",
        ],
    )
    assert result.exit_code != 0
    report_path = tmp_path / ".nexus" / "reports" / "research" / "gov-inv-retries.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["semantic_status"] == "BLOCKED"
    assert "invalid_retries" in report["rejected_reasons"]


def test_research_governance_invalid_retain_n(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "gov-inv-retain",
            "--retain-last-n",
            "0",
            "--report-file",
            ".nexus/reports/research/gov-inv-retain.json",
        ],
    )
    assert result.exit_code != 0
    report_path = tmp_path / ".nexus" / "reports" / "research" / "gov-inv-retain.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["semantic_status"] == "BLOCKED"
    assert "invalid_retain_n" in report["rejected_reasons"]


def test_research_retain_cleanup_executor(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)

    target = tmp_path / "docs" / "sample.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ok", encoding="utf-8")

    report_dir = tmp_path / ".nexus" / "reports" / "research"
    report_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(4):
        old = report_dir / f"old-{idx}.json"
        old.write_text("{}", encoding="utf-8")

    exp_root = tmp_path / ".nexus" / "experiments"
    backup_root = tmp_path / ".nexus" / "backups"
    for idx in range(4):
        (exp_root / f"exp-{idx}").mkdir(parents=True, exist_ok=True)
        (backup_root / f"bak-{idx}").mkdir(parents=True, exist_ok=True)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "retain-check",
            "--scope",
            "docs/sample.txt",
            "--retain-last-n",
            "2",
            "--report-file",
            ".nexus/reports/research/retain-check.json",
        ],
    )
    assert result.exit_code == 0
    report = json.loads((report_dir / "retain-check.json").read_text(encoding="utf-8"))
    assert report["retention"]["retain_last_n"] == 2
    assert report["semantic_status"] == "VERIFIED"
    assert report["retention"]["cleaned"]["reports"] >= 1
    assert report["retention"]["cleaned"]["experiments"] >= 1
    assert report["retention"]["cleaned"]["backups"] >= 1
    assert sum(1 for _ in report_dir.glob("*.json")) == 2
    assert len([p for p in exp_root.iterdir() if p.is_dir()]) == 2
    assert len([p for p in backup_root.iterdir() if p.is_dir()]) == 2


def test_research_schema(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    target = tmp_path / "docs" / "sample.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ok", encoding="utf-8")

    # Success Path
    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "schema-success",
            "--scope",
            "docs/sample.txt",
            "--report-file",
            ".nexus/reports/research/schema-success.json",
        ],
    )
    assert result.exit_code == 0
    report_path = tmp_path / ".nexus" / "reports" / "research" / "schema-success.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    
    assert report["schema_version"] == "1.0"
    assert report["semantic_status"] == "VERIFIED"
    assert "decision_log" in report
    assert any("schedule" in step for step in report["decision_log"])
    assert any("evaluate" in step for step in report["decision_log"])
    assert any("select" in step for step in report["decision_log"])
    
    assert "top_k" in report
    for item in report["top_k"]:
        assert "candidate_id" in item
        assert isinstance(item["average_score"], float)
        assert isinstance(item["passed_gate"], bool)

    assert "cost_curve" in report
    cc = report["cost_curve"]
    bs = report["budget_summary"]
    assert cc["budget_limit"] == bs["limit"]
    assert cc["total_cost"] == bs["used"]
    assert cc["budget_remaining"] == bs["remaining"]
    assert report["execution"]["max_parallel"] == 1
    assert report["execution"]["max_retries"] == 0
    assert "retention" in report

    # Failed Path (Low Disk)
    import shutil
    def mock_disk_usage(path):
        return (100 * 1024**3, 99 * 1024**3, 1 * 1024**3)  # 1GB free
    monkeypatch.setattr(shutil, "disk_usage", mock_disk_usage)

    result_fail = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "schema-fail",
            "--disk-watermark-gb",
            "5.0",
            "--report-file",
            ".nexus/reports/research/schema-fail.json",
        ],
    )
    assert result_fail.exit_code != 0
    report_path_fail = tmp_path / ".nexus" / "reports" / "research" / "schema-fail.json"
    report_fail = json.loads(report_path_fail.read_text(encoding="utf-8"))
    assert report_fail["status"] == "failed"
    assert report_fail["semantic_status"] == "BLOCKED"
    assert "elimination_matrix" in report_fail
    assert len(report_fail["elimination_matrix"]) > 0
    assert report_fail["elimination_matrix"][0]["candidate_id"] == "candidate-main"
    assert "low_disk_space" in report_fail["elimination_matrix"][0]["reason_codes"]



def test_research_timeout(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    
    # We use a very short timeout to trigger it quickly
    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "timeout-test",
            "--hypothesis",
            "sleep-now",
            "--timeout-sec",
            "1",
            "--report-file",
            ".nexus/reports/research/timeout.json",
        ],
    )
    assert result.exit_code != 0
    report_path = tmp_path / ".nexus" / "reports" / "research" / "timeout.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["semantic_status"] == "UNVERIFIED"
    # Seed details should show timeout
    for seed in report.get("candidate", {}).get("seed_details", []):
        assert "timed out" in seed.get("error", "").lower()

def test_research_cleanup(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    report_dir = tmp_path / ".nexus" / "reports" / "research"
    report_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "docs" / "sample.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ok", encoding="utf-8")
    
    # Pre-create 5 reports
    for i in range(5):
        (report_dir / f"old-{i}.json").write_text("{}")
        import time
        time.sleep(0.01) # Ensure different mtimes
        
    # Run with retain-last-n=3
    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:run",
            "--run-id",
            "cleanup-test",
            "--scope",
            "docs/sample.txt",
            "--retain-last-n",
            "3",
            "--report-file",
            ".nexus/reports/research/new.json",
        ],
    )
    assert result.exit_code == 0
    
    # Should only have 3 reports left
    remaining = list(report_dir.glob("*.json"))
    assert len(remaining) == 3
    report = json.loads((report_dir / "new.json").read_text(encoding="utf-8"))
    assert report["semantic_status"] == "VERIFIED"

def test_research_route_findings_reinjection(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    
    # Create a finding
    finding_dir = tmp_path / ".nexus" / "memory" / "task" / "knowledge"
    finding_dir.mkdir(parents=True, exist_ok=True)
    finding_path = finding_dir / "f1.json"
    finding_path.write_text(json.dumps({
        "id": "f1",
        "kind": "knowledge",
        "title": "Websocket Bug",
        "scope": "task",
        "tags": ["ws"],
        "retrieval_hints": ["websocket"],
        "body": "hit",
        "updated_at": "2026-04-13T12:00:00"
    }))
    
    # Hit
    result = runner.invoke(nexus, ["nexus", "research:route", "--task-desc", "Fix ws", "--findings-query", "websocket", "--output-json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["findings_hits"] == 1
    assert data["adjusted_root_cause_confidence"] == 0.85
    
    # No Hit
    result = runner.invoke(nexus, ["nexus", "research:route", "--task-desc", "Fix ws", "--findings-query", "missing", "--output-json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["findings_hits"] == 0
    assert data["adjusted_root_cause_confidence"] == 1.0
    assert "recommended_flow" in data


def test_research_route_recommended_flow_baseline(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:route",
            "--task-desc",
            "fix typo in docs heading",
            "--task-type",
            "bug",
            "--candidate-count",
            "1",
            "--root-cause-confidence",
            "0.95",
            "--output-json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["recommended_flow"] == "baseline"


def test_research_route_recommended_flow_hyper_for_risky_task(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:route",
            "--task-desc",
            "fix flaky websocket timeout race",
            "--task-type",
            "bug",
            "--candidate-count",
            "1",
            "--root-cause-confidence",
            "0.9",
            "--output-json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["recommended_flow"] == "hyper_sprint"
    assert data["should_research"] is True


def test_research_route_writes_route_decision_report_when_requested(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    report = tmp_path / ".nexus" / "reports" / "routes" / "route.json"
    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:route",
            "--task-desc",
            "fix flaky websocket timeout with xray dependency graph",
            "--task-type",
            "bug",
            "--candidate-count",
            "2",
            "--root-cause-confidence",
            "0.55",
            "--route-decision-report",
            str(report),
            "--output-json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert data["route_decision_report"] == str(report)
    assert payload["schema_version"] == "nexus_route_decision_v1"
    assert payload["decision_source"] == "capability_planner"
    assert "xray" in payload["selected_capabilities"]
    assert payload["signal_snapshot"]["pillar_signals"]["Claim"]["active"] is True


def test_research_auto_flow_baseline(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)

    target = tmp_path / "demo.py"
    target.write_text("print('buggy')\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_demo.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    def fake_generate_local_candidate(source, *_args, **_kwargs):
        return source.replace("buggy", "fixed")

    class _Res:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def fake_subprocess_run(*_args, **_kwargs):
        return _Res(returncode=0)

    monkeypatch.setattr("nexus.app.research_flow_service.generate_local_candidate", fake_generate_local_candidate)
    monkeypatch.setattr("nexus.app.research_flow_service.subprocess.run", fake_subprocess_run)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:auto-flow",
            "--task-desc",
            "fix typo in docs heading",
            "--target-file",
            "demo.py",
            "--test-file",
            "tests/test_demo.py",
            "--output-json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["chosen_flow"] == "baseline"
    assert data["result"]["status"] == "SUCCESS"
    assert data["semantic_status"] == "VERIFIED"


def test_research_auto_flow_force_hyper(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    _write_ready_learn_slo(tmp_path)

    target = tmp_path / "demo.py"
    target.write_text("print('buggy')\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_demo.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    from nexus.research.sprint_service import SprintResult

    def fake_run_hyper_sprint(*_args, **_kwargs):
        return SprintResult(
            status="SUCCESS",
            reason="stage1_pass",
            target_file="demo.py",
            winner_source="local",
            final_score=1.0,
            elapsed_sec=0.1,
            attempt_count=1,
            model_calls=0,
            quota_backoffs=0,
            test_timeouts=0,
            error_codes=[],
            candidates=[],
            pytest_cmd=["uv", "run", "pytest", "-q", "--maxfail=1", "tests/test_demo.py"],
            promotable=True,
            patch="print('fixed')\n",
        )

    class _Res:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def fake_subprocess_run(*_args, **_kwargs):
        return _Res(returncode=0)

    monkeypatch.setattr("nexus.research.sprint_service.run_hyper_sprint", fake_run_hyper_sprint)
    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:auto-flow",
            "--task-desc",
            "fix flaky websocket timeout race",
            "--target-file",
            "demo.py",
            "--test-file",
            "tests/test_demo.py",
            "--force-flow",
            "hyper_sprint",
            "--output-json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["chosen_flow"] == "hyper_sprint"
    assert data["result"]["status"] == "SUCCESS"
    assert data["semantic_status"] == "VERIFIED"


def test_research_auto_flow_early_baseline_shortcut(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    _write_ready_learn_slo(tmp_path)

    target = tmp_path / "demo.py"
    target.write_text("print('buggy')\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_demo.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    class _Res:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def fake_subprocess_run(*_args, **_kwargs):
        return _Res(returncode=0)

    called = {"hyper": 0}

    def fake_generate_local_candidate(source, *_args, **_kwargs):
        return source.replace("buggy", "fixed")

    def fake_run_hyper_sprint(*_args, **_kwargs):
        called["hyper"] += 1
        raise AssertionError("Hyper should not be called when baseline shortcut triggers")

    monkeypatch.setattr("nexus.app.research_flow_service.subprocess.run", fake_subprocess_run)
    monkeypatch.setattr("nexus.app.research_flow_service.generate_local_candidate", fake_generate_local_candidate)
    monkeypatch.setattr("nexus.app.research_flow_service.run_hyper_sprint", fake_run_hyper_sprint)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:auto-flow",
            "--task-desc",
            "fix flaky websocket timeout race",
            "--target-file",
            "demo.py",
            "--test-file",
            "tests/test_demo.py",
            "--baseline-fast-sec",
            "99",
            "--output-json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["chosen_flow"] == "baseline"
    assert data["guard"]["early_baseline_shortcut"] is True
    assert data["semantic_status"] == "VERIFIED"
    assert called["hyper"] == 0


def test_research_auto_flow_learn_guard_forces_baseline(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)

    target = tmp_path / "demo.py"
    target.write_text("print('buggy')\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_demo.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    class _Res:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def fake_subprocess_run(*_args, **_kwargs):
        return _Res(returncode=0)

    called = {"hyper": 0}

    def fake_run_hyper_sprint(*_args, **_kwargs):
        called["hyper"] += 1
        raise AssertionError("Hyper should be skipped when Learn phase-SLO blocks")

    monkeypatch.setattr("nexus.app.research_flow_service.subprocess.run", fake_subprocess_run)
    monkeypatch.setattr("nexus.app.research_flow_service.run_hyper_sprint", fake_run_hyper_sprint)
    monkeypatch.setattr(
        "nexus.app.research_flow_service.generate_local_candidate",
        lambda source, *_args, **_kwargs: source.replace("buggy", "fixed"),
    )

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:auto-flow",
            "--task-desc",
            "fix flaky websocket timeout race",
            "--target-file",
            "demo.py",
            "--test-file",
            "tests/test_demo.py",
            "--output-json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["chosen_flow"] == "baseline"
    assert data["guard"]["learn_forced_baseline"] is True
    assert data["semantic_status"] == "VERIFIED"
    assert called["hyper"] == 0


def test_run_bug_auto_flow_requires_scope_files(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    result = runner.invoke(nexus, ["run-bug", "fix deadlock", "--auto-flow"])
    assert result.exit_code != 0
    assert "--auto-flow requires --target-file and --test-file" in result.output


def test_run_bug_auto_flow_delegates(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    called = {"count": 0}
    captured = {}

    def fake_auto_flow(**_kwargs):
        called["count"] += 1
        captured.update(_kwargs)
        return (
            {
                "chosen_flow": "baseline",
                "result": {"status": "SUCCESS", "elapsed_sec": 0.1},
            },
            tmp_path / ".nexus" / "reports" / "research" / "auto-flow-report.json",
        )

    monkeypatch.setattr("nexus.app.research_flow_service.run_auto_flow", fake_auto_flow)

    result = runner.invoke(
        nexus,
        [
            "run-bug",
            "fix deadlock",
            "--auto-flow",
            "--target-file",
            "demo.py",
            "--test-file",
            "tests/test_demo.py",
        ],
    )
    assert result.exit_code == 0
    assert called["count"] == 1
    assert captured["llm_baseline"] is False
    assert captured["output_file"] is None


def test_top_level_run_compat_forwards_to_nested_group(monkeypatch):
    runner = CliRunner()
    called = {}

    def fake_subprocess_run(cmd, *args, **kwargs):
        called["cmd"] = cmd
        return MagicMock(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)
    result = runner.invoke(nexus, ["run", "fix deadlock", "--complexity", "0.3"])
    assert result.exit_code == 0
    assert "CLI-Compat" in result.output
    cmd = called["cmd"]
    assert "nexus" in cmd
    assert "run" in cmd

def test_research_run_multi_candidate(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    
    result = runner.invoke(nexus, ["nexus", "research:run", "--candidate-count", "3", "--dry-run", "--min-score-threshold", "0.1"])
    assert result.exit_code == 0
    # The output of research:run is a JSON string in some cases, but wait
    # In my implementation it's click.echo(json.dumps(...))
    data = json.loads(result.output)
    assert data["status"] == "success"
    assert data["semantic_status"] == "VERIFIED"
    
    report_file = data["report_file"]
    with open(report_file, "r") as f:
        report = json.load(f)
    assert len(report["top_k"]) == 3
    assert report["winner"] == "candidate-main"
    assert report["semantic_status"] == "VERIFIED"

def test_research_benchmark(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "cases": [
            {"id": "c1", "task_desc": "SDK bug", "task_type": "bug", "candidate_count": 1, "root_cause_confidence": 1.0}
        ]
    }))
    
    result = runner.invoke(nexus, ["nexus", "research:benchmark", "--manifest-file", str(manifest_path)])
    assert result.exit_code == 0
    assert "Benchmark Complete" in result.output
    
    report_path = tmp_path / ".nexus" / "reports" / "research" / "benchmark-report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["total_cases"] == 1
    assert report["research_chosen_cases"] == 1
    assert "success_cases" in report


def test_research_benchmark_ab_mode(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)

    target = tmp_path / "demo.py"
    target.write_text("print('buggy')\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_demo.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    manifest_path = tmp_path / "manifest_ab.json"
    manifest_path.write_text(json.dumps({
        "cases": [
            {
                "id": "ab1",
                "task_desc": "fix bug",
                "target_file": "demo.py",
                "test_file": "tests/test_demo.py",
                "candidate_count": 1,
            }
        ]
    }))

    from nexus.research.sprint_service import SprintResult

    def fake_run_hyper_sprint(*_args, **_kwargs):
        return SprintResult(
            status="SUCCESS",
            reason="stage1_pass",
            target_file="demo.py",
            winner_source="local",
            final_score=1.0,
            elapsed_sec=0.1,
            attempt_count=1,
            model_calls=0,
            quota_backoffs=0,
            test_timeouts=0,
            error_codes=[],
            candidates=[],
            pytest_cmd=["uv", "run", "pytest", "-q", "--maxfail=1", "tests/test_demo.py"],
            promotable=True,
            patch="print('fixed')\n",
        )

    def fake_generate_local_candidate(source, *_args, **_kwargs):
        return source.replace("buggy", "fixed")

    class _Res:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def fake_subprocess_run(*args, **kwargs):
        return _Res(returncode=0)

    monkeypatch.setattr("nexus.research.sprint_service.run_hyper_sprint", fake_run_hyper_sprint)
    monkeypatch.setattr("nexus.research.local_sprint_mutator.generate_local_candidate", fake_generate_local_candidate)
    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "research:benchmark",
            "--manifest-file",
            str(manifest_path),
            "--mode",
            "ab",
            "--ab-trials",
            "2",
        ],
    )
    assert result.exit_code == 0
    assert "A/B Benchmark Complete" in result.output

    report_path = tmp_path / ".nexus" / "reports" / "research" / "benchmark-report.json"
    report = json.loads(report_path.read_text())
    assert report["mode"] == "ab"
    assert report["ab_trials"] == 2
    case = report["per_case"][0]
    assert case["baseline"]["summary"]["success_rate"] == 1.0
    assert case["hyper_sprint"]["summary"]["success_rate"] == 1.0
def _write_ready_learn_slo(tmp_path):
    phase_slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    phase_slo.parent.mkdir(parents=True, exist_ok=True)
    phase_slo.write_text(
        '{"phase_slo_pass": true, "global": {"required_done_ratio": 1.0}}',
        encoding="utf-8",
    )
