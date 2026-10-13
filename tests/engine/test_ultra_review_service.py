import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from nexus.engine.ultra_review_service import UltraReviewService, os_sandbox_available

# The ghost-regression lane executes PR-controlled tests only behind an OS barrier
# (macOS sandbox-exec); elsewhere it refuses and the lane fails closed.
OS_SANDBOX = os_sandbox_available()
requires_os_sandbox = pytest.mark.skipif(not OS_SANDBOX, reason="needs macOS sandbox-exec")


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
    assert payload["gate_passed"] is False  # dry-run never verifies
    assert payload["status"] == ("DRY_RUN_NOT_VERIFIED" if OS_SANDBOX else "DRY_RUN_FAIL")
    assert payload["diff"]["has_worktree_delta"] is True
    assert "nexus/engine/sample.py" in payload["diff"]["changed_files"]
    assert (tmp_path / "reports" / "sandboxes" / payload["run_id"] / "changes.diff").exists()
    assert (tmp_path / "reports" / "sandboxes" / payload["run_id"] / "progress.jsonl").exists()
    assert payload["artifacts"]["progress_log"].endswith("progress.jsonl")
    assert payload["sandbox_mirror"]["strategy"] == "git_worktree"
    assert payload["sandbox_mirror"]["diff_applied"] is True
    assert payload["sandbox_mirror"]["untracked_overlay_count"] == 1
    assert payload["summary"]["logic_breaker_passed"] is True
    assert payload["summary"]["ghost_regression_passed"] is OS_SANDBOX
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
    if OS_SANDBOX:
        assert ghost["executed_checks"] == ["tests/engine/test_sample.py"]
        assert ghost["status"] == "PASS"
        assert payload["ghost_regression"]["passed"] is True
        assert payload["ghost_regression"]["executed_tests"] == ["tests/engine/test_sample.py"]
        assert payload["ghost_regression"]["execution_mode"] == "sandbox_mirror"
    else:
        assert ghost["executed_checks"] == []
        assert ghost["status"] == "FAIL"
        assert payload["ghost_regression"]["blocked_reason"] == "no_os_barrier"
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
    assert logic_lane["executed_checks"] == [
        "ultra_logic_repro.py",
        "path-containment",
        "test-harness-guard",
        "py_compile",
        "ruff-correctness",
    ]
    security_lane = next(item for item in payload["fleet"] if item["lane"] == "security_sentry")
    assert security_lane["executed_checks"] == ["diff-pattern-scan", "bandit", "ruff-security"]
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

    assert payload["gate_passed"] is False  # dry-run never verifies
    assert payload["sandbox_mirror"]["strategy"] == "copytree"
    assert payload["sandbox_mirror"]["fallback_reason"] == "worktree unavailable"


def test_ultra_review_copytree_ignores_dangling_runtime_symlinks(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    dangling = tmp_path / ".runtime" / "missing-state.json"
    dangling.parent.mkdir()
    dangling.symlink_to(tmp_path / "outside" / "missing-state.json")
    (tmp_path / "nexus" / "engine" / "sample.py").write_text("VALUE = 2\n", encoding="utf-8")

    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "worktree", "add"]:
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="worktree unavailable")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", fake_run)

    execution_root = tmp_path / "copy"
    UltraReviewService(tmp_path)._copy_execution_workspace(execution_root, tmp_path / "sandbox")

    copied_link = execution_root / ".runtime" / "missing-state.json"
    assert not copied_link.exists()
    assert not copied_link.is_symlink()


def test_ultra_review_worktree_mirror_keeps_empty_diff_fast_path(tmp_path):
    _init_repo(tmp_path)

    payload = UltraReviewService(tmp_path).run(
        report_path=".nexus/reports/ultra_review_report.json",
        sandbox_root=".nexus/reports/ultra_review/sandboxes",
    )

    assert payload["gate_passed"] is False  # dry-run never verifies
    assert payload["sandbox_mirror"]["strategy"] == "git_worktree"
    assert payload["sandbox_mirror"]["empty_diff"] is True


