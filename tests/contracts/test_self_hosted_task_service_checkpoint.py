"""Characterization of the checkpoint / terminal-core cluster of ``SelfHostedTaskService`` (split S8a).

Big-file split step S8a moves these class members out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin:

* ``_checkpoint`` (every lifecycle status write of a running task);
* ``TERMINAL_CORE_RECORD_SCHEMA`` and ``_TERMINAL_CORE_EXPECTED_HOST_REASONS``;
* ``_build_terminal_core_record`` and ``_record_terminal_core_not_covered`` (#2346);
* ``_heartbeat`` and the static ``_touch_owned_state``.

These tests pin the behaviour before the move and must pass unchanged after it:

* the member table (descriptor kind, signature, docstring, class constant values);
* the exact persisted state a checkpoint writes (status history, telemetry, attempt rows,
  lease / execution / resolution / promotion-packet projections, the runtime-development
  mapping), including golden bytes for a fully populated state;
* every refusal and skip: attempt ownership change, unknown task, every
  ``_build_terminal_core_record`` branch (legacy, non-terminal, receipt, captured
  Candidate, contract unavailable, card binding error, missing / unsupported port,
  non-blocking / unexpected / not-missing Core answers, empty error codes, a failing
  verdict builder) and every attach refusal of ``_record_terminal_core_not_covered``;
* the order: one ``_utc_now`` before the lock; the mutation under the ``flock``; the
  attempt transition event emitted after the lock is released; then, for a terminal
  status only, the Core record built outside the lock and attached under it; the event
  sequence numbers on the real EventBus; an event-append failure propagates after the
  state was written, records the debt, and skips the terminal record;
* the heartbeat loop (1 s wait, stop event, which errors end it and which propagate);
* that every facade-module name the moved code reads (``TERMINAL_STATUSES``,
  ``_jsonable``, ``_parse_time``, ``_utc_now``, ``time``,
  ``build_runtime_development_mapping``, ``build_core_verdict`` and the facade logger
  name) is resolved through the facade at call time, and that class and instance
  patches of the state-store / event members are reached.

Self-deadlocks fail fast instead of hanging CI: an autouse fixture bounds the runtime
store's blocking ``flock`` (it polls ``LOCK_EX | LOCK_NB`` and raises ``TimeoutError``
after 15 s, so a nested state lock fails the test and releases the outer lock), and every
test that waits on another thread uses a daemon thread with a bounded ``join``.  No test
asserts on inode numbers, file modes or other platform details.
"""

from __future__ import annotations

import fcntl
import hashlib
import inspect
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import nexus_runtime.execution_state.store as store_module
import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.events.transport import NexusEventBus
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

NOW = "2026-10-18T12:00:00+00:00"
NOW_TS = 1_792_324_800.0  # 2026-10-18T12:00:00Z
FACADE_LOGGER = "nexus.orchestrator.self_hosted_task_service"
TERMINAL = "FINAL_BLOCK"


# ---------------------------------------------------------------------------
# fixtures


class _BoundedFlock:
    """``fcntl`` for the runtime store: a blocking exclusive lock waits at most 15 s."""

    DEADLINE_S = 15.0

    def __getattr__(self, name: str) -> Any:
        return getattr(fcntl, name)

    def flock(self, fd: int, operation: int) -> None:
        if operation != fcntl.LOCK_EX:
            fcntl.flock(fd, operation)
            return
        deadline = time.monotonic() + self.DEADLINE_S
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        "state lock not acquired within 15 s (self-deadlock?)"
                    ) from None
                time.sleep(0.005)


@pytest.fixture(autouse=True)
def _bounded_state_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    assert store_module.fcntl is fcntl
    monkeypatch.setattr(store_module, "fcntl", _BoundedFlock())


@pytest.fixture(autouse=True)
def _pinned_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "_utc_now", lambda: NOW)


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def service(state_dir: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)


class FakeBus:
    """Replacement for the facade's ``NexusEventBus`` binding (records, never writes)."""

    def __init__(self, events: list[Any], *, emit_error: Exception | None = None) -> None:
        self.events = events
        self.emit_error = emit_error
        self.sequence = 0

    def ensure_configured(self, project_root: Path, *, production: bool = False) -> None:
        self.events.append(("bus.ensure_configured", production))

    def next_attempt_sequence(self, task_id: str, attempt_id: str) -> int:
        self.sequence += 1
        self.events.append(("bus.next_attempt_sequence", task_id, attempt_id))
        return self.sequence

    def emit_attempt_transition(self, event: Any) -> dict[str, Any]:
        self.events.append((
            "bus.emit",
            event.task_id,
            event.attempt_id,
            event.sequence,
            event.state,
        ))
        if self.emit_error is not None:
            raise self.emit_error
        return {}


@pytest.fixture
def events() -> list[Any]:
    return []


@pytest.fixture
def bus(monkeypatch: pytest.MonkeyPatch, events: list[Any]) -> FakeBus:
    fake = FakeBus(events)
    monkeypatch.setattr(service_module, "NexusEventBus", fake)
    return fake


@pytest.fixture
def real_bus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Bind the real EventBus to a tmp root; the binding attributes are restored."""
    root = tmp_path / "events-root"
    monkeypatch.setattr(NexusEventBus, "_attempt_sequences", {})
    monkeypatch.setattr(
        NexusEventBus._log_store, "event_log_path", NexusEventBus._log_store.event_log_path
    )
    monkeypatch.setattr(NexusEventBus._log_store, "lock_path", NexusEventBus._log_store.lock_path)
    monkeypatch.setattr(NexusEventBus, "_production_event_root", None, raising=False)
    monkeypatch.setattr(NexusEventBus, "_configured_event_root", None, raising=False)
    monkeypatch.setattr(NexusEventBus, "_event_log_path", None, raising=False)
    monkeypatch.setattr(NexusEventBus, "_event_bind_mode", None, raising=False)
    NexusEventBus.configure(root)
    return root


def _lock_held(state_dir: Path) -> bool:
    """True when another open file description holds the state ``flock``."""
    path = state_dir / ".state.lock"
    if not path.exists():
        return False
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return False


class Recorder:
    """Class-level probes for the state lock and the members the cluster reaches."""

    FUNCTIONS = (
        "_mutate_state",
        "_emit_bound_attempt_transition",
        "_record_event_append_failure",
        "_record_terminal_core_not_covered",
        "_build_terminal_core_record",
        "_touch_owned_state",
    )

    def __init__(self, monkeypatch: pytest.MonkeyPatch, events: list[Any]) -> None:
        self.events = events
        cls = SelfHostedTaskService
        lock = inspect.getattr_static(cls, "_state_lock")
        recorded = events

        @contextmanager
        def state_lock(self_: Any) -> Iterator[None]:
            recorded.append("lock+")
            with lock(self_):
                yield
            recorded.append("lock-")

        monkeypatch.setattr(cls, "_state_lock", state_lock)
        for name in self.FUNCTIONS:
            static = inspect.getattr_static(cls, name)
            if isinstance(static, staticmethod):
                monkeypatch.setattr(cls, name, staticmethod(self._wrap(name, static.__func__)))
            else:
                monkeypatch.setattr(cls, name, self._wrap(name, static))
        monkeypatch.setattr(
            service_module, "_utc_now", lambda: (recorded.append("_utc_now"), NOW)[1]
        )

    def _wrap(self, name: str, func: Any) -> Any:
        recorded = self.events

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            recorded.append(name)
            try:
                return func(*args, **kwargs)
            except BaseException as exc:
                recorded.append(("raise", name, type(exc).__name__))
                raise

        return wrapped

    def names(self) -> list[str]:
        return [e if isinstance(e, str) else e[0] for e in self.events]


def _seed(service: SelfHostedTaskService, task_id: str = "t", **extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "task_id": task_id,
        "attempt_id": "attempt-1",
        "status": "WORKER_RUNNING",
    }
    state.update(extra)
    return service._write_state(task_id, state)


def _disk(state_dir: Path) -> dict[str, str]:
    if not state_dir.exists():
        return {}
    return {
        str(path.relative_to(state_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(state_dir.rglob("*"))
        if path.is_file() and path.name != ".state.lock"
    }


def _read(state_dir: Path, task_id: str = "t") -> dict[str, Any]:
    return json.loads((state_dir / f"{task_id}.json").read_text(encoding="utf-8"))


UNIVERSE = {"universe_generation": 1, "subjects": [{"subject_id": "s", "kind": "COMMAND"}]}


def _terminal_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "task_id": "t",
        "attempt_id": "attempt-1",
        "status": TERMINAL,
        "verified_receipt": None,
        "request": {"task_id": "t", "core_envelope_required": True, "expected_evidence": UNIVERSE},
    }
    state.update(overrides)
    return state


class Port:
    def __init__(
        self, answer: Any = None, error: Exception | None = None, held: Any = None
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.answer, self.error, self.held = answer, error, held

    def record_terminal_not_covered(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.held is not None:
            self.calls[-1] = {**kwargs, "lock_held": self.held()}
        if self.error is not None:
            raise self.error
        return self.answer


MISSING_VERDICT = {
    "blocking": True,
    "core_status": "UNVERIFIABLE",
    "integrity": "MISSING",
    "reason_codes": ["CANDIDATE_MISSING", "MISSING"],
    "host_reason_codes": [
        "AMBIENT_CORE_FAILED_VERIFICATION:UNVERIFIABLE",
        "CORE_COVERAGE_INCOMPLETE",
    ],
}


class VerdictBuilder:
    """Replacement for the facade's ``build_core_verdict`` binding."""

    def __init__(self, verdict: Any = None, *, transport_error: Exception | None = None) -> None:
        self.verdict = dict(MISSING_VERDICT) if verdict is None else verdict
        self.transport_error = transport_error
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *, contract: Any, projection: Any, transport_error: Any = None) -> Any:
        self.calls.append({"projection": projection, "transport_error": transport_error})
        if transport_error is not None:
            if self.transport_error is not None:
                raise self.transport_error
            return {"blocking": True, "transport_error": transport_error}
        return self.verdict


