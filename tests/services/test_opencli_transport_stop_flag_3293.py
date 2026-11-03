"""#3293: the OpenCLI transport waits through the shared process-group path, so the #3200/#3206
process-wide stop flag kills its opencli group. Only processes these tests start are signalled."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

from nexus.core import argv_command
from nexus.core.argv_command import ProcessGroupShutdown
from nexus.services.external_intelligence import OpenCLIExternalIntelligenceTransport

STUB = """#!{python}
import os, sys, time
open({pidfile!r}, "w").write(str(os.getpid()))
time.sleep(float({sleep!r}))
sys.stdout.write("late")
"""


def _stub(tmp_path: Path, sleep: float) -> tuple[str, Path]:
    pidfile = tmp_path / "pid"
    path = tmp_path / "opencli"
    path.write_text(STUB.format(python=sys.executable, pidfile=str(pidfile), sleep=sleep))
    path.chmod(0o755)
    return str(path), pidfile


def _wait_pid(pidfile: Path) -> int:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if pidfile.exists() and pidfile.read_text().strip():
            return int(pidfile.read_text())
        time.sleep(0.05)
    raise AssertionError("stub did not start")


def _group_gone(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    return False


def test_stop_flag_stops_a_waiting_transport_and_kills_its_group(tmp_path, monkeypatch):
    executable, pidfile = _stub(tmp_path, 120)
    transport = OpenCLIExternalIntelligenceTransport(executable=executable)
    outcome: list[object] = []

    def run():
        try:
            outcome.append(transport._run([executable, "chatgpt", "ask"], os.environ))
        except BaseException as exc:  # noqa: BLE001 - the test inspects what propagated
            outcome.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    pgid = None
    try:
        thread.start()
        pgid = os.getpgid(_wait_pid(pidfile))
        started = time.monotonic()
        monkeypatch.setattr(argv_command, "_shutdown_requested", True)
        thread.join(timeout=15)
        assert not thread.is_alive()
        assert time.monotonic() - started < 15
        assert len(outcome) == 1 and isinstance(outcome[0], ProcessGroupShutdown)
        assert _group_gone(pgid)
    finally:
        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_timeout_still_returns_timed_out_and_kills_the_group(tmp_path):
    executable, pidfile = _stub(tmp_path, 120)
    transport = OpenCLIExternalIntelligenceTransport(executable=executable, timeout=-1)
    try:
        code, stdout, _stderr, timed_out = transport._run([executable], os.environ)
        assert timed_out is True
        assert stdout == ""
        assert _group_gone(int(pidfile.read_text()))
    finally:
        if pidfile.exists():
            try:
                os.killpg(int(pidfile.read_text()), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def test_normal_exit_returns_decoded_output(tmp_path):
    executable, _ = _stub(tmp_path, 0)
    transport = OpenCLIExternalIntelligenceTransport(executable=executable)
    code, stdout, stderr, timed_out = transport._run([executable], os.environ)
    assert (code, stdout, stderr, timed_out) == (0, "late", "", False)


LEADER_STUB = """#!{python}
import os, signal, subprocess, sys, time
member = subprocess.Popen([sys.executable, "-c",
    "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)"])
open({pidfile!r}, "w").write(str(member.pid))
sys.stdout.write("before-out"); sys.stdout.flush()
sys.stderr.write("before-err"); sys.stderr.flush()
time.sleep(120)
"""


def _leader_stub(tmp_path: Path) -> tuple[str, Path]:
    pidfile = tmp_path / "member-pid"
    path = tmp_path / "opencli-leader"
    path.write_text(LEADER_STUB.format(python=sys.executable, pidfile=str(pidfile)))
    path.chmod(0o755)
    return str(path), pidfile


def _pid_gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def _run_timed_out_leader(tmp_path: Path):
    executable, pidfile = _leader_stub(tmp_path)
    transport = OpenCLIExternalIntelligenceTransport(executable=executable, timeout=1)
    try:
        return transport._run([executable], os.environ), pidfile
    except BaseException:
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        raise


def test_timeout_kills_a_sigterm_ignoring_group_member_before_returning(tmp_path):
    (_code, _stdout, _stderr, timed_out), pidfile = _run_timed_out_leader(tmp_path)
    member = int(pidfile.read_text())
    try:
        assert timed_out is True
        assert _pid_gone(member)
    finally:
        try:
            os.kill(member, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def test_timeout_returns_output_written_before_the_timeout(tmp_path):
    (_code, stdout, stderr, timed_out), pidfile = _run_timed_out_leader(tmp_path)
    try:
        assert timed_out is True
        assert stdout.startswith("before-out")
        assert stderr.startswith("before-err")
    finally:
        try:
            os.kill(int(pidfile.read_text()), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def test_timeout_drain_that_finds_a_surviving_member_returns_unknown_outcome(monkeypatch):
    # All stubs: no real process is started or signalled.
    import subprocess

    from nexus.services import external_intelligence as module

    class _FakeProcess:
        pid = 999_999_999
        returncode = None
        stdout = None
        stderr = None
        args = ["opencli"]

        def wait(self, timeout=None):
            self.returncode = -9
            return self.returncode

    calls: list[float] = []

    def fake_wait(process, timeout, before_kill=None):
        calls.append(timeout)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(process.args, timeout, output=b"early", stderr=b"")
        raise PermissionError("a group member survived SIGKILL")

    monkeypatch.setattr(module, "require_child_stays_unreaped", lambda: None)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: _FakeProcess())
    monkeypatch.setattr(module, "communicate_then_kill_group", fake_wait)
    monkeypatch.setattr(module.os, "killpg", lambda *a: None)
    transport = OpenCLIExternalIntelligenceTransport(executable="opencli", timeout=1)

    code, stdout, _stderr, timed_out = transport._run(["opencli"], os.environ)

    assert timed_out is True
    assert stdout == "early"
    assert len(calls) == 2
