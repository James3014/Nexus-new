from __future__ import annotations

import fcntl
import json
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

import nexus.research.hybrid_replication_prospective as prospective
from nexus.research.hybrid_replication_pipeline import (
    AdmissionReceipt,
    AutomaticReplicationStore,
    TaskSnapshot,
    build_admission_comment,
)
from nexus.research.hybrid_replication_prospective import ProspectiveExecutionGuard
from scripts.ops import hybrid_replication_daemon as daemon

REPO = "James3014/Nexus-new"


def _snapshot(issue: int) -> TaskSnapshot:
    return TaskSnapshot.create(
        repository=REPO,
        issue_number=issue,
        created_at="2026-10-07T12:00:00Z",
        captured_at="2026-10-07T12:00:01Z",
        issue_updated_at="2026-10-07T12:00:00Z",
        title=f"Task {issue}",
        body="Implement a bounded task.",
        pre_implementation_revision="a" * 40,
        default_branch="main",
        source_event_id=f"task:{issue}",
    )


def _receipt(snapshot: TaskSnapshot) -> AdmissionReceipt:
    return AdmissionReceipt.create(
        snapshot=snapshot,
        disposition="ADMITTED_PRIMARY_FRESH_TASK",
        activation_boundary="2026-10-07T11:59:59Z",
        activation_state="AUTOMATIC_CAPTURE_READY",
        exclusion_set_sha256="6" * 64,
        issue_state_at_admission="open",
        implementation_pr_numbers=(),
        tracked_parent_issue_number=None,
        tracked_parent_created_at=None,
        admitted_at="2026-10-07T12:00:02Z",
    )


class _World:
    """Fake GitHub plus a store of admitted tasks."""

    def __init__(self, tmp_path: Path, issues: list[int]) -> None:
        self.store = AutomaticReplicationStore(tmp_path)
        self.snapshots: dict[int, TaskSnapshot] = {}
        self.receipts: dict[int, AdmissionReceipt] = {}
        self.closed: set[int] = set()
        for number in issues:
            snap = _snapshot(number)
            receipt = _receipt(snap)
            self.snapshots[number] = snap
            self.receipts[number] = receipt
            self.store.capture(snap, admission_disposition="PRE_AUTOMATION_PROVISIONAL_CAPTURE")
            self.store.apply_admission(receipt)

    def task_dir(self, number: int) -> Path:
        return self.store.tasks_root / prospective._task_dir_name(self.snapshots[number].task_key)

    def start_path(self, number: int) -> Path:
        return self.task_dir(number) / "execution_start.json"

    @staticmethod
    def _number(path: str) -> int:
        return int(path.split("/issues/")[1].split("/")[0])

    def gh_json(self, *args: str) -> Any:
        number = self._number(args[-1])
        return {
            "state": "closed" if number in self.closed else "open",
            "updated_at": "2026-10-07T12:00:00Z",
            "closed_at": "2026-10-07T12:30:00Z" if number in self.closed else None,
        }

    def gh_list(self, path: str) -> list[dict[str, Any]]:
        number = self._number(path)
        if path.endswith("/comments"):
            return [{"body": build_admission_comment(self.receipts[number])}]
        return []


class _FakeController:
    """Stands in for AutomaticReplicationController; records concurrency."""

    instances: list["_FakeController"] = []

    def __init__(self, **_: Any) -> None:
        self.lock = threading.Lock()
        self.running = 0
        self.max_running = 0
        self.calls: list[str] = []
        self.entered = threading.Semaphore(0)
        self.release = threading.Event()
        self.block = False
        self.raise_for: set[str] = set()
        _FakeController.instances.append(self)

    def advance(self, task_key: str) -> dict[str, Any]:
        with self.lock:
            self.calls.append(task_key)
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        self.entered.release()
        try:
            if self.block:
                assert self.release.wait(timeout=20)
            if task_key in self.raise_for:
                raise RuntimeError("existing_prospective_protocol_loss")
            return {"phase": "RAW_SEALED"}
        finally:
            with self.lock:
                self.running -= 1