@pytest.fixture
def verdicts(monkeypatch: pytest.MonkeyPatch) -> VerdictBuilder:
    builder = VerdictBuilder()
    monkeypatch.setattr(service_module, "build_core_verdict", builder)
    return builder


def _core_service(
    state_dir: Path, port: Any, monkeypatch: pytest.MonkeyPatch, card_error: Any = None
) -> Any:
    # typed Any: the tests subscript the Optional records they know are present
    svc = SelfHostedTaskService(
        state_dir=state_dir, auto_reconcile=False, ephemeral=True, ambient_core_port=port
    )
    monkeypatch.setattr(svc, "_card_evidence_binding_error", lambda contract, request: card_error)
    monkeypatch.setattr(svc, "build_contract", lambda request: CONTRACT)
    return svc


CONTRACT = SimpleNamespace(expected_evidence=UNIVERSE)


# ---------------------------------------------------------------------------
# member table

SIGNATURES = {
    "_checkpoint": (
        "function",
        "(self, task_id: 'str', status: 'str', values: 'Optional[Mapping[str, Any]]' = None, *, "
        "attempt_id: 'Optional[str]' = None) -> 'Optional[dict[str, Any]]'",
        None,
    ),
    "_build_terminal_core_record": (
        "function",
        "(self, state: 'Mapping[str, Any]', *, contract: 'Any' = None) -> 'Optional[dict[str, Any]]'",
        "Core's NOT_COVERED record for a declared-universe task with no receipt (#2346).",
    ),
    "_record_terminal_core_not_covered": (
        "function",
        "(self, task_id: 'str', state: 'Any') -> 'None'",
        "Persist the #2346 record; never changes the terminal state it describes.",
    ),
    "_heartbeat": (
        "function",
        "(self, task_id: 'str', attempt_id: 'str', stop: 'threading.Event') -> 'None'",
        None,
    ),
    "_touch_owned_state": (
        "staticmethod",
        "(state: 'dict[str, Any]', attempt_id: 'str') -> 'None'",
        None,
    ),
}


def test_checkpoint_members_keep_kinds_signatures_and_docstrings() -> None:
    for name, (kind, signature, doc) in SIGNATURES.items():
        static = inspect.getattr_static(SelfHostedTaskService, name)
        assert type(static).__name__ == kind, name
        func = static.__func__ if isinstance(static, staticmethod) else static
        assert str(inspect.signature(func)) == signature, name
        first_line = (func.__doc__ or "").strip().splitlines()[0] if func.__doc__ else None
        assert first_line == doc, name
    assert (
        SelfHostedTaskService.TERMINAL_CORE_RECORD_SCHEMA
        == "nexus.self_hosted_terminal_core_record.v1"
    )
    assert SelfHostedTaskService._TERMINAL_CORE_EXPECTED_HOST_REASONS == frozenset({
        "AMBIENT_CORE_FAILED_VERIFICATION:UNVERIFIABLE",
        "CORE_COVERAGE_INCOMPLETE",
    })
    assert type(SelfHostedTaskService._TERMINAL_CORE_EXPECTED_HOST_REASONS) is frozenset
    # the static helper is reachable from the class and from an instance (runtime bridge)
    assert (
        SelfHostedTaskService._touch_owned_state
        is SelfHostedTaskService(
            state_dir=Path("/nonexistent-s8a"), auto_reconcile=False, ephemeral=True
        )._touch_owned_state
    )


# ---------------------------------------------------------------------------
# _checkpoint: persisted state


class Color(Enum):
    RED = "red"


FULL_SEED: dict[str, Any] = {
    "task_id": "t",
    "attempt_id": "attempt-1",
    "status": "WORKER_RUNNING",
    "action_id": "act-7",
    "submitted_at": "2026-10-18T11:59:00+00:00",
    "worker_started_at": "2026-10-18T11:59:30+00:00",
    "status_history": [{"status": "SUBMITTED", "at": "s"}, {"status": "WORKER_RUNNING", "at": "w"}],
    "executions": [
        {"wall_time_ms": 1000, "provider_calls": 2, "provider_attempt_count": 3},
        {"wall_time_ms": "500", "provider_calls": None},
        "not-a-mapping",
        {"provider_attempt_count": 0},
    ],
    "execution": {"outcome": "COMPLETED", "wall_time_ms": 999},
    "verified_receipt": {"verifier_evidence": [{"wall_time_ms": 200}, {"wall_time_ms": None}, 7]},
    "telemetry": {"worktree_time_ms": 30, "commit_hook_time_ms": "40", "cleanup_time_ms": None},
    "attempts": [
        {"attempt_id": "attempt-0", "last_status": "FINAL_BLOCK"},
        {"attempt_id": "attempt-1", "last_status": "WORKER_RUNNING"},
    ],
    "lease": {
        "controller_status_sha256": "c" * 64,
        "target_worktree": "/wt",
        "initial_head": "h" * 40,
        "target_branch": "nexus/t",
    },
    "contract": {"controller_repo_root": "/controller"},
    "attempt_resolution": {"verdict": "REJECTED"},
    "promotion_packet": {
        "candidate_commit_sha": "1" * 40,
        "candidate_tree_sha": "2" * 40,
        "candidate_state_hash": "3" * 64,
        "verified_receipt_hash": "4" * 64,
        "other": "ignored",
    },
    "promotion_status": "APPROVED",
    "candidate_status": "CAPTURED",
    "runtime_phase": " c ",
    "runtime_terminal_state": "complete",
    "runtime_receipt_ref": "rt-ref",
}

EXPECTED_TELEMETRY = {
    "wall_time_ms": 60000,
    "worker_wall_time_ms": 30000,
    "provider_time_ms": 1500,
    "provider_calls": 2,
    "provider_attempts": 4,
    "tokens": None,
    "cost": None,
    "token_status": "unmeasured",
    "cost_status": "unmeasured",
    "savings_claim_allowed": False,
    "verifier_time_ms": 200,
    "worktree_time_ms": 30,
    "commit_hook_time_ms": 40,
    "cleanup_time_ms": 0,
    "overhead_ms": 60000 - (1500 + 200 + 30 + 40 + 0),
}


