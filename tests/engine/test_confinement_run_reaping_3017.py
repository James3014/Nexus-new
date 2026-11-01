"""#3017 follow-up: nothing model code run through ``Confinement.run`` starts outlives the run.

``Confinement.run`` (confined_test_runner, the committee execution verifier, swarm_run) ran
model-written code with a plain ``subprocess.run``: a background child that closed its output
kept running after a normal exit, and a timeout killed only the direct child. It now goes
through ``run_reaping_process_group`` like the model sandbox runners. The OS barrier is
macOS-only and the reaping under test does not depend on it, so ``sandbox-exec`` is replaced by
a pass-through wrapper here; every background child a test starts records its pid and is
killed in ``finally`` if it is still running.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from nexus.core import argv_command
from nexus.engine import sandboxed_lane as lane

DETACH = "sleep 60 >/dev/null 2>&1 & echo $! > bg.pid"


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
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
        assert _gone(pid), f"background child {pid} outlived the run"
    finally:
        if not _gone(pid):
            os.kill(pid, signal.SIGKILL)


@pytest.fixture
def bound(tmp_path, monkeypatch):
    # sandbox-exec -p <profile> argv...  ->  argv...
    wrapper = tmp_path / "fake-sandbox-exec"
    wrapper.write_text('#!/bin/sh\nshift 2\nexec "$@"\n')
    wrapper.chmod(0o755)
    monkeypatch.setattr(lane, "SANDBOX_EXEC", str(wrapper))
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    work = (tmp_path / "ws").resolve()
    work.mkdir()
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    return lane.Confinement(profile="(version 1)", env=env, roots=(work,)), work


def test_a_detached_child_does_not_outlive_a_normal_exit(bound):
    confined, work = bound
    run = confined.run(["/bin/sh", "-c", DETACH], cwd=work, timeout=20)
    assert run.returncode == 0
    _assert_reaped(_background_pid(work))


def test_a_child_does_not_outlive_a_timeout(bound):
    confined, work = bound
    script = "sleep 60 & echo $! > bg.pid; wait"
    with pytest.raises(subprocess.TimeoutExpired):
        confined.run(["/bin/sh", "-c", script], cwd=work, timeout=1)
    _assert_reaped(_background_pid(work))


def test_output_and_exit_status_are_kept(bound):
    confined, work = bound
    run = confined.run(["/bin/sh", "-c", "echo out; echo err >&2; exit 3"], cwd=work, timeout=20)
    assert (run.returncode, run.stdout, run.stderr) == (3, "out\n", "err\n")


@pytest.mark.parametrize(
    "error",
    [
        argv_command.ProcessGroupReapingUnavailable("no unreaped wait"),
        PermissionError("a group member survived"),
        ChildProcessError("the leader was reaped elsewhere"),
    ],
)
def test_a_run_whose_group_cannot_be_reaped_is_a_sandbox_error(bound, monkeypatch, error):
    # Callers treat SandboxError as "not verified"; a survivor never reads as a result.
    confined, work = bound

    def refuse(*_a, **_kw):
        raise error

    monkeypatch.setattr(lane, "run_reaping_process_group", refuse)
    with pytest.raises(lane.SandboxError, match="process_group_not_reaped"):
        confined.run(["/bin/sh", "-c", "exit 0"], cwd=work, timeout=20)


def test_ghost_lane_keeps_its_stdin_path(tmp_path):
    # kill_process_group (#2650) keeps its own runner; reaping takes no stdin.
    with pytest.raises(lane.SandboxError, match="reap_process_group_takes_no_stdin"):
        lane.run_confined(
            ["/bin/sh", "-c", "exit 0"],
            cwd=tmp_path,
            confine_roots=(tmp_path,),
            profile=lambda: "(version 1)",
            env={},
            timeout=5,
            stdin_text="x",
            reap_process_group=True,
        )