@pytest.fixture
def controller_factory(monkeypatch: pytest.MonkeyPatch) -> _FakeController:
    _FakeController.instances = []
    monkeypatch.setattr(daemon, "AutomaticReplicationController", _FakeController)
    monkeypatch.setattr(daemon, "ExternalFrozenStackRunner", lambda command: object())
    monkeypatch.setattr(daemon, "ExternalGroundTruthResolver", lambda command: object())
    return _FakeController  # type: ignore[return-value]


def _patch_github(monkeypatch: pytest.MonkeyPatch, world: _World) -> None:
    monkeypatch.setattr(prospective, "_gh_json", world.gh_json)
    monkeypatch.setattr(prospective, "_gh_list", world.gh_list)


def _advance(world: _World, **kwargs: Any) -> dict[str, Any]:
    return daemon.advance_all(
        store=world.store,
        frozen_policy_sha256="f" * 64,
        stack_command="stack",
        ground_truth_command="gt",
        **kwargs,
    )


def test_all_execution_starts_written_before_any_slow_stack_call_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, controller_factory: Any
) -> None:
    issues = [2001, 2002, 2003, 2004, 2005, 2006]
    world = _World(tmp_path, issues)
    _patch_github(monkeypatch, world)

    box: dict[str, Any] = {}

    def run() -> None:
        box["report"] = _advance(world, max_concurrent_tasks=2)

    # Patch controller to block: set before the thread starts via the class hook.
    original_init = _FakeController.__init__

    def blocking_init(self: _FakeController, **kw: Any) -> None:
        original_init(self, **kw)
        self.block = True

    monkeypatch.setattr(_FakeController, "__init__", blocking_init)
    thread = threading.Thread(target=run)
    thread.start()
    controller = None
    try:
        # Two workers are now inside the slow call; 4 tasks are still queued behind them.
        deadline = threading.Event()
        while not _FakeController.instances:
            deadline.wait(0.01)
        controller = _FakeController.instances[-1]
        for _ in range(2):
            assert controller.entered.acquire(timeout=20)
        assert all(world.start_path(n).is_file() for n in issues)
        assert controller.running == 2
    finally:
        if controller is not None:
            controller.release.set()
        thread.join(timeout=30)
    report = box["report"]
    assert controller is not None and controller.max_running == 2
    assert [item["task_key"] for item in report["advanced"]] == sorted(
        world.snapshots[n].task_key for n in issues
    )
    assert report["failures"] == []
    assert report["excluded_protocol_loss"] == []


def test_default_single_task_is_serial_without_early_fence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, controller_factory: Any
) -> None:
    world = _World(tmp_path, [2101, 2102, 2103])
    _patch_github(monkeypatch, world)

    def no_fence(*_: Any, **__: Any) -> None:
        raise AssertionError("fence must not run at N=1")

    monkeypatch.setattr(daemon, "_take_execution_start_fence", no_fence)
    report = _advance(world)
    controller = _FakeController.instances[-1]
    assert controller.max_running == 1
    assert set(report) == {
        "schema",
        "advanced",
        "failures",
        "excluded_protocol_loss",
    }
    assert report["schema"] == "nexus.hybrid_replication.daemon_advance.v1"
    assert [a["before"] for a in report["advanced"]] == ["ADMITTED"] * 3
    assert all(a["after"] == "RAW_SEALED" for a in report["advanced"])
    assert not any(world.start_path(n).exists() for n in (2101, 2102, 2103))


def test_task_lock_is_exclusive_across_threads_and_fence_skips_held_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _World(tmp_path, [2201])
    _patch_github(monkeypatch, world)
    guard = ProspectiveExecutionGuard(store_root=world.store.root, snapshot=world.snapshots[2201])
    results: dict[str, Any] = {}
    with guard.task_lock():

        def probe() -> None:
            with (guard.task_dir / "execution.lock").open("a+", encoding="utf-8") as handle:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    results["acquired"] = True
                except BlockingIOError:
                    results["acquired"] = False
            results["fenced"] = daemon._take_execution_start_fence(
                world.store, world.snapshots[2201].task_key
            )

        thread = threading.Thread(target=probe)
        thread.start()
        thread.join(timeout=10)
    assert results == {"acquired": False, "fenced": False}
    assert not world.start_path(2201).exists()
    # Once released the fence is taken, and it is idempotent.
    assert daemon._take_execution_start_fence(world.store, world.snapshots[2201].task_key) is True
    first = world.start_path(2201).read_bytes()
    assert daemon._take_execution_start_fence(world.store, world.snapshots[2201].task_key) is True
    assert world.start_path(2201).read_bytes() == first


