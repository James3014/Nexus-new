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
    assert result.executable_identity == str(Path(sys.executable).resolve())
    assert result.argv == request.argv
    assert result.cwd == str(tmp_path.resolve())
    assert result.stdout_sha256 == result.hash_bytes(result.stdout)
    assert result.stderr_sha256 == result.hash_bytes(result.stderr)
    assert result.wall_time_ms >= 0
    assert result.telemetry["wall_time_ms"] == result.wall_time_ms
    assert result.telemetry["process_group_id"] == result.process_group_id


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