@pytest.fixture
def frozen_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module.time, "time", lambda: NOW_TS)


def test_checkpoint_persists_the_full_projection(service, state_dir, bus, frozen_time) -> None:
    _seed(service, **{k: v for k, v in FULL_SEED.items() if k not in {"task_id"}})
    result = service._checkpoint(
        "t", TERMINAL, {"error": "boom", "color": Color.RED, "pair": (1, 2), "submitted_at": "x"}
    )
    on_disk = _read(state_dir)
    assert result == on_disk
    assert on_disk["status"] == TERMINAL
    assert on_disk["submitted_at"] == FULL_SEED["submitted_at"]  # values["submitted_at"] dropped
    assert on_disk["color"] == "red" and on_disk["pair"] == [1, 2] and on_disk["error"] == "boom"
    assert on_disk["updated_at"] == on_disk["heartbeat_at"] == NOW
    assert on_disk["status_history"][-1] == {"status": TERMINAL, "at": NOW}
    assert len(on_disk["status_history"]) == 3
    assert on_disk["telemetry"] == EXPECTED_TELEMETRY
    assert on_disk["worker_finished_at"] == NOW and on_disk["worker_child_pgid"] is None
    assert on_disk["attempts"] == [
        {"attempt_id": "attempt-0", "last_status": "FINAL_BLOCK"},
        {"attempt_id": "attempt-1", "last_status": TERMINAL, "updated_at": NOW, "finished_at": NOW},
    ]
    assert {
        k: on_disk[k]
        for k in (
            "controller_worktree",
            "controller_status_sha256",
            "target_worktree",
            "target_initial_revision",
            "target_branch",
            "target_created_at",
        )
    } == {
        "controller_worktree": "/controller",
        "controller_status_sha256": "c" * 64,
        "target_worktree": "/wt",
        "target_initial_revision": "h" * 40,
        "target_branch": "nexus/t",
        "target_created_at": NOW,
    }
    assert on_disk["execution_outcome"] == "COMPLETED"
    assert on_disk["verification_verdict"] == "REJECTED"
    for field in (
        "candidate_commit_sha",
        "candidate_tree_sha",
        "candidate_state_hash",
        "verified_receipt_hash",
    ):
        assert on_disk[field] == FULL_SEED["promotion_packet"][field]
    assert "other" not in on_disk
    mapping = on_disk["runtime_development_mapping"]
    assert mapping["identity"] == {"task_id": "t", "attempt_id": "attempt-1", "action_id": "act-7"}
    assert mapping["runtime"]["success"] is True
    assert mapping["runtime"]["phase"] == "C" and mapping["runtime"]["terminal_state"] == "COMPLETE"
    assert mapping["runtime"]["receipt_ref"] == "rt-ref"
    assert mapping["development"] == {
        "task_id": "t",
        "attempt_id": "attempt-1",
        "action_id": "act-7",
        "status": TERMINAL,
        "candidate_status": "CAPTURED",
        "candidate_accepted": True,
        "integration_status": "APPROVED",
        "integrated": False,
        "receipt_ref": "4" * 64,
    }
    assert hashlib.sha256((state_dir / "t.json").read_bytes()).hexdigest() == GOLDEN_FULL


GOLDEN_FULL = "2f4d4ffb2bea8655d2c0615ae58a0664d09c3b4f7934730cb660ed554ceb952a"


def test_checkpoint_minimal_state_bytes(service, state_dir, bus) -> None:
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    result = service._checkpoint("t", "WORKER_RUNNING", {"x": 1})
    assert result == _read(state_dir)
    assert "telemetry" not in result  # no submitted_at
    assert "worker_finished_at" not in result
    for key in (
        "controller_worktree",
        "execution_outcome",
        "verification_verdict",
        "candidate_commit_sha",
    ):
        assert key not in result
    assert result["status_history"] == [{"status": "WORKER_RUNNING", "at": NOW}]
    assert result["runtime_development_mapping"]["identity"] == {
        "task_id": "t",
        "attempt_id": "attempt-unknown",
        "action_id": "action-t",
    }
    assert hashlib.sha256((state_dir / "t.json").read_bytes()).hexdigest() == GOLDEN_MINIMAL
    assert bus.events == []  # no attempt_id: no attempt transition


GOLDEN_MINIMAL = "bfe344ffca92ac56966d42ca2c6a0790501d5b22d13f04c7a139a0151a10e9c0"


@pytest.mark.parametrize("values", [None, {}], ids=["none", "empty"])
def test_checkpoint_without_values_changes_only_derived_fields(
    service, state_dir, bus, values
) -> None:
    _seed(service, custom="kept")
    service._checkpoint("t", "WORKER_RUNNING", values)
    on_disk = _read(state_dir)
    assert on_disk["custom"] == "kept"
    assert on_disk["status_history"] == []  # same status: no history row
    assert on_disk["updated_at"] == NOW


def test_checkpoint_history_appends_only_on_a_status_change(service, state_dir, bus) -> None:
    _seed(service, status_history=[{"status": "WORKER_RUNNING", "at": "old"}])
    service._checkpoint("t", "WORKER_RUNNING")
    service._checkpoint("t", "CANDIDATE_CAPTURED")
    service._checkpoint("t", "CANDIDATE_CAPTURED")
    assert _read(state_dir)["status_history"] == [
        {"status": "WORKER_RUNNING", "at": "old"},
        {"status": "CANDIDATE_CAPTURED", "at": NOW},
    ]


def test_checkpoint_telemetry_edges(service, state_dir, bus, monkeypatch) -> None:
    # submitted in the future: wall time clamps to 0; no worker start: worker time 0;
    # no executions list: falls back to the single execution; overhead clamps to 0
    monkeypatch.setattr(service_module.time, "time", lambda: NOW_TS)
    _seed(
        service,
        submitted_at="2026-10-18T12:00:10+00:00",
        execution={"wall_time_ms": 5000, "provider_calls": 1},
    )
    service._checkpoint("t", "WORKER_RUNNING")
    telemetry = _read(state_dir)["telemetry"]
    assert telemetry["wall_time_ms"] == 0 and telemetry["worker_wall_time_ms"] == 0
    assert telemetry["provider_time_ms"] == 5000 and telemetry["provider_calls"] == 1
    assert telemetry["provider_attempts"] == 1
    assert telemetry["overhead_ms"] == 0
    # unparseable submitted_at: no telemetry at all (existing telemetry is kept)
    _seed(service, task_id="u", submitted_at="not-a-time", telemetry={"kept": True})
    service._checkpoint("u", "WORKER_RUNNING")
    assert _read(state_dir, "u")["telemetry"] == {"kept": True}


def test_checkpoint_pending_human_approval_finishes_the_attempt_only(
    service, state_dir, bus
) -> None:
    _seed(service, attempts=[{"attempt_id": "attempt-1"}], worker_child_pgid=42)
    service._checkpoint("t", "PENDING_HUMAN_APPROVAL")
    on_disk = _read(state_dir)
    assert on_disk["attempts"] == [
        {
            "attempt_id": "attempt-1",
            "last_status": "PENDING_HUMAN_APPROVAL",
            "updated_at": NOW,
            "finished_at": NOW,
        }
    ]
    assert "worker_finished_at" not in on_disk and on_disk["worker_child_pgid"] == 42


def test_checkpoint_keeps_an_existing_target_created_at(service, state_dir, bus) -> None:
    _seed(service, lease={"target_branch": "b"}, target_created_at="earlier")
    service._checkpoint("t", "WORKER_RUNNING")
    on_disk = _read(state_dir)
    assert on_disk["target_created_at"] == "earlier"
    assert on_disk["controller_worktree"] is None and on_disk["target_worktree"] is None


