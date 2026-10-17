"""Characterization of the read/receipt projection cluster of ``SelfHostedTaskService`` (split S2).

Big-file split step S2 moves the read/receipt projection methods out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin.  These tests pin the
behaviour before the move and must pass unchanged after it:

* every projection's result, including each error path (``wait_task`` argument
  validation, missing tasks, ``_snapshot_target_integrity`` failure kinds);
* the call order of the state lock and state reads/writes (recording probes on the
  class, so they also work once the methods live in a mixin).  ``wait_task``,
  ``list_actionable_tasks``, ``get_task``, ``get_task_snapshot`` and
  ``get_promotion_packet`` take no lock and write nothing; ``get_receipt`` reads under
  the state lock (through ``_read_state``); ``project_candidate_acceptance_for_retry``
  writes through ``_mutate_state`` only for a REPAIRABLE verdict;
* that facade-module names the moved code reads (``time``, ``project_autonomy_submission``,
  ``reduce_candidate_acceptance``, ``project_candidate_acceptance_for_runtime_repair``)
  are still resolved through the facade at call time, so patches on the facade keep
  taking effect.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.orchestrator.acceptance_loop import (
    CandidateAcceptanceRequest,
    IndependentReviewReceipt,
    reduce_candidate_acceptance,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

# Members of the read/receipt projection cluster; each one is exercised below.
READ_MEMBERS = {
    "wait_task": "function",
    "list_actionable_tasks": "function",
    "get_task": "function",
    "get_task_snapshot": "function",
    "get_receipt": "function",
    "get_promotion_packet": "function",
    "_snapshot_target_integrity": "staticmethod",
    "evaluate_candidate_acceptance": "staticmethod",
    "project_candidate_acceptance_for_retry": "function",
}

STATUS_KEYS = [
    "schema",
    "task_id",
    "status",
    "promotion_status",
    "verification_verdict",
    "found",
    "state_valid",
    "blocker",
    "retry_authorized",
    "task_action",
]

RECEIPT_KEYS = [
    "task_id",
    "attempt_id",
    "status",
    "submitted_at",
    "telemetry",
    "contract_hash",
    "controller_worktree",
    "controller_revision",
    "controller_status_sha256",
    "target_worktree",
    "target_initial_revision",
    "target_branch",
    "target_created_at",
    "worker_provider",
    "worker_pid",
    "heartbeat_at",
    "execution_outcome",
    "verification_verdict",
    "candidate_commit_sha",
    "candidate_tree_sha",
    "candidate_ref",
    "candidate_state_hash",
    "verified_receipt_hash",
    "salvage_commit_sha",
    "salvage_ref",
    "salvage_only",
    "promotion_eligible",
    "promotion_status",
    "approved_binding",
    "integration_branch",
    "integration_base_sha",
    "integration_result_sha",
    "terminal_status",
    "superseded_by",
    "cleanup_eligible",
    "cleanup_decision",
    "cleanup_blocker",
    "cleanup_performed",
    "cleanup_performed_at",
    "state_retention_status",
    "archive_eligible",
    "archive_location",
    "execution",
    "candidate",
    "verified_receipt",
    "execution_authority",
    "provider_receipt_authoritative",
    "workforce_admission_authoritative",
    "runtime_development_mapping",
    "collaboration_realm",
    "submission_collaboration_provenance",
    "collaboration_provenance",
    "candidate_collaboration_provenance",
    "error",
    "operator_outcome_receipt",
    "operator_outcome_receipts",
]

IO_EVENTS = (
    "lock+",
    "lock-",
    "_state_path",
    "_read_state",
    "_read_state_snapshot",
    "_write_state_locked",
    "_mutate_state",
    "_latest_archived_state",
    "_load_state_path",
)

COMMIT = "a" * 40
TREE = "b" * 40
STATE_HASH = "c" * 64
DIFF = "d" * 64
RECEIPT = "e" * 64
ARTIFACT = "f" * 64


# ---------------------------------------------------------------------------
# helpers


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def service(state_dir: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)


def _seed(
    service: SelfHostedTaskService,
    task_id: str = "task-1",
    *,
    status: str = "FINAL_BLOCK",
    **extra: Any,
) -> None:
    state: dict[str, Any] = {"task_id": task_id, "attempt_id": "attempt-1", "status": status}
    state.update(extra)
    service._write_state(task_id, state)


def _disk_bytes(state_dir: Path) -> dict[str, str]:
    if not state_dir.exists():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(state_dir.glob("*.json"))
    }


class Recorder:
    """Class-level recording probes for the state lock and state I/O."""

    FUNCTIONS = (
        "_state_path",
        "_read_state",
        "_read_state_snapshot",
        "_write_state_locked",
        "_mutate_state",
        "_latest_archived_state",
        "get_task_snapshot",
        "get_task",
    )
    CLASS = ("_load_state_path", "_task_action_envelope", "_with_task_action", "_projected_blocker")
    STATIC = ("_approval_requirements",)

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.events: list[str] = []
        cls = SelfHostedTaskService
        lock = inspect.getattr_static(cls, "_state_lock")
        events = self.events

        @contextmanager
        def state_lock(self: Any) -> Iterator[None]:
            events.append("lock+")
            with lock(self):
                yield
            events.append("lock-")

        monkeypatch.setattr(cls, "_state_lock", state_lock)
        for name in self.FUNCTIONS:
            monkeypatch.setattr(cls, name, self._wrap_function(name, getattr(cls, name)))
        for name in self.CLASS:
            func = inspect.getattr_static(cls, name).__func__
            monkeypatch.setattr(cls, name, classmethod(self._wrap_class(name, func)))
        for name in self.STATIC:
            func = inspect.getattr_static(cls, name).__func__
            monkeypatch.setattr(cls, name, staticmethod(self._wrap_plain(name, func)))

    def _wrap_function(self, name: str, func: Any) -> Any:
        events = self.events

        def wrapped(self_: Any, *args: Any, **kwargs: Any) -> Any:
            events.append(name)
            return func(self_, *args, **kwargs)

        return wrapped

    def _wrap_class(self, name: str, func: Any) -> Any:
        events = self.events

        def wrapped(cls: Any, *args: Any, **kwargs: Any) -> Any:
            events.append(name)
            return func(cls, *args, **kwargs)

        return wrapped

    def _wrap_plain(self, name: str, func: Any) -> Any:
        events = self.events

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            events.append(name)
            return func(*args, **kwargs)

        return wrapped

    def io(self) -> list[str]:
        return [event for event in self.events if event in IO_EVENTS]


class FakeTime:
    """Replacement for the facade's ``time`` module inside ``wait_task``."""

    def __init__(self, ticks: list[float], on_sleep: Any = None) -> None:
        self.ticks = list(ticks)
        self.calls: list[tuple[str, float]] = []
        self.on_sleep = on_sleep

    def monotonic(self) -> float:
        value = self.ticks.pop(0) if len(self.ticks) > 1 else self.ticks[0]
        self.calls.append(("monotonic", value))
        return value

    def sleep(self, seconds: float) -> None:
        self.calls.append(("sleep", seconds))
        if self.on_sleep is not None:
            self.on_sleep()


