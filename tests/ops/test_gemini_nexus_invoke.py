import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from scripts.ops import gemini_nexus_invoke


def test_gemini_invoker_strips_nexus_runner_and_sandbox_env(monkeypatch):
    monkeypatch.setenv("NEXUS_RUNNER", "Gemini")
    monkeypatch.setenv("GEMINI_SANDBOX", "true")
    monkeypatch.setenv("NEXUS_KEEP_ME", "yes")

    env = gemini_nexus_invoke._gemini_subprocess_env()

    assert "NEXUS_RUNNER" not in env
    assert "GEMINI_SANDBOX" not in env
    assert env["NEXUS_KEEP_ME"] == "yes"
    assert os.environ["GEMINI_SANDBOX"] == "true"


def test_lock_file_left_by_a_killed_run_does_not_block_the_next_run(tmp_path):
    """#3203: a lock file whose holder died (no live lock on it) is taken over."""
    lock = tmp_path / "gemini.lock"
    lock.write_text("999999999", encoding="utf-8")

    assert gemini_nexus_invoke._acquire_lock(lock) is True
    try:
        assert lock.read_text(encoding="utf-8") == str(os.getpid())
    finally:
        gemini_nexus_invoke._release_lock(lock)
    assert not lock.exists()


def test_lock_held_by_a_live_holder_still_blocks(tmp_path):
    """#3203: single flight still holds while another descriptor owns the lock."""
    import fcntl

    lock = tmp_path / "gemini.lock"
    holder = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert gemini_nexus_invoke._acquire_lock(lock) is False
        assert lock.exists()
    finally:
        os.close(holder)

    assert gemini_nexus_invoke._acquire_lock(lock) is True
    gemini_nexus_invoke._release_lock(lock)


def test_lock_released_by_holder_is_reacquired_on_the_new_file(tmp_path, monkeypatch):
    """#3203: when the holder unlinks the file while we lock it, retry on the current path."""
    lock = tmp_path / "gemini.lock"
    real_flock = gemini_nexus_invoke.fcntl.flock
    calls: list[int] = []

    def flock_after_holder_released(fd, operation):
        calls.append(fd)
        if len(calls) == 1:
            # The previous holder releases between our open() and flock(): it unlinks the
            # file we opened, and a third run creates a fresh one at the same path.
            lock.unlink()
            lock.write_text("third run", encoding="utf-8")
        return real_flock(fd, operation)

    monkeypatch.setattr(gemini_nexus_invoke.fcntl, "flock", flock_after_holder_released)
    assert gemini_nexus_invoke._acquire_lock(lock) is True
    try:
        assert len(calls) == 2
        assert os.path.samestat(os.fstat(gemini_nexus_invoke._LOCK_FDS[lock]), os.stat(lock))
    finally:
        gemini_nexus_invoke._release_lock(lock)
    gemini_nexus_invoke._release_lock(lock)
    assert not lock.exists()


@pytest.mark.parametrize("target_exists", [True, False])
def test_lock_path_planted_as_symlink_is_refused_without_touching_the_target(
    tmp_path, target_exists
):
    """#3203 review: the shared lock path is opened with O_NOFOLLOW, never through a symlink."""
    target = tmp_path / "victim.txt"
    if target_exists:
        target.write_text("keep me", encoding="utf-8")
    lock = tmp_path / "gemini.lock"
    lock.symlink_to(target)

    with pytest.raises(OSError):
        gemini_nexus_invoke._acquire_lock(lock)

    assert lock.is_symlink()
    if target_exists:
        assert target.read_text(encoding="utf-8") == "keep me"
    else:
        assert not target.exists()
    assert lock not in gemini_nexus_invoke._LOCK_FDS


def test_lock_path_planted_as_hard_link_is_refused_without_truncating(tmp_path):
    """#3203 review: a hard link at the lock path is not locked or truncated."""
    target = tmp_path / "victim.txt"
    target.write_text("keep me", encoding="utf-8")
    lock = tmp_path / "gemini.lock"
    os.link(target, lock)

    with pytest.raises(OSError):
        gemini_nexus_invoke._acquire_lock(lock)

    assert target.read_text(encoding="utf-8") == "keep me"
    assert lock not in gemini_nexus_invoke._LOCK_FDS


