"""#3052: a CLI worker's process group is killed after a normal exit by default.

Group cleanup after a normal exit used to depend on ``sweep_descendants_on_exit`` (off by
default): a child the worker left in its process group outlived the receipt. The group is now
SIGKILLed once the worker exits, before it is reaped. Each test starts its own detached child
and records its pid; only that pid is ever signalled (in ``finally``, if still running).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nexus.core import argv_command
from nexus.executors import cli_worker
from nexus.executors.cli_worker import CliWorkerRequest, CliWorkerStatus, run_cli_worker

_DETACH = (
    "import subprocess, sys\n"
    "p = subprocess.Popen(['/bin/sleep', '60'], stdin=subprocess.DEVNULL,"
    " stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
    "open(sys.argv[1], 'w').write(str(p.pid))\n"
    "print('worker out')\n"
)


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return not state or state.startswith("Z")


def _assert_reaped(pid_file: Path) -> None:
    pid = int(pid_file.read_text().strip())
    try:
        deadline = time.monotonic() + 5
        while not _gone(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _gone(pid), f"worker child {pid} outlived the worker"
    finally:
        if not _gone(pid):
            os.kill(pid, signal.SIGKILL)


def test_a_child_left_in_the_group_does_not_outlive_a_normal_exit(tmp_path):
    pid_file = tmp_path / "bg.pid"
    result = run_cli_worker(
        CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", _DETACH, str(pid_file)),
            cwd=str(tmp_path),
            timeout_seconds=30,
        )
    )
    assert result.status == CliWorkerStatus.COMPLETED
    assert (result.exit_code, result.stdout) == (0, b"worker out\n")
    _assert_reaped(pid_file)


def test_timeout_still_reports_partial_output_and_kills_the_group(tmp_path):
    pid_file = tmp_path / "bg.pid"
    script = _DETACH + "sys.stdout.flush()\nimport time\ntime.sleep(60)\n"
    result = run_cli_worker(
        CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", script, str(pid_file)),
            cwd=str(tmp_path),
            timeout_seconds=2,
        )
    )
    assert result.status == CliWorkerStatus.TIMED_OUT
    assert result.stdout == b"worker out\n"
    _assert_reaped(pid_file)


def test_refused_before_spawning_when_the_worker_could_not_stay_unreaped(tmp_path, monkeypatch):
    def refuse() -> None:
        raise argv_command.ProcessGroupReapingUnavailable("SIGCHLD is not SIG_DFL")

    monkeypatch.setattr(cli_worker, "require_child_stays_unreaped", refuse)
    marker = tmp_path / "ran"
    result = run_cli_worker(
        CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", f"open({str(marker)!r}, 'w').write('x')"),
            cwd=str(tmp_path),
            timeout_seconds=30,
        )
    )
    assert result.status == CliWorkerStatus.START_FAILED
    assert b"SIGCHLD" in result.stderr
    assert not marker.exists()


def test_a_group_member_that_survives_is_not_a_completed_run(tmp_path, monkeypatch):
    # PermissionError after the reap: the pid may already name another group, so the
    # failure path must not signal it again.
    def survivor(process, timeout, before_kill=None):
        process.wait()
        raise PermissionError("a group member survived SIGKILL")

    signalled: list[int] = []
    monkeypatch.setattr(cli_worker, "communicate_then_kill_group", survivor)
    monkeypatch.setattr(cli_worker.os, "killpg", lambda pgid, sig: signalled.append(pgid))
    result = run_cli_worker(
        CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", "pass"),
            cwd=str(tmp_path),
            timeout_seconds=30,
        )
    )
    assert result.status == CliWorkerStatus.START_FAILED
    assert signalled == []


def test_before_kill_runs_while_the_group_is_alive_and_the_group_is_killed_if_it_raises(
    tmp_path,
):
    pid_file = tmp_path / "bg.pid"
    argv_command.require_child_stays_unreaped()
    process = subprocess.Popen(
        [sys.executable, "-c", _DETACH, str(pid_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    seen_alive: list[bool] = []

    def before_kill() -> None:
        seen_alive.append(not _gone(int(pid_file.read_text().strip())))
        raise RuntimeError("probe failed")

    with pytest.raises(RuntimeError, match="probe failed"):
        argv_command.communicate_then_kill_group(process, 30, before_kill=before_kill)
    assert seen_alive == [True]
    assert process.returncode == 0
    _assert_reaped(pid_file)