def test_existing_protocol_loss_is_skipped_and_does_not_exit_5(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    controller_factory: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    world = _World(tmp_path, [2301, 2302])
    _patch_github(monkeypatch, world)
    (world.task_dir(2301) / "prospective_protocol_loss.json").write_text(
        json.dumps({"reason": "TERMINAL_BEFORE_EXECUTION_START"}), encoding="utf-8"
    )
    for workers in (1, 3):
        report = _advance(world, max_concurrent_tasks=workers)
        controller = _FakeController.instances[-1]
        assert world.snapshots[2301].task_key not in controller.calls
        assert report["failures"] == []
        assert report["excluded_protocol_loss"] == [
            {
                "task_key": world.snapshots[2301].task_key,
                "reason": "TERMINAL_BEFORE_EXECUTION_START",
                "newly_recorded": False,
            }
        ]
        assert [a["task_key"] for a in report["advanced"]] == [world.snapshots[2302].task_key]

    ingest_report = {
        "schema": "nexus.hybrid_replication.daemon_ingest.v1",
        "expected_count": 2,
        "mirrored_count": 2,
        "missing_capture": [],
        "missing_admission": [],
        "watchdog": {"status": "COMPLETE"},
    }
    monkeypatch.setattr(daemon, "ingest", lambda **_: ingest_report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "daemon",
            "--root",
            str(tmp_path),
            "--since",
            "2026-10-01T00:00:00Z",
            "--frozen-policy-sha256",
            "f" * 64,
            "--stack-command",
            "stack",
            "--ground-truth-command",
            "gt",
            "--max-concurrent-tasks",
            "3",
        ],
    )
    assert daemon.main() == 0
    assert '"excluded_protocol_loss"' in capsys.readouterr().out


def test_real_failure_still_exits_5_next_to_excluded_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, controller_factory: Any
) -> None:
    world = _World(tmp_path, [2401, 2402])
    _patch_github(monkeypatch, world)
    (world.task_dir(2401) / "prospective_protocol_loss.json").write_text("{}", encoding="utf-8")
    original_init = _FakeController.__init__

    def init(self: _FakeController, **kw: Any) -> None:
        original_init(self, **kw)
        self.raise_for = {world.snapshots[2402].task_key}

    monkeypatch.setattr(_FakeController, "__init__", init)
    report = _advance(world, max_concurrent_tasks=2)
    assert [f["task_key"] for f in report["failures"]] == [world.snapshots[2402].task_key]
    assert report["failures"][0]["phase"] == "ADMITTED"
    assert len(report["excluded_protocol_loss"]) == 1


def test_loss_newly_recorded_during_fence_is_reported_as_excluded_not_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, controller_factory: Any
) -> None:
    world = _World(tmp_path, [2501, 2502])
    world.closed.add(2501)
    _patch_github(monkeypatch, world)
    report = _advance(world, max_concurrent_tasks=2)
    controller = _FakeController.instances[-1]
    assert controller.calls == [world.snapshots[2502].task_key]
    assert report["failures"] == []
    assert report["excluded_protocol_loss"] == [
        {
            "task_key": world.snapshots[2501].task_key,
            "reason": "TERMINAL_BEFORE_EXECUTION_START",
            "newly_recorded": True,
        }
    ]
    assert world.start_path(2502).is_file() and not world.start_path(2501).exists()
    # The next run treats it as an already-excluded task.
    again = _advance(world, max_concurrent_tasks=2)
    assert again["excluded_protocol_loss"][0]["newly_recorded"] is False


def test_max_concurrent_tasks_must_be_positive(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    with pytest.raises(ValueError, match="max_concurrent_tasks_must_be_positive"):
        daemon.advance_all(
            store=store,
            frozen_policy_sha256="f" * 64,
            stack_command="stack",
            ground_truth_command="gt",
            max_concurrent_tasks=0,
        )