def test_main_reports_a_planted_symlink_lock_as_unusable(tmp_path, monkeypatch, capsys):
    """#3203 review: main does not resolve the lock path past a planted symlink."""
    import json
    import sys

    fake_gemini = tmp_path / "gemini"
    fake_gemini.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    target = tmp_path / "victim.txt"
    target.write_text("keep me", encoding="utf-8")
    lock = tmp_path / "gemini.lock"
    lock.symlink_to(target)
    monkeypatch.setattr(gemini_nexus_invoke, "GEMINI_BIN", fake_gemini)
    monkeypatch.setattr(
        sys, "argv", ["gemini_nexus_invoke.py", "--prompt", "hi", "--lock-file", str(lock)]
    )

    code = gemini_nexus_invoke.main.__wrapped__()

    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 3
    assert report["reason"] == "single_flight_lock_unusable"
    assert target.read_text(encoding="utf-8") == "keep me"


# --- #3203: the Gemini child's lifetime is bounded by the single-flight lock -------------

_REPO_ROOT = Path(__file__).resolve().parents[2]

_FAKE_GEMINI = """\
import os, sys, time
from pathlib import Path
here = Path(__file__).resolve().parent
(here / "child.pid").write_text(str(os.getpid()))
print("started", flush=True)
deadline = time.monotonic() + 30
n = 0
while not (here / "stop").exists() and time.monotonic() < deadline:
    n += 1
    (here / "heartbeat").write_text(str(n))
    time.sleep(0.05)
(here / "exited").write_text("1")
"""


def _fake_gemini(tmp_path: Path) -> Path:
    """A fake Gemini CLI that heartbeats silently until ``stop`` appears (30 s at most)."""
    home = tmp_path / "fake"
    home.mkdir()
    fake = home / "gemini"
    fake.write_text(f"#!{sys.executable}\n" + _FAKE_GEMINI, encoding="utf-8")
    fake.chmod(0o755)
    return fake


