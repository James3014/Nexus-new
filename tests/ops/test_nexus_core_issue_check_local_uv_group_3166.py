"""The uv process group dies with the run; install I/O errors fail closed (#3166)."""

from __future__ import annotations

import fcntl
import importlib.machinery
import importlib.util
import os
import signal
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-core-issue-check-local"
PIN = "d" * 40


def _load_module():
    loader = importlib.machinery.SourceFileLoader("nexus_core_issue_check_local_3166", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeProc:
    pid = 424242

    def __init__(self, wait_action, running=True):
        self._wait_action = wait_action
        self._running = running
        self.reaped = False
        self.hung = False
        self.returncode = None if running else 0

    def poll(self):
        return None if self._running else 0

    def wait(self, timeout=None):
        if self._running and self._wait_action is not None:
            action, self._wait_action = self._wait_action, None
            action()
        self._running = False
        self.reaped = True
        self.returncode = 0
        return 0

    def exited(self):
        """One poll of the run's wait loop, standing in for argv_command.kill_group_if_exited:
        True once the child has exited (its group killed, then reaped). A TimeoutExpired wait
        action makes the child hang until its group is killed."""
        if self.hung:
            return False
        try:
            self.wait()
        except subprocess.TimeoutExpired:
            self.hung = True
            return False
        return True


def _stub(module, monkeypatch, proc):
    kills: list[tuple[int, int]] = []

    def killpg(pid, sig):
        kills.append((pid, sig))
        proc.hung = False

    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(module.os, "killpg", killpg)
    monkeypatch.setattr(module, "_group_stopped_if_exited", lambda p: p.exited())
    monkeypatch.setattr(module, "_leader_unreaped", lambda p: p.returncode is None)
    return kills


def _run(module, tmp_path):
    return module._run_with_timeout(
        ["uv", "tool", "install"], cwd=tmp_path, env={}, code="CORE_INSTALL_FAILED", timeout=5
    )


def _raiser(exc):
    def action():
        raise exc

    return action


@pytest.mark.parametrize("exc", [KeyboardInterrupt(), RuntimeError("boom"), SystemExit(1)])
def test_group_is_killed_on_any_exit_path(tmp_path, monkeypatch, exc):
    module = _load_module()
    proc = FakeProc(_raiser(exc))
    kills = _stub(module, monkeypatch, proc)
    with pytest.raises(type(exc)):
        _run(module, tmp_path)
    assert kills == [(proc.pid, signal.SIGKILL)]
    assert proc.reaped


def test_sigterm_to_the_parent_stops_the_group_and_restores_the_handler(tmp_path, monkeypatch):
    module = _load_module()

    def previous(signum, frame):
        raise AssertionError("SIGTERM reached the previous handler: the run did not own it")

    old = signal.signal(signal.SIGTERM, previous)
    before = previous
    proc = FakeProc(lambda: os.kill(os.getpid(), signal.SIGTERM))
    kills = _stub(module, monkeypatch, proc)
    try:
        with pytest.raises(SystemExit):
            _run(module, tmp_path)
        assert kills == [(proc.pid, signal.SIGKILL)]
        assert signal.getsignal(signal.SIGTERM) == before
    finally:
        signal.signal(signal.SIGTERM, old)


def test_a_finished_child_group_is_not_signalled(tmp_path, monkeypatch):
    module = _load_module()
    proc = FakeProc(None, running=False)
    kills = _stub(module, monkeypatch, proc)
    _run(module, tmp_path)
    assert kills == []


def test_timeout_still_kills_once_and_fails_closed(tmp_path, monkeypatch):
    module = _load_module()
    proc = FakeProc(_raiser(subprocess.TimeoutExpired("uv", 5)))
    kills = _stub(module, monkeypatch, proc)
    with pytest.raises(module.LocalCheckError) as err:
        _run(module, tmp_path)
    assert err.value.code == "CORE_INSTALL_FAILED"
    assert kills == [(proc.pid, signal.SIGKILL)]


def test_tools_dir_oserror_is_a_local_check_error(tmp_path):
    module = _load_module()
    blocker = tmp_path / "cache"
    blocker.write_text("a file, not a directory")
    with pytest.raises(module.LocalCheckError) as err:
        module.ensure_tool(blocker, PIN, timeout=1)
    assert err.value.code == "CORE_INSTALL_FAILED"


def test_main_exits_2_on_an_unwrapped_oserror(monkeypatch, capsys):
    module = _load_module()

    def boom(args):
        raise PermissionError("denied")

    monkeypatch.setattr(module, "run_check", boom)
    assert module.main(["--issue", "1"]) == module.EXIT_ERROR
    assert '"error_code": "LOCAL_IO_ERROR"' in capsys.readouterr().out


def test_waiting_for_the_lock_is_bounded_by_the_runs_own_timeout(tmp_path, monkeypatch):
    module = _load_module()
    tools = tmp_path / "cache" / "tools"
    tools.mkdir(parents=True)
    monkeypatch.setattr(
        module, "_ensure_tool_locked", lambda *a: pytest.fail("must not install without the lock")
    )
    with open(tools / f"{PIN}.lock", "a") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        with pytest.raises(module.LocalCheckError) as err:
            module.ensure_tool(tmp_path / "cache", PIN, timeout=0.3)
    assert err.value.code == "CORE_INSTALL_FAILED"
    assert "lock" in str(err.value)
