"""Issue #2202: re-check the process start time right before SIGKILL (PID reuse)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.executors import cli_worker

PID = 424242
TAG = "reusetag"


def _fake_proc(root, *, start_ticks):
    proc = root / "proc"
    (proc / "self").mkdir(parents=True)
    (proc / "self" / "environ").write_bytes(b"")
    entry = proc / str(PID)
    entry.mkdir()
    fields = ["S"] + ["0"] * 18 + [str(start_ticks)] + ["0"] * 10
    (entry / "stat").write_text(f"{PID} (agy) " + " ".join(fields) + "\n")
    (entry / "environ").write_bytes(f"{cli_worker.RUN_TAG_ENV}={TAG}\0".encode())
    return proc


def _scripted(scans):
    """A ``_tagged_pids`` stand-in that reports ``{pid: start_ticks}`` per scan."""

    def fake(tag, starts=None):
        found = scans.pop(0)
        if starts is not None:
            starts.update(found)
        return set(found)

    return fake


def _kill_recorder(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(cli_worker.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    return sent


def test_sweep_skips_kill_when_pid_was_reused_after_detection(monkeypatch):
    sent = _kill_recorder(monkeypatch)
    scans = [{PID: 100}, {}]
    monkeypatch.setattr(cli_worker, "_tagged_pids", _scripted(scans))
    monkeypatch.setattr(cli_worker, "_proc_start_ticks", lambda entry: 999)  # new process
    assert cli_worker._sweep_tagged_processes(TAG) is True
    assert sent == []


def test_sweep_kills_when_start_time_is_unchanged(monkeypatch):
    sent = _kill_recorder(monkeypatch)
    scans = [{PID: 100}, {}]
    monkeypatch.setattr(cli_worker, "_tagged_pids", _scripted(scans))
    monkeypatch.setattr(cli_worker, "_proc_start_ticks", lambda entry: 100)
    assert cli_worker._sweep_tagged_processes(TAG) is True
    assert sent == [(PID, cli_worker.signal.SIGKILL)]


def test_sweep_kills_when_start_time_is_unknown_on_both_sides(monkeypatch):
    # macOS has no /proc: the ps listing gives no start time, so we cannot prove reuse.
    sent = _kill_recorder(monkeypatch)
    scans = [{PID: None}, {}]
    monkeypatch.setattr(cli_worker, "_tagged_pids", _scripted(scans))
    monkeypatch.setattr(cli_worker, "_proc_start_ticks", lambda entry: None)
    assert cli_worker._sweep_tagged_processes(TAG) is True
    assert sent == [(PID, cli_worker.signal.SIGKILL)]


def test_sweep_reports_dirty_when_a_reused_pid_hides_a_real_survivor(monkeypatch):
    # Reuse is skipped, but the next scan still finds the tag: stay not-clean at the deadline.
    sent = _kill_recorder(monkeypatch)
    monkeypatch.setattr(cli_worker, "_SWEEP_DEADLINE_SECONDS", 0.0)
    monkeypatch.setattr(cli_worker, "_tagged_pids", _scripted([{PID: 100}] * 50))
    monkeypatch.setattr(cli_worker, "_proc_start_ticks", lambda entry: 999)
    assert cli_worker._sweep_tagged_processes(TAG) is False
    assert sent == []


def test_tagged_pids_records_start_ticks_from_proc(monkeypatch, tmp_path):
    proc = _fake_proc(tmp_path, start_ticks=777)
    monkeypatch.setattr(cli_worker, "Path", lambda *a: proc if a == ("/proc",) else Path(*a))
    starts: dict[int, int | None] = {}
    assert cli_worker._tagged_pids(TAG, starts) == {PID}
    assert starts == {PID: 777}
