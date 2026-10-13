from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod


def _forbid_subprocess(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("retired delegate must not spawn any backend")

    monkeypatch.setattr(cli_mod.subprocess, "run", _boom)
    monkeypatch.setattr(cli_mod.SanitizedRunner, "run_safe", staticmethod(_boom))


def _invoke_removed_delegate(monkeypatch, tmp_path, *args):
    """`nexus delegate` (retired #1739) is removed by the 2026-10-13 archive batch (#1906)."""
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    _forbid_subprocess(monkeypatch)
    return CliRunner().invoke(cli_mod.nexus, ["nexus", "delegate", *args])


def _assert_no_such_command(res) -> None:
    assert res.exit_code == 2, res.output
    assert "No such command" in res.output


def test_delegate_writes_completion_envelope(monkeypatch, tmp_path):
    # Historical node id retained; the command is gone, so no envelope is written.
    report_path = tmp_path / "reports" / "delegate_report.json"
    res = _invoke_removed_delegate(
        monkeypatch, tmp_path, "repair completion contract", "--report-file", str(report_path), "--output-json"
    )

    _assert_no_such_command(res)
    assert not report_path.exists()


def test_delegate_message_names_retirement_and_multi_agent_commands(monkeypatch, tmp_path):
    # Historical node id retained; `nexus multi-agent` remains the real path.
    res = _invoke_removed_delegate(monkeypatch, tmp_path, "repair completion contract")

    _assert_no_such_command(res)
    help_res = CliRunner().invoke(cli_mod.nexus, ["nexus", "--help"])
    assert "multi-agent" in help_res.output
    assert not hasattr(cli_mod, "DELEGATE_RETIRED_MESSAGE")


def test_delegate_fails_closed_when_supervisor_fails(monkeypatch, tmp_path):
    # Historical node id retained; the removed command never reaches a backend.
    res = _invoke_removed_delegate(monkeypatch, tmp_path, "repair completion contract")

    _assert_no_such_command(res)
    assert "DELEGATION_BACKEND_UNAVAILABLE" not in res.output


def test_delegate_passes_task_name_unquoted(monkeypatch, tmp_path):
    # Historical node id retained; no envelope (and so no task name) is produced.
    res = _invoke_removed_delegate(monkeypatch, tmp_path, "repair completion contract", "--output-json")

    _assert_no_such_command(res)


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
    res = _invoke_removed_delegate(monkeypatch, tmp_path, "bad; rm -rf /")

    _assert_no_such_command(res)
