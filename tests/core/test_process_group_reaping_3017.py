"""#3017: nothing a sandboxed model command starts outlives the command.

A child that forks and closes its output lets ``subprocess.run`` return while the fork keeps
running, and a timeout kills only the direct child. ``run_reaping_process_group`` starts the
command in its own session and kills that whole process group on every return path; the
model-command runners (``run_model_argv``, ``run_model_command_string``) go through it.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from nexus.core import argv_command
from nexus.core.argv_command import run_command_string, run_reaping_process_group
from nexus.engine import model_output_sandbox

# The background child writes its pid, then sleeps with its output closed.
DETACH = "sleep 60 >/dev/null 2>&1 & echo $! > bg.pid"


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    # A zombie still answers kill(0); it is not running.
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return not state or state.startswith("Z")


def _background_pid(work: Path) -> int:
    for _ in range(100):
        text = (work / "bg.pid").read_text().strip() if (work / "bg.pid").exists() else ""
        if text:
            return int(text)
        time.sleep(0.05)
    raise AssertionError("the command did not record its background child")


def _assert_reaped(pid: int) -> None:
    try:
        deadline = time.monotonic() + 5
        while not _gone(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _gone(pid), f"background child {pid} outlived the command"
    finally:
        if not _gone(pid):
            os.kill(pid, signal.SIGKILL)


def test_a_detached_child_does_not_outlive_a_normal_exit(tmp_path):
    result = run_reaping_process_group(["/bin/sh", "-c", DETACH], cwd=tmp_path, timeout=20)
    assert result.returncode == 0
    _assert_reaped(_background_pid(tmp_path))


def test_a_child_does_not_outlive_a_timeout(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired):
        run_reaping_process_group(["/bin/sh", "-c", f"{DETACH}; sleep 60"], cwd=tmp_path, timeout=1)
    _assert_reaped(_background_pid(tmp_path))


def test_output_exit_status_and_bytes_mode_match_subprocess_run(tmp_path):
    result = run_reaping_process_group(
        ["/bin/sh", "-c", "echo out; echo err >&2; exit 3"], cwd=tmp_path, timeout=20
    )
    assert (result.returncode, result.stdout, result.stderr) == (3, "out\n", "err\n")
    raw = run_reaping_process_group(["/bin/sh", "-c", "printf x"], text=False, timeout=20)
    assert raw.stdout == b"x"
    with pytest.raises(FileNotFoundError):
        run_reaping_process_group([str(tmp_path / "missing")], timeout=20)


def test_command_string_segments_are_reaped_when_asked(tmp_path):
    (tmp_path / "s.sh").write_text(DETACH + "\n")
    result = run_command_string(
        "/bin/sh s.sh && echo next", cwd=tmp_path, timeout=20, reap_process_group=True
    )
    assert (result.returncode, result.stdout) == (0, "next\n")
    _assert_reaped(_background_pid(tmp_path))


@contextmanager
def _no_barrier(work_dir, *, readable=(), writable=()):
    # The OS barrier is macOS-only; the reaping under test does not depend on it.
    yield [], dict(os.environ)


def test_model_argv_runs_reap_the_process_group(tmp_path, monkeypatch):
    monkeypatch.setattr(model_output_sandbox, "model_sandbox", _no_barrier)
    model_output_sandbox.run_model_argv(["/bin/sh", "-c", DETACH], work_dir=tmp_path, timeout=20)
    _assert_reaped(_background_pid(tmp_path))


def test_model_command_string_runs_reap_the_process_group(tmp_path, monkeypatch):
    monkeypatch.setattr(model_output_sandbox, "model_sandbox", _no_barrier)
    monkeypatch.setattr(model_output_sandbox, "_command_readable_roots", lambda *_a: ())
    (tmp_path / "s.sh").write_text(DETACH + "\n")
    model_output_sandbox.run_model_command_string("/bin/sh s.sh", work_dir=tmp_path, timeout=20)
    _assert_reaped(_background_pid(tmp_path))


def test_other_command_string_callers_keep_plain_subprocess_run(tmp_path, monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(argv_command.subprocess, "run", fake_run)
    run_command_string("echo hi", cwd=tmp_path)
    assert calls == [["echo", "hi"]]