def _acceptance_request(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "implementer_id": "worker-1",
        "candidate_commit_sha": COMMIT,
        "candidate_tree_sha": TREE,
        "candidate_state_hash": STATE_HASH,
        "candidate_diff_hash": DIFF,
        "verified_receipt_hash": RECEIPT,
    }
    values.update(changes)
    return values


def _review(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "reviewer_id": "reviewer-1",
        "candidate_commit_sha": COMMIT,
        "candidate_tree_sha": TREE,
        "candidate_state_hash": STATE_HASH,
        "candidate_diff_hash": DIFF,
        "verified_receipt_hash": RECEIPT,
        "verifier_artifact_hash": ARTIFACT,
        "review_status": "PASS",
        "exit_code": 0,
    }
    values.update(changes)
    return values


# ---------------------------------------------------------------------------
# surface


def test_read_members_kinds_and_signatures() -> None:
    cls = SelfHostedTaskService
    kinds = {name: type(inspect.getattr_static(cls, name)).__name__ for name in READ_MEMBERS}
    assert kinds == READ_MEMBERS
    assert str(inspect.signature(cls.wait_task)) == (
        "(self, task_id: 'str', *, timeout_seconds: 'float' = 10.0, "
        "poll_interval_seconds: 'float' = 0.25, include_details: 'bool' = False) "
        "-> 'Optional[dict[str, Any]]'"
    )
    assert str(inspect.signature(cls.project_candidate_acceptance_for_retry)) == (
        "(self, request: 'CandidateAcceptanceRequest | Mapping[str, Any]', "
        "review: 'IndependentReviewReceipt | Mapping[str, Any]', *, "
        "verified_repair_evidence: 'Mapping[str, Any] | None' = None, "
        "repair_target: 'str' = 'IMPLEMENTATION') -> 'dict[str, Any]'"
    )


# ---------------------------------------------------------------------------
# wait_task


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timeout_seconds": -1}, "timeout_seconds must be non-negative"),
        (
            {"timeout_seconds": -1, "poll_interval_seconds": 0},
            "timeout_seconds must be non-negative",
        ),
        ({"poll_interval_seconds": 0}, "poll_interval_seconds must be positive"),
        ({"poll_interval_seconds": -0.5}, "poll_interval_seconds must be positive"),
        (
            {"timeout_seconds": 61, "poll_interval_seconds": 0},
            "poll_interval_seconds must be positive",
        ),
        ({"timeout_seconds": 60.01}, "timeout_seconds must be <= 60"),
        ({"timeout_seconds": "abc"}, "could not convert string to float: 'abc'"),
        ({"poll_interval_seconds": "x"}, "could not convert string to float: 'x'"),
    ],
)
def test_wait_task_argument_validation_precedes_any_state_read(
    service: SelfHostedTaskService,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, Any],
    message: str,
) -> None:
    recorder = Recorder(monkeypatch)
    with pytest.raises(ValueError) as caught:
        service.wait_task("missing", **kwargs)
    assert str(caught.value) == message
    assert recorder.events == []


def test_wait_task_accepts_boundary_arguments(service: SelfHostedTaskService) -> None:
    assert service.wait_task("missing", timeout_seconds=60, poll_interval_seconds=0.001) is None
    as_text: Any = {"timeout_seconds": "0", "poll_interval_seconds": "1"}
    assert service.wait_task("missing", **as_text) is None


