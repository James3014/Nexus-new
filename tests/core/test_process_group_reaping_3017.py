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
import sys
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

    # Linux lists the group from /proc after its successful killpg; neither platform runs ps.
    monkeypatch.setattr(argv_command, "_ps_live_group_members", no_ps)
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


darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason="kqueue and libproc are macOS")


def _no_spawn(monkeypatch):
    def popen(*_a, **_k):
        raise AssertionError("nothing may be spawned")

    monkeypatch.setattr(argv_command.subprocess, "Popen", popen)


def test_without_waitid_macos_waits_through_kqueue_and_others_refuse(tmp_path, monkeypatch):
    # macOS before Python 3.13 has no os.waitid; the leader is then waited for through kqueue.
    monkeypatch.delattr(os, "waitid", raising=False)
    if sys.platform != "darwin":
        _no_spawn(monkeypatch)
        with pytest.raises(argv_command.ProcessGroupReapingUnavailable):
            run_reaping_process_group(["/bin/sh", "-c", "exit 0"], timeout=20)
        return
    order = _ReapOrder(monkeypatch)
    result = run_reaping_process_group(["/bin/sh", "-c", DETACH], cwd=tmp_path, timeout=20)
    assert result.returncode == 0
    order.assert_group_killed_before_reap()
    _assert_reaped(_background_pid(tmp_path))
    (tmp_path / "bg.pid").unlink()
    with pytest.raises(subprocess.TimeoutExpired):
        run_reaping_process_group(["/bin/sh", "-c", f"{DETACH}; sleep 60"], cwd=tmp_path, timeout=1)
    _assert_reaped(_background_pid(tmp_path))


@darwin_only
def test_kqueue_wait_neither_reaps_nor_misses_an_exit(monkeypatch):
    monkeypatch.delattr(os, "waitid", raising=False)
    sleeper = subprocess.Popen(["/bin/sleep", "60"], start_new_session=True)
    quick = subprocess.Popen(["/bin/sh", "-c", "exit 0"], start_new_session=True)
    try:
        assert argv_command._wait_leader_unreaped(sleeper.pid, time.monotonic() + 0.2) is False
        # Exited before the wait starts: kqueue answers ESRCH; the zombie is still unreaped.
        for _ in range(200):
            info = argv_command._darwin_proc(quick.pid)
            if info is not None and info.pbi_status == argv_command._SZOMB:
                break
            time.sleep(0.01)
        assert argv_command._wait_leader_unreaped(quick.pid, None) is True
        assert argv_command._leader_unreaped(quick.pid) is True
        # Exits during the wait.
        sleeper.kill()
        assert argv_command._wait_leader_unreaped(sleeper.pid, time.monotonic() + 10) is True
        assert argv_command._leader_unreaped(sleeper.pid) is True
    finally:
        for child in (sleeper, quick):
            if child.returncode is None:
                child.kill()
            child.wait()
    assert argv_command._leader_unreaped(quick.pid) is False


def test_no_way_to_wait_unreaped_refuses_before_spawning(monkeypatch):
    monkeypatch.delattr(os, "waitid", raising=False)
    monkeypatch.delattr(argv_command.select, "kqueue", raising=False)
    _no_spawn(monkeypatch)
    with pytest.raises(argv_command.ProcessGroupReapingUnavailable, match="without reaping"):
        run_reaping_process_group(["/bin/sh", "-c", "exit 0"], timeout=20)


@pytest.mark.parametrize("handler", [signal.SIG_IGN, lambda signum, frame: None])
def test_sigchld_not_at_its_default_is_refused_before_spawning(monkeypatch, handler):
    # SIG_IGN makes the kernel reap children itself; a handler may reap with waitpid(-1).
    _no_spawn(monkeypatch)
    previous = signal.signal(signal.SIGCHLD, handler)
    try:
        with pytest.raises(argv_command.ProcessGroupReapingUnavailable, match="SIGCHLD"):
            run_reaping_process_group(["/bin/sh", "-c", "exit 0"], timeout=20)
    finally:
        signal.signal(signal.SIGCHLD, previous)


