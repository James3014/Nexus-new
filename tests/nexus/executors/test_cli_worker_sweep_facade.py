"""Issue #2260: behaviour of the public cli_worker sweep facade."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.executors import cli_worker

TAG = "facadetag"


class _Tracker:
    def __init__(self, pids=frozenset(), probe_failed=False):
        self._pids = set(pids)
        self.probe_failed = probe_failed
        self.stopped = 0

    def stop(self):
        self.stopped += 1
        return set(self._pids)


@pytest.fixture
def clean_sweep(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(
        cli_worker, "_sweep_tagged_processes", lambda tag: seen.update(tag=tag) or True
    )
    monkeypatch.setattr(
        cli_worker, "_pids_with_cwd_under", lambda roots, base: seen.update(roots=roots) or set()
    )
    monkeypatch.setattr(
        cli_worker, "_sweep_clean", lambda tracked, cwd: seen.update(tracked=tracked) or True
    )
    return seen


BASELINE = SimpleNamespace(preexisting=frozenset({7}))


def test_sweep_run_is_true_only_when_everything_is_clean(clean_sweep):
    tracker = _Tracker({7, 8})
    assert cli_worker.sweep_run(TAG, tracker, BASELINE, ["/a", "/b"]) is True
    assert tracker.stopped == 1
    assert clean_sweep == {"tag": TAG, "roots": ("/a", "/b"), "tracked": {8}}


def test_sweep_run_is_not_clean_when_a_probe_failed(clean_sweep):
    assert cli_worker.sweep_run(TAG, _Tracker(probe_failed=True), BASELINE, ["/a"]) is False


def test_sweep_run_is_not_clean_without_a_baseline(clean_sweep):
    assert cli_worker.sweep_run(TAG, _Tracker(), None, ["/a"]) is False


def test_sweep_run_is_not_clean_when_the_tag_sweep_is_not(clean_sweep, monkeypatch):
    monkeypatch.setattr(cli_worker, "_sweep_tagged_processes", lambda tag: False)
    assert cli_worker.sweep_run(TAG, _Tracker(), BASELINE, ["/a"]) is False


def test_sweep_run_is_not_clean_when_descendants_survive(clean_sweep, monkeypatch):
    monkeypatch.setattr(cli_worker, "_sweep_clean", lambda tracked, cwd: False)
    assert cli_worker.sweep_run(TAG, _Tracker(), BASELINE, ["/a"]) is False


def test_release_run_drops_the_tick_and_is_idempotent(monkeypatch):
    monkeypatch.setitem(cli_worker._RUN_START_TICKS, TAG, 5)
    cli_worker.release_run(TAG)
    assert TAG not in cli_worker._RUN_START_TICKS
    cli_worker.release_run(TAG)


def _fake_proc(root: Path, pid: int, ticks: int) -> Path:
    proc = root / "proc"
    (proc / str(pid)).mkdir(parents=True)
    fields = ["S"] + ["0"] * 18 + [str(ticks)] + ["0"] * 10
    (proc / str(pid) / "stat").write_text(f"{pid} (x) " + " ".join(fields) + "\n")
    return proc


def test_track_run_registers_the_start_tick_and_returns_a_tracker(monkeypatch, tmp_path):
    proc = _fake_proc(tmp_path, 555, 4242)
    made: list[int] = []
    monkeypatch.setattr(cli_worker, "Path", lambda *a: proc if a == ("/proc",) else Path(*a))
    monkeypatch.setattr(
        cli_worker, "_DescendantTracker", lambda pid: made.append(pid) or _Tracker()
    )
    monkeypatch.delitem(cli_worker._RUN_START_TICKS, TAG, raising=False)
    tracker = cli_worker.track_run(TAG, 555)
    assert cli_worker._RUN_START_TICKS[TAG] == 4242
    assert made == [555] and isinstance(tracker, _Tracker)
    cli_worker.release_run(TAG)


def test_track_run_without_proc_registers_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli_worker, "Path", lambda *a: tmp_path / "none" if a == ("/proc",) else Path(*a)
    )
    monkeypatch.setattr(cli_worker, "_DescendantTracker", lambda pid: _Tracker())
    monkeypatch.delitem(cli_worker._RUN_START_TICKS, TAG, raising=False)
    cli_worker.track_run(TAG, 555)
    assert TAG not in cli_worker._RUN_START_TICKS


def test_baseline_facade_delegates(monkeypatch):
    monkeypatch.setattr(cli_worker, "_sweep_baseline", lambda: "sentinel")
    assert cli_worker.sweep_baseline() == "sentinel"
    assert cli_worker.RUN_TAG_ENV == cli_worker._RUN_TAG_ENV
