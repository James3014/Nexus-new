import json
import os
import subprocess
from pathlib import Path

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from nexus.engine.ultra_review_service import UltraReviewService, os_sandbox_available

# The ghost-regression lane executes PR-controlled tests only behind an OS barrier
# (macOS sandbox-exec); elsewhere it refuses and the lane fails closed.
OS_SANDBOX = os_sandbox_available()


def _assert_no_barrier_fail_closed(payload):
    """Without an OS barrier (every Linux CI runner) the PR's tests never run and the gate
    fails closed. Sandbox-dependent tests assert this instead of skipping, so they pass
    (and prove the no-barrier contract) on every platform."""
    assert payload["isolation"]["barrier"] == "none"
    assert payload["gate_passed"] is False
    assert payload["ghost_regression"]["executed_tests"] == []
    if payload["mode"] == "review":
        assert payload["blocked_reason"] == "ghost_regression_not_executed:no_os_barrier"


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
    assert payload["ghost_regression"]["timeout_sec"] == 300
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
        if cmd and os.path.basename(cmd[0]) == "sandbox-exec" and not OS_SANDBOX:
            cmd = cmd[3:]
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", fake_run)
    monkeypatch.setattr("nexus.engine.ultra_review_service.os_sandbox_available", lambda: True)

    payload = UltraReviewService(tmp_path).run(
        report_path="reports/ultra.json",
        sandbox_root="reports/sandboxes",
    )

    # Name kept for test-id stability: since #2623 a timeout is inconclusive, not a finding.
    assert payload["gate_passed"] is False
    assert payload["ghost_regression"]["timeout"] is True
    finding = payload["findings"][0]
    assert finding["rule_id"] == "regression_test_timeout"
    assert finding["state"] == "INCONCLUSIVE_TIMEOUT"
    assert finding["severity"] == "info"


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


def test_ultra_review_review_mode_flags_eval_and_failing_test(tmp_path):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return value\n\n\ndef unsafe():\n    return eval(input())\n",
        encoding="utf-8",
    )

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    if not OS_SANDBOX:
        _assert_no_barrier_fail_closed(payload)
        assert any(f["rule_id"] == "bandit:B307" for f in payload["findings"])
        return
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


def test_ultra_review_review_mode_passes_clean_change(tmp_path):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return value.strip()\n\n\ndef shout(value):\n    return handler(value).upper()\n",
        encoding="utf-8",
    )

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    if not OS_SANDBOX:
        _assert_no_barrier_fail_closed(payload)
        return
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

    assert not marker.exists()
    if not OS_SANDBOX:
        _assert_no_barrier_fail_closed(payload)
        assert not (Path(payload["sandbox_path"]) / "worktree" / "env_seen.json").exists()
        return
    assert payload["isolation"]["barrier"] == "macos_sandbox_exec"
    assert payload["gate_passed"] is False
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

    if not OS_SANDBOX:
        _assert_no_barrier_fail_closed(payload)
        return
    # The gate still does not pass, but a timeout is INCONCLUSIVE, not FAIL (#2623).
    assert payload["ghost_regression"]["timeout"] is True
    assert payload["gate_passed"] is False
    assert payload["status"] == "INCONCLUSIVE"
    timeout_finding = next(f for f in payload["findings"] if f["rule_id"] == "regression_test_timeout")
    assert timeout_finding["state"] == "INCONCLUSIVE_TIMEOUT"


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

    # Name kept for test-id stability: since #2623 no mapped tests is an advisory UNCOVERED
    # result, never a block on its own.
    assert payload["blocked_reason"] == ""
    assert payload["status"] == "PASS"
    uncovered = next(f for f in payload["findings"] if f["rule_id"] == "no_mapped_tests")
    assert uncovered["state"] == "UNCOVERED"
    assert uncovered["unmapped_paths"] == ["other.py"]


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
        if cmd[0] == "git":
            # Review git calls (mirror setup) run with a scrubbed env, sandbox HOME and no
            # system/global config; they are not lane commands.
            assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_CONFIG_GLOBAL"] == os.devnull
            continue
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


SBPL_INJECTION_NAME = 'x") (allow default) ("'


def test_sbpl_path_rejects_policy_injection_and_relative_paths(tmp_path):
    import pytest

    from nexus.engine.ultra_review_service import UltraReviewError, sbpl_path

    for bad in (
        str(tmp_path / SBPL_INJECTION_NAME),
        str(tmp_path / "a)b"),
        str(tmp_path / 'q"q'),
        str(tmp_path / "back\\slash"),
        str(tmp_path / "new\nline"),
        "relative/path",
        "",
    ):
        with pytest.raises(UltraReviewError):
            sbpl_path(bad)
    assert sbpl_path(tmp_path) == str(tmp_path.resolve())


def test_ultra_review_sandbox_root_with_sbpl_injection_fails_closed(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()\n", encoding="utf-8")
    seen = []
    original_run = subprocess.run

    def spy(cmd, **kwargs):
        seen.append(list(cmd))
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", spy)
    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root=f"reports/{SBPL_INJECTION_NAME}"
    )

    assert payload["status"] == "BLOCKED"
    assert payload["gate_passed"] is False
    assert "sandbox_path_unsafe_for_policy" in payload["blocked_reason"]
    assert not any(cmd and os.path.basename(cmd[0]) == "sandbox-exec" and "-p" in cmd[1:2] for cmd in seen)
    assert not any("(allow default)" in " ".join(cmd) for cmd in seen if cmd and cmd[0] != "git")


