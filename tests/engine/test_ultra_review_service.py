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


def test_ultra_review_dry_run_writes_report_and_sandbox(tmp_path):
    _init_repo(tmp_path)
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
    ghost = next(item for item in payload["fleet"] if item["lane"] == "ghost_regression")
    assert ghost["planned_checks"] == ["tests/engine/test_sample.py"]
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


def test_ultra_review_maps_research_tests_and_security_observations(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "nexus" / "research").mkdir(parents=True)
    (tmp_path / "nexus" / "research" / "probe.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "add research"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "tests" / "research").mkdir(parents=True)
    (tmp_path / "tests" / "research" / "test_probe.py").write_text("def test_probe(): pass\n", encoding="utf-8")
    (tmp_path / "nexus" / "research" / "probe.py").write_text(
        "API_KEY = '123456789abcdef'\n",
        encoding="utf-8",
    )

    payload = UltraReviewService(tmp_path).run(
        report_path="reports/ultra.json",
        sandbox_root="reports/sandboxes",
    )

    assert payload["findings"][0]["state"] == "UNVERIFIED_OBSERVATION"
    assert payload["findings"][0]["rule_id"] == "secret_literal"
    security = next(item for item in payload["fleet"] if item["lane"] == "security_sentry")
    assert security["status"] == "DRY_RUN_READY_WITH_OBSERVATIONS"
    ghost = next(item for item in payload["fleet"] if item["lane"] == "ghost_regression")
    assert ghost["planned_checks"] == ["tests/research/test_probe.py"]


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