@pytest.mark.parametrize(
    "seed, expected",
    [
        (
            {"status": "INTEGRATED", "promotion_status": "APPROVED"},
            {"integrated": True, "candidate_accepted": True, "integration_status": "APPROVED"},
        ),
        (
            {"promotion_status": "INTEGRATED"},
            {"integrated": True, "candidate_accepted": True, "integration_status": "INTEGRATED"},
        ),
        (
            {"promotion_status": "PENDING"},
            {"integrated": False, "candidate_accepted": False, "integration_status": "PENDING"},
        ),
    ],
    ids=["status-integrated", "promotion-integrated", "pending"],
)
def test_checkpoint_mapping_integration_flags(service, state_dir, bus, seed, expected) -> None:
    seed = dict(seed)
    status = seed.pop("status", "WORKER_RUNNING")
    _seed(service, **seed)
    service._checkpoint("t", status)
    development = _read(state_dir)["runtime_development_mapping"]["development"]
    assert {k: development[k] for k in expected} == expected


@pytest.mark.parametrize(
    "seed, status, code",
    [
        ({}, "INTEGRATED", "RUNTIME_DEVELOPMENT_MAPPING_INTEGRATION_REQUIRES_ACCEPTANCE"),
        (
            {"runtime_phase": "B"},
            "WORKER_RUNNING",
            "RUNTIME_DEVELOPMENT_MAPPING_RUNTIME_PHASE_INVALID",
        ),
    ],
    ids=["integrated-unaccepted", "phase-invalid"],
)
def test_checkpoint_mapping_refusal_leaves_the_state(
    service, state_dir, events, bus, monkeypatch, seed, status, code
) -> None:
    # the mapping is built inside the mutation: a refusal aborts the whole write
    _seed(service, **seed)
    before = _disk(state_dir)
    recorder = Recorder(monkeypatch, events)
    with pytest.raises(ValueError, match=f"^{code}$"):
        service._checkpoint("t", status)
    assert _disk(state_dir) == before and not _lock_held(state_dir)
    assert recorder.names() == ["_utc_now", "_mutate_state", "lock+", "raise"]


@pytest.mark.parametrize(
    "phase, terminal, success",
    [
        ("C", "COMPLETE", True),
        ("c", " complete ", True),
        ("A", "COMPLETE", False),
        ("C", "FAILED", False),
        (None, None, False),
    ],
)
def test_checkpoint_mapping_runtime_success(
    service, state_dir, bus, phase, terminal, success
) -> None:
    _seed(service, runtime_phase=phase, runtime_terminal_state=terminal)
    service._checkpoint("t", "WORKER_RUNNING")
    assert _read(state_dir)["runtime_development_mapping"]["runtime"]["success"] is success


def test_checkpoint_state_without_attempt_refuses_an_explicit_attempt(
    service, state_dir, bus
) -> None:
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    with pytest.raises(RuntimeError, match="^task attempt ownership changed$"):
        service._checkpoint("t", "WORKER_RUNNING", attempt_id="arg-attempt")


@pytest.mark.parametrize(
    "seed, expected",
    [
        ({"action_id": "act-1"}, "act-1"),
        ({}, "action-attempt-1"),
        ({"attempt_id": None}, "action-t"),
    ],
    ids=["explicit", "from-attempt", "from-task"],
)
def test_checkpoint_mapping_action_id_fallbacks(service, state_dir, bus, seed, expected) -> None:
    _seed(service, **seed)
    service._checkpoint("t", "WORKER_RUNNING")
    identity = _read(state_dir)["runtime_development_mapping"]["identity"]
    assert identity["action_id"] == expected


def test_checkpoint_refuses_a_changed_attempt_and_leaves_everything(
    service, state_dir, events, bus, monkeypatch
) -> None:
    _seed(service)
    before = _disk(state_dir)
    recorder = Recorder(monkeypatch, events)
    with pytest.raises(RuntimeError, match="^task attempt ownership changed$"):
        service._checkpoint("t", TERMINAL, {"x": 1}, attempt_id="attempt-2")
    assert _disk(state_dir) == before
    assert recorder.names() == ["_utc_now", "_mutate_state", "lock+", "raise"]
    assert not _lock_held(state_dir)


def test_checkpoint_with_the_owning_attempt_id(service, state_dir, bus) -> None:
    _seed(service)
    result = service._checkpoint("t", "WORKER_RUNNING", attempt_id="attempt-1")
    assert result is not None and result["attempt_id"] == "attempt-1"


def test_checkpoint_unknown_task_returns_none_without_effects(
    service, state_dir, events, bus, monkeypatch
) -> None:
    recorder = Recorder(monkeypatch, events)
    assert service._checkpoint("missing", TERMINAL) is None
    assert _disk(state_dir) == {}
    assert recorder.names() == [
        "_utc_now",
        "_mutate_state",
        "lock+",
        "lock-",
        "_emit_bound_attempt_transition",
        "_record_terminal_core_not_covered",
    ]


# ---------------------------------------------------------------------------
# _checkpoint: order, lock and events


def test_checkpoint_order_non_terminal(service, state_dir, events, bus, monkeypatch) -> None:
    _seed(service)
    recorder = Recorder(monkeypatch, events)
    service._checkpoint("t", "WORKER_RUNNING")
    assert recorder.names() == [
        "_utc_now",
        "_mutate_state",
        "lock+",
        "lock-",
        "_emit_bound_attempt_transition",
        "bus.next_attempt_sequence",
        "bus.emit",
    ]


def test_checkpoint_order_terminal_records_core_after_the_event(
    state_dir, events, bus, monkeypatch, verdicts
) -> None:
    port = Port(answer={"terminal_status": TERMINAL}, held=lambda: _lock_held(state_dir))
    svc = _core_service(state_dir, port, monkeypatch)
    svc._write_state("t", _terminal_state(status="WORKER_RUNNING"))
    recorder = Recorder(monkeypatch, events)
    result = svc._checkpoint("t", TERMINAL, {"error": "x"}, attempt_id="attempt-1")
    assert recorder.names() == [
        "_utc_now",
        "_mutate_state",
        "lock+",
        "lock-",
        "_emit_bound_attempt_transition",
        "bus.next_attempt_sequence",
        "bus.emit",
        "_record_terminal_core_not_covered",
        "_build_terminal_core_record",
        "_mutate_state",
        "lock+",
        "lock-",
    ]
    assert port.calls[0]["lock_held"] is False  # Core is asked outside the state lock
    on_disk = _read(state_dir)
    assert on_disk["terminal_core_record"]["record_status"] == "RECORDED"
    # the returned state is the one written before the record was attached
    assert result is not None and "terminal_core_record" not in result


def test_checkpoint_mutation_runs_under_the_flock_and_emit_outside(
    service, state_dir, monkeypatch, events
) -> None:
    seen: list[Any] = []
    real_mapping = service_module.build_runtime_development_mapping

    def mapping(**kwargs: Any) -> Any:
        seen.append(("mapping", _lock_held(state_dir)))
        return real_mapping(**kwargs)

    class Bus(FakeBus):
        def emit_attempt_transition(self, event: Any) -> dict[str, Any]:
            seen.append(("emit", _lock_held(state_dir)))
            return {}

    monkeypatch.setattr(service_module, "build_runtime_development_mapping", mapping)
    monkeypatch.setattr(service_module, "NexusEventBus", Bus(events))
    _seed(service)
    service._checkpoint("t", "WORKER_RUNNING")
    assert seen == [("mapping", True), ("emit", False)]


def test_checkpoint_events_on_the_real_bus_are_sequenced(service, state_dir, real_bus) -> None:
    _seed(service)
    service._checkpoint("t", "WORKER_RUNNING")
    service._checkpoint("t", "CANDIDATE_CAPTURED", {"candidate_commit_sha": "e" * 40})
    service._checkpoint("t", TERMINAL, {"error": "verifier failed"})
    records = SelfHostedTaskService.read_canonical_attempt_events("t", "attempt-1")
    payloads = [record["payload"] for record in records]
    assert [p["sequence"] for p in payloads] == [1, 2, 3]
    assert [p["state"] for p in payloads] == ["WORKER_RUNNING", "CANDIDATE_CAPTURED", TERMINAL]
    assert payloads[1]["candidate_refs"] == ["e" * 40]
    assert payloads[2]["reason"] == "verifier failed"
    assert [record["seq"] for record in records] == sorted(record["seq"] for record in records)