def test_ultra_review_can_reuse_worktree_in_benchmark_mode(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setenv("NEXUS_ULTRA_REUSE_WORKTREE", "1")
    (tmp_path / "nexus" / "engine" / "sample.py").write_text("VALUE = 2\n", encoding="utf-8")

    first = UltraReviewService(tmp_path).run(
        report_path="reports/ultra_first.json",
        sandbox_root="reports/sandboxes",
    )
    assert first["sandbox_mirror"]["strategy"] == "git_worktree_reuse"
    assert first["sandbox_mirror"]["reused"] is False

    (tmp_path / "nexus" / "engine" / "sample.py").write_text("VALUE = 3\n", encoding="utf-8")
    second = UltraReviewService(tmp_path).run(
        report_path="reports/ultra_second.json",
        sandbox_root="reports/sandboxes",
    )
    assert second["sandbox_mirror"]["strategy"] == "git_worktree_reuse"
    assert second["sandbox_mirror"]["reused"] is True


def test_ultra_review_can_skip_ghost_regression_via_env(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setenv("NEXUS_ULTRA_SKIP_GHOST_REGRESSION", "1")
    (tmp_path / "tests" / "engine").mkdir(parents=True)
    (tmp_path / "tests" / "engine" / "test_sample.py").write_text("def test_sample():\n    assert False\n", encoding="utf-8")
    (tmp_path / "nexus" / "engine" / "sample.py").write_text("VALUE = 2\n", encoding="utf-8")

    payload = UltraReviewService(tmp_path).run(
        report_path="reports/ultra_skip_ghost.json",
        sandbox_root="reports/sandboxes",
    )
    assert payload["ghost_regression"]["execution_mode"] == "skipped_by_env"
    assert payload["ghost_regression"]["passed"] is True
    assert payload["ghost_regression"]["executed_tests"] == []

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
        if "ultra_security_repro_" in str(cmd[-1]):
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
    if not OS_SANDBOX:
        # Without an OS barrier the failing test is never executed: fail closed, no finding.
        assert payload["ghost_regression"]["blocked_reason"] == "no_os_barrier"
        return
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
        if "pytest" in cmd and "-q" in cmd:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30, output="running", stderr="timeout")
        if cmd[:1] == ["sandbox-exec"] and not OS_SANDBOX:
            cmd = cmd[3:]
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", fake_run)
    monkeypatch.setattr("nexus.engine.ultra_review_service.os_sandbox_available", lambda: True)

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
        if str(cmd[-1]).endswith("ultra_logic_repro.py"):
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

    assert payload["gate_passed"] is False  # dry-run never verifies
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

    assert payload["gate_passed"] is False  # dry-run never verifies
    assert payload["logic_breaker"]["passed"] is True


def test_ultra_review_logic_repro_accepts_deleted_files(tmp_path):
    _init_repo(tmp_path)
    target = tmp_path / "docs" / "obsolete.md"
    target.parent.mkdir()
    target.write_text("remove me\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "add obsolete doc"], cwd=tmp_path, check=True, capture_output=True)
    target.unlink()

    payload = UltraReviewService(tmp_path).run(
        report_path="reports/ultra.json",
        sandbox_root="reports/sandboxes",
    )

    assert payload["gate_passed"] is False  # dry-run never verifies
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
    assert payload["gate_passed"] is False  # dry-run never verifies


def _init_app_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    (path / "app.py").write_text("def handler(value):\n    return value.strip()\n", encoding="utf-8")
    (path / "tests").mkdir()
    (path / "tests" / "test_app.py").write_text(
        "from app import handler\n\n\ndef test_handler_strips():\n    assert handler('  a ') == 'a'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


@requires_os_sandbox
def test_ultra_review_review_mode_flags_eval_and_failing_test(tmp_path):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return value\n\n\ndef unsafe():\n    return eval(input())\n",
        encoding="utf-8",
    )

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["mode"] == "review"
    assert payload["status"] == "FAIL"
    assert payload["gate_passed"] is False
    rules = {(f["lane"], f["rule_id"]) for f in payload["findings"]}
    assert ("security_sentry", "bandit:B307") in rules
    assert ("ghost_regression", "regression_test_failed") in rules
    security = payload["security_sentry"]
    assert security["passed"] is False
    assert security["executed_checks"] == ["diff-pattern-scan", "bandit", "ruff-security"]
    eval_finding = next(f for f in payload["findings"] if f["rule_id"] == "bandit:B307")
    assert eval_finding["file"] == "app.py" and eval_finding["line"] == 6
    assert "ruff:S307" in eval_finding.get("corroborated_by", [])
    assert payload["ghost_regression"]["executed_tests"] == ["tests/test_app.py"]
    # the per-run git worktree registration is removed in review mode
    assert payload["worktree_cleanup"]["removed"] is True
    listed = subprocess.run(["git", "worktree", "list"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert len(listed.strip().splitlines()) == 1


@requires_os_sandbox
def test_ultra_review_review_mode_passes_clean_change(tmp_path):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return value.strip()\n\n\ndef shout(value):\n    return handler(value).upper()\n",
        encoding="utf-8",
    )

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["status"] == "PASS"
    assert payload["gate_passed"] is True
    assert payload["findings"] == []
    lanes = {item["lane"]: item for item in payload["fleet"]}
    assert lanes["security_sentry"]["executed_checks"] == ["diff-pattern-scan", "bandit", "ruff-security"]
    assert lanes["ghost_regression"]["executed_checks"] == ["tests/test_app.py"]


def test_ultra_review_review_mode_logic_breaker_flags_undefined_name(tmp_path):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return value.strip()\n\n\ndef broken():\n    return missing_name\n",
        encoding="utf-8",
    )

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["gate_passed"] is False
    assert payload["logic_breaker"]["passed"] is False
    assert any(f["rule_id"] == "ruff:F821" for f in payload["findings"])


def test_ultra_review_review_mode_empty_diff_fails_closed(tmp_path):
    _init_app_repo(tmp_path)

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["status"] == "BLOCKED"
    assert payload["blocked_reason"] == "no_diff_to_review"
    assert payload["gate_passed"] is False


def test_ultra_review_review_mode_missing_tool_fails_closed(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # ok\n", encoding="utf-8")
    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if "bandit" in cmd and "-m" in cmd:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="No module named bandit")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", fake_run)
    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["status"] == "BLOCKED"
    assert payload["blocked_reason"] == "check_tool_unavailable:security_sentry"
    assert "bandit" not in payload["security_sentry"]["executed_checks"]
    assert payload["gate_passed"] is False


def test_ultra_review_outside_git_repo_fails_closed_without_raising(tmp_path):
    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["status"] == "BLOCKED"
    assert payload["gate_passed"] is False
    assert "UltraReviewError" in payload["blocked_reason"]


def test_ultra_review_refuses_nested_review_from_its_own_test_run(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_IN_PROGRESS", "1")

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["status"] == "BLOCKED"
    assert "nested_ultra_review_refused" in payload["blocked_reason"]


def test_ultra_review_review_mode_without_os_sandbox_refuses_to_run_pr_tests(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    marker = tmp_path.parent / f"{tmp_path.name}_escape_marker.txt"
    (tmp_path / "tests" / "test_app.py").write_text(
        "from pathlib import Path\n\n\ndef test_escape():\n"
        f"    Path({str(marker)!r}).write_text('escaped')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX", "1")

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["status"] == "BLOCKED"
    assert payload["blocked_reason"] == "ghost_regression_not_executed:no_os_barrier"
    assert payload["gate_passed"] is False
    assert payload["ghost_regression"]["executed_tests"] == []
    assert payload["isolation"]["barrier"] == "none"
    assert not marker.exists()


@requires_os_sandbox
def test_ultra_review_contains_a_diff_that_escapes_the_sandbox(tmp_path, monkeypatch):
    """A PR test that writes outside the worktree, reads credentials and calls the network
    is contained (no write, no token, no connection) and reported as a failing test."""
    _init_app_repo(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_super_secret_value")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    marker = tmp_path.parent / f"{tmp_path.name}_escape_marker.txt"
    (tmp_path / "tests" / "test_app.py").write_text(
        "import json, os, socket\n"
        "from pathlib import Path\n\n\n"
        "def test_env_is_scrubbed():\n"
        "    seen = {k: v for k, v in os.environ.items() if 'TOKEN' in k or 'KEY' in k}\n"
        "    Path('env_seen.json').write_text(json.dumps(seen))\n\n\n"
        "def test_escape_write():\n"
        f"    Path({str(marker)!r}).write_text('escaped')\n\n\n"
        "def test_escape_ssh_read():\n"
        "    open(os.path.expanduser('~/.ssh/nexus-owner-deletion.pub')).read()\n\n\n"
        "def test_escape_home_read():\n"
        "    [p.read_bytes() for p in Path(os.path.expanduser('~')).glob('.*rc') if p.is_file()]\n"
        "    assert list(Path(os.path.expanduser('~')).glob('.*rc'))\n\n\n"
        "def test_escape_network():\n"
        "    socket.create_connection(('1.1.1.1', 443), timeout=3)\n",
        encoding="utf-8",
    )
    payload = UltraReviewService(tmp_path).run(
        dry_run=True, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["isolation"]["barrier"] == "macos_sandbox_exec"
    assert payload["gate_passed"] is False
    assert not marker.exists()
    ghost = payload["ghost_regression"]
    assert ghost["passed"] is False
    assert any(f["rule_id"] == "regression_test_failed" for f in payload["findings"])
    tail = ghost["pytest_stdout_tail"]
    assert "test_escape_write" in tail and "test_escape_network" in tail
    assert "test_escape_ssh_read" in tail  # denied (or absent) either way: never readable
    assert "test_escape_home_read" in tail
    assert "PermissionError" in tail or "Operation not permitted" in tail
    seen = json.loads((Path(payload["sandbox_path"]) / "worktree" / "env_seen.json").read_text())
    assert seen == {}


@requires_os_sandbox
def test_ultra_review_ghost_lane_timeout_fails_the_gate_closed(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "import time\n\n\ndef handler(value):\n    time.sleep(30)\n    return value.strip()\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("nexus.engine.ultra_review_service.GHOST_REGRESSION_TIMEOUT_SEC", 3)

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["ghost_regression"]["timeout"] is True
    assert payload["gate_passed"] is False
    assert payload["status"] == "FAIL"
    assert any(f["rule_id"] == "regression_test_timeout" for f in payload["findings"])


def test_ultra_review_tool_timeout_fails_the_gate_closed(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")
    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if "bandit" in cmd:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", fake_run)
    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["gate_passed"] is False
    assert payload["status"] == "BLOCKED"
    assert payload["blocked_reason"] == "check_tool_unavailable:security_sentry"
    assert payload["security_sentry"]["unavailable_checks"][0]["timeout"] is True


def test_ultra_review_review_mode_ghost_skip_env_cannot_pass(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")
    monkeypatch.setenv("NEXUS_ULTRA_SKIP_GHOST_REGRESSION", "1")

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["gate_passed"] is False
    assert payload["blocked_reason"] == "ghost_regression_not_executed:skipped_by_env"


def test_ultra_review_review_mode_without_mapped_tests_cannot_pass(tmp_path):
    _init_app_repo(tmp_path)
    (tmp_path / "other.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "other.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "other"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "other.py").write_text("VALUE = 2\n", encoding="utf-8")

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["gate_passed"] is False
    assert payload["blocked_reason"] == "ghost_regression_not_executed:no_mapped_tests"


def test_ultra_review_flags_test_harness_changes(tmp_path):
    _init_app_repo(tmp_path)
    (tmp_path / "conftest.py").write_text(
        "def pytest_runtest_makereport(item, call):\n    pass\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "conftest.py"], cwd=tmp_path, check=True)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["gate_passed"] is False
    assert any(f["rule_id"] == "test_harness_modified" for f in payload["findings"])


def _write_marker_shadows(root, marker):
    # Files named like stdlib / tool modules: imported only if PR code reaches an interpreter.
    body = f"open({str(marker)!r}, 'w').write('executed')\n"
    for name in ("re.py", "json.py", "bandit.py", "ruff.py", "py_compile.py", "sitecustomize.py"):
        (root / name).write_text(body, encoding="utf-8")


def test_ultra_review_without_os_barrier_executes_no_pr_code(tmp_path, monkeypatch):
    """Linux-CI shape: no barrier -> the PR's tests never run, static tools run isolated (-I)
    so PR files shadowing stdlib/tool modules are never imported, and the gate fails closed."""
    _init_app_repo(tmp_path)
    marker = tmp_path.parent / f"{tmp_path.name}_pr_code_ran.txt"
    _write_marker_shadows(tmp_path, marker)
    for name in ("re.py", "json.py", "bandit.py", "ruff.py", "py_compile.py", "sitecustomize.py"):
        subprocess.run(["git", "add", name], cwd=tmp_path, check=True)
    (tmp_path / "tests" / "test_app.py").write_text(
        f"from pathlib import Path\n\n\ndef test_x():\n    Path({str(marker)!r}).write_text('test ran')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_should_not_leak")

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert not marker.exists()
    assert payload["gate_passed"] is False
    assert payload["blocked_reason"] == "ghost_regression_not_executed:no_os_barrier"
    assert payload["ghost_regression"]["executed_tests"] == []
    assert {"bandit", "ruff-security"} <= set(payload["security_sentry"]["executed_checks"])
    assert payload["isolation"]["barrier"] == "none"


def test_ultra_review_sandbox_env_is_scrubbed_and_cwd_is_the_sandbox(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_should_not_leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    seen = []
    original_run = subprocess.run

    def spy(cmd, **kwargs):
        if kwargs.get("env") is not None:
            seen.append((list(cmd), dict(kwargs["env"]), str(kwargs.get("cwd")), kwargs.get("shell")))
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", spy)
    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert seen, "lane subprocesses must run through the sandbox runner"
    for cmd, env, cwd, shell in seen:
        assert shell is None
        assert "GITHUB_TOKEN" not in env and "ANTHROPIC_API_KEY" not in env
        assert env["HOME"].startswith(payload["sandbox_path"])
        assert cwd.startswith(payload["sandbox_path"])
        assert "-I" in cmd  # static tools / repro scripts never import from the PR tree


def test_disable_os_sandbox_env_never_grants_a_barrier(monkeypatch):
    import nexus.engine.ultra_review_service as svc

    monkeypatch.setitem(svc._OS_SANDBOX_PROBE, "sandbox-exec", True)
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX", "1")
    assert svc.os_sandbox_available() is False
    monkeypatch.setitem(svc._OS_SANDBOX_PROBE, "sandbox-exec", False)
    for value in ("0", "", "false", "no"):
        monkeypatch.setenv("NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX", value)
        assert svc.os_sandbox_available() is False


def test_ultra_review_symlink_in_diff_pointing_outside_is_not_scanned_and_fails(tmp_path):
    _init_app_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}_outside_secret.py"
    outside.write_text("API" + "_KEY = 'outside-secret-123456'\n", encoding="utf-8")
    (tmp_path / "evil.py").symlink_to(outside)
    subprocess.run(["git", "add", "evil.py"], cwd=tmp_path, check=True)

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["gate_passed"] is False
    assert any(
        f["rule_id"] == "path_outside_worktree" and f["file"] == "evil.py" for f in payload["findings"]
    )
    assert "evil.py" not in payload["security_sentry"]["scanned_python_files"]
    assert "outside-secret" not in json.dumps(payload)


def test_ultra_review_untracked_symlink_is_not_copied_into_the_sandbox(tmp_path):
    _init_app_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}_outside_key.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "leak.txt").symlink_to(outside)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")

    payload = UltraReviewService(tmp_path).run(
        dry_run=True, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    mirror = Path(payload["sandbox_path"]) / "worktree"
    assert not (mirror / "leak.txt").exists()


def test_ultra_review_dotdot_paths_are_never_inside_the_worktree(tmp_path):
    service = UltraReviewService(tmp_path)
    root = tmp_path / "wt"
    (root / "pkg").mkdir(parents=True)
    (tmp_path / "outside.py").write_text("x = 1\n", encoding="utf-8")
    diff = "diff --git a/../outside.py b/../outside.py\n+++ b/../outside.py\n@@ -0,0 +1 @@\n+x = 1\n"
    assert service._changed_python_files(diff, root) == []
    assert service._uncontained_changed_files(diff, root) == ["../outside.py"]
    assert service._contained_path("pkg/../../outside.py", root) is None
