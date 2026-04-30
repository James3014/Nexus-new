import json
import subprocess

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from nexus.engine.ultra_review_service import UltraReviewService


def _init_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    (path / "nexus" / "engine").mkdir(parents=True)
    (path / "nexus" / "engine" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_ultra_review_dry_run_writes_report_and_sandbox(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setenv("NEXUS_LLM_CANDIDATE_CAP", "3")
    (tmp_path / "tests" / "engine").mkdir(parents=True)
    (tmp_path / "tests" / "engine" / "test_sample.py").write_text("def test_sample(): pass\n", encoding="utf-8")
    (tmp_path / "nexus" / "engine" / "sample.py").write_text("VALUE = 2\n", encoding="utf-8")

    payload = UltraReviewService(tmp_path).run(
        task="review sample change",
        report_path="reports/ultra.json",
        sandbox_root="reports/sandboxes",
    )

    report_path = tmp_path / "reports" / "ultra.json"
    assert report_path.exists()
    assert payload["gate_passed"] is True
    assert payload["status"] == "DRY_RUN_PASS"
    assert payload["diff"]["has_worktree_delta"] is True
    assert "nexus/engine/sample.py" in payload["diff"]["changed_files"]
    assert (tmp_path / "reports" / "sandboxes" / payload["run_id"] / "changes.diff").exists()
    assert (tmp_path / "reports" / "sandboxes" / payload["run_id"] / "progress.jsonl").exists()
    assert payload["artifacts"]["progress_log"].endswith("progress.jsonl")
    assert payload["sandbox_mirror"]["strategy"] == "git_worktree"
    assert payload["sandbox_mirror"]["diff_applied"] is True
    assert payload["sandbox_mirror"]["untracked_overlay_count"] == 1
    assert payload["summary"]["logic_breaker_passed"] is True
    assert payload["summary"]["ghost_regression_passed"] is True
    assert payload["summary"]["security_verified_findings"] == 0
    assert [event["stage"] for event in payload["progress"]] == [
        "sandbox_prepared",
        "diff_captured",
        "security_sentry_complete",
        "logic_breaker_complete",
        "ghost_regression_complete",
        "report_written",
    ]
    ghost = next(item for item in payload["fleet"] if item["lane"] == "ghost_regression")
    assert ghost["planned_checks"] == ["tests/engine/test_sample.py"]
    assert ghost["executed_checks"] == ["tests/engine/test_sample.py"]
    assert ghost["status"] == "PASS"
    assert payload["ghost_regression"]["passed"] is True
    assert payload["ghost_regression"]["executed_tests"] == ["tests/engine/test_sample.py"]
    assert payload["ghost_regression"]["execution_mode"] == "sandbox_mirror"
    assert payload["ghost_regression"]["timeout_sec"] == 30
    assert payload["ghost_regression"]["dependency_mode"] == "active_venv"
    assert payload["ghost_regression"]["sanitized_env"] == ["NEXUS_LLM_CANDIDATE_CAP"]
    assert payload["ghost_regression"]["execution_cwd"].startswith(payload["sandbox_path"])
    assert (tmp_path / "reports" / "sandboxes" / payload["run_id"] / "worktree").exists()
    logic = payload["logic_breaker"]
    assert logic["passed"] is True
    assert logic["execution_mode"] == "sandbox_mirror"
    assert logic["repro_script"].startswith(payload["sandbox_path"])
    assert "ultra_logic_repro.py" in logic["repro_command"]
    assert (tmp_path / "reports" / "sandboxes" / payload["run_id"] / "ultra_logic_repro.py").exists()
    logic_lane = next(item for item in payload["fleet"] if item["lane"] == "logic_breaker")
    assert logic_lane["status"] == "PASS"
    assert logic_lane["executed_checks"] == ["ultra_logic_repro.py"]
    assert payload["regression_candidate_map"] == [
        {
            "changed_file": "nexus/engine/sample.py",
            "candidates": ["tests/engine/test_sample.py", "tests/test_sample.py"],
            "existing": ["tests/engine/test_sample.py"],
            "skipped": ["tests/test_sample.py"],
            "status": "READY",
            "skip_reason": "",
        }
    ]


def test_ultra_review_sandbox_mirror_falls_back_to_copytree(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "nexus" / "engine" / "sample.py").write_text("VALUE = 2\n", encoding="utf-8")
    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "worktree", "add"]:
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="worktree unavailable")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", fake_run)

    payload = UltraReviewService(tmp_path).run(
        report_path=".nexus/reports/ultra_review_report.json",
        sandbox_root=".nexus/reports/ultra_review/sandboxes",
    )

    assert payload["gate_passed"] is True
    assert payload["sandbox_mirror"]["strategy"] == "copytree"
    assert payload["sandbox_mirror"]["fallback_reason"] == "worktree unavailable"