def test_checkpoint_event_failure_propagates_after_the_write(
    state_dir, events, monkeypatch, verdicts
) -> None:
    port = Port(answer={})
    svc = _core_service(state_dir, port, monkeypatch)
    svc._write_state("t", _terminal_state(status="WORKER_RUNNING"))
    monkeypatch.setattr(
        service_module, "NexusEventBus", FakeBus(events, emit_error=OSError("disk"))
    )
    recorder = Recorder(monkeypatch, events)
    with pytest.raises(OSError, match="^disk$"):
        svc._checkpoint("t", TERMINAL)
    on_disk = _read(state_dir)
    assert on_disk["status"] == TERMINAL  # the state write stands
    assert on_disk["event_reconciliation_required"] is True
    assert on_disk["event_append_failure"]["error_type"] == "OSError"
    assert "terminal_core_record" not in on_disk and port.calls == []
    assert recorder.names() == [
        "_utc_now",
        "_mutate_state",
        "lock+",
        "lock-",
        "_emit_bound_attempt_transition",
        "bus.next_attempt_sequence",
        "bus.emit",
        "_record_event_append_failure",
        "_utc_now",
        "_mutate_state",
        "lock+",
        "lock-",
        "raise",
    ]
    assert events[-1] == ("raise", "_emit_bound_attempt_transition", "OSError")


def test_checkpoint_concurrent_holder_blocks_the_write(service, state_dir, bus) -> None:
    _seed(service)
    holder_in, release = threading.Event(), threading.Event()

    def hold() -> None:
        with service._state_lock():
            holder_in.set()
            release.wait(10)

    order: list[str] = []

    def write() -> None:
        service._checkpoint("t", "CANDIDATE_CAPTURED")
        order.append("written")

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    assert holder_in.wait(10)
    writer = threading.Thread(target=write, daemon=True)
    writer.start()
    writer.join(0.3)
    assert writer.is_alive() and _read(state_dir)["status"] == "WORKER_RUNNING"
    order.append("released")
    release.set()
    writer.join(20)
    holder.join(10)
    assert not writer.is_alive() and order == ["released", "written"]
    assert _read(state_dir)["status"] == "CANDIDATE_CAPTURED"


def test_checkpoint_two_threads_serialise(service, state_dir, bus) -> None:
    _seed(service, counter=0)
    real_mapping = service_module.build_runtime_development_mapping

    def worker(status: str) -> None:
        for _ in range(5):
            service._checkpoint("t", status)

    threads = [
        threading.Thread(target=worker, args=(s,), daemon=True) for s in ("A_STATUS", "B_STATUS")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not any(thread.is_alive() for thread in threads)
    assert real_mapping is service_module.build_runtime_development_mapping
    history = _read(state_dir)["status_history"]
    assert all(row["status"] in {"A_STATUS", "B_STATUS"} for row in history)
    assert 2 <= len(history) <= 10


# ---------------------------------------------------------------------------
# _build_terminal_core_record


def test_core_record_recorded(state_dir, monkeypatch, verdicts) -> None:
    port = Port(answer={"terminal_status": "SUPERSEDED", "x": 1})
    svc = _core_service(state_dir, port, monkeypatch)
    record = svc._build_terminal_core_record(_terminal_state(), contract=CONTRACT)
    assert record == {
        "schema": "nexus.self_hosted_terminal_core_record.v1",
        "task_id": "t",
        "attempt_id": "attempt-1",
        "terminal_status": "SUPERSEDED",
        "record_status": "RECORDED",
        "failure_reason": None,
        "verified": False,
        "candidate_commit_allowed": False,
        "core_verdict": MISSING_VERDICT,
    }
    assert list(record) == [
        "schema",
        "task_id",
        "attempt_id",
        "terminal_status",
        "record_status",
        "failure_reason",
        "verified",
        "candidate_commit_allowed",
        "core_verdict",
    ]
    assert port.calls == [
        {
            "contract": CONTRACT,
            "request": _terminal_state()["request"],
            "task_id": "t",
            "attempt_id": "attempt-1",
            "terminal_status": TERMINAL,
        }
    ]
    assert verdicts.calls == [{"projection": port.answer, "transport_error": None}]


@pytest.mark.parametrize("projection", [{}, {"terminal_status": ""}, ["terminal_status"], None])
def test_core_record_keeps_the_state_status_without_a_projection_status(
    state_dir, monkeypatch, verdicts, projection
) -> None:
    svc = _core_service(state_dir, Port(answer=projection), monkeypatch)
    record = svc._build_terminal_core_record(_terminal_state(), contract=CONTRACT)
    assert record["record_status"] == "RECORDED" and record["terminal_status"] == TERMINAL


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "WORKER_RUNNING"},
        {"status": None},
        {"verified_receipt": {}},
        {"candidate": {"x": 1}},
        {"candidate_state_hash": "h"},
        {"candidate_commit_sha": "c"},
        {"candidate_ref": "r"},
        {"promotion_packet": {"a": 1}},
        {"request": None},
        {"request": ["not", "a", "mapping"]},
    ],
    ids=lambda o: "-".join(f"{k}" for k in o) + ("-" + type(next(iter(o.values()))).__name__),
)
def test_core_record_skips(state_dir, monkeypatch, verdicts, overrides) -> None:
    port = Port(answer={})
    svc = _core_service(state_dir, port, monkeypatch)
    assert svc._build_terminal_core_record(_terminal_state(**overrides), contract=CONTRACT) is None
    assert port.calls == [] and verdicts.calls == []


@pytest.mark.parametrize("empty", [None, "", {}])
def test_core_record_empty_candidate_fields_do_not_skip(
    state_dir, monkeypatch, verdicts, empty
) -> None:
    svc = _core_service(state_dir, Port(answer={}), monkeypatch)
    state = _terminal_state(candidate=empty, candidate_ref=empty, promotion_packet=empty)
    assert svc._build_terminal_core_record(state, contract=CONTRACT)["record_status"] == "RECORDED"


@pytest.mark.parametrize("status", sorted(service_module.TERMINAL_STATUSES))
def test_core_record_every_terminal_status(state_dir, monkeypatch, verdicts, status) -> None:
    svc = _core_service(state_dir, Port(answer={}), monkeypatch)
    record = svc._build_terminal_core_record(_terminal_state(status=status), contract=CONTRACT)
    assert record["terminal_status"] == status


def test_core_record_legacy_task_builds_nothing(state_dir, monkeypatch, verdicts) -> None:
    port = Port(answer={})
    svc = _core_service(state_dir, port, monkeypatch)
    built: list[Any] = []
    monkeypatch.setattr(svc, "build_contract", lambda request: built.append(request))
    legacy = _terminal_state(request={"task_id": "t", "core_envelope_required": False})
    assert svc._build_terminal_core_record(legacy) is None
    assert built == [] and port.calls == []
    # an explicit legacy contract (no expected evidence) is also nothing to record
    no_universe = SimpleNamespace(expected_evidence=None)
    assert svc._build_terminal_core_record(legacy, contract=no_universe) is None
    assert svc._build_terminal_core_record(legacy, contract=object()) is None
    # an explicit universe contract records even when the request claims none
    assert svc._build_terminal_core_record(legacy, contract=CONTRACT)["record_status"] == "RECORDED"


@pytest.mark.parametrize(
    "request_extra",
    [{"expected_evidence": {}}, {"core_envelope_required": True}],
    ids=["evidence", "envelope"],
)
def test_core_record_claims_universe_builds_the_contract(
    state_dir, monkeypatch, verdicts, request_extra
) -> None:
    port = Port(answer={})
    svc = _core_service(state_dir, port, monkeypatch)
    built: list[Any] = []
    contract = SimpleNamespace(expected_evidence=None)
    monkeypatch.setattr(
        svc, "build_contract", lambda request: (built.append(dict(request)), contract)[1]
    )
    request = {"task_id": "t", **request_extra}
    record = svc._build_terminal_core_record(_terminal_state(request=request))
    assert built == [request]
    assert record["record_status"] == "RECORDED" and port.calls[0]["contract"] is contract


