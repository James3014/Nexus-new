"""#2470 item 1: on the Agy write boundary the cwd sweep reports, and never kills,
processes it cannot prove are the run's.

With ``kill_unproven_cwd_matches=False`` (only ``AgyDispatchBoundary`` passes it)
``sweep_run`` kills tracked descendants and run-tagged processes only. Any
other same-uid process that started after the baseline with a cwd inside the
target (an Owner shell or editor that ``cd``-ed into the disposable worktree)
is left running and makes the sweep unclean, so the caller reconciles. Every
other caller (``run_cli_worker``: codex executor, Claude measurement worker,
the Agy worker adapter) keeps main's behaviour and kills such processes.

The physical tests start real processes and only ever signal them by PID.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from nexus.executors import cli_worker

needs_lsof = pytest.mark.skipif(shutil.which("lsof") is None, reason="cwd scan needs lsof")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return bool(stat) and not stat.startswith("Z")


def _wait_dead(pid: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


def _kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


_SPAWN_CHILD = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],\n"
    "    cwd=sys.argv[1], env={}, start_new_session=True,\n"
    "    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
    "print(child.pid, flush=True)\n"
    "time.sleep(0.6)\n"
)


def _launch_run(target: Path, tag: str):
    """A worker whose env-cleared, setsid child sits in ``target``; returns (worker, child, tracker)."""
    worker = subprocess.Popen(
        [sys.executable, "-c", _SPAWN_CHILD, str(target)],
        cwd=str(target),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    tracker = cli_worker.track_run(tag, worker.pid)
    assert worker.stdout is not None
    child = int(worker.stdout.readline().strip())
    worker.wait(timeout=10)
    return worker, child, tracker


@pytest.fixture
def target(tmp_path: Path) -> Path:
    path = (tmp_path / "worktree").resolve()
    path.mkdir()
    return path


@needs_lsof
def test_unrelated_same_uid_process_in_worktree_survives_and_sweep_is_unclean(target):
    tag = "scope2470unrelated"
    baseline = cli_worker.sweep_baseline()
    assert baseline is not None
    # An Owner shell that cd-ed into the worktree while the run was active:
    # same uid, started after the baseline, no run tag, not a descendant.
    bystander = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=str(target),
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    child = None
    try:
        _worker, child, tracker = _launch_run(target, tag)
        clean = cli_worker.sweep_run(
            tag, tracker, baseline, [str(target)], kill_unproven_cwd_matches=False
        )
        assert clean is False  # reported, fail closed
        assert bystander.poll() is None  # and not killed
        assert _alive(bystander.pid)
        assert _wait_dead(child)  # the run's own descendant is still killed
    finally:
        cli_worker.release_run(tag)
        _kill(bystander.pid)
        bystander.wait(timeout=5)
        if child is not None:
            _kill(child)


@needs_lsof
def test_positive_control_real_descendant_is_killed_and_sweep_is_clean(target):
    tag = "scope2470descendant"
    baseline = cli_worker.sweep_baseline()
    assert baseline is not None
    child = None
    try:
        _worker, child, tracker = _launch_run(target, tag)
        assert _alive(child)
        assert (
            cli_worker.sweep_run(
                tag, tracker, baseline, [str(target)], kill_unproven_cwd_matches=False
            )
            is True
        )
        assert _wait_dead(child)
    finally:
        cli_worker.release_run(tag)
        if child is not None:
            _kill(child)


@needs_lsof
def test_run_tagged_process_in_worktree_is_killed(target):
    """A process carrying the run tag is the run's even when the tracker missed it."""
    tag = "scope2470tagged"
    baseline = cli_worker.sweep_baseline()
    assert baseline is not None
    tagged = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=str(target),
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            cli_worker.RUN_TAG_ENV: tag,
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    # Reap the child as soon as it dies, as init does for a real escaped
    # descendant: on Linux an unreaped zombie child of the test process keeps
    # its /proc entry and would read as a surviving tagged process.
    reaper = threading.Thread(target=tagged.wait, daemon=True)
    reaper.start()
    try:
        time.sleep(0.2)

        class _Empty:  # the tracker saw nothing: only the tag can find it
            probe_failed = False

            def stop(self):
                return set()

        assert (
            cli_worker.sweep_run(
                tag, _Empty(), baseline, [str(target)], kill_unproven_cwd_matches=False
            )
            is True
        )
        reaper.join(timeout=5)
        assert tagged.returncode == -signal.SIGKILL
    finally:
        cli_worker.release_run(tag)
        if tagged.poll() is None:
            _kill(tagged.pid)
            tagged.wait(timeout=5)


def test_sweep_clean_kills_only_tracked_and_reports_other_cwd_matches(monkeypatch):
    killed: list[set[int]] = []
    monkeypatch.setattr(
        cli_worker, "_kill_and_confirm", lambda pids: killed.append(set(pids)) or True
    )
    monkeypatch.setattr(cli_worker, "_pid_live_resident", lambda pid: True)
    assert cli_worker._sweep_clean({11, 12}, {12, 99}, kill_unproven=False) is False
    assert killed == [{11, 12}]  # 99 is reported, never signalled


