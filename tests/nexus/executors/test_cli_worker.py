import os
import sys
import time
from pathlib import Path

import pytest

from nexus.executors.cli_worker import (
    CliWorkerRequest,
    CliWorkerStatus,
    run_cli_worker,
)


def _python_request(tmp_path: Path, script: str, *, timeout_seconds: float = 5.0):
    script_path = tmp_path / "fake_cli.py"
    script_path.write_text(script, encoding="utf-8")
    return CliWorkerRequest(
        executable=sys.executable,
        argv=(str(script_path), "--target", str(tmp_path)),
        cwd=str(tmp_path),
        timeout_seconds=timeout_seconds,
    )


def test_worker_runs_without_shell_and_records_hashes_and_telemetry(tmp_path):
    request = _python_request(
        tmp_path,
        "import sys; print('stdout:' + sys.argv[2]); print('stderr-line', file=sys.stderr)",
    )

    result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.COMPLETED
    assert result.exit_code == 0
    assert result.executable_identity == request.executable
    assert result.executable_sha256 == result.hash_bytes(Path(result.executable_identity).read_bytes())
    assert result.argv == request.argv
    assert result.cwd == str(tmp_path.resolve())
    assert result.stdout_sha256 == result.hash_bytes(result.stdout)
    assert result.stderr_sha256 == result.hash_bytes(result.stderr)
    assert result.wall_time_ms >= 0
    assert result.telemetry["wall_time_ms"] == result.wall_time_ms
    assert result.telemetry["process_group_id"] == result.process_group_id


def test_worker_records_nonzero_exit_with_executable_hash(tmp_path):
    request = _python_request(
        tmp_path,
        "import sys; print('bad', file=sys.stderr); sys.exit(7)",
    )

    result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.COMPLETED
    assert result.exit_code == 7
    assert result.executable_sha256 == result.hash_bytes(Path(result.executable_identity).read_bytes())
    assert result.timed_out is False
    assert result.process_group_killed is False


def test_worker_preserves_explicit_interpreter_symlink(tmp_path):
    alias = tmp_path / "python-alias"
    alias.symlink_to(sys.executable)
    request = CliWorkerRequest(
        executable=str(alias),
        argv=("-c", "print('alias-ok')"),
        cwd=str(tmp_path),
    )

    result = run_cli_worker(request)

    assert request.executable == str(alias)
    assert result.executable_identity == str(alias)
    assert result.exit_code == 0
    assert result.stdout == b"alias-ok\n"


def test_worker_invokes_and_clears_process_group_callback(tmp_path):
    calls = []

    def on_pg(pg_id):
        calls.append(pg_id)

    request = _python_request(
        tmp_path,
        "print('ok')",
    )

    result = run_cli_worker(request, on_process_group=on_pg)

    assert result.status is CliWorkerStatus.COMPLETED
    assert len(calls) == 2
    assert calls[0] == result.process_group_id
    assert calls[1] is None


def test_worker_rejects_commit_merge_and_push_commands(tmp_path):
    with pytest.raises(ValueError, match="commit|merge|push"):
        CliWorkerRequest(
            executable="git",
            argv=("commit", "-m", "unsafe"),
            cwd=str(tmp_path),
        )


def test_worker_timeout_kills_process_group(tmp_path):
    request = _python_request(
        tmp_path,
        "import time; time.sleep(30)",
        timeout_seconds=0.05,
    )

    result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.TIMED_OUT
    assert result.timed_out is True
    assert result.process_group_killed is True
    assert result.exit_code is not None


def test_worker_requires_existing_target_cwd(tmp_path):
    with pytest.raises(ValueError, match="cwd"):
        CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", "print('ok')"),
            cwd=str(tmp_path / "missing"),
        )


def test_worker_forces_pythondontwritebytecode_and_prevents_bytecode_generation(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "0")
    script_path = tmp_path / "test_bytecode.py"
    script_path.write_text("import os\nprint('BYTECODE_ENV=' + os.environ.get('PYTHONDONTWRITEBYTECODE', ''))\n", encoding="utf-8")

    request = CliWorkerRequest(
        executable=sys.executable,
        argv=(str(script_path),),
        cwd=str(tmp_path),
        env={"PYTHONDONTWRITEBYTECODE": "0"},
    )
    result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.COMPLETED
    assert result.exit_code == 0
    assert b"BYTECODE_ENV=1" in result.stdout
    pycache_dir = tmp_path / "__pycache__"
    assert not pycache_dir.exists()