def test_wait_task_missing_task_returns_none_without_lock(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTime([5.0])
    monkeypatch.setattr(service_module, "time", fake)
    recorder = Recorder(monkeypatch)
    assert service.wait_task("missing", timeout_seconds=3) is None
    assert recorder.io() == ["_read_state_snapshot"]
    assert fake.calls == [("monotonic", 5.0)]


def test_wait_task_settled_compact_result(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, state_dir: Path
) -> None:
    _seed(
        service,
        promotion_status="NOT_CREATED",
        verification_verdict="FAIL",
        retry_authorized=False,
        operator_outcome_receipt={"x": 1},
    )
    before = _disk_bytes(state_dir)
    recorder = Recorder(monkeypatch)
    result = service.wait_task("task-1", timeout_seconds=2, poll_interval_seconds=0.5)
    io_events = recorder.io()
    assert result is not None
    assert list(result) == [*STATUS_KEYS, "wait"]
    state = service._read_state_snapshot("task-1")
    assert state is not None
    assert result["schema"] == "nexus.self_hosted_task_status.v1"
    assert result["task_id"] == "task-1"
    assert result["status"] == "FINAL_BLOCK"
    assert result["promotion_status"] == "NOT_CREATED"
    assert result["verification_verdict"] == "FAIL"
    assert result["found"] is True and result["state_valid"] is True
    assert result["blocker"] == SelfHostedTaskService._projected_blocker(state)
    assert result["retry_authorized"] is False
    assert result["task_action"] == SelfHostedTaskService._task_action_envelope(state)
    assert result["wait"] == {
        "timed_out": False,
        "timeout_seconds": 2.0,
        "poll_interval_seconds": 0.5,
    }
    assert isinstance(result["wait"]["timeout_seconds"], float)
    assert io_events == ["_read_state_snapshot"]
    assert "lock+" not in recorder.events
    assert _disk_bytes(state_dir) == before


def test_wait_task_settled_detailed_result_drops_operator_receipts(
    service: SelfHostedTaskService,
) -> None:
    _seed(
        service,
        status="CANCELLED",
        operator_outcome_receipt={"x": 1},
        operator_outcome_receipts=[{"x": 1}],
        note="kept",
    )
    result = service.wait_task("task-1", include_details=True, timeout_seconds=0)
    assert result is not None
    assert "operator_outcome_receipt" not in result
    assert "operator_outcome_receipts" not in result
    assert result["note"] == "kept"
    assert result["status"] == "CANCELLED"
    assert result["task_action"]["action_state"] == "TERMINAL"
    assert list(result)[-1] == "wait"
    assert result["wait"]["timed_out"] is False


def test_wait_task_in_progress_times_out_with_flagged_envelope(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, status="SUBMITTED")
    fake = FakeTime([100.0])
    monkeypatch.setattr(service_module, "time", fake)
    result = service.wait_task("task-1", timeout_seconds=0, poll_interval_seconds=1)
    assert result is not None
    assert list(result) == [*STATUS_KEYS, "wait"]
    assert result["task_action"]["action_state"] == "IN_PROGRESS"
    assert result["task_action"]["wait_timed_out"] is True
    assert result["wait"] == {
        "timed_out": True,
        "timeout_seconds": 0.0,
        "poll_interval_seconds": 1.0,
    }
    assert fake.calls == [("monotonic", 100.0), ("monotonic", 100.0)]


def test_wait_task_in_progress_detailed_timeout_overrides_task_action(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, status="WORKER_RUNNING", operator_outcome_receipts=[])
    monkeypatch.setattr(service_module, "time", FakeTime([1.0]))
    result = service.wait_task("task-1", timeout_seconds=0, include_details=True)
    assert result is not None
    assert "operator_outcome_receipts" not in result
    assert result["task_action"]["wait_timed_out"] is True
    assert result["status"] == "WORKER_RUNNING"
    keys = list(result)
    assert keys[-1] == "wait" and keys.count("task_action") == 1
    assert keys.index("task_action") < keys.index("wait") - 1
    assert result["wait"]["timed_out"] is True


def test_wait_task_polls_until_settled_and_bounds_sleep(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, status="SUBMITTED")
    sleeps: list[int] = []

    def settle() -> None:
        sleeps.append(1)
        if len(sleeps) == 2:
            _seed(service, status="FINAL_BLOCK")

    # deadline = 10 + 1; loop 1 check 10, sleep calc 10.25; loop 2 check 10.5, calc 10.9
    fake = FakeTime([10.0, 10.0, 10.25, 10.5, 10.9, 11.5], on_sleep=settle)
    monkeypatch.setattr(service_module, "time", fake)
    recorder = Recorder(monkeypatch)
    result = service.wait_task("task-1", timeout_seconds=1, poll_interval_seconds=0.5)
    assert result is not None
    assert result["status"] == "FINAL_BLOCK"
    assert result["wait"]["timed_out"] is False
    assert fake.calls == [
        ("monotonic", 10.0),
        ("monotonic", 10.0),
        ("monotonic", 10.25),
        ("sleep", 0.5),
        ("monotonic", 10.5),
        ("monotonic", 10.9),
        ("sleep", pytest.approx(0.1)),
    ]
    assert [e for e in recorder.io() if e != "_state_path"] == [
        "_read_state_snapshot",
        "_read_state_snapshot",
        "lock+",
        "_write_state_locked",
        "lock-",
        "_read_state_snapshot",
    ]


def test_wait_task_sleep_never_negative(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, status="SUBMITTED")
    # deadline 0 + 1; check 0.5 (< deadline), sleep calc 2.0 (past deadline) -> sleep(0.0)
    fake = FakeTime([0.0, 0.5, 2.0, 3.0])
    monkeypatch.setattr(service_module, "time", fake)
    result = service.wait_task("task-1", timeout_seconds=1, poll_interval_seconds=0.25)
    assert result is not None and result["wait"]["timed_out"] is True
    assert ("sleep", 0.0) in fake.calls


def test_wait_task_reads_time_through_the_facade(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, status="SUBMITTED")
    seen: list[str] = []
    fake = SimpleNamespace(
        monotonic=lambda: seen.append("monotonic") or 0.0,
        sleep=lambda _s: pytest.fail("must not sleep when timeout is 0"),
    )
    monkeypatch.setattr(service_module, "time", fake)
    result = service.wait_task("task-1", timeout_seconds=0)
    assert result is not None and result["wait"]["timed_out"] is True
    assert seen == ["monotonic", "monotonic"]


def test_wait_task_invalid_state_is_settled(
    service: SelfHostedTaskService, state_dir: Path
) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "broken.json").write_text("{bad", encoding="utf-8")
    result = service.wait_task("broken", timeout_seconds=0)
    assert result is not None
    assert result["status"] == "BLOCKED_INVALID_STATE"
    assert result["state_valid"] is False
    assert result["blocker"]["code"] == "STATE_JSON_INVALID"
    assert result["wait"]["timed_out"] is False


# ---------------------------------------------------------------------------
# list_actionable_tasks


def test_list_actionable_without_state_dir(tmp_path: Path) -> None:
    service = SelfHostedTaskService(state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True)
    if service.state_dir.exists():
        for path in service.state_dir.iterdir():
            if path.is_file():
                path.unlink()
        service.state_dir.rmdir()
    assert service.list_actionable_tasks() == {
        "schema": "nexus.self_hosted_actionable_tasks.v1",
        "actionable_count": 0,
        "details_included": False,
        "tasks": [],
    }