def test_core_record_contract_unavailable(state_dir, monkeypatch, verdicts) -> None:
    port = Port(answer={})
    svc = _core_service(state_dir, port, monkeypatch)

    def explode(request: Any) -> Any:
        raise ValueError("bad request")

    monkeypatch.setattr(svc, "build_contract", explode)
    record = svc._build_terminal_core_record(_terminal_state(attempt_id=None, task_id=None))
    assert record == {
        "schema": "nexus.self_hosted_terminal_core_record.v1",
        "task_id": "t",  # from the request
        "attempt_id": "",
        "terminal_status": TERMINAL,
        "record_status": "FAILED",
        "failure_reason": "CORE_TERMINAL_CONTRACT_UNAVAILABLE:ValueError",
        "verified": False,
        "candidate_commit_allowed": False,
        "core_verdict": None,
    }
    assert port.calls == [] and verdicts.calls == []


def _failed(record: dict[str, Any], code: str) -> None:
    assert record["record_status"] == "FAILED"
    assert record["failure_reason"] == f"CORE_TERMINAL_RECORD_FAILED:{code}"
    assert record["verified"] is False and record["candidate_commit_allowed"] is False


def test_core_record_card_binding_error(state_dir, monkeypatch, verdicts) -> None:
    port = Port(answer={})
    svc = _core_service(state_dir, port, monkeypatch, card_error="CARD_HASH_MISMATCH: edited")
    record = svc._build_terminal_core_record(_terminal_state(), contract=CONTRACT)
    _failed(record, "CARD_HASH_MISMATCH")
    assert port.calls == []
    assert record["core_verdict"] == {
        "blocking": True,
        "transport_error": "CORE_TERMINAL_RECORD_FAILED:CARD_HASH_MISMATCH",
    }


@pytest.mark.parametrize(
    "port, code",
    [
        (None, "AMBIENT_CORE_CONTROL_PORT_REQUIRED"),
        (object(), "AMBIENT_CORE_TERMINAL_RECORD_UNSUPPORTED"),
        (
            SimpleNamespace(record_terminal_not_covered="not callable"),
            "AMBIENT_CORE_TERMINAL_RECORD_UNSUPPORTED",
        ),
    ],
    ids=["none", "no-recorder", "not-callable"],
)
def test_core_record_port_refusals(state_dir, monkeypatch, verdicts, port, code) -> None:
    svc = _core_service(state_dir, port, monkeypatch)
    _failed(svc._build_terminal_core_record(_terminal_state(), contract=CONTRACT), code)


def test_core_record_non_blocking_answer(state_dir, monkeypatch) -> None:
    builder = VerdictBuilder({**MISSING_VERDICT, "blocking": False})
    monkeypatch.setattr(service_module, "build_core_verdict", builder)
    record = _core_service(state_dir, Port(answer={}), monkeypatch)._build_terminal_core_record(
        _terminal_state(), contract=CONTRACT
    )
    _failed(record, "CORE_TERMINAL_RECORD_NOT_BLOCKING")
    assert (
        record["core_verdict"]["transport_error"]
        == "CORE_TERMINAL_RECORD_FAILED:CORE_TERMINAL_RECORD_NOT_BLOCKING"
    )


def test_core_record_unexpected_host_reason_keeps_the_verdict(state_dir, monkeypatch) -> None:
    verdict = {
        **MISSING_VERDICT,
        "host_reason_codes": ["CORE_COVERAGE_INCOMPLETE", "CORE_PROVENANCE_NOT_PINNED:x", "OTHER"],
    }
    builder = VerdictBuilder(verdict)
    monkeypatch.setattr(service_module, "build_core_verdict", builder)
    record = _core_service(state_dir, Port(answer={}), monkeypatch)._build_terminal_core_record(
        _terminal_state(), contract=CONTRACT
    )
    _failed(record, "CORE_PROVENANCE_NOT_PINNED")
    assert record["core_verdict"] == verdict and len(builder.calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"core_status": "FAILED_VERIFICATION"},
        {"integrity": "VALID"},
        {"reason_codes": ["CANDIDATE_MISSING"]},
        {"reason_codes": None},
        {"host_reason_codes": ["CORE_COVERAGE_INCOMPLETE"]},
    ],
    ids=["status", "integrity", "reason", "no-reasons", "host-reason"],
)
def test_core_record_not_missing(state_dir, monkeypatch, change) -> None:
    verdict = {**MISSING_VERDICT, **change}
    monkeypatch.setattr(service_module, "build_core_verdict", VerdictBuilder(verdict))
    record = _core_service(state_dir, Port(answer={}), monkeypatch)._build_terminal_core_record(
        _terminal_state(), contract=CONTRACT
    )
    _failed(record, "CORE_TERMINAL_RECORD_NOT_MISSING")
    assert record["core_verdict"] == verdict


@pytest.mark.parametrize(
    "error, code",
    [
        (RuntimeError("BOOM: core exploded"), "BOOM"),
        (RuntimeError(""), "RuntimeError"),
        (KeyError("k"), "'k'"),
        (ValueError("  : leading colon"), "ValueError"),
    ],
    ids=["code", "empty", "keyerror", "blank-code"],
)
def test_core_record_port_error_codes(state_dir, monkeypatch, verdicts, error, code) -> None:
    record = _core_service(state_dir, Port(error=error), monkeypatch)._build_terminal_core_record(
        _terminal_state(), contract=CONTRACT
    )
    _failed(record, code)
    assert verdicts.calls[-1]["transport_error"] == f"CORE_TERMINAL_RECORD_FAILED:{code}"


def test_core_record_verdict_builder_failure_leaves_no_verdict(state_dir, monkeypatch) -> None:
    builder = VerdictBuilder(transport_error=RuntimeError("verdict"))
    monkeypatch.setattr(service_module, "build_core_verdict", builder)
    record = _core_service(
        state_dir, Port(error=RuntimeError("X")), monkeypatch
    )._build_terminal_core_record(_terminal_state(), contract=CONTRACT)
    _failed(record, "X")
    assert record["core_verdict"] is None


def test_core_record_with_the_real_verdict_builder(state_dir, monkeypatch) -> None:
    # The real build_core_verdict on a transport failure: fail closed and blocking.
    record = _core_service(
        state_dir, Port(error=RuntimeError("DOWN")), monkeypatch
    )._build_terminal_core_record(_terminal_state(), contract=CONTRACT)
    _failed(record, "DOWN")
    assert record["core_verdict"]["blocking"] is True


# ---------------------------------------------------------------------------
# _record_terminal_core_not_covered


def _recording_service(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch, record: Any
) -> tuple[SelfHostedTaskService, list[Any]]:
    svc = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    built: list[Any] = []
    monkeypatch.setattr(
        svc, "_build_terminal_core_record", lambda state: (built.append(dict(state)), record)[1]
    )
    return svc, built


RECORD = {"attempt_id": "attempt-1", "record_status": "RECORDED", "pair": (1, 2)}


def test_record_attach_persists_the_jsonable_record(state_dir, monkeypatch) -> None:
    svc, built = _recording_service(state_dir, monkeypatch, RECORD)
    state = svc._write_state("t", _terminal_state())
    assert svc._record_terminal_core_not_covered("t", state) is None
    assert len(built) == 1
    assert _read(state_dir)["terminal_core_record"] == {
        "attempt_id": "attempt-1",
        "record_status": "RECORDED",
        "pair": [1, 2],
    }


@pytest.mark.parametrize("state", [None, "x", ["a"], 7])
def test_record_ignores_a_non_mapping_state(state_dir, monkeypatch, state) -> None:
    svc, built = _recording_service(state_dir, monkeypatch, RECORD)
    assert svc._record_terminal_core_not_covered("t", state) is None
    assert built == [] and _disk(state_dir) == {}


@pytest.mark.parametrize(
    "existing, rebuilt",
    [
        ({"attempt_id": "attempt-1", "record_status": "RECORDED"}, False),
        ({"attempt_id": "attempt-0", "record_status": "RECORDED"}, True),
        ({"attempt_id": "attempt-1", "record_status": "FAILED"}, True),
        ("RECORDED", True),
    ],
    ids=["recorded", "other-attempt", "failed", "not-mapping"],
)
def test_record_retries_only_when_not_recorded(state_dir, monkeypatch, existing, rebuilt) -> None:
    svc, built = _recording_service(state_dir, monkeypatch, None)
    svc._record_terminal_core_not_covered("t", _terminal_state(terminal_core_record=existing))
    assert bool(built) is rebuilt