@pytest.mark.parametrize(
    ("alone", "listed", "raises"),
    [
        ([False] * 1000, [424242], True),  # survivor with other credentials
        ([False] * 1000, None, True),  # group cannot be listed
        ([False, False, True], [424242], False),  # killed members die within the bound
    ],
)
def test_a_successful_killpg_is_checked_for_survivors(monkeypatch, alone, listed, raises):
    # killpg succeeds once any member got the signal; a member it did not reach must not pass.
    order = _ReapOrder(monkeypatch)
    answers = iter(alone)

    def reached_some(pgid, sig):
        order.events.append(("killpg", pgid))

    monkeypatch.setattr(os, "killpg", reached_some)
    monkeypatch.setattr(argv_command, "_KILL_SETTLE_SECONDS", 0.2)
    monkeypatch.setattr(argv_command, "_only_exited_leader_left", lambda pgid: next(answers))
    monkeypatch.setattr(argv_command, "_live_group_members", lambda pgid: listed)
    if raises:
        with pytest.raises(PermissionError, match="may not signal"):
            run_reaping_process_group(["/bin/sh", "-c", "exit 0"], timeout=20)
    else:
        assert run_reaping_process_group(["/bin/sh", "-c", "exit 0"], timeout=20).returncode == 0
    reaps = [pid for kind, pid in order.events if kind == "reap"]
    assert reaps and order.events.index(("killpg", reaps[0])) < order.events.index((
        "reap",
        reaps[0],
    ))
    assert order.events[-1] == ("reap", reaps[0])


@pytest.mark.parametrize(
    "listing",
    [
        "",
        "garbage\n",
        "{me} {mine}\n",  # a row without its state
        "{me} {mine} S\nabc 777 S\n",
        "{me} {mine} S\n500 777 S extra\n",
        "500 777 S\n",  # truncated: this process is missing
    ],
)
def test_ps_output_that_cannot_be_read_is_unknown(monkeypatch, listing):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        text = listing.format(me=os.getpid(), mine=os.getpgid(0))
        return subprocess.CompletedProcess(argv, 0, text, "")

    monkeypatch.setattr(argv_command.subprocess, "run", fake_run)
    assert argv_command._ps_live_group_members(777) is None
    assert calls[0][0] == "/bin/ps"


