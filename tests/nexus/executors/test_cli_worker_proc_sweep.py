"""Issue #2202 follow-ups: the Linux /proc branches of the descendant sweep.

Every test builds a fake /proc tree and points ``cli_worker`` at it, so the
Linux logic is exercised on every platform and never skipped.
"""

from __future__ import annotations

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