def test_record_none_writes_nothing(state_dir, monkeypatch, events) -> None:
    svc, built = _recording_service(state_dir, monkeypatch, None)
    svc._write_state("t", _terminal_state())
    before = _disk(state_dir)
    recorder = Recorder(monkeypatch, events)
    svc._record_terminal_core_not_covered("t", _terminal_state())
    assert _disk(state_dir) == before and len(built) == 1
    assert "_mutate_state" not in recorder.names()


@pytest.mark.parametrize(
    "current",
    [
        {"attempt_id": "attempt-2"},
        {"status": "WORKER_RUNNING"},
        {"verified_receipt": {"verified": False}},
        {
            "terminal_core_record": {
                "attempt_id": "attempt-1",
                "record_status": "RECORDED",
                "kept": True,
            }
        },
    ],
    ids=["attempt-changed", "status-changed", "receipt-appeared", "already-recorded"],
)
def test_record_attach_refusals_leave_the_state(state_dir, monkeypatch, current) -> None:
    svc, _ = _recording_service(state_dir, monkeypatch, RECORD)
    svc._write_state("t", _terminal_state(**current))
    before = _read(state_dir)
    svc._record_terminal_core_not_covered("t", _terminal_state())
    assert _read(state_dir) == before


def test_record_attach_replaces_a_failed_record(state_dir, monkeypatch) -> None:
    svc, _ = _recording_service(state_dir, monkeypatch, RECORD)
    svc._write_state(
        "t",
        _terminal_state(
            terminal_core_record={"attempt_id": "attempt-1", "record_status": "FAILED"}
        ),
    )
    svc._record_terminal_core_not_covered("t", _terminal_state())
    assert _read(state_dir)["terminal_core_record"]["record_status"] == "RECORDED"


def test_record_attach_runs_under_the_lock(state_dir, monkeypatch) -> None:
    svc, _ = _recording_service(state_dir, monkeypatch, RECORD)
    svc._write_state("t", _terminal_state())
    seen: list[bool] = []
    real_jsonable = service_module._jsonable

    def jsonable(value: Any) -> Any:
        if isinstance(value, dict) and value.get("pair") == (1, 2):
            seen.append(_lock_held(state_dir))
        return real_jsonable(value)

    monkeypatch.setattr(service_module, "_jsonable", jsonable)
    svc._record_terminal_core_not_covered("t", _terminal_state())
    assert seen == [True]


@pytest.mark.parametrize("where", ["build", "mutate"])
def test_record_failure_is_logged_on_the_facade_logger_and_swallowed(
    state_dir, monkeypatch, caplog, where
) -> None:
    svc = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)

    def explode(*args: Any, **kwargs: Any) -> Any:
        raise LookupError("secret detail")

    if where == "build":
        monkeypatch.setattr(svc, "_build_terminal_core_record", explode)
    else:
        monkeypatch.setattr(svc, "_build_terminal_core_record", lambda state: RECORD)
        monkeypatch.setattr(svc, "_mutate_state", explode)
    with caplog.at_level(logging.WARNING, logger=FACADE_LOGGER):
        assert svc._record_terminal_core_not_covered("task-x", _terminal_state()) is None
    rows = [(r.name, r.levelno, r.msg, r.args) for r in caplog.records]
    assert rows == [
        (
            FACADE_LOGGER,
            logging.WARNING,
            "terminal Core record for %s not persisted: %s",
            ("task-x", "LookupError"),
        )
    ]
    assert "secret detail" not in caplog.text


def test_record_base_exception_is_not_swallowed(state_dir, monkeypatch) -> None:
    svc = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)

    def interrupt(state: Any) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr(svc, "_build_terminal_core_record", interrupt)
    with pytest.raises(KeyboardInterrupt):
        svc._record_terminal_core_not_covered("t", _terminal_state())


# ---------------------------------------------------------------------------
# _heartbeat / _touch_owned_state


class FakeStop:
    def __init__(self, beats: int) -> None:
        self.beats = beats
        self.waits: list[float] = []

    def wait(self, timeout: float) -> bool:
        self.waits.append(timeout)
        return len(self.waits) > self.beats


def test_heartbeat_touches_until_stopped(service, state_dir, events, monkeypatch) -> None:
    _seed(service, heartbeat_at="old", updated_at="old")
    recorder = Recorder(monkeypatch, events)
    stop = FakeStop(beats=2)
    assert service._heartbeat("t", "attempt-1", stop) is None  # type: ignore[arg-type]
    assert stop.waits == [1.0, 1.0, 1.0]
    assert recorder.names() == [
        "_mutate_state",
        "lock+",
        "_touch_owned_state",
        "_utc_now",
        "lock-",
        "_mutate_state",
        "lock+",
        "_touch_owned_state",
        "_utc_now",
        "lock-",
    ]
    on_disk = _read(state_dir)
    assert on_disk["heartbeat_at"] == on_disk["updated_at"] == NOW


@pytest.mark.parametrize(
    "seed",
    [{"attempt_id": "attempt-2"}, {"status": TERMINAL}],
    ids=["other-attempt", "terminal"],
)
def test_heartbeat_ends_when_the_attempt_lost_ownership(service, state_dir, seed) -> None:
    _seed(service, **seed)
    before = _disk(state_dir)
    stop = FakeStop(beats=5)
    service._heartbeat("t", "attempt-1", stop)  # type: ignore[arg-type]
    assert stop.waits == [1.0]
    assert _disk(state_dir) == before


@pytest.mark.parametrize(
    "error",
    [OSError("io"), json.JSONDecodeError("bad", "{", 0), RuntimeError("x")],
    ids=["os", "json", "runtime"],
)
def test_heartbeat_ends_on_store_errors(service, monkeypatch, error) -> None:
    calls: list[str] = []

    def mutate(task_id: str, mutator: Any) -> Any:
        calls.append(task_id)
        raise error

    monkeypatch.setattr(service, "_mutate_state", mutate)
    stop = FakeStop(beats=5)
    service._heartbeat("t", "attempt-1", stop)  # type: ignore[arg-type]
    assert calls == ["t"] and stop.waits == [1.0]


def test_heartbeat_propagates_other_errors(service, monkeypatch) -> None:
    def mutate(task_id: str, mutator: Any) -> Any:
        raise ValueError("unexpected")

    monkeypatch.setattr(service, "_mutate_state", mutate)
    with pytest.raises(ValueError, match="^unexpected$"):
        service._heartbeat("t", "attempt-1", FakeStop(beats=5))  # type: ignore[arg-type]


def test_heartbeat_unknown_task_keeps_beating(service, state_dir) -> None:
    stop = FakeStop(beats=3)
    service._heartbeat("missing", "attempt-1", stop)  # type: ignore[arg-type]
    assert stop.waits == [1.0] * 4 and _disk(state_dir) == {}


def test_heartbeat_thread_stops_on_the_event(service, state_dir) -> None:
    _seed(service)
    stop = threading.Event()
    thread = threading.Thread(target=service._heartbeat, args=("t", "attempt-1", stop), daemon=True)
    thread.start()
    stop.set()
    thread.join(10)
    assert not thread.is_alive()


def test_touch_owned_state() -> None:
    state: dict[str, Any] = {"attempt_id": "a", "status": "WORKER_RUNNING", "x": 1}
    assert SelfHostedTaskService._touch_owned_state(state, "a") is None
    assert state == {
        "attempt_id": "a",
        "status": "WORKER_RUNNING",
        "x": 1,
        "heartbeat_at": NOW,
        "updated_at": NOW,
    }
    assert list(state)[-2:] == ["heartbeat_at", "updated_at"]