def test_sweep_clean_ignores_a_reported_pid_that_already_exited(monkeypatch):
    monkeypatch.setattr(cli_worker, "_kill_and_confirm", lambda pids: True)
    monkeypatch.setattr(cli_worker, "_pid_live_resident", lambda pid: False)
    assert cli_worker._sweep_clean({11}, {11, 99}, kill_unproven=False) is True


def test_sweep_clean_is_clean_when_every_cwd_match_is_tracked(monkeypatch):
    monkeypatch.setattr(cli_worker, "_kill_and_confirm", lambda pids: True)
    monkeypatch.setattr(cli_worker, "_pid_live_resident", lambda pid: True)
    assert cli_worker._sweep_clean({11, 12}, {11}, kill_unproven=False) is True


def test_sweep_clean_unknown_scan_and_failed_kill_are_unclean(monkeypatch):
    monkeypatch.setattr(cli_worker, "_pid_live_resident", lambda pid: True)
    monkeypatch.setattr(cli_worker, "_kill_and_confirm", lambda pids: True)
    assert cli_worker._sweep_clean({11}, None, kill_unproven=False) is False
    monkeypatch.setattr(cli_worker, "_kill_and_confirm", lambda pids: False)
    assert cli_worker._sweep_clean({11}, set(), kill_unproven=False) is False


def test_default_sweep_clean_still_kills_every_cwd_match(monkeypatch):
    killed: list[set[int]] = []
    monkeypatch.setattr(
        cli_worker, "_kill_and_confirm", lambda pids: killed.append(set(pids)) or True
    )
    assert cli_worker._sweep_clean({11}, {11, 99}) is True
    assert killed == [{11, 99}]
    assert cli_worker._sweep_clean({11}, None) is False


@needs_lsof
def test_default_run_cli_worker_still_kills_a_cwd_matching_process(target):
    """The codex / measurement path (run_cli_worker + sweep_roots) is unchanged:
    a post-baseline process cd-ed into the sweep root is killed, sweep clean."""
    from nexus.executors.cli_worker import CliWorkerRequest, run_cli_worker

    holder: dict = {}

    def start_bystander():
        time.sleep(0.5)  # after the worker's baseline
        holder["p"] = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=str(target),
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    import threading

    starter = threading.Thread(target=start_bystander)
    starter.start()
    try:
        result = run_cli_worker(
            CliWorkerRequest(
                executable=sys.executable,
                argv=("-c", "import time; time.sleep(1.5)"),
                cwd=str(target),
                sweep_descendants_on_exit=True,
                sweep_roots=(str(target),),
            )
        )
        starter.join()
        bystander = holder["p"]
        assert result.descendants_swept is True
        bystander.wait(timeout=5)
        assert bystander.returncode == -signal.SIGKILL
    finally:
        starter.join()
        if "p" in holder and holder["p"].poll() is None:
            _kill(holder["p"].pid)
            holder["p"].wait(timeout=5)


def test_agy_dispatch_boundary_opts_into_report_not_kill(tmp_path, monkeypatch):
    from nexus.executors import agy_dispatch_boundary as boundary_mod

    seen: dict = {}

    def fake_sweep_run(tag, tracker, baseline, roots, **kwargs):
        seen.update(kwargs)
        return False

    monkeypatch.setattr(boundary_mod.cli_worker, "sweep_run", fake_sweep_run)
    boundary = object.__new__(boundary_mod.AgyDispatchBoundary)
    boundary.target = tmp_path
    boundary.run_root = tmp_path
    boundary.run_tag = "t"
    boundary._baseline = None
    boundary._tracker = object()
    boundary._launched = True
    boundary._swept = None
    assert boundary.sweep() is False
    assert seen == {"kill_unproven_cwd_matches": False}


def test_report_mode_does_not_count_an_unreaped_zombie_as_resident(target):
    """A SIGKILLed child that its parent has not reaped yet is not a live writer."""
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=str(target),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        os.kill(child.pid, signal.SIGKILL)
        time.sleep(0.3)  # dead but not reaped: a zombie of this test process
        assert cli_worker._pid_alive(child.pid) is True
        assert cli_worker._pid_live_resident(child.pid) is False
        assert cli_worker._sweep_clean(set(), {child.pid}, kill_unproven=False) is True
    finally:
        child.wait(timeout=5)


def test_report_mode_still_flags_a_live_resident(target):
    """Positive control: a live untracked process in the target keeps the sweep unclean."""
    resident = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=str(target),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        time.sleep(0.2)
        assert cli_worker._pid_live_resident(resident.pid) is True
        assert cli_worker._sweep_clean(set(), {resident.pid}, kill_unproven=False) is False
        assert resident.poll() is None
    finally:
        _kill(resident.pid)
        resident.wait(timeout=5)
