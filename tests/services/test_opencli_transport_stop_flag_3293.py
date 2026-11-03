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