def _bound_service(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    service = UltraReviewService(root)
    sandbox = root / ".nexus" / "sandbox"
    execution_root = sandbox / "worktree"
    execution_root.mkdir(parents=True)
    service._bind_sandbox(sandbox_path=sandbox, execution_root=execution_root)
    return service, sandbox, execution_root


def test_sandbox_profile_reads_are_default_deny_and_home_denied_before_allows(tmp_path):
    service, sandbox, _ = _bound_service(tmp_path)
    lines = service._sandbox_profile().splitlines()
    home = str(Path("~").expanduser().resolve())

    assert "(allow file-read*)" not in lines  # no blanket read grant
    assert "(allow default)" not in lines
    home_deny = lines.index(f'(deny file-read* (subpath "{home}"))')
    first_allow = next(i for i, line in enumerate(lines) if line.startswith("(allow file-read* "))
    read_allow = next(i for i, line in enumerate(lines) if line.startswith("(allow file-read* (subpath "))
    assert home_deny < first_allow <= read_allow
    assert '(subpath "/")' not in lines[read_allow]
    assert '(subpath "/Users")' not in lines[read_allow]
    assert f'(subpath "{home}")' not in lines[read_allow]
    assert f'(subpath "{sandbox.resolve()}")' in lines[read_allow]
    # Credential stores are denied again after every allow (last match wins).
    assert lines[-1].startswith("(deny file-read* ") and f"{home}/.ssh" in lines[-1]


def test_sandboxed_run_pins_cwd_interpreter_and_isolation(tmp_path, monkeypatch):
    import sys

    import pytest

    from nexus.engine.ultra_review_service import UltraReviewError

    service, sandbox, execution_root = _bound_service(tmp_path)
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX", "1")
    with pytest.raises(UltraReviewError, match="lane_cwd_outside_sandbox"):
        service._sandboxed_run([sys.executable, "-I", "-c", "pass"], cwd=tmp_path, timeout=10)
    with pytest.raises(UltraReviewError, match="python_lane_not_isolated"):
        service._sandboxed_run([sys.executable, "-c", "pass"], cwd=execution_root, timeout=10)
    monkeypatch.setattr(sys, "executable", str(execution_root / "bin" / "python"))
    with pytest.raises(UltraReviewError, match="interpreter_inside_reviewed_tree"):
        service._sandboxed_run([sys.executable, "-I", "-c", "pass"], cwd=execution_root, timeout=10)


def test_sandbox_env_path_never_points_into_reviewed_tree(tmp_path, monkeypatch):
    service, sandbox, execution_root = _bound_service(tmp_path)
    monkeypatch.setenv("PATH", f"{execution_root}/bin:{service.project_root}/bin:relative/bin:/usr/bin:/bin")
    monkeypatch.setenv("PYTHONPATH", str(execution_root))
    env = service._sandbox_env()

    assert env["PATH"].split(":") == ["/usr/bin", "/bin"]
    assert "PYTHONPATH" not in env


def test_mirror_writes_never_follow_pr_symlinks(tmp_path):
    from nexus.engine.ultra_review_service import _write_no_follow

    service, sandbox, execution_root = _bound_service(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    (execution_root / "changes.diff").symlink_to(victim)
    _write_no_follow(execution_root / "changes.diff", b"diff")
    assert victim.read_text(encoding="utf-8") == "keep"
    assert not (execution_root / "changes.diff").is_symlink()

    (execution_root / "linked_dir").symlink_to(outside, target_is_directory=True)
    assert service._target_inside(execution_root / "linked_dir" / "new.txt", execution_root) is False
    assert service._target_inside(execution_root / "pkg" / "new.txt", execution_root) is True


def test_untracked_overlay_does_not_write_through_a_mirror_symlink(tmp_path):
    _init_app_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}_overlay_outside"
    outside.mkdir()
    service = UltraReviewService(tmp_path)
    sandbox = tmp_path / "reports" / "sbx"
    execution_root = sandbox / "worktree"
    execution_root.mkdir(parents=True)
    (execution_root / "drop").symlink_to(outside, target_is_directory=True)
    (tmp_path / "drop").mkdir()
    (tmp_path / "drop" / "payload.txt").write_text("x", encoding="utf-8")

    service._overlay_untracked_files(execution_root, sandbox_path=sandbox)

    assert not (outside / "payload.txt").exists()


def test_review_git_calls_never_run_hooks_filters_or_global_config(tmp_path, monkeypatch):
    """sandbox-escape-git-config: hooks, in-tree .gitattributes filters and user/global
    config never execute anything during mirror setup, diff capture or apply."""
    _init_app_repo(tmp_path)
    marker_dir = tmp_path.parent / f"{tmp_path.name}_git_markers"
    marker_dir.mkdir()
    hooks = tmp_path.parent / f"{tmp_path.name}_hooks"
    hooks.mkdir()
    for hook in ("post-checkout", "pre-commit", "post-index-change"):
        script = hooks / hook
        script.write_text(f"#!/bin/sh\ntouch {marker_dir}/{hook}\n", encoding="utf-8")
        script.chmod(0o755)
    subprocess.run(["git", "config", "core.hooksPath", str(hooks)], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "filter.evil.smudge", f"sh -c 'touch {marker_dir}/smudge; cat'"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "filter.evil.clean", f"sh -c 'touch {marker_dir}/clean; cat'"], cwd=tmp_path, check=True
    )
    fake_home = tmp_path.parent / f"{tmp_path.name}_home"
    fake_home.mkdir()
    (fake_home / ".gitconfig").write_text(
        f"[core]\n\tfsmonitor = sh -c 'touch {marker_dir}/fsmonitor'\n", encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(fake_home))
    (tmp_path / ".gitattributes").write_text("*.py filter=evil\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitattributes"], cwd=tmp_path, check=True)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")
    for leftover in marker_dir.iterdir():
        leftover.unlink()

    service = UltraReviewService(tmp_path)
    service.run(dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes")

    assert sorted(path.name for path in marker_dir.iterdir()) == []
    env = service._git_env()
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert env["HOME"] != str(fake_home)
    assert not any(key.startswith("GIT_DIR") for key in env)


def test_mirror_git_dir_refuses_a_pr_supplied_git_entry(tmp_path):
    import pytest

    from nexus.engine.ultra_review_service import UltraReviewError

    _init_app_repo(tmp_path)
    service = UltraReviewService(tmp_path)
    fake = tmp_path / "mirror"
    (fake / ".git").mkdir(parents=True)  # a nested .git directory, not our worktree file
    with pytest.raises(UltraReviewError, match="mirror_git_dir_not_regular_file"):
        service._mirror_git_dir(fake)
    (fake / ".git").rmdir()
    (fake / ".git").write_text(f"gitdir: {tmp_path / 'elsewhere'}\n", encoding="utf-8")
    with pytest.raises(UltraReviewError, match="mirror_git_dir_outside_repository"):
        service._mirror_git_dir(fake)


def test_diff_policy_flags_symlink_modes_and_nested_git_paths():
    diff = "\n".join(
        [
            "diff --git a/link.py b/link.py",
            "new file mode 120000",
            "index 0000000..1111111",
            "diff --git a/old_link b/old_link",
            "index 2222222..3333333 120000",
            "diff --git a/became_link b/became_link",
            "old mode 100644",
            "new mode 120000",
            "diff --git a/pkg/.git/config b/pkg/.git/config",
            "new file mode 100644",
            "diff --git a/plain.py b/plain.py",
            "index 4444444..5555555 100644",
            "",
        ]
    )
    violations = UltraReviewService._diff_policy_violations(diff)
    assert violations["symlinks"] == ["link.py", "old_link", "became_link"]
    assert violations["nested_git"] == ["pkg/.git/config"]


def test_ultra_review_refuses_to_apply_a_patch_that_creates_a_symlink(tmp_path, monkeypatch):
    """sandbox-escape-symlink-follow: a diff creating a symlink is never applied (no git apply,
    no copy), the lane reports symlink_in_diff, and the gate fails closed."""
    _init_app_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}_outside_target.py"
    outside.write_text("SECRET_VALUE = 'never-read-by-review'\n", encoding="utf-8")
    (tmp_path / "link.py").symlink_to(outside)
    subprocess.run(["git", "add", "link.py"], cwd=tmp_path, check=True)
    seen = []
    original_run = subprocess.run

    def spy(cmd, **kwargs):
        seen.append(list(cmd))
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", spy)
    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["gate_passed"] is False
    assert payload["sandbox_mirror"]["strategy"] == "refused"
    assert payload["sandbox_mirror"]["symlinks"] == ["link.py"]
    # Only the read-only `git apply --summary` classification runs; nothing is applied.
    assert not any(
        (cmd[:2] == ["git", "apply"] and "--summary" not in cmd) or cmd[:3] == ["git", "worktree", "add"]
        for cmd in seen
    )
    rules = {(f["rule_id"], f["file"]) for f in payload["findings"]}
    assert ("symlink_in_diff", "link.py") in rules
    assert ("path_outside_worktree", "link.py") in rules
    assert not (Path(payload["sandbox_path"]) / "worktree" / "link.py").is_symlink()
    assert "never-read-by-review" not in json.dumps(payload)


