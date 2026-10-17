"""Issue #2367 items 1-3: the codex run guard's process boundary.

``codex_run_guard.py exec`` runs codex in its own session.  These tests pin
what must hold when it returns: no child that left the process group
(``setsid``) can still write into the work copy, the group kill cannot hit a
reused PID, and a signal that arrives during launch is not lost.
"""

from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

_GUARD = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "codex_run_guard.py"

# Forks; the grandchild leaves the process group with setsid(), waits until
# the guard process has exited (polling its pid, so a slow sweep cannot make
# the write early), then writes into the work copy (its cwd).  The
# direct child exits at once, so codex "finishes" immediately.  With
# "clear", the grandchild re-executes itself with an empty environment (so
# the run tag is gone) before waiting; only its cwd still ties it to the run.
_ESCAPER = textwrap.dedent(
    """
    import os, sys, time
    work, mode = sys.argv[1], sys.argv[2]
    if mode == "late":
        guard = int(sys.argv[3])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                os.kill(guard, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        time.sleep(0.2)
        with open(os.path.join(work, "late-write.txt"), "w") as handle:
            handle.write("written after the guard returned\\n")
        os._exit(0)
    guard = os.getppid()
    if os.fork() == 0:
        os.setsid()
        os.chdir(work)
        env = {} if mode == "clear" else dict(os.environ)
        os.execve(sys.executable, [sys.executable, "-I", sys.argv[0], work, "late", str(guard)], env)
    os._exit(0)
    """
)


def _load_guard():
    spec = importlib.util.spec_from_file_location("codex_run_guard_under_test", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_escaper(tmp_path: Path, guard_args: list[str], mode: str):
    escaper = tmp_path / "escaper.py"
    escaper.write_text(_ESCAPER, encoding="utf-8")
    work = Path(guard_args[-1]) if len(guard_args) > 1 else tmp_path / "work"
    res = subprocess.run(
        [
            sys.executable,
            "-I",
            str(_GUARD),
            "exec",
            *guard_args,
            "--",
            sys.executable,
            "-I",
            str(escaper),
            str(work),
            mode,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    time.sleep(1.5)  # a surviving grandchild writes ~0.25 s after the guard exits
    return res, work


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    run_home = tmp_path / "home"
    (run_home / "tmp").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    return run_home, work


def test_codex_guard_kills_a_tagged_setsid_child_before_returning(tmp_path):
    # Legacy CLI form (no work copy argument): the run tag alone finds it.
    run_home, work = _dirs(tmp_path)
    res, _ = _run_escaper(tmp_path, [str(run_home)], "keep")

    assert not (work / "late-write.txt").exists(), (
        "a setsid child outlived the guard and wrote into the work copy"
    )
    assert res.returncode == 0, res.stderr


def test_codex_guard_kills_an_untagged_setsid_child_in_the_work_copy(tmp_path):
    run_home, work = _dirs(tmp_path)
    res, _ = _run_escaper(tmp_path, [str(run_home), str(work)], "clear")

    assert not (work / "late-write.txt").exists(), (
        "an env-cleared setsid child outlived the guard and wrote into the work copy"
    )
    assert res.returncode == 0, res.stderr


def test_codex_guard_kills_the_group_before_reaping_the_leader(tmp_path, monkeypatch):
    guard = _load_guard()
    observed: list[bool] = []
    real_killpg = os.killpg
    holder: dict[str, int] = {}

    def recording_killpg(group, signum):
        if signum == signal.SIGKILL and group == holder.get("pid"):
            try:
                # Still unreaped (a zombie) means its PID cannot be reused yet.
                info = os.waitid(os.P_PID, group, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                observed.append(info is not None)
            except ChildProcessError:
                observed.append(False)
        return real_killpg(group, signum)

    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        if kwargs.get("start_new_session"):
            holder["pid"] = child.pid  # the codex launch, not the sweep's ps probes
        return child

    monkeypatch.setattr(guard.os, "killpg", recording_killpg)
    monkeypatch.setattr(guard.subprocess, "Popen", recording_popen)
    work = tmp_path / "work"
    work.mkdir()

    status = guard.run_in_own_group([sys.executable, "-I", "-c", "pass"], dict(os.environ), work)

    assert status == 0
    assert observed and all(observed), "the group was killed after the leader was reaped"


def test_codex_guard_installs_signal_handlers_before_launch(tmp_path, monkeypatch):
    guard = _load_guard()
    seen: dict[int, object] = {}
    real_popen = subprocess.Popen

    def checking_popen(*args, **kwargs):
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            seen[signum] = signal.getsignal(signum)
        return real_popen(*args, **kwargs)

    previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    monkeypatch.setattr(guard.subprocess, "Popen", checking_popen)
    work = tmp_path / "work"
    work.mkdir()
    try:
        guard.run_in_own_group([sys.executable, "-I", "-c", "pass"], dict(os.environ), work)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        assert seen[signum] is not previous[signum], f"{signum!r} handler installed after Popen"
        assert callable(seen[signum])


def test_codex_guard_forwards_a_signal_that_arrives_during_launch(tmp_path, monkeypatch):
    guard = _load_guard()
    real_popen = subprocess.Popen

    def signalled_popen(*args, **kwargs):
        if kwargs.get("start_new_session"):
            os.kill(os.getpid(), signal.SIGTERM)  # arrives before the group is known
        return real_popen(*args, **kwargs)

    previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    monkeypatch.setattr(guard.subprocess, "Popen", signalled_popen)
    work = tmp_path / "work"
    work.mkdir()
    started = time.monotonic()
    try:
        status = guard.run_in_own_group(
            [sys.executable, "-I", "-c", "import time; time.sleep(30)"], dict(os.environ), work
        )
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)

    assert status == 128 + signal.SIGTERM
    assert time.monotonic() - started < 20, "the queued SIGTERM was never forwarded"