def _wait_for(predicate, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _heartbeat_stopped(fake: Path) -> bool:
    beat = fake.parent / "heartbeat"
    first = beat.read_text(encoding="utf-8")
    time.sleep(0.6)
    return beat.read_text(encoding="utf-8") == first


def _start_invoker(tmp_path: Path, fake: Path, lock: Path) -> subprocess.Popen:
    argv = [
        "gemini_nexus_invoke.py",
        "--prompt",
        "hi",
        "--cwd",
        str(tmp_path),
        "--lock-file",
        str(lock),
        "--timeout-sec",
        "60",
        "--max-retries",
        "0",
    ]
    code = (
        "import sys\n"
        "from scripts.ops import gemini_nexus_invoke as g\n"
        f"sys.argv = {argv!r}\n"
        "raise SystemExit(g.main.__wrapped__())\n"
    )
    env = dict(os.environ, GEMINI_BIN=str(fake))
    return subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=str(_REPO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.mark.parametrize("signame", ["SIGTERM", "SIGHUP"])
def test_terminated_invoker_stops_its_gemini_child_before_releasing_the_lock(tmp_path, signame):
    """#3203: TERM/HUP to the invoker stops the Gemini child too, so no run overlaps it."""
    fake = _fake_gemini(tmp_path)
    lock = tmp_path / "gemini.lock"
    invoker = _start_invoker(tmp_path, fake, lock)
    try:
        assert _wait_for(lambda: (fake.parent / "heartbeat").exists()), "fake Gemini never ran"
        invoker.send_signal(getattr(signal, signame))
        exit_code = invoker.wait(timeout=15)
        assert _heartbeat_stopped(fake), "the Gemini child outlived the invoker"
        assert exit_code == 128 + getattr(signal, signame)
        assert not (fake.parent / "exited").exists()
        assert gemini_nexus_invoke._acquire_lock(lock) is True
        gemini_nexus_invoke._release_lock(lock)
    finally:
        (fake.parent / "stop").write_text("1")
        if invoker.poll() is None:
            invoker.kill()
            invoker.wait()
        gemini_nexus_invoke._release_lock(lock)


def test_killed_invoker_leaves_the_lock_held_until_its_gemini_child_exits(tmp_path):
    """#3203: SIGKILL cannot be handled, so the orphaned child keeps the lock until it exits."""
    fake = _fake_gemini(tmp_path)
    lock = tmp_path / "gemini.lock"
    invoker = _start_invoker(tmp_path, fake, lock)
    try:
        assert _wait_for(lambda: (fake.parent / "heartbeat").exists()), "fake Gemini never ran"
        invoker.kill()
        invoker.wait(timeout=15)
        assert not _heartbeat_stopped(fake), "precondition: the orphan is still working"
        assert gemini_nexus_invoke._acquire_lock(lock) is False, "a second run would overlap"

        (fake.parent / "stop").write_text("1")
        assert _wait_for(lambda: (fake.parent / "exited").exists())

        def acquired() -> bool:
            return gemini_nexus_invoke._acquire_lock(lock)

        assert _wait_for(acquired, timeout=10)
    finally:
        (fake.parent / "stop").write_text("1")
        if invoker.poll() is None:
            invoker.kill()
            invoker.wait()
        gemini_nexus_invoke._release_lock(lock)


def test_wall_clock_timeout_stops_the_gemini_group_and_reports_124(tmp_path, monkeypatch):
    """#3203: the timeout path reaps the child's group and keeps its documented exit code."""
    fake = _fake_gemini(tmp_path)
    monkeypatch.setattr(gemini_nexus_invoke, "GEMINI_BIN", fake)
    try:
        code, _out, _elapsed, cls = gemini_nexus_invoke._run_once(
            model="m", prompt="p", cwd=tmp_path, timeout_sec=1
        )
        assert (code, cls) == (124, "TIMEOUT_WALLCLOCK")
        assert _heartbeat_stopped(fake)
        assert not (fake.parent / "exited").exists()
    finally:
        (fake.parent / "stop").write_text("1")


def test_termination_signals_keep_an_ignored_hangup_ignored():
    """#3203: under nohup SIGHUP stays ignored; SIGTERM raises; both restored afterwards."""
    previous_hup = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    previous_term = signal.getsignal(signal.SIGTERM)
    try:
        with gemini_nexus_invoke._termination_signals_raise():
            assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
            handler = signal.getsignal(signal.SIGTERM)
            assert callable(handler)
            with pytest.raises(SystemExit) as raised:
                handler(signal.SIGTERM, None)
            assert raised.value.code == 128 + signal.SIGTERM
        assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
        assert signal.getsignal(signal.SIGTERM) == previous_term
    finally:
        signal.signal(signal.SIGHUP, previous_hup)


def test_termination_signals_leave_a_non_python_hangup_handler_in_place(monkeypatch):
    """#3203: a handler getsignal reports as None is neither replaced nor "restored"."""
    real_getsignal = signal.getsignal
    real_signal = signal.signal
    replaced: list[object] = []

    def getsignal(signum):
        return None if signum == signal.SIGHUP else real_getsignal(signum)

    def fake_signal(signum, handler):
        if signum != signal.SIGHUP:
            return real_signal(signum, handler)
        replaced.append(handler)
        return None

    monkeypatch.setattr(gemini_nexus_invoke.signal, "getsignal", getsignal)
    monkeypatch.setattr(gemini_nexus_invoke.signal, "signal", fake_signal)
    with gemini_nexus_invoke._termination_signals_raise():
        pass
    assert replaced == []


def test_termination_signals_install_nothing_off_the_main_thread():
    """#3203: from a worker thread no handler is installed (signal.signal would raise there)."""
    before = signal.getsignal(signal.SIGTERM)
    seen: list[object] = []
    errors: list[BaseException] = []

    def body():
        try:
            with gemini_nexus_invoke._termination_signals_raise():
                seen.append(signal.getsignal(signal.SIGTERM))
        except BaseException as exc:  # noqa: BLE001 - reported to the main thread
            errors.append(exc)

    worker = threading.Thread(target=body)
    worker.start()
    worker.join(timeout=10)
    assert errors == []
    assert seen == [before]