def test_ultra_review_worktree_mirror_keeps_empty_diff_fast_path(tmp_path):
    _init_repo(tmp_path)

    payload = UltraReviewService(tmp_path).run(
        report_path=".nexus/reports/ultra_review_report.json",
        sandbox_root=".nexus/reports/ultra_review/sandboxes",
    )

    assert payload["gate_passed"] is True
    assert payload["sandbox_mirror"]["strategy"] == "git_worktree"
    assert payload["sandbox_mirror"]["empty_diff"] is True


def test_ultra_review_maps_research_tests_and_security_observations(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "nexus" / "research").mkdir(parents=True)
    (tmp_path / "nexus" / "research" / "probe.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "add research"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "tests" / "research").mkdir(parents=True)
    (tmp_path / "tests" / "research" / "test_probe.py").write_text("def test_probe(): pass\n", encoding="utf-8")
    secret_line = "API" + "_KEY = '123456789abcdef'\n"
    (tmp_path / "nexus" / "research" / "probe.py").write_text(secret_line, encoding="utf-8")

    payload = UltraReviewService(tmp_path).run(
        report_path=".nexus/reports/ultra_review_report.json",
        sandbox_root=".nexus/reports/ultra_review/sandboxes",
    )

    assert payload["gate_passed"] is False
    assert payload["findings"][0]["state"] == "VERIFIED_FINDING"
    assert payload["findings"][0]["rule_id"] == "secret_literal"
    assert payload["findings"][0]["repro_command"]
    assert payload["findings"][0]["execution_cwd"].startswith(payload["sandbox_path"])
    assert payload["security_sentry"]["verified_findings"] == 1
    assert payload["security_sentry"]["passed"] is False
    security = next(item for item in payload["fleet"] if item["lane"] == "security_sentry")
    assert security["status"] == "FAIL"
    ghost = next(item for item in payload["fleet"] if item["lane"] == "ghost_regression")
    assert ghost["planned_checks"] == ["tests/research/test_probe.py"]


def test_ultra_review_security_repro_failure_becomes_unverified_observation(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    secret_line = "API" + "_KEY = '123456789abcdef'\n"
    (tmp_path / "nexus" / "engine" / "sample.py").write_text(secret_line, encoding="utf-8")

    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[:4] == ["uv", "run", "--active", "python"] and "ultra_security_repro_" in str(cmd[4]):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not reproduced")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", fake_run)

    payload = UltraReviewService(tmp_path).run(
        report_path="reports/ultra.json",
        sandbox_root="reports/sandboxes",
    )

    assert payload["security_sentry"]["passed"] is True
    assert payload["security_sentry"]["unverified_observations"] == 1
    assert payload["findings"][0]["state"] == "UNVERIFIED_OBSERVATION"


def test_ultra_review_ghost_regression_failure_becomes_verified_finding(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "tests" / "engine").mkdir(parents=True)
    (tmp_path / "tests" / "engine" / "test_sample.py").write_text("def test_sample():\n    assert False\n", encoding="utf-8")
    (tmp_path / "nexus" / "engine" / "sample.py").write_text("VALUE = 2\n", encoding="utf-8")

    payload = UltraReviewService(tmp_path).run(
        report_path="reports/ultra.json",
        sandbox_root="reports/sandboxes",
    )

    ghost = next(item for item in payload["fleet"] if item["lane"] == "ghost_regression")
    assert ghost["status"] == "FAIL"
    assert payload["gate_passed"] is False
    assert payload["ghost_regression"]["passed"] is False
    finding = payload["findings"][0]
    assert finding["state"] == "VERIFIED_FINDING"
    assert finding["lane"] == "ghost_regression"
    assert finding["repro_command"]
    assert finding["execution_cwd"].startswith(payload["sandbox_path"])


def test_ultra_review_ghost_regression_timeout_becomes_verified_finding(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "tests" / "engine").mkdir(parents=True)
    (tmp_path / "tests" / "engine" / "test_sample.py").write_text("def test_sample(): pass\n", encoding="utf-8")
    (tmp_path / "nexus" / "engine" / "sample.py").write_text("VALUE = 2\n", encoding="utf-8")

    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[:5] == ["uv", "run", "--active", "pytest", "-q"]:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30, output="running", stderr="timeout")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", fake_run)

    payload = UltraReviewService(tmp_path).run(
        report_path="reports/ultra.json",
        sandbox_root="reports/sandboxes",
    )

    assert payload["gate_passed"] is False
    assert payload["ghost_regression"]["timeout"] is True
    finding = payload["findings"][0]
    assert finding["rule_id"] == "regression_test_timeout"
    assert finding["state"] == "VERIFIED_FINDING"