def test_ps_output_lists_live_members_only(monkeypatch):
    # Z: zombie; E: exiting (macOS shows ?E for a leader mid-exit); ? alone: unknown, so live.
    listing = (
        f"{os.getpid()} {os.getpgid(0)} Ss\n500 777 S+\n501 777 Z\n  502   777 R\n"
        "503 777 ?NE\n504 777 ?N\n"
    )
    monkeypatch.setattr(
        argv_command.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, listing, ""),
    )
    assert argv_command._ps_live_group_members(777) == [500, 502, 504]

    def broken(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(argv_command.subprocess, "run", broken)
    assert argv_command._ps_live_group_members(777) is None


def _fake_proc(root: Path, stats: dict[str, bytes]) -> None:
    for name, stat in stats.items():
        (root / name).mkdir()
        (root / name / "stat").write_bytes(stat)


def test_proc_listing_reads_state_and_group_past_the_command_name(tmp_path, monkeypatch):
    me = os.getpid()
    _fake_proc(
        tmp_path,
        {
            str(me): f"{me} (python) S 1 {me} 0".encode(),
            "500": b"500 (odd) name) R 1 777 0",
            "501": b"501 (dead) Z 1 777 0",
            "502": b"502 (other) S 1 778 0",
            "self": b"not a pid",
        },
    )
    monkeypatch.setattr(argv_command, "_PROC_ROOT", str(tmp_path))
    assert argv_command._proc_live_group_members(777) == [500]


@pytest.mark.parametrize("bad", [b"500 odd S 1 777", b"500 (x) S 1", b"500 (x) S 1 seven"])
def test_proc_listing_that_cannot_be_read_is_unknown(tmp_path, monkeypatch, bad):
    me = os.getpid()
    _fake_proc(tmp_path, {str(me): f"{me} (python) S 1 {me} 0".encode(), "500": bad})
    monkeypatch.setattr(argv_command, "_PROC_ROOT", str(tmp_path))
    assert argv_command._proc_live_group_members(777) is None
    (tmp_path / "500" / "stat").write_bytes(b"500 (x) S 1 777 0")
    (tmp_path / str(me) / "stat").unlink()
    (tmp_path / str(me)).rmdir()
    # This process missing from the listing: not a full one.
    assert argv_command._proc_live_group_members(777) is None


@pytest.mark.parametrize(
    ("filled", "expected"), [(0, None), (6, None), (4096, None), (8, [777, 9])]
)
def test_libproc_byte_counts_that_are_not_whole_pids_are_unknown(monkeypatch, filled, expected):
    class FakeLibproc:
        def proc_listpids(self, kind, pgid, buffer, size):
            assert (kind, pgid, size) == (2, 777, 4096)
            buffer[0], buffer[1] = 777, 9
            return filled

    monkeypatch.setattr(argv_command, "_libproc", FakeLibproc)
    assert argv_command._darwin_group_pids(777) == expected


@pytest.mark.parametrize("where", ["_leader_unreaped", "_only_exited_leader_left"])
def test_an_interrupted_cleanup_still_signals_the_group_before_the_reap(
    tmp_path, monkeypatch, where
):
    # A signal handler raising inside the cleanup, before the group was signalled and checked.
    order = _ReapOrder(monkeypatch)

    def interrupted(*_a):
        raise KeyboardInterrupt

    monkeypatch.setattr(argv_command, where, interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_reaping_process_group(["/bin/sh", "-c", DETACH], cwd=tmp_path, timeout=20)
    order.assert_group_killed_before_reap()
    _assert_reaped(_background_pid(tmp_path))


def test_an_interrupted_read_still_signals_the_group(tmp_path, monkeypatch):
    order = _ReapOrder(monkeypatch)

    def interrupted(process, deadline):
        _background_pid(tmp_path)
        raise KeyboardInterrupt

    monkeypatch.setattr(argv_command, "_read_pipes", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_reaping_process_group(
            ["/bin/sh", "-c", f"{DETACH}; sleep 60"], cwd=tmp_path, timeout=20
        )
    order.assert_group_killed_before_reap()
    _assert_reaped(_background_pid(tmp_path))


def test_large_simultaneous_stdout_and_stderr_are_read_whole():
    script = (
        "import sys\n"
        "for i in range(64):\n"
        "    sys.stdout.buffer.write(b'o' * 16384); sys.stderr.buffer.write(b'e' * 16384)\n"
    )
    result = run_reaping_process_group([sys.executable, "-c", script], text=False, timeout=60)
    assert result.returncode == 0
    assert result.stdout == b"o" * (1 << 20) and result.stderr == b"e" * (1 << 20)


def test_a_character_split_across_reads_decodes_whole():
    script = (
        "import sys, time\n"
        "out = sys.stdout.buffer\n"
        "out.write(b'\\xe4'); out.flush(); time.sleep(0.3); out.write(b'\\xb8\\xad\\r\\n')\n"
    )
    result = run_reaping_process_group(
        [sys.executable, "-c", script], env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=60
    )
    assert result.stdout == "中\n"


@darwin_only
def test_a_live_leader_alone_is_not_an_exited_leader_alone(tmp_path):
    # Only an exited (zombie) leader with no other member counts as an empty group.
    leader = subprocess.Popen(["/bin/sleep", "60"], start_new_session=True)
    with_child = subprocess.Popen(["/bin/sh", "-c", DETACH], cwd=tmp_path, start_new_session=True)
    background = _background_pid(tmp_path)
    try:
        assert argv_command._only_exited_leader_left(leader.pid) is False
        leader.kill()
        for _ in range(200):
            if argv_command._only_exited_leader_left(leader.pid):
                break
            time.sleep(0.01)
        assert argv_command._only_exited_leader_left(leader.pid) is True
        # The leader exited, but its background child still runs in the group.
        argv_command._wait_leader_unreaped(with_child.pid, time.monotonic() + 10)
        assert argv_command._only_exited_leader_left(with_child.pid) is False
    finally:
        os.kill(background, signal.SIGKILL)
        for child in (leader, with_child):
            if child.returncode is None:
                child.kill()
            child.wait()
        _assert_reaped(background)


def test_a_leader_that_survives_sigkill_is_not_waited_for_without_bound(monkeypatch):
    # A live leader this process may not signal (simulated: nothing is sent) must not turn the
    # cleanup into an unbounded wait.
    sent, leaders = [], []

    def refused(pgid):
        leaders.append(pgid)
        raise PermissionError(1, "process group keeps members it may not signal")

    monkeypatch.setattr(argv_command, "_kill_process_group", refused)
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: sent.append(pgid))
    monkeypatch.setattr(argv_command, "_KILL_SETTLE_SECONDS", 0.3)
    started = time.monotonic()
    try:
        with pytest.raises(PermissionError, match="left unreaped"):
            run_reaping_process_group(["/bin/sleep", "60"], timeout=0.5)
        assert time.monotonic() - started < 10
        assert sent == leaders  # the fallback SIGKILL, before giving up, never after
    finally:
        monkeypatch.undo()
        for pid in leaders:  # the child this test started
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)


def test_a_kqueue_exit_waits_until_the_leader_is_a_zombie(monkeypatch):
    # kqueue reports NOTE_EXIT while the leader is still exiting; macOS then refuses killpg on
    # it and ps shows it as live, so the wait goes on until it is a zombie, as waitid reports.
    class Info:
        def __init__(self, status):
            self.pbi_status = status

    states = iter([2, 2, 2, argv_command._SZOMB])
    asked = []

    def proc(pid):
        asked.append(pid)
        return Info(next(states))

    monkeypatch.setattr(argv_command, "_darwin_proc", proc)
    argv_command._await_zombie(4242)
    assert asked == [4242] * 4