def test_list_actionable_compact_sorted_and_read_only(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, state_dir: Path
) -> None:
    _seed(service, "b-final", status="FINAL_BLOCK")
    _seed(service, "a-running", status="SUBMITTED")
    _seed(service, "c-cancelled", status="CANCELLED")
    _seed(
        service,
        "d-approval",
        status="CANDIDATE_COMMITTED",
        promotion_status="PENDING_HUMAN_APPROVAL",
    )
    (state_dir / "e-broken.json").write_text("[]", encoding="utf-8")
    before = _disk_bytes(state_dir)
    recorder = Recorder(monkeypatch)
    result = service.list_actionable_tasks()
    assert result["schema"] == "nexus.self_hosted_actionable_tasks.v1"
    assert result["details_included"] is False
    assert [task["task_id"] for task in result["tasks"]] == ["b-final", "d-approval", "e-broken"]
    assert result["actionable_count"] == 3
    for task in result["tasks"]:
        envelope = dict(task)
        nested = envelope.pop("task_action")
        assert nested == envelope
        assert envelope["schema"] == "nexus.self_hosted_task_action.v1"
        assert envelope["attention_required"] is True
    assert "lock+" not in recorder.events
    assert recorder.io() == ["_read_state_snapshot"] * 5
    assert _disk_bytes(state_dir) == before


def test_list_actionable_details_returns_full_snapshots(service: SelfHostedTaskService) -> None:
    _seed(service, "t1", status="FINAL_BLOCK", operator_outcome_receipt={"kept": True})
    _seed(service, "t2", status="SUBMITTED")
    result = service.list_actionable_tasks(include_details=True)
    assert result["details_included"] is True
    assert result["actionable_count"] == 1
    (task,) = result["tasks"]
    assert task == service._read_state_snapshot("t1")
    assert task["operator_outcome_receipt"] == {"kept": True}


def test_list_actionable_skips_vanished_snapshots(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, "t1", status="FINAL_BLOCK")
    _seed(service, "t2", status="FINAL_BLOCK")
    original = SelfHostedTaskService._read_state_snapshot

    def vanished(self: Any, task_id: str) -> Any:
        return None if task_id == "t1" else original(self, task_id)

    monkeypatch.setattr(SelfHostedTaskService, "_read_state_snapshot", vanished)
    result = service.list_actionable_tasks()
    assert [task["task_id"] for task in result["tasks"]] == ["t2"]


# ---------------------------------------------------------------------------
# get_task / get_task_snapshot


