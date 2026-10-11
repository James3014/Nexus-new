import json

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod


def _forbid_subprocess(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("retired delegate must not spawn any backend")

    monkeypatch.setattr(cli_mod.subprocess, "run", _boom)
    monkeypatch.setattr(cli_mod.SanitizedRunner, "run_safe", staticmethod(_boom))


def test_delegate_writes_completion_envelope(monkeypatch, tmp_path):
    """Retired (#1739): the envelope is still written, now as a non-retryable BLOCKED result."""
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    _forbid_subprocess(monkeypatch)

    report_path = tmp_path / "reports" / "delegate_report.json"
    res = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "delegate", "repair completion contract", "--report-file", str(report_path), "--output-json"],
    )

    assert res.exit_code == 78, res.output
    payload = json.loads(res.output)
    assert payload["status"] == "FAILED"
    assert payload["semantic_status"] == "BLOCKED"
    assert payload["retryable"] is False
    assert payload["execution_path"] == "retired"
    assert "delegate_retired_1739" in payload["semantic_failures"]
    assert report_path.exists()


def test_delegate_message_names_retirement_and_multi_agent_commands(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    _forbid_subprocess(monkeypatch)

    res = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "delegate", "repair completion contract", "--report-file", str(tmp_path / "r.json")],
    )

    assert res.exit_code == 78
    assert "retired" in res.output and "#1739" in res.output
    for sub in ("create-task", "start", "submit", "verify"):
        assert f"nexus multi-agent {sub} --task-id" in res.output
    help_res = CliRunner().invoke(cli_mod.nexus, ["nexus", "delegate", "--help"])
    assert "RETIRED" in help_res.output and "multi-agent" in help_res.output


def test_delegate_fails_closed_when_supervisor_fails(monkeypatch, tmp_path):
    """Retired (#1739): delegate fails closed without ever invoking the supervisor backend."""
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    _forbid_subprocess(monkeypatch)

    res = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "delegate", "repair completion contract", "--report-file", str(tmp_path / "r.json")],
    )

    assert res.exit_code == 78
    assert "DELEGATION_BACKEND_UNAVAILABLE" in res.output


def test_delegate_passes_task_name_unquoted(monkeypatch, tmp_path):
    """The validated task name is recorded verbatim (no shell quoting) in the envelope."""
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    _forbid_subprocess(monkeypatch)

    res = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "delegate", "repair completion contract", "--report-file", str(tmp_path / "r.json"), "--output-json"],
    )

    payload = json.loads(res.output)
    assert payload["task_name"] == "repair completion contract"


def test_supervisor_engine_refuses_real_tasks_without_writing(tmp_path):
    """The synthetic demo must not report success or write files for a real task."""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(cli_mod.__file__).resolve().parents[1] / "ops" / "supervisor_engine.py"
    res = subprocess.run(
        [sys.executable, str(script), "repair completion contract"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert res.returncode == 78
    assert "DELEGATION_BACKEND_UNAVAILABLE" in res.stderr
    assert "repair completion contract" in res.stderr
    assert list(tmp_path.iterdir()) == []


def test_delegate_rejects_invalid_task_name_without_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    _forbid_subprocess(monkeypatch)

    res = CliRunner().invoke(cli_mod.nexus, ["nexus", "delegate", "bad; rm -rf /"])

    assert res.exit_code == 1
    assert "Invalid task name" in res.output