def test_ultra_review_logic_breaker_failure_becomes_verified_finding(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "nexus" / "engine" / "sample.py").write_text("VALUE = 2\n", encoding="utf-8")

    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[:4] == ["uv", "run", "--active", "python"] and str(cmd[4]).endswith("ultra_logic_repro.py"):
            return subprocess.CompletedProcess(cmd, 1, stdout="logic failed", stderr="edge mismatch")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", fake_run)

    payload = UltraReviewService(tmp_path).run(
        report_path="reports/ultra.json",
        sandbox_root="reports/sandboxes",
    )

    assert payload["gate_passed"] is False
    assert payload["logic_breaker"]["passed"] is False
    finding = payload["findings"][0]
    assert finding["lane"] == "logic_breaker"
    assert finding["rule_id"] == "logic_repro_failed"
    assert finding["state"] == "VERIFIED_FINDING"
    assert finding["repro_command"]


def test_security_sentry_covers_shell_and_delete_rules(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "nexus" / "engine" / "sample.py").write_text(
        "import shutil\n"
        "import subprocess\n"
        "subprocess.run('echo ok', shell=True)\n"
        "shutil.rmtree('/tmp/nexus-delete-me', ignore_errors=True)\n",
        encoding="utf-8",
    )

    payload = UltraReviewService(tmp_path).run(
        report_path="reports/ultra.json",
        sandbox_root="reports/sandboxes",
    )

    rule_ids = {finding["rule_id"] for finding in payload["findings"]}
    assert {"shell_true_subprocess", "unsafe_delete"} <= rule_ids


def test_changed_files_preserves_paths_with_spaces(tmp_path):
    service = UltraReviewService(tmp_path)
    diff_text = "diff --git a/docs/Ops - Learning Closure Matrix.md b/docs/Ops - Learning Closure Matrix.md\n"

    assert service._changed_files(diff_text) == ["docs/Ops - Learning Closure Matrix.md"]


def test_ultra_review_filters_runtime_artifacts_from_diff_and_status(tmp_path):
    _init_repo(tmp_path)
    runtime_file = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text('{"status":"old"}\n', encoding="utf-8")
    swarm_db = tmp_path / ".nexus-swarm-001" / "swarmtasks.db"
    swarm_db.parent.mkdir(parents=True)
    swarm_db.write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "add runtime artifacts"], cwd=tmp_path, check=True, capture_output=True)

    runtime_file.write_text('{"status":"new"}\n', encoding="utf-8")
    swarm_db.write_text("new\n", encoding="utf-8")
    (tmp_path / ".nexus" / "reports" / "bench" / "run.json").parent.mkdir(parents=True)
    (tmp_path / ".nexus" / "reports" / "bench" / "run.json").write_text("{}\n", encoding="utf-8")

    payload = UltraReviewService(tmp_path).run(
        report_path=".nexus/reports/ultra_review_report.json",
        sandbox_root=".nexus/reports/ultra_review/sandboxes",
    )

    assert payload["gate_passed"] is True
    assert payload["diff"]["changed_files"] == []
    assert payload["diff"]["has_worktree_delta"] is False
    diff_text = (tmp_path / payload["artifacts"]["diff"]).read_text(encoding="utf-8")
    assert ".nexus/reports" not in diff_text
    assert ".nexus-swarm-001" not in diff_text


def test_ultra_review_logic_repro_handles_changed_paths_with_spaces(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "Ops - Learning Closure Matrix.md").write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "add docs"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "docs" / "Ops - Learning Closure Matrix.md").write_text("after\n", encoding="utf-8")

    payload = UltraReviewService(tmp_path).run(
        report_path="reports/ultra.json",
        sandbox_root="reports/sandboxes",
    )

    assert payload["gate_passed"] is True
    assert payload["logic_breaker"]["passed"] is True


def test_ultra_review_cli_help_includes_contract_options():
    runner = CliRunner()
    result = runner.invoke(cli_mod.nexus, ["nexus", "ultra-review", "--help"])

    assert result.exit_code == 0, result.output
    assert "--dry-run / --no-dry-run" in result.output
    assert "--report-file" in result.output
    assert "--sandbox-root" in result.output


def test_ultra_review_cli_outputs_json(monkeypatch, tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "nexus" / "engine" / "sample.py").write_text("VALUE = 3\n", encoding="utf-8")
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "ultra-review",
            "--task",
            "review cli route",
            "--report-file",
            str(tmp_path / "ultra.json"),
            "--sandbox-root",
            str(tmp_path / "sandboxes"),
            "--output-json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["task"] == "review cli route"
    assert payload["gate_passed"] is True
