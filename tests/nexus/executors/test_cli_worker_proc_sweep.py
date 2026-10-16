"""Issue #2202 follow-ups: the Linux /proc branches of the descendant sweep.

Every test builds a fake /proc tree and points ``cli_worker`` at it, so the
Linux logic is exercised on every platform and never skipped.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nexus.executors import cli_worker

PID = 424242
TAG = "proctag"


def _fake_proc(
    root: Path,
    *,
    state: str,
    threads: int | None,
    comm: str = "agy",
    environ: bytes | None = b"",
    start_ticks: int = 300,
) -> Path:
    proc = root / "proc"
    (proc / "self").mkdir(parents=True)
    (proc / "self" / "environ").write_bytes(b"")
    entry = proc / str(PID)
    entry.mkdir()
    fields = [state] + ["0"] * 18 + [str(start_ticks)] + ["0"] * 10
    (entry / "stat").write_text(f"{PID} ({comm}) " + " ".join(fields) + "\n")
    if threads is not None:
        (entry / "task").mkdir()
        for tid in range(threads):
            (entry / "task" / str(PID + tid)).mkdir()
    if environ is not None:
        (entry / "environ").write_bytes(environ)
    return proc


def _point_at(monkeypatch: pytest.MonkeyPatch, proc: Path) -> None:
    monkeypatch.setattr(cli_worker, "Path", lambda *a: proc if a == ("/proc",) else Path(*a))
    monkeypatch.delitem(cli_worker._RUN_START_TICKS, TAG, raising=False)


@pytest.mark.parametrize("state", ["Z", "X"])
@pytest.mark.parametrize("comm", ["agy", "a) S (b", ")"])
def test_dead_leader_with_live_threads_and_empty_environ_is_unknown(
    monkeypatch, tmp_path, state, comm
):
    # The leader's mm is gone so environ reads empty, but another thread still
    # runs: "no tag found" would be a false clean.
    proc = _fake_proc(tmp_path, state=state, threads=2, comm=comm, environ=b"")
    _point_at(monkeypatch, proc)
    with pytest.raises(PermissionError):
        cli_worker._tagged_pids(TAG)


def test_dead_leader_with_live_threads_and_unlistable_task_dir_is_unknown(monkeypatch, tmp_path):
    proc = _fake_proc(tmp_path, state="Z", threads=None, environ=b"")
    _point_at(monkeypatch, proc)
    with pytest.raises(PermissionError):
        cli_worker._tagged_pids(TAG)


@pytest.mark.parametrize("threads", [0, 1])
def test_single_threaded_zombie_with_empty_environ_is_excused(monkeypatch, tmp_path, threads):
    proc = _fake_proc(tmp_path, state="Z", threads=threads, comm="a) S (b", environ=b"")
    _point_at(monkeypatch, proc)
    assert cli_worker._tagged_pids(TAG) == set()


def test_empty_environ_of_a_live_process_is_not_unknown(monkeypatch, tmp_path):
    # Kernel threads and exec'd-away processes legitimately read empty.
    proc = _fake_proc(tmp_path, state="S", threads=2, environ=b"")
    _point_at(monkeypatch, proc)
    assert cli_worker._tagged_pids(TAG) == set()


def test_tagged_leader_in_zombie_state_with_live_threads_is_reported(monkeypatch, tmp_path):
    env = f"A=1\0{cli_worker.RUN_TAG_ENV}={TAG}\0".encode()
    proc = _fake_proc(tmp_path, state="Z", threads=3, environ=env)
    _point_at(monkeypatch, proc)
    assert cli_worker._tagged_pids(TAG) == {PID}


@pytest.mark.parametrize("comm", ["agy", "a) S (b"])
def test_zombie_with_more_than_one_task_is_never_excused(tmp_path, comm):
    proc = _fake_proc(tmp_path, state="Z", threads=2, comm=comm)
    assert cli_worker._proc_is_zombie(proc / str(PID)) is False


# --- gating and retry of the dead-leader unknown (review of #2330) -----------


def test_dead_leader_of_another_user_is_not_unknown(monkeypatch, tmp_path):
    proc = _fake_proc(tmp_path, state="Z", threads=2, environ=b"")
    _point_at(monkeypatch, proc)
    monkeypatch.setattr(cli_worker.os, "getuid", lambda: os.stat(proc / str(PID)).st_uid + 1)
    assert cli_worker._tagged_pids(TAG) == set()


def test_dead_leader_older_than_the_run_is_not_unknown(monkeypatch, tmp_path):
    proc = _fake_proc(tmp_path, state="Z", threads=2, environ=b"", start_ticks=100)
    _point_at(monkeypatch, proc)
    monkeypatch.setitem(cli_worker._RUN_START_TICKS, TAG, 200)
    assert cli_worker._tagged_pids(TAG) == set()


def test_dead_leader_started_during_the_run_is_still_unknown(monkeypatch, tmp_path):
    proc = _fake_proc(tmp_path, state="Z", threads=2, environ=b"", start_ticks=300)
    _point_at(monkeypatch, proc)
    monkeypatch.setitem(cli_worker._RUN_START_TICKS, TAG, 200)
    with pytest.raises(cli_worker._TagScanUnknown):
        cli_worker._tagged_pids(TAG)


def test_sweep_retries_a_transient_unknown_until_clean(monkeypatch):
    scans = [cli_worker._TagScanUnknown("mid-exit"), set()]

    def fake(tag, starts=None):
        item = scans.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(cli_worker, "_tagged_pids", fake)
    monkeypatch.setattr(cli_worker.time, "sleep", lambda _s: None)
    assert cli_worker._sweep_tagged_processes(TAG) is True
    assert scans == []


def test_sweep_reports_not_clean_when_the_unknown_persists_to_the_deadline(monkeypatch):
    calls: list[int] = []

    def fake(tag, starts=None):
        calls.append(1)
        raise cli_worker._TagScanUnknown("still unknown")

    monkeypatch.setattr(cli_worker, "_tagged_pids", fake)
    monkeypatch.setattr(cli_worker, "_SWEEP_DEADLINE_SECONDS", 0.05)
    assert cli_worker._sweep_tagged_processes(TAG) is False
    assert len(calls) >= 1