def test_get_task_snapshot_missing(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder(monkeypatch)
    assert service.get_task_snapshot("missing") is None
    assert service.get_task_snapshot("missing", include_details=True) is None
    assert service.get_task("missing") is None
    assert "lock+" not in recorder.events


def test_get_task_snapshot_compact_projection(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, state_dir: Path
) -> None:
    _seed(
        service,
        promotion_status="NOT_CREATED",
        verification_verdict="PASS",
        retry_authorized=True,
        blocker={"code": "X"},
        operator_outcome_receipt={"y": 1},
    )
    before = _disk_bytes(state_dir)
    recorder = Recorder(monkeypatch)
    result = service.get_task_snapshot("task-1")
    io_events = recorder.io()
    assert result is not None
    assert list(result) == [*STATUS_KEYS, "autonomy", "approval_requirements"]
    state = service._read_state_snapshot("task-1")
    assert state is not None
    assert result["blocker"] == {"code": "X"}
    assert result["retry_authorized"] is True
    assert result["verification_verdict"] == "PASS"
    assert result["task_action"] == state["task_action"]
    assert result["autonomy"] == service_module.project_autonomy_submission(state)
    assert result["approval_requirements"] == SelfHostedTaskService._approval_requirements(state)
    assert io_events == ["_read_state_snapshot"]
    assert "_approval_requirements" in recorder.events
    assert _disk_bytes(state_dir) == before


def test_get_task_snapshot_uses_persisted_task_action_when_present(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = {"schema": "sentinel"}

    def snapshot(self: Any, task_id: str) -> dict[str, Any]:
        return {"task_id": task_id, "status": "FINAL_BLOCK", "task_action": sentinel}

    monkeypatch.setattr(SelfHostedTaskService, "_read_state_snapshot", snapshot)
    result = service.get_task_snapshot("x")
    assert result is not None
    assert result["task_action"] is sentinel
    assert result["found"] is True and result["state_valid"] is True

    def no_action(self: Any, task_id: str) -> dict[str, Any]:
        return {"task_id": task_id, "status": "FINAL_BLOCK", "task_action": {}}

    monkeypatch.setattr(SelfHostedTaskService, "_read_state_snapshot", no_action)
    result = service.get_task_snapshot("x")
    assert result is not None
    assert result["task_action"]["schema"] == "nexus.self_hosted_task_action.v1"


def test_get_task_snapshot_reads_project_autonomy_through_the_facade(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service)
    seen: list[str] = []

    def fake(state: Any) -> dict[str, Any]:
        seen.append(state["task_id"])
        return {"patched": True}

    monkeypatch.setattr(service_module, "project_autonomy_submission", fake)
    result = service.get_task_snapshot("task-1")
    assert result is not None
    assert result["autonomy"] == {"patched": True}
    assert seen == ["task-1"]


def test_get_task_snapshot_details(service: SelfHostedTaskService) -> None:
    _seed(
        service, operator_outcome_receipt={"a": 1}, operator_outcome_receipts=[{"a": 1}], note="n"
    )
    result = service.get_task_snapshot("task-1", include_details=True)
    state = service._read_state_snapshot("task-1")
    assert result is not None and state is not None
    expected = {
        **state,
        "approval_requirements": SelfHostedTaskService._approval_requirements(state),
    }
    expected.pop("operator_outcome_receipt")
    expected.pop("operator_outcome_receipts")
    assert result == expected
    assert list(result)[-1] == "approval_requirements"


def test_get_task_is_detailed_snapshot_without_operator_receipts(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, operator_outcome_receipt={"a": 1}, operator_outcome_receipts=[{"a": 1}])
    recorder = Recorder(monkeypatch)
    result = service.get_task("task-1")
    assert result == service.get_task_snapshot("task-1", include_details=True)
    assert result is not None and "operator_outcome_receipt" not in result
    assert recorder.events[:2] == ["get_task", "get_task_snapshot"]
    assert "lock+" not in recorder.events


def test_get_task_pops_receipts_from_snapshot_result(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def snapshot(self: Any, task_id: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((task_id, kwargs))
        return {
            "task_id": task_id,
            "operator_outcome_receipt": 1,
            "operator_outcome_receipts": 2,
            "k": 3,
        }

    monkeypatch.setattr(SelfHostedTaskService, "get_task_snapshot", snapshot)
    assert service.get_task("t") == {"task_id": "t", "k": 3}
    assert calls == [("t", {"include_details": True})]


# ---------------------------------------------------------------------------
# get_receipt


def test_get_receipt_missing_task(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder(monkeypatch)
    assert service.get_receipt("missing") is None
    assert recorder.io() == ["_read_state", "_state_path", "_latest_archived_state"]


def test_get_receipt_defaults_and_lock_order(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, state_dir: Path
) -> None:
    _seed(service, status="SUBMITTED")
    before = _disk_bytes(state_dir)
    recorder = Recorder(monkeypatch)
    receipt = service.get_receipt("task-1")
    assert receipt is not None
    assert list(receipt) == RECEIPT_KEYS
    assert receipt["task_id"] == "task-1"
    assert receipt["attempt_id"] == "attempt-1"
    assert receipt["telemetry"] == {"wall_time_ms": 0, "overhead_ms": 0}
    assert receipt["salvage_only"] is False
    assert receipt["promotion_eligible"] is False
    assert receipt["provider_receipt_authoritative"] is False
    assert receipt["workforce_admission_authoritative"] is False
    assert receipt["operator_outcome_receipts"] == []
    assert receipt["state_retention_status"] is None
    assert receipt["archive_location"] is None
    none_keys = set(RECEIPT_KEYS) - {
        "task_id",
        "attempt_id",
        "status",
        "telemetry",
        "salvage_only",
        "promotion_eligible",
        "provider_receipt_authoritative",
        "workforce_admission_authoritative",
        "operator_outcome_receipts",
    }
    assert {key for key in none_keys if receipt[key] is not None} == set()
    assert recorder.io() == [
        "_read_state",
        "_state_path",
        "lock+",
        "_load_state_path",
        "lock-",
        "_latest_archived_state",
    ]
    assert _disk_bytes(state_dir) == before


def test_get_receipt_fallbacks_from_contract_lease_and_packet(
    service: SelfHostedTaskService,
) -> None:
    _seed(
        service,
        contract={
            "controller_repo_root": "/c",
            "controller_revision": "rev-c",
            "target_repo_root": "/t",
            "target_base_revision": "base-c",
            "collaboration_realm": "realm-c",
        },
        lease={
            "controller_status_sha256": "lease-status",
            "target_worktree": "/lease-t",
            "initial_head": "lease-head",
            "target_branch": "lease-branch",
        },
        promotion_packet={
            "candidate_commit_sha": "p-commit",
            "candidate_tree_sha": "p-tree",
            "candidate_state_hash": "p-state",
            "verified_receipt_hash": "p-receipt",
        },
    )
    receipt = service.get_receipt("task-1")
    assert receipt is not None
    assert receipt["controller_worktree"] == "/c"
    assert receipt["controller_revision"] == "rev-c"
    assert receipt["controller_status_sha256"] == "lease-status"
    assert receipt["target_worktree"] == "/lease-t"
    assert receipt["target_initial_revision"] == "lease-head"
    assert receipt["target_branch"] == "lease-branch"
    assert receipt["candidate_commit_sha"] == "p-commit"
    assert receipt["candidate_tree_sha"] == "p-tree"
    assert receipt["candidate_state_hash"] == "p-state"
    assert receipt["verified_receipt_hash"] == "p-receipt"
    assert receipt["collaboration_realm"] == "realm-c"


def test_get_receipt_state_fields_win_over_fallbacks(service: SelfHostedTaskService) -> None:
    _seed(
        service,
        contract={
            "controller_repo_root": "/c",
            "target_repo_root": "/t",
            "target_base_revision": "b",
        },
        lease={"target_worktree": "/lease-t", "initial_head": "h"},
        controller_worktree="/state-c",
        target_worktree="/state-t",
        target_initial_revision="state-rev",
        collaboration_realm="realm-s",
        telemetry={"wall_time_ms": 5, "overhead_ms": 1},
        salvage_only=True,
        promotion_eligible=True,
        provider_receipt_authoritative=True,
        error="boom",
    )
    receipt = service.get_receipt("task-1")
    assert receipt is not None
    assert receipt["controller_worktree"] == "/state-c"
    assert receipt["target_worktree"] == "/state-t"
    assert receipt["target_initial_revision"] == "state-rev"
    assert receipt["collaboration_realm"] == "realm-s"
    assert receipt["telemetry"] == {"wall_time_ms": 5, "overhead_ms": 1}
    assert receipt["salvage_only"] is True
    assert receipt["promotion_eligible"] is True
    assert receipt["provider_receipt_authoritative"] is True
    assert receipt["error"] == "boom"


def test_get_receipt_target_worktree_falls_back_to_contract(service: SelfHostedTaskService) -> None:
    _seed(service, contract={"target_repo_root": "/t", "target_base_revision": "base"})
    receipt = service.get_receipt("task-1")
    assert receipt is not None
    assert receipt["target_worktree"] == "/t"
    assert receipt["target_initial_revision"] == "base"


@pytest.mark.parametrize(
    ("fields", "candidate_expected", "overall_expected"),
    [
        (
            {
                "candidate": {"collaboration_provenance": "cand"},
                "verified_receipt": {"collaboration_provenance": "vr"},
            },
            "cand",
            "cand",
        ),
        (
            {
                "verified_receipt": {"collaboration_provenance": "vr"},
                "promotion_packet": {"collaboration_provenance": "pp"},
            },
            "vr",
            "vr",
        ),
        (
            {
                "promotion_packet": {"collaboration_provenance": "pp"},
                "lease": {"collaboration_provenance": "ls"},
            },
            "pp",
            "pp",
        ),
        (
            {"lease": {"collaboration_provenance": "ls"}, "collaboration_provenance": "st"},
            "ls",
            "ls",
        ),
        ({"collaboration_provenance": "st"}, None, "st"),
        ({}, None, None),
    ],
)
def test_get_receipt_collaboration_provenance_precedence(
    service: SelfHostedTaskService,
    fields: dict[str, Any],
    candidate_expected: Any,
    overall_expected: Any,
) -> None:
    _seed(service, **fields)
    receipt = service.get_receipt("task-1")
    assert receipt is not None
    assert receipt["candidate_collaboration_provenance"] == candidate_expected
    assert receipt["collaboration_provenance"] == overall_expected


def test_get_receipt_submission_provenance(service: SelfHostedTaskService) -> None:
    _seed(service, collaboration_provenance="st")
    receipt = service.get_receipt("task-1")
    assert receipt is not None and receipt["submission_collaboration_provenance"] == "st"
    _seed(service, collaboration_provenance="st", submission_collaboration_provenance="sub")
    receipt = service.get_receipt("task-1")
    assert receipt is not None and receipt["submission_collaboration_provenance"] == "sub"


def test_get_receipt_reports_archive(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _seed(service, state_retention_status="TERMINAL", archive_location="old")
    archived = tmp_path / "archive" / "task-1.json"
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_latest_archived_state",
        lambda self, task_id: (archived, {"task_id": task_id}),
    )
    receipt = service.get_receipt("task-1")
    assert receipt is not None
    assert receipt["state_retention_status"] == "ARCHIVED"
    assert receipt["archive_location"] == str(archived)


def test_get_receipt_without_archive_keeps_state_retention(service: SelfHostedTaskService) -> None:
    _seed(service, state_retention_status="TERMINAL", archive_location="loc", archive_eligible=True)
    receipt = service.get_receipt("task-1")
    assert receipt is not None
    assert receipt["state_retention_status"] == "TERMINAL"
    assert receipt["archive_location"] == "loc"
    assert receipt["archive_eligible"] is True


def test_get_receipt_reads_archived_state_when_live_state_is_gone(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archived = tmp_path / "archive" / "gone.json"
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_latest_archived_state",
        lambda self, task_id: (
            archived,
            {"task_id": task_id, "status": "INTEGRATED", "attempt_id": "a9"},
        ),
    )
    recorder = Recorder(monkeypatch)
    receipt = service.get_receipt("gone")
    assert receipt is not None
    assert receipt["status"] == "INTEGRATED"
    assert receipt["attempt_id"] == "a9"
    assert receipt["archive_location"] == str(archived)
    assert "lock+" not in recorder.events
    assert recorder.io() == [
        "_read_state",
        "_state_path",
        "_latest_archived_state",
        "_latest_archived_state",
    ]


# ---------------------------------------------------------------------------
# get_promotion_packet


def test_get_promotion_packet_missing(service: SelfHostedTaskService) -> None:
    assert service.get_promotion_packet("missing") is None


def test_get_promotion_packet_defaults_and_values(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service)
    recorder = Recorder(monkeypatch)
    packet = service.get_promotion_packet("task-1")
    assert packet == {
        "task_id": "task-1",
        "promotion_status": None,
        "promotion_packet": None,
        "candidate_commit_created": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "merge_performed": False,
        "push_performed": False,
    }
    assert recorder.events[0] == "get_task"
    assert "lock+" not in recorder.events
    _seed(
        service,
        promotion_status="PENDING_HUMAN_APPROVAL",
        promotion_packet={"candidate_commit_sha": "c"},
        candidate_commit_created=True,
        public_claim_allowed=True,
        production_ready=True,
        merge_performed=True,
        push_performed=True,
    )
    packet = service.get_promotion_packet("task-1")
    assert packet is not None
    assert packet["promotion_status"] == "PENDING_HUMAN_APPROVAL"
    assert packet["promotion_packet"] == {"candidate_commit_sha": "c"}
    assert all(packet[key] is True for key in list(packet)[3:])


def test_get_promotion_packet_goes_through_get_task(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        SelfHostedTaskService,
        "get_task",
        lambda self, task_id: {"promotion_status": f"via-{task_id}"},
    )
    packet = service.get_promotion_packet("z")
    assert packet is not None and packet["promotion_status"] == "via-z"


# ---------------------------------------------------------------------------
# _snapshot_target_integrity


def _tree(root: Path) -> Path:
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("print(1)\n", encoding="utf-8")
    (root / "b.txt").write_text("b", encoding="utf-8")
    os.symlink("pkg/a.py", root / "link")
    return root


def test_snapshot_target_integrity_missing_and_not_directory(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert SelfHostedTaskService._snapshot_target_integrity(missing) == (
        "MISSING",
        f"target worktree missing: {missing}",
    )
    file_path = tmp_path / "file"
    file_path.write_text("x", encoding="utf-8")
    assert SelfHostedTaskService._snapshot_target_integrity(file_path) == (
        "NOT_DIRECTORY",
        f"target worktree is not a directory: {file_path}",
    )


def test_snapshot_target_integrity_digest_is_exact(tmp_path: Path) -> None:
    root = _tree(tmp_path / "t")
    digest, error = SelfHostedTaskService._snapshot_target_integrity(root)
    assert error is None
    expected = hashlib.sha256()
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        dirs.sort()
        files.sort()
        for name, kind in [(name, "dir") for name in dirs] + [(name, "file") for name in files]:
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            metadata = path.lstat()
            expected.update(f"{kind}:{relative}\0".encode())
            expected.update(
                f"mode={metadata.st_mode & 0o7777};size={metadata.st_size};mtime={metadata.st_mtime_ns}\0".encode()
            )
            if path.is_symlink():
                expected.update(os.readlink(path).encode())
            elif path.is_file():
                expected.update(path.read_bytes())
            else:
                expected.update(f"special={metadata.st_mode}\0".encode())
    assert digest == expected.hexdigest()
    assert SelfHostedTaskService._snapshot_target_integrity(root) == (digest, None)


def test_snapshot_target_integrity_detects_changes(tmp_path: Path) -> None:
    root = _tree(tmp_path / "t")
    first, _ = SelfHostedTaskService._snapshot_target_integrity(root)
    stamp = (root / "b.txt").stat().st_mtime_ns
    (root / "b.txt").write_text("c", encoding="utf-8")
    os.utime(root / "b.txt", ns=(stamp, stamp))
    second, _ = SelfHostedTaskService._snapshot_target_integrity(root)
    assert second != first
    os.chmod(root / "b.txt", 0o600)
    third, _ = SelfHostedTaskService._snapshot_target_integrity(root)
    assert third != second


def test_snapshot_target_integrity_does_not_follow_links(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("1", encoding="utf-8")
    root = tmp_path / "t"
    root.mkdir()
    os.symlink(outside, root / "out")
    first, error = SelfHostedTaskService._snapshot_target_integrity(root)
    assert error is None
    (outside / "secret").write_text("2", encoding="utf-8")
    assert SelfHostedTaskService._snapshot_target_integrity(root) == (first, None)


def test_snapshot_target_integrity_special_file(tmp_path: Path) -> None:
    root = tmp_path / "t"
    root.mkdir()
    os.mkfifo(root / "fifo")
    digest, error = SelfHostedTaskService._snapshot_target_integrity(root)
    assert error is None
    metadata = (root / "fifo").lstat()
    expected = hashlib.sha256()
    expected.update(b"file:fifo\0")
    expected.update(
        f"mode={metadata.st_mode & 0o7777};size={metadata.st_size};mtime={metadata.st_mtime_ns}\0".encode()
    )
    expected.update(f"special={metadata.st_mode}\0".encode())
    assert digest == expected.hexdigest()


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read mode-000 files")
def test_snapshot_target_integrity_unreadable_file(tmp_path: Path) -> None:
    root = tmp_path / "t"
    root.mkdir()
    locked = root / "locked"
    locked.write_text("x", encoding="utf-8")
    locked.chmod(0)
    try:
        code, error = SelfHostedTaskService._snapshot_target_integrity(root)
    finally:
        locked.chmod(0o600)
    assert code == "UNREADABLE:locked"
    assert error is not None and error.startswith("unable to read locked: ")


def test_snapshot_target_integrity_stat_readlink_and_walk_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path / "t")
    real_lstat = Path.lstat

    def failing_lstat(self: Path) -> Any:
        if self.name == "b.txt":
            raise OSError("no stat")
        return real_lstat(self)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", failing_lstat)
        assert SelfHostedTaskService._snapshot_target_integrity(root) == (
            "UNREADABLE:b.txt",
            "unable to stat b.txt: no stat",
        )

    def failing_readlink(path: Any) -> str:
        raise OSError("no link")

    with monkeypatch.context() as patch:
        patch.setattr(os, "readlink", failing_readlink)
        assert SelfHostedTaskService._snapshot_target_integrity(root) == (
            "UNREADABLE:link",
            "unable to read link link: no link",
        )

    def failing_walk(*args: Any, **kwargs: Any) -> Any:
        raise OSError("no walk")

    with monkeypatch.context() as patch:
        patch.setattr(os, "walk", failing_walk)
        assert SelfHostedTaskService._snapshot_target_integrity(root) == (
            "UNREADABLE",
            "unable to walk target worktree: no walk",
        )

    def failing_exists(self: Path) -> bool:
        raise OSError("no exists")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "exists", failing_exists)
        assert SelfHostedTaskService._snapshot_target_integrity(root) == (
            "UNREADABLE",
            "unable to inspect target worktree: no exists",
        )


def test_snapshot_target_integrity_is_reachable_through_instances(
    service: SelfHostedTaskService, tmp_path: Path
) -> None:
    root = _tree(tmp_path / "t")
    assert service._snapshot_target_integrity(
        root
    ) == SelfHostedTaskService._snapshot_target_integrity(root)


# ---------------------------------------------------------------------------
# evaluate_candidate_acceptance / project_candidate_acceptance_for_retry


def test_evaluate_candidate_acceptance_mappings_and_objects() -> None:
    expected = reduce_candidate_acceptance(
        CandidateAcceptanceRequest(**_acceptance_request()), IndependentReviewReceipt(**_review())
    ).to_dict()
    from_mappings = SelfHostedTaskService.evaluate_candidate_acceptance(
        _acceptance_request(), _review()
    )
    from_objects = SelfHostedTaskService.evaluate_candidate_acceptance(
        CandidateAcceptanceRequest(**_acceptance_request()), IndependentReviewReceipt(**_review())
    )
    assert from_mappings == from_objects == expected
    assert expected["decision"] == "ACCEPT"
    repairable = SelfHostedTaskService.evaluate_candidate_acceptance(
        _acceptance_request(), _review(review_status="DEFECT", reasons=("verifier_fixture_defect",))
    )
    assert repairable["decision"] == "REPAIRABLE"
    blocked = SelfHostedTaskService.evaluate_candidate_acceptance(
        _acceptance_request(), _review(reviewer_id="worker-1")
    )
    assert blocked["decision"] == "BLOCK"


def test_evaluate_candidate_acceptance_rejects_unknown_fields() -> None:
    with pytest.raises(TypeError):
        SelfHostedTaskService.evaluate_candidate_acceptance(
            {**_acceptance_request(), "bogus": 1}, _review()
        )
    with pytest.raises(TypeError):
        SelfHostedTaskService.evaluate_candidate_acceptance(
            _acceptance_request(), {**_review(), "bogus": 1}
        )


def test_evaluate_candidate_acceptance_reads_reducer_through_the_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, Any, Any]] = []

    class Result:
        def to_dict(self) -> dict[str, Any]:
            return {"patched": True}

    def fake_reduce(request: Any, review: Any, *, verified_repair_evidence: Any = None) -> Result:
        calls.append((request, review, verified_repair_evidence))
        return Result()

    monkeypatch.setattr(service_module, "reduce_candidate_acceptance", fake_reduce)
    evidence = {"e": 1}
    output = SelfHostedTaskService.evaluate_candidate_acceptance(
        _acceptance_request(), _review(), verified_repair_evidence=evidence
    )
    assert output == {"patched": True}
    ((request, review, passed),) = calls
    assert request == CandidateAcceptanceRequest(**_acceptance_request())
    assert type(request) is CandidateAcceptanceRequest
    assert review == IndependentReviewReceipt(**_review())
    assert type(review) is IndependentReviewReceipt
    assert passed is evidence
    # prebuilt request / review objects are passed through unchanged
    prebuilt_request = CandidateAcceptanceRequest(**_acceptance_request())
    prebuilt_review = IndependentReviewReceipt(**_review())
    SelfHostedTaskService.evaluate_candidate_acceptance(prebuilt_request, prebuilt_review)
    assert calls[-1][0] is prebuilt_request
    assert calls[-1][1] is prebuilt_review
    assert calls[-1][2] is None


def test_acceptance_types_on_the_facade_are_the_acceptance_loop_types() -> None:
    import nexus.orchestrator.acceptance_loop as acceptance_loop

    for name in (
        "CandidateAcceptanceRequest",
        "CandidateAcceptanceResult",
        "IndependentReviewReceipt",
        "reduce_candidate_acceptance",
    ):
        assert getattr(service_module, name) is getattr(acceptance_loop, name)


def test_project_candidate_acceptance_for_retry_delegates_through_the_facade(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Any, ...]] = []

    def fake(owner: Any, request: Any, review: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append((owner, request, review, kwargs))
        return {"delegated": True}

    monkeypatch.setattr(service_module, "project_candidate_acceptance_for_runtime_repair", fake)
    request, review = {"r": 1}, {"v": 1}
    assert service.project_candidate_acceptance_for_retry(request, review) == {"delegated": True}
    evidence = {"e": 1}
    service.project_candidate_acceptance_for_retry(
        request, review, verified_repair_evidence=evidence, repair_target="VERIFIER"
    )
    assert calls == [
        (
            service,
            request,
            review,
            {"verified_repair_evidence": None, "repair_target": "IMPLEMENTATION"},
        ),
        (
            service,
            request,
            review,
            {"verified_repair_evidence": evidence, "repair_target": "VERIFIER"},
        ),
    ]
    assert calls[1][3]["verified_repair_evidence"] is evidence


@pytest.mark.parametrize(
    ("review_changes", "decision"),
    [({}, "ACCEPT"), ({"reviewer_id": "worker-1"}, "BLOCK")],
)
def test_project_candidate_acceptance_for_retry_non_repairable_is_read_only(
    service: SelfHostedTaskService,
    monkeypatch: pytest.MonkeyPatch,
    state_dir: Path,
    review_changes: dict[str, Any],
    decision: str,
) -> None:
    _seed(service)
    before = _disk_bytes(state_dir)
    recorder = Recorder(monkeypatch)
    result = service.project_candidate_acceptance_for_retry(
        _acceptance_request(), _review(**review_changes)
    )
    assert result["acceptance"]["decision"] == decision
    assert result["repair_projection"] is None
    assert result["mutated"] is False
    assert recorder.io() == []
    assert _disk_bytes(state_dir) == before


def test_project_candidate_acceptance_for_retry_repairable_missing_state_fails_closed(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder(monkeypatch)
    with pytest.raises(RuntimeError) as caught:
        service.project_candidate_acceptance_for_retry(
            _acceptance_request(task_id="nope"),
            _review(task_id="nope", review_status="DEFECT", reasons=("verifier_fixture_defect",)),
        )
    assert str(caught.value) == "BOUNDED_RECONCILIATION_STATE_MISSING"
    assert recorder.io() == ["_read_state_snapshot"]


def test_project_candidate_acceptance_for_retry_repairable_writes_under_the_lock(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.orchestrator.runtime_retry_bridge as bridge

    _seed(service)
    projection = {"bounded_reconciliation_projection": {"p": 1}, "verifier_residual": {"r": 1}}
    monkeypatch.setattr(
        bridge, "_build_repair_projection", lambda *args, **kwargs: dict(projection)
    )
    recorder = Recorder(monkeypatch)
    result = service.project_candidate_acceptance_for_retry(
        _acceptance_request(), _review(review_status="DEFECT", reasons=("verifier_fixture_defect",))
    )
    assert result["mutated"] is True
    assert result["repair_projection"] == {"p": 1}
    assert result["residual_packet"] == {"r": 1}
    assert [e for e in recorder.io() if e != "_state_path"] == [
        "_read_state_snapshot",
        "_mutate_state",
        "lock+",
        "lock-",
    ]
    stored = json.loads(service._state_path("task-1").read_text(encoding="utf-8"))
    assert stored["bounded_reconciliation_projection"] == {"p": 1}
    # idempotent replay: same projection, no second mutation
    again = service.project_candidate_acceptance_for_retry(
        _acceptance_request(), _review(review_status="DEFECT", reasons=("verifier_fixture_defect",))
    )
    assert again["mutated"] is False
