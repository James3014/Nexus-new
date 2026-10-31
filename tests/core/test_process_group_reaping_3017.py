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


class _ReapOrder:
    """Records killpg and the reaping waitpid. killpg reaches a real group only while its leader
    (a child this test started) is unreaped; after that it is only recorded, never sent."""

    def __init__(self, monkeypatch):
        self.events: list[tuple[str, int]] = []
        self.reaped: set[int] = set()
        real_killpg, real_waitpid = os.killpg, os.waitpid

        def killpg(pgid, sig):
            self.events.append(("killpg", pgid))
            if pgid not in self.reaped:
                real_killpg(pgid, sig)

        def waitpid(pid, options):
            result = real_waitpid(pid, options)
            if result[0] == pid and pid > 0:
                self.reaped.add(pid)
                self.events.append(("reap", pid))
            return result

        monkeypatch.setattr(os, "killpg", killpg)
        monkeypatch.setattr(os, "waitpid", waitpid)

    def assert_group_killed_before_reap(self):
        reaps = [pid for kind, pid in self.events if kind == "reap"]
        assert len(reaps) == 1, self.events
        leader = reaps[0]
        assert ("killpg", leader) in self.events, self.events
        assert self.events.index(("killpg", leader)) < self.events.index(("reap", leader))
        assert self.events[-1] == ("reap", leader), f"killpg after the reap: {self.events}"


def test_the_group_is_never_signalled_after_its_leader_is_reaped(tmp_path, monkeypatch):
    order = _ReapOrder(monkeypatch)
    result = run_reaping_process_group(["/bin/sh", "-c", "echo done"], cwd=tmp_path, timeout=20)
    assert (result.returncode, result.stdout) == (0, "done\n")
    order.assert_group_killed_before_reap()


def test_a_timeout_signals_the_group_before_its_leader_is_reaped(tmp_path, monkeypatch):
    order = _ReapOrder(monkeypatch)
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        run_reaping_process_group(["/bin/sh", "-c", "echo part; sleep 60"], timeout=1)
    assert raised.value.stdout == b"part\n"
    order.assert_group_killed_before_reap()


def test_a_leader_reaped_elsewhere_leaves_the_group_unsignalled(tmp_path, monkeypatch):
    order = _ReapOrder(monkeypatch)

    def reap_it(pid, deadline):
        os.waitpid(pid, 0)
        return True

    monkeypatch.setattr(argv_command, "_wait_leader_unreaped", reap_it)
    with pytest.raises(ChildProcessError, match="not signalled"):
        run_reaping_process_group(["/bin/sh", "-c", "exit 0"], timeout=20)
    assert [kind for kind, _pid in order.events] == ["reap"]


def test_an_exited_leader_alone_is_not_a_survivor(tmp_path, monkeypatch):
    # macOS refuses killpg on a group holding only a zombie; that is the normal exit, not ps work.
    def no_ps(pgid):
        raise AssertionError("an empty group should not need ps")

    monkeypatch.setattr(argv_command, "_live_group_members", no_ps)
    assert run_reaping_process_group(["/bin/sh", "-c", "exit 0"], timeout=20).returncode == 0


@pytest.mark.parametrize(("survivors", "raises"), [([], False), ([424242], True), (None, True)])
def test_a_member_that_may_not_be_signalled_is_raised(monkeypatch, survivors, raises):
    order = _ReapOrder(monkeypatch)

    def refuse(pgid, sig):
        order.events.append(("killpg", pgid))
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "killpg", refuse)
    monkeypatch.setattr(argv_command, "_only_exited_leader_left", lambda pgid: False)
    monkeypatch.setattr(argv_command, "_live_group_members", lambda pgid: survivors)
    if raises:
        with pytest.raises(PermissionError, match="may not signal"):
            run_reaping_process_group(["/bin/sh", "-c", "exit 0"], timeout=20)
    else:
        assert run_reaping_process_group(["/bin/sh", "-c", "exit 0"], timeout=20).returncode == 0
    # Raised or not, the leader is reaped, after the attempt.
    order.assert_group_killed_before_reap()


def test_a_live_member_is_not_mistaken_for_an_exited_leader_alone(tmp_path, monkeypatch):
    # The group keeps a running child of the command; killpg is refused (simulated), so the
    # libproc shortcut must not call the group empty and ps must be asked.
    asked = []

    def refuse(pgid, sig):
        raise PermissionError(1, "Operation not permitted")

    def ps_says(pgid):
        asked.append(pgid)
        return [_background_pid(tmp_path)]

    monkeypatch.setattr(os, "killpg", refuse)
    monkeypatch.setattr(argv_command, "_live_group_members", ps_says)
    try:
        with pytest.raises(PermissionError, match="may not signal"):
            run_reaping_process_group(["/bin/sh", "-c", DETACH], cwd=tmp_path, timeout=20)
        assert len(asked) == 1
    finally:
        # The refusal was simulated, so the child (started by this test) is still running.
        monkeypatch.undo()
        background = _background_pid(tmp_path)
        try:
            os.kill(background, signal.SIGKILL)
        except ProcessLookupError:
            pass
        _assert_reaped(background)
