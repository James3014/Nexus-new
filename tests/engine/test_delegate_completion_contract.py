import json

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod


def test_delegate_writes_completion_envelope(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)

    def _fake_run(*_args, **_kwargs):
        class _Res:
            returncode = 0
        return _Res()

    monkeypatch.setattr(cli_mod.subprocess, "run", _fake_run)

    report_path = tmp_path / "reports" / "delegate_report.json"
    runner = CliRunner()
    res = runner.invoke(
        cli_mod.nexus,
        ["nexus", "delegate", "repair completion contract", "--report-file", str(report_path), "--output-json"],
    )

    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["status"] == "SUCCESS"
    assert payload["semantic_status"] == "VERIFIED"
    assert payload["runtime_classification"] == "verified_pass"
    assert payload["retryable"] is False
    assert payload["execution_path"] == "cli->supervisor_engine"
    assert report_path.exists()


def test_delegate_fails_closed_when_supervisor_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)

    def _fake_run(*_args, **_kwargs):
        class _Res:
            returncode = 7
        return _Res()

    monkeypatch.setattr(cli_mod.subprocess, "run", _fake_run)

    report_path = tmp_path / "reports" / "delegate_fail.json"
    runner = CliRunner()
    res = runner.invoke(
        cli_mod.nexus,
        ["nexus", "delegate", "repair completion contract", "--report-file", str(report_path)],
    )

    assert res.exit_code != 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["semantic_status"] == "UNVERIFIED"
    assert payload["retryable"] is True
    assert payload["blocker_type"] == "runtime_defect"


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


def test_delegate_passes_task_name_unquoted(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    seen = {}

    def _fake_run(cmd, *_args, **_kwargs):
        seen["cmd"] = cmd

        class _Res:
            returncode = 78
        return _Res()

    monkeypatch.setattr(cli_mod.subprocess, "run", _fake_run)

    runner = CliRunner()
    res = runner.invoke(
        cli_mod.nexus,
        ["nexus", "delegate", "repair completion contract", "--report-file", str(tmp_path / "r.json")],
    )

    assert res.exit_code != 0
    assert seen["cmd"][-1] == "repair completion contract"