@pytest.mark.parametrize(
    "state",
    [
        {"attempt_id": "b", "status": "WORKER_RUNNING"},
        {"attempt_id": "a", "status": "CANCELLED"},
        {},
    ],
    ids=["other-attempt", "terminal", "empty"],
)
def test_touch_owned_state_refusals(state) -> None:
    before = dict(state)
    with pytest.raises(RuntimeError, match="^task is no longer owned by this attempt$"):
        SelfHostedTaskService._touch_owned_state(state, "a")
    assert state == before


def test_touch_owned_state_reads_the_clock_once(monkeypatch) -> None:
    ticks = iter(["t1", "t2"])
    monkeypatch.setattr(service_module, "_utc_now", lambda: next(ticks))
    state: dict[str, Any] = {"attempt_id": "a"}
    SelfHostedTaskService._touch_owned_state(state, "a")
    assert state["heartbeat_at"] == state["updated_at"] == "t1"


# ---------------------------------------------------------------------------
# late binding through the facade module


def test_late_terminal_statuses(service, state_dir, bus, monkeypatch, verdicts) -> None:
    monkeypatch.setattr(service_module, "TERMINAL_STATUSES", frozenset({"CUSTOM_END"}))
    recorded: list[str] = []
    _seed(service, attempts=[{"attempt_id": "attempt-1"}])
    with monkeypatch.context() as patch:
        patch.setattr(
            SelfHostedTaskService,
            "_record_terminal_core_not_covered",
            lambda self, task_id, state: recorded.append(state["status"]),
        )
        service._checkpoint("t", TERMINAL)  # not terminal under the patched set
        mid = _read(state_dir)
        assert "worker_finished_at" not in mid and "finished_at" not in mid["attempts"][0]
        service._checkpoint("t", "CUSTOM_END")
    on_disk = _read(state_dir)
    assert on_disk["worker_finished_at"] == NOW and on_disk["attempts"][0]["finished_at"] == NOW
    assert recorded == ["CUSTOM_END"]
    with pytest.raises(RuntimeError):
        SelfHostedTaskService._touch_owned_state({"attempt_id": "a", "status": "CUSTOM_END"}, "a")
    SelfHostedTaskService._touch_owned_state({"attempt_id": "a", "status": TERMINAL}, "a")
    svc = _core_service(state_dir, Port(answer={}), monkeypatch)
    assert svc._build_terminal_core_record(_terminal_state(), contract=CONTRACT) is None
    assert (
        svc._build_terminal_core_record(_terminal_state(status="CUSTOM_END"), contract=CONTRACT)
        is not None
    )


def test_late_jsonable_and_parse_time(service, state_dir, bus, monkeypatch) -> None:
    calls: list[Any] = []
    real_jsonable = service_module._jsonable

    def jsonable(value: Any) -> Any:
        if value == {"marker": 1}:
            calls.append("jsonable")
            return {**real_jsonable(value), "via": "facade"}
        return real_jsonable(value)

    parsed: list[Any] = []
    monkeypatch.setattr(service_module, "_jsonable", jsonable)
    monkeypatch.setattr(
        service_module, "_parse_time", lambda value: (parsed.append(value), 100.0)[1]
    )
    monkeypatch.setattr(service_module, "time", SimpleNamespace(time=lambda: 101.5))
    _seed(service, submitted_at="S", worker_started_at="W")
    service._checkpoint("t", "WORKER_RUNNING", {"marker": 1})
    on_disk = _read(state_dir)
    assert calls == ["jsonable"] and on_disk["via"] == "facade"
    assert parsed == ["S", "W"]
    assert (
        on_disk["telemetry"]["wall_time_ms"] == 1500
        and on_disk["telemetry"]["worker_wall_time_ms"] == 1500
    )


def test_late_utc_now_and_mapping(service, state_dir, bus, monkeypatch) -> None:
    monkeypatch.setattr(service_module, "_utc_now", lambda: "LATE-NOW")
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        service_module,
        "build_runtime_development_mapping",
        lambda **kw: (seen.append(kw), {"late": True})[1],
    )
    _seed(service)
    service._checkpoint("t", "WORKER_RUNNING")
    on_disk = _read(state_dir)
    assert on_disk["updated_at"] == "LATE-NOW" and on_disk["runtime_development_mapping"] == {
        "late": True
    }
    assert sorted(seen[0]) == sorted([
        "task_id",
        "attempt_id",
        "action_id",
        "runtime_phase",
        "runtime_terminal_state",
        "development_status",
        "runtime_success",
        "candidate_status",
        "candidate_accepted",
        "integration_status",
        "integrated",
        "runtime_receipt_ref",
        "development_receipt_ref",
    ])
    state: dict[str, Any] = {"attempt_id": "a"}
    SelfHostedTaskService._touch_owned_state(state, "a")
    assert state["heartbeat_at"] == "LATE-NOW"


def test_late_build_core_verdict_reaches_both_sites(state_dir, monkeypatch) -> None:
    builder = VerdictBuilder()
    monkeypatch.setattr(service_module, "build_core_verdict", builder)
    svc = _core_service(state_dir, Port(answer={"p": 1}), monkeypatch)
    svc._build_terminal_core_record(_terminal_state(), contract=CONTRACT)
    svc = _core_service(state_dir, None, monkeypatch)
    svc._build_terminal_core_record(_terminal_state(), contract=CONTRACT)
    assert builder.calls == [
        {"projection": {"p": 1}, "transport_error": None},
        {
            "projection": None,
            "transport_error": "CORE_TERMINAL_RECORD_FAILED:AMBIENT_CORE_CONTROL_PORT_REQUIRED",
        },
    ]


def test_late_logger_name_follows_the_facade_module_name(state_dir, monkeypatch, caplog) -> None:
    monkeypatch.setattr(service_module, "__name__", "nexus.s8a.renamed")
    svc = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    monkeypatch.setattr(svc, "_build_terminal_core_record", lambda state: 1 / 0)
    with caplog.at_level(logging.WARNING):
        svc._record_terminal_core_not_covered("t", _terminal_state())
    assert [r.name for r in caplog.records] == ["nexus.s8a.renamed"]


def test_instance_and_class_patches_are_reached(service, state_dir, bus, monkeypatch) -> None:
    _seed(service)
    calls: list[str] = []
    real_mutate = service._mutate_state
    monkeypatch.setattr(
        service,
        "_mutate_state",
        lambda t, f: (calls.append("instance-mutate"), real_mutate(t, f))[1],
    )
    real_emit = inspect.getattr_static(SelfHostedTaskService, "_emit_bound_attempt_transition")
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_emit_bound_attempt_transition",
        lambda self, result, task_id: (
            calls.append("class-emit"),
            real_emit(self, result, task_id),
        )[1],
    )
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_record_terminal_core_not_covered",
        lambda self, task_id, state: calls.append("class-record"),
    )
    service._checkpoint("t", TERMINAL)
    assert calls == ["instance-mutate", "class-emit", "class-record"]


def test_class_patch_of_touch_owned_state_reaches_the_heartbeat(
    service, state_dir, monkeypatch
) -> None:
    _seed(service)
    touched: list[str] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_touch_owned_state",
        staticmethod(lambda state, attempt_id: touched.append(attempt_id)),
    )
    service._heartbeat("t", "attempt-1", FakeStop(beats=1))  # type: ignore[arg-type]
    assert touched == ["attempt-1"]


def test_subclass_overrides_are_dispatched_through_self(state_dir, bus) -> None:
    class Sub(SelfHostedTaskService):
        def _build_terminal_core_record(self, state: Any, *, contract: Any = None) -> Any:
            return {"attempt_id": "attempt-1", "record_status": "SUB"}

    svc = Sub(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    svc._write_state("t", _terminal_state(status="WORKER_RUNNING"))
    svc._checkpoint("t", TERMINAL)
    assert _read(state_dir)["terminal_core_record"] == {
        "attempt_id": "attempt-1",
        "record_status": "SUB",
    }


def test_no_files_besides_the_state_and_the_lock(service, state_dir, bus) -> None:
    _seed(service)
    service._checkpoint("t", "WORKER_RUNNING")
    service._checkpoint("t", TERMINAL)
    names = sorted(p.name for p in state_dir.rglob("*"))
    assert names == [".state.lock", "t.json"]
    assert not any(name.endswith(".tmp") for name in os.listdir(state_dir))