def test_sandbox_read_roots_exclude_home_users_tmp_and_repo_root(tmp_path, monkeypatch):
    import sys

    import pytest

    from nexus.engine.ultra_review_service import UltraReviewError

    service, sandbox, execution_root = _bound_service(tmp_path)
    roots = service._sandbox_read_roots()
    home = str(Path("~").expanduser().resolve())
    temp_roots = (os.path.join(os.sep, "private", "tmp"), os.path.join(os.sep, "tmp"))
    for forbidden in ("/", "/Users", *temp_roots, home, str(service.project_root)):
        assert forbidden not in roots
    allowed_prefixes = (
        str(sandbox.resolve()),
        str(Path(sys.prefix).resolve()),
        str(Path(sys.base_prefix).resolve()),
        "/usr/lib",
        "/usr/share/zoneinfo",
        "/System/Library",
    )
    assert all(root.startswith(allowed_prefixes) for root in roots)
    profile = service._sandbox_profile()
    assert '(subpath "/usr/share")' not in profile and '(subpath "/dev")' not in profile
    assert '(literal "/dev/urandom")' in profile and '(literal "/private/etc/passwd")' in profile

    monkeypatch.setattr(sys, "prefix", home)
    with pytest.raises(UltraReviewError, match="sandbox_read_root_overbroad"):
        service._sandbox_read_roots()
    monkeypatch.setattr(sys, "prefix", temp_roots[0])
    with pytest.raises(UltraReviewError, match="sandbox_read_root_overbroad"):
        service._sandbox_read_roots()


RENAME_FROM_SYMLINK_PATCH = (
    "diff --git a/link.py b/renamed.py\n"
    "similarity index 100%\n"
    "rename from link.py\n"
    "rename to renamed.py\n"
)


