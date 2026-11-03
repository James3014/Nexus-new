"""#3200: a shutdown request stops every wait on a reaped child group, from any thread.

Signal handlers run only on the main thread, so a service that runs helpers from worker
threads cannot reach them by raising from its handler. ``request_process_group_shutdown``
makes each waiting thread raise ProcessGroupShutdown, so the thread that owns the child kills
its group and reaps it on the way out, and refuses new spawns. Only children these tests start
are signalled.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest

from nexus.core import argv_command
from nexus.core.argv_command import (
    ProcessGroupShutdown,
    communicate_then_kill_group,
    kill_group_if_exited,
    require_child_stays_unreaped,
    run_reaping_process_group,
)

# The leader records its pid and its background child's, then waits on that child, keeping
# the output open; the child sleeps with its output closed.
HOLD = 'sleep 60 >/dev/null 2>&1 & echo "$$ $!" > pids; wait'


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return not state or state.startswith("Z")


def _pids(work: Path) -> list[int]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        text = (work / "pids").read_text().strip() if (work / "pids").exists() else ""
        if len(text.split()) == 2:
            return [int(value) for value in text.split()]
        time.sleep(0.02)
    raise AssertionError("the command did not record its pids")


def _assert_gone(pids: list[int]) -> None:
    deadline = time.monotonic() + 5
    while not all(_gone(pid) for pid in pids) and time.monotonic() < deadline:
        time.sleep(0.05)
    survivors = [pid for pid in pids if not _gone(pid)]
    for pid in survivors:  # never leave them running; these are this test's own children
        os.kill(pid, signal.SIGKILL)
    assert survivors == [], f"outlived the shutdown: {survivors}"


def _in_thread(target) -> tuple[threading.Thread, list[BaseException]]:
    raised: list[BaseException] = []

    def run():
        try:
            target()
        except BaseException as exc:  # noqa: BLE001 - the test inspects what the thread raised
            raised.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, raised


def test_nothing_is_spawned_once_shutdown_is_requested(tmp_path, monkeypatch):
    monkeypatch.setattr(argv_command, "_shutdown_requested", True)
    with pytest.raises(ProcessGroupShutdown):
        run_reaping_process_group(["/bin/sh", "-c", "touch spawned"], cwd=tmp_path, timeout=20)
    with pytest.raises(ProcessGroupShutdown):
        require_child_stays_unreaped()
    assert not (tmp_path / "spawned").exists()


def test_a_worker_thread_waiting_on_a_group_kills_it_and_reaps(tmp_path, monkeypatch):
    thread, raised = _in_thread(
        lambda: run_reaping_process_group(["/bin/sh", "-c", HOLD], cwd=tmp_path, timeout=300)
    )
    pids = _pids(tmp_path)
    monkeypatch.setattr(argv_command, "_shutdown_requested", True)
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert len(raised) == 1 and isinstance(raised[0], ProcessGroupShutdown)
    _assert_gone(pids)


def test_communicate_then_kill_group_kills_the_group_when_its_wait_is_interrupted(
    tmp_path, monkeypatch
):
    process = subprocess.Popen(
        ["/bin/sh", "-c", HOLD],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    thread, raised = _in_thread(lambda: communicate_then_kill_group(process, 300))
    pids = _pids(tmp_path)
    monkeypatch.setattr(argv_command, "_shutdown_requested", True)
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert len(raised) == 1 and isinstance(raised[0], ProcessGroupShutdown)
    assert process.returncode is not None  # reaped by the helper, after the group kill
    _assert_gone(pids)


def test_kill_group_if_exited_still_answers_a_poll_during_shutdown(tmp_path, monkeypatch):
    process = subprocess.Popen(["/bin/sh", "-c", "sleep 1"], cwd=tmp_path, start_new_session=True)
    try:
        monkeypatch.setattr(argv_command, "_shutdown_requested", True)
        # A non-blocking poll is not a wait: it reports the child still running.
        assert kill_group_if_exited(process) is False
    finally:
        monkeypatch.setattr(argv_command, "_shutdown_requested", False)
        deadline = time.monotonic() + 10
        while not kill_group_if_exited(process) and time.monotonic() < deadline:
            time.sleep(0.05)
    assert process.returncode == 0


def test_an_interrupt_right_after_popen_returns_still_kills_and_reaps_the_group(monkeypatch):
    """#3306: the gap between Popen returning and the cleanup block must be protected."""
    spawned: list[int] = []

    class InterruptedPopen(subprocess.Popen):
        armed = False

        @property
        def stdout(self):
            if self.armed:
                raise KeyboardInterrupt  # a terminate-signal handler raising
            return self._out

        @stdout.setter
        def stdout(self, value):
            self._out = value

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            spawned.append(self.pid)
            self.armed = True

    monkeypatch.setattr(argv_command.subprocess, "Popen", InterruptedPopen)
    with pytest.raises(KeyboardInterrupt):
        run_reaping_process_group(["/bin/sh", "-c", "sleep 60 & wait"], timeout=60)
    (pgid,) = spawned
    try:
        # Only this test's own child group; it must be gone, i.e. killed and reaped.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        with pytest.raises(ProcessLookupError):
            os.killpg(pgid, 0)
        with pytest.raises(ChildProcessError):
            os.waitpid(pgid, os.WNOHANG)  # already reaped: no zombie left
    finally:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