def test_git_summary_refuses_rename_from_symlink_patch_even_if_hand_parser_misses(tmp_path):
    """parser-differential: git's own --summary rejects a rename/copy patch the hand parser
    never classifies as a symlink."""
    _init_app_repo(tmp_path)
    (tmp_path / "link.py").symlink_to(tmp_path / "app.py")
    subprocess.run(["git", "add", "link.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "link"], cwd=tmp_path, check=True)
    patch = tmp_path.parent / f"{tmp_path.name}_rename.diff"
    patch.write_text(RENAME_FROM_SYMLINK_PATCH, encoding="utf-8")
    service = UltraReviewService(tmp_path)

    assert service._diff_policy_violations(RENAME_FROM_SYMLINK_PATCH)["symlinks"] == []
    summary = service._unsafe_patch_summary(patch)
    assert summary and "rename" in summary[0]
    copy_patch = patch.with_name(patch.stem + "_copy.diff")
    copy_patch.write_text(RENAME_FROM_SYMLINK_PATCH.replace("rename", "copy"), encoding="utf-8")
    assert any("copy" in line for line in service._unsafe_patch_summary(copy_patch))


def _binary_symlink_patch(tmp_path, monkeypatch):
    """A crafted ``GIT binary patch`` whose new entry has mode 120000 (a symlink pointing
    outside the repo), served to the review as its captured diff."""
    _init_app_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}_bin_outside.txt"
    outside.write_text("binary-secret-content", encoding="utf-8")
    (tmp_path / ".gitattributes").write_text("blink -diff\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitattributes"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "attrs"], cwd=tmp_path, check=True)
    (tmp_path / "blink").write_text(str(outside), encoding="utf-8")
    subprocess.run(["git", "add", "blink"], cwd=tmp_path, check=True)
    diff = subprocess.run(
        ["git", "diff", "--cached", "--binary", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout
    subprocess.run(["git", "rm", "-q", "--cached", "blink"], cwd=tmp_path, check=True)
    (tmp_path / "blink").unlink()
    diff = diff.replace("new file mode 100644", "new file mode 120000")
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")
    monkeypatch.setattr(UltraReviewService, "_capture_diff", lambda self, base_ref: diff)
    return diff, outside


def test_binary_symlink_patch_is_refused_by_git_summary_without_the_hand_parser(tmp_path, monkeypatch):
    diff, _ = _binary_symlink_patch(tmp_path, monkeypatch)
    assert "GIT binary patch" in diff and "120000" in diff
    monkeypatch.setattr(
        UltraReviewService, "_diff_policy_violations", staticmethod(lambda text: {"symlinks": [], "nested_git": []})
    )

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["gate_passed"] is False
    assert payload["sandbox_mirror"]["strategy"] == "refused"
    assert any("create mode 120000" in line for line in payload["sandbox_mirror"]["git_summary"])
    assert any(f["rule_id"] == "unsafe_patch_summary" for f in payload["findings"])
    assert "binary-secret-content" not in json.dumps(payload)


def test_post_apply_lstat_walk_is_authoritative_when_both_patch_checks_are_bypassed(tmp_path, monkeypatch):
    """Even if the hand parser and git --summary both miss it, the applied mirror is walked
    with lstat; a link git created is unlinked and the lane fails closed."""
    diff, outside = _binary_symlink_patch(tmp_path, monkeypatch)
    monkeypatch.setattr(
        UltraReviewService, "_diff_policy_violations", staticmethod(lambda text: {"symlinks": [], "nested_git": []})
    )
    monkeypatch.setattr(UltraReviewService, "_unsafe_patch_summary", lambda self, path: [])

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    assert payload["gate_passed"] is False
    assert payload["sandbox_mirror"]["diff_applied"] is False
    assert payload["sandbox_mirror"]["post_apply_violations"] == ["blink"]
    assert any(f["rule_id"] == "mirror_link_or_escape" and f["file"] == "blink" for f in payload["findings"])
    assert not (Path(payload["sandbox_path"]) / "worktree" / "blink").is_symlink()
    assert outside.read_text(encoding="utf-8") == "binary-secret-content"
    assert "binary-secret-content" not in json.dumps(payload)


def test_post_apply_walk_allows_only_head_tracked_inside_symlinks(tmp_path):
    _init_app_repo(tmp_path)
    (tmp_path / "inside_link.py").symlink_to("app.py")
    subprocess.run(["git", "add", "inside_link.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "link"], cwd=tmp_path, check=True)
    service = UltraReviewService(tmp_path)
    mirror = tmp_path.parent / f"{tmp_path.name}_mirror"
    mirror.mkdir()
    (mirror / "app.py").write_text("x = 1\n", encoding="utf-8")
    (mirror / "inside_link.py").symlink_to("app.py")
    assert service._post_apply_violations(mirror) == []
    (mirror / "inside_link.py").unlink()
    (mirror / "inside_link.py").symlink_to("../elsewhere.py")
    (mirror / "new_link").symlink_to("app.py")
    assert sorted(service._post_apply_violations(mirror)) == ["inside_link.py", "new_link"]


def test_post_apply_walk_unlinks_head_tracked_symlinks_that_point_outside(tmp_path):
    _init_app_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}_head_outside.txt"
    outside.write_text("head-link-secret", encoding="utf-8")
    (tmp_path / "state.json").symlink_to(outside)
    subprocess.run(["git", "add", "state.json"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "runtime link"], cwd=tmp_path, check=True)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")

    payload = UltraReviewService(tmp_path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )

    mirror = payload["sandbox_mirror"]
    assert mirror["neutralized_head_links"] == ["state.json"]
    assert "post_apply_violations" not in mirror
    assert not any(f["rule_id"] == "mirror_link_or_escape" for f in payload["findings"])
    assert outside.read_text(encoding="utf-8") == "head-link-secret"
    assert "head-link-secret" not in json.dumps(payload)


# --- #2623: content-independent blocks --------------------------------------------------
# The ghost lane refuses to run PR tests without an OS barrier (Linux CI). These tests run
# trusted fixture tests only, so they lift that refusal; on macOS the real barrier still applies.
_ALWAYS_RED = "\n\ndef test_always_red():\n    assert False\n"


def _allow_ghost_run(monkeypatch):
    monkeypatch.setattr("nexus.engine.ultra_review_service.os_sandbox_available", lambda: True)


def _init_app_repo_with_red_test(path):
    _init_app_repo(path)
    with (path / "tests" / "test_app.py").open("a", encoding="utf-8") as handle:
        handle.write(_ALWAYS_RED)
    subprocess.run(["git", "commit", "-qam", "red test"], cwd=path, check=True, capture_output=True)


def _review(path, *, dry_run=False, service_kwargs=None, **kwargs):
    return UltraReviewService(path, **(service_kwargs or {})).run(
        dry_run=dry_run, report_path="reports/ultra.json", sandbox_root="reports/sandboxes", **kwargs
    )


def test_ultra_review_no_mapped_tests_is_advisory_uncovered(tmp_path):
    _init_app_repo(tmp_path)
    (tmp_path / "README.md").write_text("docs\n", encoding="utf-8")
    (tmp_path / "data.json").write_text("{}\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "docs"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "README.md").write_text("docs v2\n", encoding="utf-8")
    (tmp_path / "data.json").write_text('{"a": 1}\n', encoding="utf-8")

    payload = _review(tmp_path)

    assert payload["status"] == "PASS"
    assert payload["gate_passed"] is True
    assert payload["blocked_reason"] == ""
    assert payload["ghost_regression"]["coverage"] == "UNCOVERED"
    assert payload["ghost_regression"]["uncovered_paths"] == ["README.md", "data.json"]
    (uncovered,) = [f for f in payload["findings"] if f["lane"] == "ghost_regression"]
    assert (uncovered["state"], uncovered["severity"]) == ("UNCOVERED", "info")
    assert uncovered["unmapped_paths"] == ["README.md", "data.json"]
    assert payload["summary"]["verified_findings"] == 0
    assert _review(tmp_path, dry_run=True)["status"] == "DRY_RUN_NOT_VERIFIED"


def test_ultra_review_ghost_timeout_is_inconclusive_info_not_fail(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")
    original_run = subprocess.run
    seen_timeouts = []

    def fake_run(cmd, **kwargs):
        if "pytest" in cmd and "-q" in cmd:
            seen_timeouts.append(kwargs.get("timeout"))
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout") or 0, output="running")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", fake_run)
    _allow_ghost_run(monkeypatch)
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_TEST_TIMEOUT_SEC", "45")

    payload = _review(tmp_path)

    assert payload["status"] == "INCONCLUSIVE"
    assert payload["gate_passed"] is False
    assert payload["blocked_reason"] == ""
    assert seen_timeouts == [45.0]
    assert payload["ghost_regression"]["timeout_sec"] == 45.0
    assert payload["ghost_regression"]["inconclusive"] is True
    assert payload["summary"]["verified_findings"] == 0
    (finding,) = [f for f in payload["findings"] if f["lane"] == "ghost_regression"]
    assert (finding["state"], finding["severity"]) == ("INCONCLUSIVE_TIMEOUT", "info")
    assert "review mode" in finding["summary"] and "dry-run" not in finding["summary"]
    ghost = next(item for item in payload["fleet"] if item["lane"] == "ghost_regression")
    assert ghost["status"] == "INCONCLUSIVE"


def test_ultra_review_test_timeout_is_configurable(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_ULTRA_REVIEW_TEST_TIMEOUT_SEC", raising=False)
    assert UltraReviewService(tmp_path)._ghost_timeout_sec() == 300.0
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_TEST_TIMEOUT_SEC", "90")
    assert UltraReviewService(tmp_path)._ghost_timeout_sec() == 90.0
    assert UltraReviewService(tmp_path, test_timeout_sec=7)._ghost_timeout_sec() == 7.0
    for bad in ("abc", "0", "-5"):
        monkeypatch.setenv("NEXUS_ULTRA_REVIEW_TEST_TIMEOUT_SEC", bad)
        assert UltraReviewService(tmp_path)._ghost_timeout_sec() == 300.0
    try:
        UltraReviewService(tmp_path, test_timeout_sec=0)
    except ValueError:
        pass
    else:
        raise AssertionError("non-positive test_timeout_sec must be refused")


def test_ultra_review_test_failing_on_base_and_head_is_pre_existing(tmp_path, monkeypatch):
    _init_app_repo_with_red_test(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return value.strip()\n\n\ndef shout(value):\n    return handler(value).upper()\n",
        encoding="utf-8",
    )
    _allow_ghost_run(monkeypatch)

    payload = _review(tmp_path)

    ghost = payload["ghost_regression"]
    assert payload["status"] == "PASS", payload["findings"]
    assert payload["gate_passed"] is True
    assert ghost["failed_tests"] == []
    assert ghost["pre_existing_failures"] == ["tests/test_app.py::test_always_red"]
    assert ghost["base_comparison"]["base_returncode"] == 1
    (finding,) = [f for f in payload["findings"] if f["lane"] == "ghost_regression"]
    assert (finding["state"], finding["severity"]) == ("PRE_EXISTING_FAILURE", "info")
    # the base checkout is a temporary worktree: removed again after the comparison
    listed = subprocess.run(["git", "worktree", "list"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert "base_worktree" not in listed


def test_ultra_review_only_base_pass_head_fail_is_a_regression(tmp_path, monkeypatch):
    _init_app_repo_with_red_test(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value\n", encoding="utf-8")
    _allow_ghost_run(monkeypatch)

    payload = _review(tmp_path)

    ghost = payload["ghost_regression"]
    assert payload["status"] == "FAIL"
    assert payload["gate_passed"] is False
    assert ghost["failed_tests"] == ["tests/test_app.py::test_handler_strips"]
    assert ghost["pre_existing_failures"] == ["tests/test_app.py::test_always_red"]
    states = {f["rule_id"]: f for f in payload["findings"] if f["lane"] == "ghost_regression"}
    assert states["regression_test_failed"]["state"] == "VERIFIED_FINDING"
    assert states["regression_test_failed"]["tests"] == ["tests/test_app.py::test_handler_strips"]
    assert "review mode" in states["regression_test_failed"]["summary"]
    assert states["pre_existing_test_failure"]["state"] == "PRE_EXISTING_FAILURE"


def test_ultra_review_unpreparable_base_is_inconclusive_not_fail(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value\n", encoding="utf-8")
    _allow_ghost_run(monkeypatch)
    original_git_run = UltraReviewService._git_run

    def failing_base_checkout(self, args, **kwargs):
        if args[:2] == ["worktree", "add"] and str(args[3]).endswith("base_worktree"):
            return subprocess.CompletedProcess(args, 128, stdout="", stderr="fatal: no base")
        return original_git_run(self, args, **kwargs)

    monkeypatch.setattr(UltraReviewService, "_git_run", failing_base_checkout)

    payload = _review(tmp_path)

    assert payload["status"] == "INCONCLUSIVE"
    assert payload["gate_passed"] is False
    assert payload["summary"]["verified_findings"] == 0
    assert payload["ghost_regression"]["inconclusive_tests"] == ["tests/test_app.py::test_handler_strips"]
    (finding,) = [f for f in payload["findings"] if f["lane"] == "ghost_regression"]
    assert (finding["state"], finding["severity"]) == ("INCONCLUSIVE", "info")
    assert "base_worktree_unavailable" in finding["summary"]


def test_ultra_review_explicit_regression_test_gets_no_base_exemption(tmp_path, monkeypatch):
    # Callers that require a test to pass (the post-candidate seam's visible test) keep strict
    # semantics: failing on base too does not excuse it.
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_visible.py").write_text("def test_visible():\n    assert False\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "visible"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")
    _allow_ghost_run(monkeypatch)

    payload = _review(tmp_path, regression_tests=["tests/test_visible.py"])

    assert payload["status"] == "FAIL"
    assert payload["ghost_regression"]["failed_tests"] == ["tests/test_visible.py::test_visible"]
    assert payload["ghost_regression"]["pre_existing_failures"] == []


def test_ultra_review_head_failure_attribution_fails_closed(tmp_path):
    attribute = UltraReviewService._attribute_head_failures
    candidates = ["tests/test_a.py", "tests/test_b.py"]
    # unparseable failing run: every candidate counts, nothing is compared on base
    assert attribute([], candidates, ()) == (candidates, [])
    assert attribute(["tests/test_a.py::t", "other.py::t", "tests/test_b.py"], candidates, ("tests/test_b.py",)) == (
        ["other.py::t", "tests/test_b.py"],
        ["tests/test_a.py::t"],
    )
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<?xml version="1.0"?><testsuites><testsuite>'
        '<testcase classname="tests.test_a" name="t[a - b]" file="tests/test_a.py"><failure message="x"/></testcase>'
        '<testcase classname="tests.test_a" name="t[a - c]" file="tests/test_a.py"/>'
        '<testcase classname="tests.test_a.TestK" name="m" file="tests/test_a.py"><skipped/></testcase>'
        '<testcase classname="" name="tests.test_b"><error message="collection failure"/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    assert UltraReviewService._junit_outcomes(junit) == {
        "tests/test_a.py::t[a - b]": "failed",
        "tests/test_a.py::t[a - c]": "passed",
        "tests/test_a.py::TestK::m": "skipped",
        "tests/test_b.py": "error_file",
    }
    junit.write_text("<testsuites><testcase classname='x' name='y'/>", encoding="utf-8")
    assert UltraReviewService._junit_outcomes(junit) is None  # unparseable -> fail closed
    assert UltraReviewService._junit_outcomes(tmp_path / "missing.xml") is None
    junit.write_text('<!DOCTYPE x [<!ENTITY a "b">]><testsuites/>', encoding="utf-8")
    assert UltraReviewService._junit_outcomes(junit) is None  # entity declarations refused



def test_ultra_review_review_mode_summaries_do_not_say_dry_run(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "nexus" / "engine" / "sample.py").write_text("VALUE = 2\n", encoding="utf-8")
    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if str(cmd[-1]).endswith("ultra_logic_repro.py"):
            return subprocess.CompletedProcess(cmd, 1, stdout="logic failed", stderr="edge mismatch")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("nexus.engine.ultra_review_service.subprocess.run", fake_run)

    review = _review(tmp_path)
    dry = _review(tmp_path, dry_run=True)

    review_logic = next(f for f in review["findings"] if f["rule_id"] == "logic_repro_failed")
    dry_logic = next(f for f in dry["findings"] if f["rule_id"] == "logic_repro_failed")
    assert review_logic["summary"] == "Logic Breaker deterministic repro failed in ultra-review review mode."
    assert dry_logic["summary"] == "Logic Breaker deterministic repro failed in ultra-review dry-run."


def _commit(path, msg):
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", msg], cwd=path, check=True, capture_output=True)


# Adversarial cases from the independent review of PR #2628.
def test_ultra_review_new_head_failure_beside_passing_base_is_regression(tmp_path, monkeypatch):
    # base: both tests pass. head: change breaks a second behaviour.
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_app.py").write_text(
        "from app import handler\n\ndef test_handler_strips():\n    assert handler('  a ') == 'a'\n\n"
        "def test_handler_type():\n    assert isinstance(handler(' b'), str)\n",
        encoding="utf-8",
    )
    _commit(tmp_path, "two tests")
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return 1 if value == ' b' else value.strip()\n", encoding="utf-8"
    )
    _allow_ghost_run(monkeypatch)
    payload = _review(tmp_path)
    assert payload["status"] == "FAIL", payload["findings"]
    assert payload["ghost_regression"]["failed_tests"] == ["tests/test_app.py::test_handler_type"]


def test_ultra_review_head_session_abort_is_never_excused_by_base(tmp_path, monkeypatch):
    # base: red test first, handler test passes. head: handler raises KeyboardInterrupt, so
    # pytest aborts (exit 2) and only the pre-existing failure is reported.
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_app.py").write_text(
        "from app import handler\n\ndef test_a_always_red():\n    assert False\n\n"
        "def test_handler_strips():\n    assert handler('  a ') == 'a'\n",
        encoding="utf-8",
    )
    _commit(tmp_path, "red first")
    (tmp_path / "app.py").write_text("def handler(value):\n    raise KeyboardInterrupt\n", encoding="utf-8")
    _allow_ghost_run(monkeypatch)
    payload = _review(tmp_path)
    assert payload["status"] == "FAIL", payload["findings"]
    assert payload["ghost_regression"]["pre_existing_failures"] == []
    assert payload["ghost_regression"]["base_comparison"] == {}


def test_ultra_review_parametrized_ids_with_dash_do_not_collide(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_app.py").write_text(
        "import pytest\nfrom app import handler\n\n"
        "@pytest.mark.parametrize('v', ['a - b', 'a - c'], ids=['a - b', 'a - c'])\n"
        "def test_p(v):\n    assert handler(v) == v.strip() and v != 'a - b'\n",
        encoding="utf-8",
    )
    _commit(tmp_path, "param")
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return '' if value == 'a - c' else value.strip()\n", encoding="utf-8"
    )
    _allow_ghost_run(monkeypatch)
    payload = _review(tmp_path)
    ghost = payload["ghost_regression"]
    assert payload["status"] == "FAIL", payload["findings"]
    assert ghost["failed_tests"] == ["tests/test_app.py::test_p[a - c]"]
    assert ghost["pre_existing_failures"] == ["tests/test_app.py::test_p[a - b]"]


def test_ultra_review_base_collection_error_is_inconclusive_not_pre_existing(tmp_path, monkeypatch):
    # base: the test file does not even import; head fixes the import but the test fails.
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_app.py").write_text(
        "from app import handler, missing\n\n\ndef test_handler_strips():\n    assert handler('  a ') == 'a'\n",
        encoding="utf-8",
    )
    _commit(tmp_path, "broken import on base")
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return value\n\n\ndef missing():\n    return 1\n", encoding="utf-8"
    )
    _allow_ghost_run(monkeypatch)
    payload = _review(tmp_path)
    ghost = payload["ghost_regression"]
    assert payload["status"] == "INCONCLUSIVE", payload["findings"]
    assert ghost["pre_existing_failures"] == []
    assert ghost["inconclusive_tests"] == ["tests/test_app.py::test_handler_strips"]


def test_ultra_review_base_worktree_cleanup_failure_is_surfaced(tmp_path, monkeypatch):
    _init_app_repo_with_red_test(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")
    _allow_ghost_run(monkeypatch)
    original_git_run = UltraReviewService._git_run

    def failing_base_removal(self, args, **kwargs):
        if args[:2] == ["worktree", "remove"] and str(args[-1]).endswith("base_worktree"):
            original_git_run(self, args, **kwargs)
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="cannot remove")
        return original_git_run(self, args, **kwargs)

    monkeypatch.setattr(UltraReviewService, "_git_run", failing_base_removal)
    payload = _review(tmp_path)
    assert payload["ghost_regression"]["base_comparison"]["base_cleanup"] == {"removed": False, "detail": "cannot remove"}
    assert any(f["rule_id"] == "base_worktree_cleanup_failed" for f in payload["findings"])


# --- #2644: forgeries by code that does NOT read the HMAC key ---------------------------------
# Scope (confirmed residual, #2644 stays open): the key lives in pytest's process, so code under
# review that reads it from the interpreter (gc / closures of the witness plugin) can still sign
# a forged report. These tests cover code that does not read the key; the real fix is
# out-of-process result collection.
# The first three are the #2628 round-2 reviewer's adversarial tests
# (rev-2628 tests/engine/test_zz_review2628_v3.py), renamed; the exit-0 control now asserts
# the fixed verdict instead of only printing it.

_RED_FIRST = (
    "from app import handler\n\ndef test_a_always_red():\n    assert False\n\n"
    "def test_handler_strips():\n    assert handler('  a ') == 'a'\n"
)
_FORGED_JUNIT = (
    '<?xml version="1.0"?><testsuites><testsuite><testcase classname="tests.test_app" '
    'name="test_a_always_red" file="tests/test_app.py"><failure message="x"/></testcase>'
    "</testsuite></testsuites>"
)
_FORGED_ALL_PASS = (
    '<?xml version="1.0"?><testsuites><testsuite><testcase classname="tests.test_app" '
    'name="test_handler_strips" file="tests/test_app.py"/></testsuite></testsuites>'
)


def test_ultra_review_crafted_param_ids_cannot_collide_with_base_failure(tmp_path, monkeypatch):
    # A head-only failure must not pass as pre-existing by crafting '::', '.', ' - ' into ids.
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_app.py").write_text(
        "import pytest\nfrom app import handler\n\n"
        "class TestK:\n    def test_m(self):\n        assert False\n\n"
        "@pytest.mark.parametrize('v', ['x', 'y'], ids=['TestK::test_m', 'K.test_m - z'])\n"
        "def test_p(v):\n    assert handler(' ' + v) == v\n",
        encoding="utf-8",
    )
    _commit(tmp_path, "crafted")
    (tmp_path / "app.py").write_text("def handler(value):\n    return value\n", encoding="utf-8")
    _allow_ghost_run(monkeypatch)
    payload = _review(tmp_path)
    ghost = payload["ghost_regression"]
    assert payload["status"] == "FAIL"
    assert sorted(ghost["failed_tests"]) == [
        "tests/test_app.py::test_p[K.test_m - z]",
        "tests/test_app.py::test_p[TestK::test_m]",
    ]
    assert ghost["pre_existing_failures"] == ["tests/test_app.py::TestK::test_m"]


def test_ultra_review_forged_junit_then_exit1_is_not_a_pass(tmp_path, monkeypatch):
    # Candidate code writes a junit naming only the pre-existing failure, then os._exit(1).
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_app.py").write_text(_RED_FIRST, encoding="utf-8")
    _commit(tmp_path, "red first")
    (tmp_path / "app.py").write_text(
        "import os\n"
        f"FORGED = {_FORGED_JUNIT!r}\n"
        "def handler(value):\n"
        "    for p in ['../ghost-head-junit.xml']:\n"
        "        try:\n            open(p, 'w').write(FORGED)\n"
        "        except OSError as e:\n            print('WRITE_FAIL', e)\n"
        "    os._exit(1)\n",
        encoding="utf-8",
    )
    _allow_ghost_run(monkeypatch)
    payload = _review(tmp_path)
    assert payload["status"] != "PASS"
    assert payload["status"] == "FAIL"
    assert payload["ghost_regression"]["pre_existing_failures"] == []


def test_ultra_review_os_exit0_in_candidate_code_is_not_a_pass(tmp_path, monkeypatch):
    # Before #2644 an os._exit(0) in the code under test made the review PASS.
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text("import os\ndef handler(value):\n    os._exit(0)\n", encoding="utf-8")
    _allow_ghost_run(monkeypatch)
    payload = _review(tmp_path)
    assert payload["status"] != "PASS"
    assert payload["status"] == "INCONCLUSIVE"
    assert payload["gate_passed"] is False
    assert any(f["rule_id"] == "pytest_report_unverified" for f in payload["findings"])
    assert payload["ghost_regression"]["head_report"]["verified"] is False


def _argv_forger(exit_code, junit_text, *, witness=True):
    # Keyless forger: finds the real report paths in argv (stronger than the reviewer's fixed
    # path) but does not read the key from the interpreter, so it cannot produce a valid MAC.
    return (
        "import json, os, sys\n"
        f"FORGED = {junit_text!r}\n"
        "def handler(value):\n"
        "    paths = [a for a in sys.argv if a.startswith('/') and a.endswith(('junit.xml', 'witness.json'))]\n"
        "    for p in paths:\n"
        "        if p.endswith('junit.xml'):\n"
        "            open(p, 'w').write(FORGED)\n"
        f"        elif {witness!r}:\n"
        "            payload = json.dumps({'exitstatus': " + str(exit_code) + ", 'junit_sha256': ''})\n"
        "            open(p, 'w').write(json.dumps({'payload': payload, 'mac': '0' * 64}))\n"
        f"    os._exit({exit_code})\n"
    )


def test_ultra_review_keyless_argv_forged_report_and_witness_exit0_is_not_a_pass(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text(_argv_forger(0, _FORGED_ALL_PASS), encoding="utf-8")
    _allow_ghost_run(monkeypatch)
    payload = _review(tmp_path)
    assert payload["status"] == "INCONCLUSIVE"
    assert payload["ghost_regression"]["head_report"]["reason"] in {"witness_mac_mismatch", "witness_missing"}


def test_ultra_review_keyless_argv_forged_report_exit1_is_a_regression(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_app.py").write_text(_RED_FIRST, encoding="utf-8")
    _commit(tmp_path, "red first")
    (tmp_path / "app.py").write_text(_argv_forger(1, _FORGED_JUNIT), encoding="utf-8")
    _allow_ghost_run(monkeypatch)
    payload = _review(tmp_path)
    assert payload["status"] == "FAIL"
    assert payload["ghost_regression"]["pre_existing_failures"] == []


def test_ultra_review_keyless_junit_rewrite_after_session_is_not_trusted(tmp_path, monkeypatch):
    # Keyless: an atexit hook rewrites the junit after pytest signed it: the hash no longer matches.
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_app.py").write_text(_RED_FIRST, encoding="utf-8")
    _commit(tmp_path, "red first")
    (tmp_path / "app.py").write_text(
        "import atexit, sys\n"
        f"FORGED = {_FORGED_JUNIT!r}\n"
        "def _rewrite():\n"
        "    for p in sys.argv:\n"
        "        if p.startswith('/') and p.endswith('junit.xml'):\n"
        "            open(p, 'w').write(FORGED)\n"
        "atexit.register(_rewrite)\n"
        "def handler(value):\n    return value\n",
        encoding="utf-8",
    )
    _allow_ghost_run(monkeypatch)
    payload = _review(tmp_path)
    ghost = payload["ghost_regression"]
    assert payload["status"] == "FAIL"
    assert ghost["head_report"] == {"verified": False, "reason": "junit_hash_mismatch"}
    assert ghost["pre_existing_failures"] == []


def test_ultra_review_honest_run_has_verified_report(tmp_path, monkeypatch):
    _init_app_repo_with_red_test(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value.strip()  # x\n", encoding="utf-8")
    _allow_ghost_run(monkeypatch)
    payload = _review(tmp_path)
    ghost = payload["ghost_regression"]
    assert ghost["head_report"] == {"verified": True, "reason": ""}
    assert ghost["pre_existing_failures"] == ["tests/test_app.py::test_always_red"]
    assert payload["status"] == "PASS", payload["findings"]
    assert "<ghost-pytest-bootstrap>" in ghost["base_comparison"]["repro_command"]


def test_verify_ghost_report_rejects_wrong_key_exit_code_and_swapped_dir(tmp_path):
    import hashlib
    import hmac as hmac_mod

    def signed(report, exitstatus, junit_bytes, key=None):
        report["junit"].write_bytes(junit_bytes)
        payload = json.dumps(
            {"exitstatus": exitstatus, "junit_sha256": hashlib.sha256(junit_bytes).hexdigest()}, sort_keys=True
        )
        mac = hmac_mod.new(key or report["key"], payload.encode(), hashlib.sha256).hexdigest()
        report["witness"].write_text(json.dumps({"payload": payload, "mac": mac}), encoding="utf-8")

    verify = UltraReviewService._verify_ghost_report
    report = UltraReviewService._new_ghost_report(tmp_path, "head")
    assert verify(report, 0)["reason"] == "witness_missing"
    signed(report, 0, _FORGED_ALL_PASS.encode())
    good = verify(report, 0)
    assert good["verified"] is True and good["junit_bytes"] == _FORGED_ALL_PASS.encode()
    assert verify(report, 1)["reason"] == "exit_code_mismatch"

    other = UltraReviewService._new_ghost_report(tmp_path, "head")
    signed(other, 0, b"<testsuites/>", key=b"k" * 32)
    assert verify(other, 0)["reason"] == "witness_mac_mismatch"

    swapped = UltraReviewService._new_ghost_report(tmp_path, "head")
    signed(swapped, 0, b"<testsuites/>")
    moved = tmp_path / "moved"
    swapped["dir"].rename(moved)
    swapped["dir"].mkdir()
    for name in ("junit.xml", "witness.json"):
        (swapped["dir"] / name).write_bytes((moved / name).read_bytes())
    assert verify(swapped, 0)["reason"] == "report_dir_replaced"
