"""Characterization of the events / continuity cluster of ``SelfHostedTaskService`` (split S3).

Big-file split step S3 moves the attempt-event and continuity methods out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin.  These tests pin the
behaviour before the move and must pass unchanged after it:

* ``_emit_attempt_transition``: the early returns, the order "sequence first, then
  validation, then build, then emit", every continuity-type / continuity-list / identity
  fallback and each fail-closed message;
* ``_emit_bound_attempt_transition`` / ``_record_event_append_failure``: the EventBus bind
  for non-ephemeral services, and that an append failure is persisted as reconciliation
  debt (under the state lock, without another event) before the error is re-raised;
* ``read_canonical_attempt_events`` / ``read_canonical_attempt_continuity``: the read-only
  bind, the store-path sync, the filter and its fail-closed errors;
* ``rehydrate_task_continuation`` / ``rehydrate_project_entry`` /
  ``rehydrate_task_continuation_snapshot``: every denial path (malformed state, work
  claim, attempt id, project-entry selector / request hash / authority duplicates), the
  ephemeral vs canonical read path, and that rehydration never writes state;
* ``_record_direct_failure`` / ``record_canonical_action_failure`` / ``_request_hash``;
* that every facade-module name the code reads (``NexusEventBus``,
  ``build_attempt_transition_event``, ``events_from_attempt_records``, ``project``,
  ``build_rehydration_projection``, ``canonical_request_hash``, ``_utc_now``,
  ``_validated_action_request``, ``_validate_project_entry_authority_binding``,
  ``_reject_unbound_project_entry_authority_hints``, ``SelfHostedTaskService``) is still
  resolved through the facade at call time, so patches on the facade keep taking effect.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, Iterator

import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.contracts.lifecycle_action import canonical_request_hash
from nexus.events.transport import NexusEventBus
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

FIXED_NOW = "2026-10-17T00:00:00+00:00"

EVENTS_MEMBERS = {
    "_record_event_append_failure": (
        "function",
        "(self, task_id: 'str', error: 'Exception') -> 'None'",
    ),
    "_emit_bound_attempt_transition": (
        "function",
        "(self, result: 'Optional[Mapping[str, Any]]', task_id: 'str') -> 'None'",
    ),
    "_emit_attempt_transition": (
        "staticmethod",
        "(result: 'Optional[Mapping[str, Any]]', task_id: 'str') -> 'None'",
    ),
    "read_canonical_attempt_events": (
        "staticmethod",
        "(task_id: 'str', attempt_id: 'str', *, project_root: 'Optional[Path]' = None)"
        " -> 'list[dict[str, Any]]'",
    ),
    "read_canonical_attempt_continuity": (
        "staticmethod",
        "(task_id: 'str', attempt_id: 'str') -> 'list[Any]'",
    ),
    "rehydrate_task_continuation": (
        "function",
        "(self, task_id: 'str', attempt_id: 'Optional[str]' = None, *, _project_entry: 'bool' = False,"
        " _state: 'Mapping[str, Any] | None' = None, _project_entry_repository: 'str | None' = None,"
        " _project_entry_issue: 'int | None' = None) -> 'dict[str, Any]'",
    ),
    "rehydrate_project_entry": (
        "function",
        "(self, task_id: 'str', attempt_id: 'Optional[str]', *, repository: 'str', issue_number: 'int')"
        " -> 'dict[str, Any]'",
    ),
    "rehydrate_task_continuation_snapshot": (
        "classmethod",
        "(task_state: 'Mapping[str, Any]', attempt_continuity_events: 'Iterable[Any]', *,"
        " attempt_id: 'Optional[str]' = None) -> 'dict[str, Any]'",
    ),
    "_request_hash": ("staticmethod", "(request: 'Mapping[str, Any]') -> 'str'"),
    "_record_direct_failure": (
        "function",
        "(self, task_id: 'str', blocker: 'str', error: 'str' = '') -> 'Optional[dict[str, Any]]'",
    ),
    "record_canonical_action_failure": (
        "function",
        "(self, task_id: 'str', blocker: 'str', error: 'str' = '') -> 'Optional[dict[str, Any]]'",
    ),
}

IO_EVENTS = (
    "lock+",
    "lock-",
    "_read_state",
    "_read_state_snapshot",
    "_write_state_locked",
    "_mutate_state",
)

BUILD_KWARGS = (
    "task_id",
    "attempt_id",
    "sequence",
    "state",
    "reason",
    "action",
    "observation",
    "continuity_event_type",
    "strategy_delta",
    "do_not_repeat",
    "unresolved_risks",
    "unknowns",
    "next_action",
    "claim_ceiling",
    "candidate_refs",
    "evidence_refs",
    "source_revision",
    "contract_revision",
)


# ---------------------------------------------------------------------------
# helpers


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def service(state_dir: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)


@pytest.fixture
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(service_module, "_utc_now", lambda: FIXED_NOW)
    return FIXED_NOW


def _seed(service: SelfHostedTaskService, task_id: str, **extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "task_id": task_id,
        "attempt_id": "attempt-1",
        "status": "WORKER_RUNNING",
    }
    state.update(extra)
    return service._write_state(task_id, state)


def _disk_bytes(state_dir: Path) -> dict[str, str]:
    if not state_dir.exists():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(state_dir.rglob("*"))
        if path.is_file() and path.name != ".state.lock"
    }


class Recorder:
    """Class-level recording probes for the state lock, state I/O and the cluster's own hops."""

    FUNCTIONS = (
        "_read_state",
        "_read_state_snapshot",
        "_write_state_locked",
        "_mutate_state",
        "_record_event_append_failure",
        "_emit_bound_attempt_transition",
    )

    def __init__(self, monkeypatch: pytest.MonkeyPatch, events: list[Any] | None = None) -> None:
        self.events: list[Any] = events if events is not None else []
        cls = SelfHostedTaskService
        lock = inspect.getattr_static(cls, "_state_lock")
        recorded = self.events

        @contextmanager
        def state_lock(self: Any) -> Iterator[None]:
            recorded.append("lock+")
            with lock(self):
                yield
            recorded.append("lock-")

        monkeypatch.setattr(cls, "_state_lock", state_lock)
        for name in self.FUNCTIONS:
            monkeypatch.setattr(cls, name, self._wrap(name, getattr(cls, name)))

    def _wrap(self, name: str, func: Any) -> Any:
        recorded = self.events

        def wrapped(self_: Any, *args: Any, **kwargs: Any) -> Any:
            recorded.append(name)
            return func(self_, *args, **kwargs)

        return wrapped

    def io(self) -> list[str]:
        return [event for event in self.events if isinstance(event, str) and event in IO_EVENTS]

    def names(self) -> list[str]:
        return [event if isinstance(event, str) else event[0] for event in self.events]


class FakeLogStore:
    _events: list[Any]
    _records: list[Any]
    _error: Exception | None
    event_log_path: Path

    def __init__(
        self, events: list[Any], records: list[Any], *, error: Exception | None = None
    ) -> None:
        object.__setattr__(self, "_events", events)
        object.__setattr__(self, "_records", records)
        object.__setattr__(self, "_error", error)
        object.__setattr__(self, "event_log_path", Path("/store/path"))

    def __setattr__(self, name: str, value: Any) -> None:
        self._events.append(("store.set", name, value))
        object.__setattr__(self, name, value)

    def read_recent(self, **kwargs: Any) -> list[Any]:
        self._events.append(("store.read_recent", kwargs))
        if self._error is not None:
            raise self._error
        return list(self._records)


class FakeBus:
    """Replacement for the facade's ``NexusEventBus`` binding (patched on the facade module)."""

    def __init__(
        self,
        events: list[Any],
        *,
        sequence: int = 7,
        records: list[Any] | None = None,
        ensure_error: Exception | None = None,
        emit_error: Exception | None = None,
        sequence_error: Exception | None = None,
        read_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.sequence = sequence
        self.ensure_error = ensure_error
        self.emit_error = emit_error
        self.sequence_error = sequence_error
        self._event_log_path = Path("/bus/path")
        self._log_store = FakeLogStore(events, records or [], error=read_error)

    def ensure_configured(self, project_root: Path, *, production: bool = False) -> None:
        self.events.append(("bus.ensure_configured", project_root, production))
        if self.ensure_error is not None:
            raise self.ensure_error

    def configure(
        self, project_root: Path, *, create: bool = True, production: bool = False
    ) -> None:
        self.events.append(("bus.configure", project_root, create, production))

    def next_attempt_sequence(self, task_id: str, attempt_id: str) -> int:
        self.events.append(("bus.next_attempt_sequence", task_id, attempt_id))
        if self.sequence_error is not None:
            raise self.sequence_error
        return self.sequence

    def emit_attempt_transition(self, event: Any) -> dict[str, Any]:
        self.events.append(("bus.emit_attempt_transition", event))
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
def builder(monkeypatch: pytest.MonkeyPatch, events: list[Any]) -> list[dict[str, Any]]:
    """Record ``build_attempt_transition_event`` kwargs through the facade binding."""
    built: list[dict[str, Any]] = []

    def build(**kwargs: Any) -> Any:
        built.append(kwargs)
        events.append(("build", kwargs["task_id"], kwargs["attempt_id"]))
        return SimpleNamespace(built=len(built))

    monkeypatch.setattr(service_module, "build_attempt_transition_event", build)
    return built


def _emit(result: Any, task_id: str = "arg-task") -> None:
    SelfHostedTaskService._emit_attempt_transition(result, task_id)


@pytest.fixture
def real_bus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Bind the real EventBus to a tmp root; conftest restores the binding attributes."""
    root = tmp_path / "events-root"
    monkeypatch.setattr(NexusEventBus, "_attempt_sequences", {})
    monkeypatch.setattr(
        NexusEventBus._log_store, "event_log_path", NexusEventBus._log_store.event_log_path
    )
    monkeypatch.setattr(NexusEventBus._log_store, "lock_path", NexusEventBus._log_store.lock_path)
    monkeypatch.setattr(NexusEventBus, "_production_event_root", None, raising=False)
    NexusEventBus.configure(root)
    return root


# ---------------------------------------------------------------------------
# member table


def test_events_members_keep_descriptor_kinds_and_signatures() -> None:
    for name, (kind, signature) in EVENTS_MEMBERS.items():
        static = inspect.getattr_static(SelfHostedTaskService, name)
        assert type(static).__name__ == kind, name
        func = static.__func__ if isinstance(static, (staticmethod, classmethod)) else static
        assert str(inspect.signature(func)).replace("cls, ", "") == signature, name


# ---------------------------------------------------------------------------
# _request_hash


def test_request_hash_is_sorted_compact_utf8_json_sha256() -> None:
    request = {"b": 1, "a": "é", "c": [1, {"z": None, "y": True}]}
    text = '{"a":"é","b":1,"c":[1,{"y":true,"z":null}]}'
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert SelfHostedTaskService._request_hash(request) == expected
    assert SelfHostedTaskService._request_hash(MappingProxyType(request)) == expected


def test_request_hash_differs_from_canonical_request_hash_and_rejects_unserializable() -> None:
    request = {"task_id": "t", "issue": 1}
    assert (
        SelfHostedTaskService._request_hash(request)
        == hashlib.sha256(b'{"issue":1,"task_id":"t"}').hexdigest()
    )
    with pytest.raises(TypeError):
        SelfHostedTaskService._request_hash({"x": object()})


# ---------------------------------------------------------------------------
# _record_event_append_failure


def test_record_event_append_failure_persists_debt_under_lock_without_event(
    monkeypatch: pytest.MonkeyPatch,
    service: SelfHostedTaskService,
    fixed_now: str,
    bus: FakeBus,
    events: list[Any],
) -> None:
    _seed(service, "t", keep="me")
    recorder = Recorder(monkeypatch)
    error = OSError("disk full")
    assert service._record_event_append_failure("t", error) is None
    state = service._read_state_snapshot("t")
    assert state is not None
    assert state["keep"] == "me" and state["status"] == "WORKER_RUNNING"
    assert state["event_reconciliation_required"] is True
    assert state["event_append_failure"] == {
        "status": "BLOCKED",
        "error_type": "OSError",
        "error_sha256": hashlib.sha256(b"disk full").hexdigest(),
        "at": FIXED_NOW,
    }
    assert state["updated_at"] == FIXED_NOW
    assert recorder.io()[:3] == ["_mutate_state", "lock+", "lock-"]
    assert events == []  # no event, no bind


def test_record_event_append_failure_overwrites_previous_debt(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, "t", event_append_failure={"status": "OLD"}, event_reconciliation_required=False)
    monkeypatch.setattr(service_module, "_utc_now", lambda: "T1")
    service._record_event_append_failure("t", ValueError(""))
    state = service._read_state_snapshot("t")
    assert state is not None
    assert state["event_append_failure"] == {
        "status": "BLOCKED",
        "error_type": "ValueError",
        "error_sha256": hashlib.sha256(b"").hexdigest(),
        "at": "T1",
    }
    assert state["event_reconciliation_required"] is True


def test_record_event_append_failure_on_missing_task_writes_nothing(
    service: SelfHostedTaskService, state_dir: Path, fixed_now: str
) -> None:
    before = _disk_bytes(state_dir)
    assert service._record_event_append_failure("missing", RuntimeError("x")) is None
    assert service._read_state_snapshot("missing") is None
    assert _disk_bytes(state_dir) == before


# ---------------------------------------------------------------------------
# _emit_bound_attempt_transition


def _probe_emit(
    monkeypatch: pytest.MonkeyPatch, events: list[Any], error: Exception | None = None
) -> None:
    def emit(result: Any, task_id: str) -> None:
        events.append(("emit", result, task_id))
        if error is not None:
            raise error

    monkeypatch.setattr(SelfHostedTaskService, "_emit_attempt_transition", staticmethod(emit))


def test_emit_bound_ephemeral_skips_bind_and_emits(
    monkeypatch: pytest.MonkeyPatch, service: SelfHostedTaskService, bus: FakeBus, events: list[Any]
) -> None:
    _probe_emit(monkeypatch, events)
    result = {"attempt_id": "a"}
    assert service._emit_bound_attempt_transition(result, "t") is None
    assert events == [("emit", result, "t")]


def test_emit_bound_non_ephemeral_binds_canonical_root_for_production_first(
    monkeypatch: pytest.MonkeyPatch,
    service: SelfHostedTaskService,
    bus: FakeBus,
    events: list[Any],
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical"
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(canonical))
    monkeypatch.setattr(service, "ephemeral", False)
    _probe_emit(monkeypatch, events)
    service._emit_bound_attempt_transition(None, "t")
    assert events == [("bus.ensure_configured", canonical.resolve(), True), ("emit", None, "t")]


def test_emit_bound_bind_failure_records_debt_and_reraises_same_error(
    monkeypatch: pytest.MonkeyPatch,
    service: SelfHostedTaskService,
    events: list[Any],
    tmp_path: Path,
) -> None:
    error = RuntimeError("conflicting production event root")
    monkeypatch.setattr(service_module, "NexusEventBus", FakeBus(events, ensure_error=error))
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(tmp_path / "c"))
    monkeypatch.setattr(service, "ephemeral", False)
    _probe_emit(monkeypatch, events)
    recorded: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_record_event_append_failure",
        lambda self, task_id, exc: recorded.append((task_id, exc)),
    )
    with pytest.raises(RuntimeError) as info:
        service._emit_bound_attempt_transition({"attempt_id": "a"}, "t")
    assert info.value is error
    assert recorded == [("t", error)]
    assert [e[0] for e in events] == ["bus.ensure_configured"]  # emit never reached


def test_emit_bound_emit_failure_persists_debt_then_reraises(
    monkeypatch: pytest.MonkeyPatch,
    service: SelfHostedTaskService,
    bus: FakeBus,
    events: list[Any],
    fixed_now: str,
) -> None:
    _seed(service, "t")
    error = ValueError("attempt transition sequence must be contiguous")
    _probe_emit(monkeypatch, events, error)
    recorder = Recorder(monkeypatch, events)
    with pytest.raises(ValueError) as info:
        service._emit_bound_attempt_transition({"attempt_id": "a"}, "t")
    assert info.value is error
    assert recorder.names() == [
        "_emit_bound_attempt_transition",
        "emit",
        "_record_event_append_failure",
        "_mutate_state",
        "lock+",
        "lock-",
    ]
    state = service._read_state_snapshot("t")
    assert state is not None
    assert state["event_reconciliation_required"] is True
    assert state["event_append_failure"]["error_type"] == "ValueError"


def test_emit_bound_debt_write_failure_surfaces_with_original_as_context(
    monkeypatch: pytest.MonkeyPatch, service: SelfHostedTaskService, bus: FakeBus, events: list[Any]
) -> None:
    original = OSError("append")
    _probe_emit(monkeypatch, events, original)
    secondary = RuntimeError("state write failed")

    def fail(self: Any, task_id: str, exc: Exception) -> None:
        raise secondary

    monkeypatch.setattr(SelfHostedTaskService, "_record_event_append_failure", fail)
    with pytest.raises(RuntimeError) as info:
        service._emit_bound_attempt_transition({"attempt_id": "a"}, "t")
    assert info.value is secondary
    assert info.value.__context__ is original


# ---------------------------------------------------------------------------
# _emit_attempt_transition


@pytest.mark.parametrize(
    "result", [None, {}, {"attempt_id": ""}, {"attempt_id": None, "task_id": "t"}, {"status": "X"}]
)
def test_emit_returns_early_without_attempt_id(
    result: Any, bus: FakeBus, builder: list[Any], events: list[Any]
) -> None:
    assert _emit(result) is None
    assert events == [] and builder == []


def test_emit_minimal_result_uses_defaults(
    bus: FakeBus, builder: list[dict[str, Any]], events: list[Any]
) -> None:
    _emit({"attempt_id": 5})
    assert [e[0] for e in events] == [
        "bus.next_attempt_sequence",
        "build",
        "bus.emit_attempt_transition",
    ]
    assert events[0] == ("bus.next_attempt_sequence", "arg-task", "5")
    assert events[2][1] == SimpleNamespace(built=1)
    (kwargs,) = builder
    assert tuple(kwargs) == BUILD_KWARGS
    assert kwargs == {
        "task_id": "arg-task",
        "attempt_id": "5",
        "sequence": 7,
        "state": "None",
        "reason": "",
        "action": "",
        "observation": "",
        "continuity_event_type": "OBSERVATION_RECORDED",
        "strategy_delta": "",
        "do_not_repeat": (),
        "unresolved_risks": (),
        "unknowns": (),
        "next_action": "",
        "claim_ceiling": "",
        "candidate_refs": (),
        "evidence_refs": (),
        "source_revision": "unknown",
        "contract_revision": "unknown",
    }


def test_emit_full_result_fields_win_over_request(
    bus: FakeBus, builder: list[dict[str, Any]], events: list[Any]
) -> None:
    result = {
        "task_id": "res-task",
        "attempt_id": "a1",
        "status": "VERIFIED",
        "error": "err",
        "reason": "ignored-because-error",
        "action": "act",
        "observation": "obs",
        "strategy_delta": "delta",
        "next_action": "next",
        "claim_ceiling": "ceiling",
        "do_not_repeat": ["x", "y"],
        "unresolved_risks": ("r",),
        "unknowns": "u",
        "candidate_commit_sha": "c" * 40,
        "promotion_packet": {"candidate_tree_sha": "t" * 40},
        "verified_receipt_hash": "v" * 64,
        "verified_receipt": {"receipt_ref": "ref-1"},
        "source_revision": "src",
        "contract_revision": "con",
        "request": {
            "action": "req-act",
            "observation": "req-obs",
            "strategy_delta": "req-delta",
            "next_action": "req-next",
            "claim_ceiling": "req-ceiling",
            "do_not_repeat": ["req"],
            "unknowns": ["req"],
        },
    }
    _emit(result)
    assert events[0] == ("bus.next_attempt_sequence", "res-task", "a1")
    (kwargs,) = builder
    assert kwargs == {
        "task_id": "res-task",
        "attempt_id": "a1",
        "sequence": 7,
        "state": "VERIFIED",
        "reason": "err",
        "action": "act",
        "observation": "obs",
        "continuity_event_type": "OBSERVATION_RECORDED",
        "strategy_delta": "delta",
        "do_not_repeat": ("x", "y"),
        "unresolved_risks": ("r",),
        "unknowns": ("u",),
        "next_action": "next",
        "claim_ceiling": "ceiling",
        "candidate_refs": ("c" * 40, "t" * 40),
        "evidence_refs": ("v" * 64, "ref-1"),
        "source_revision": "src",
        "contract_revision": "con",
    }


def test_emit_request_fallbacks_and_reason(bus: FakeBus, builder: list[dict[str, Any]]) -> None:
    _emit({
        "attempt_id": "a1",
        "status": "RUNNING",
        "reason": "why",
        "promotion_packet": None,
        "verified_receipt": None,
        "request": {
            "action": "req-act",
            "observation": "req-obs",
            "strategy_delta": "req-delta",
            "next_action": "req-next",
            "claim_ceiling": "req-ceiling",
            "rejected_strategies": ["alias"],
            "unresolved_risks": "one",
            "unknowns": [],
            "source_revision": "req-src",
            "contract_hash": "req-hash",
        },
    })
    (kwargs,) = builder
    assert kwargs["reason"] == "why"
    assert (kwargs["action"], kwargs["observation"], kwargs["strategy_delta"]) == (
        "req-act",
        "req-obs",
        "req-delta",
    )
    assert (kwargs["next_action"], kwargs["claim_ceiling"]) == ("req-next", "req-ceiling")
    assert kwargs["do_not_repeat"] == ("alias",)
    assert kwargs["unresolved_risks"] == ("one",)
    assert kwargs["unknowns"] == ()
    assert kwargs["candidate_refs"] == () and kwargs["evidence_refs"] == ()
    assert kwargs["source_revision"] == "req-src"
    assert kwargs["contract_revision"] == "req-hash"


def test_emit_non_mapping_request_and_contract_are_ignored(
    bus: FakeBus, builder: list[dict[str, Any]]
) -> None:
    _emit({
        "attempt_id": "a",
        "request": ["action", "x"],
        "contract": "source_revision",
        "action": None,
    })
    (kwargs,) = builder
    assert kwargs["action"] == "" and kwargs["source_revision"] == "unknown"


def test_emit_refs_skip_falsy_values(bus: FakeBus, builder: list[dict[str, Any]]) -> None:
    _emit({
        "attempt_id": "a",
        "candidate_commit_sha": "",
        "promotion_packet": {"candidate_tree_sha": "tree"},
        "verified_receipt_hash": None,
        "verified_receipt": {"receipt_ref": 0},
    })
    (kwargs,) = builder
    assert kwargs["candidate_refs"] == ("tree",)
    assert kwargs["evidence_refs"] == ()


@pytest.mark.parametrize("status", ["REJECTED", "ATTEMPT_REJECTED"])
def test_emit_rejected_states_default_to_attempt_rejected(
    status: str, bus: FakeBus, builder: list[dict[str, Any]]
) -> None:
    _emit({"attempt_id": "a", "status": status})
    assert builder[0]["continuity_event_type"] == "ATTEMPT_REJECTED"
    assert builder[0]["state"] == status


def test_emit_explicit_type_from_result_wins_over_request(
    bus: FakeBus, builder: list[dict[str, Any]]
) -> None:
    _emit({
        "attempt_id": "a",
        "continuity_event_type": "STRATEGY_CHANGED",
        "request": {"continuity_event_type": "X"},
    })
    _emit({"attempt_id": "a", "request": {"continuity_event_type": "FROM_REQUEST"}})
    _emit({"attempt_id": "a", "status": "REJECTED", "continuity_event_type": "ATTEMPT_REJECTED"})
    _emit({
        "attempt_id": "a",
        "continuity_event_type": "",
        "request": {"continuity_event_type": "FALLBACK"},
    })
    assert [k["continuity_event_type"] for k in builder] == [
        "STRATEGY_CHANGED",
        "FROM_REQUEST",
        "ATTEMPT_REJECTED",
        "FALLBACK",
    ]


@pytest.mark.parametrize(
    ("result", "message"),
    [
        ({"continuity_event_type": "  "}, "continuity_event_type must be a non-empty string"),
        ({"continuity_event_type": 3}, "continuity_event_type must be a non-empty string"),
        (
            {"request": {"continuity_event_type": ["x"]}},
            "continuity_event_type must be a non-empty string",
        ),
        (
            {"status": "REJECTED", "continuity_event_type": "OBSERVATION_RECORDED"},
            "rejected state requires ATTEMPT_REJECTED continuity type",
        ),
        (
            {"status": "ATTEMPT_REJECTED", "request": {"continuity_event_type": "X"}},
            "rejected state requires ATTEMPT_REJECTED continuity type",
        ),
    ],
)
def test_emit_explicit_type_fails_closed_after_sequence_before_build(
    result: dict[str, Any], message: str, bus: FakeBus, builder: list[Any], events: list[Any]
) -> None:
    with pytest.raises(ValueError, match=message):
        _emit({"attempt_id": "a", **result})
    assert [e[0] for e in events] == ["bus.next_attempt_sequence"]
    assert builder == []


def test_emit_continuity_list_precedence(bus: FakeBus, builder: list[dict[str, Any]]) -> None:
    # result name > result alias > request name > request alias
    _emit({
        "attempt_id": "a",
        "do_not_repeat": ["n"],
        "rejected_strategies": ["al"],
        "request": {"do_not_repeat": ["r"]},
    })
    _emit({"attempt_id": "a", "rejected_strategies": ["al"], "request": {"do_not_repeat": ["r"]}})
    _emit({"attempt_id": "a", "request": {"do_not_repeat": ["r"], "rejected_strategies": ["ra"]}})
    _emit({"attempt_id": "a", "request": {"rejected_strategies": ["ra"]}})
    _emit({"attempt_id": "a", "do_not_repeat": "", "unknowns": ("k",)})
    assert [k["do_not_repeat"] for k in builder] == [("n",), ("al",), ("r",), ("ra",), ("",)]
    assert builder[-1]["unknowns"] == ("k",)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("do_not_repeat", {"a": 1}, "do_not_repeat must be a list/tuple of non-empty strings"),
        ("do_not_repeat", {"a"}, "do_not_repeat must be a list/tuple of non-empty strings"),
        ("rejected_strategies", 7, "do_not_repeat must be a list/tuple of non-empty strings"),
        (
            "unresolved_risks",
            {"a": 1},
            "unresolved_risks must be a list/tuple of non-empty strings",
        ),
        ("unknowns", ["ok", ""], "unknowns must contain non-empty strings"),
        ("unknowns", ["ok", 1], "unknowns must contain non-empty strings"),
        ("do_not_repeat", [" "], "do_not_repeat must contain non-empty strings"),
    ],
)
def test_emit_continuity_list_fails_closed_before_build(
    field: str, value: Any, message: str, bus: FakeBus, builder: list[Any], events: list[Any]
) -> None:
    with pytest.raises(ValueError, match=message):
        _emit({"attempt_id": "a", field: value})
    assert [e[0] for e in events] == ["bus.next_attempt_sequence"] and builder == []


def test_emit_continuity_list_errors_in_argument_order(bus: FakeBus, builder: list[Any]) -> None:
    with pytest.raises(ValueError, match="^do_not_repeat must"):
        _emit({"attempt_id": "a", "unknowns": 1, "unresolved_risks": 1, "do_not_repeat": 1})
    with pytest.raises(ValueError, match="^unresolved_risks must"):
        _emit({"attempt_id": "a", "unknowns": 1, "unresolved_risks": 1})


def test_emit_identity_precedence(bus: FakeBus, builder: list[dict[str, Any]]) -> None:
    contract = {
        "source_revision": "c-src",
        "controller_revision": "c-ctrl",
        "current_source_revision": "c-cur",
        "contract_revision": "c-rev",
        "contract_hash": "c-hash",
        "current_contract_revision": "c-cur-rev",
        "current_contract_hash": "c-cur-hash",
    }
    request = {
        "source_revision": "r-src",
        "controller_revision": "r-ctrl",
        "contract_revision": "r-rev",
        "contract_hash": "r-hash",
    }
    cases = [
        {
            "source_revision": "e",
            "controller_revision": "d",
            "contract_revision": "e2",
            "contract_hash": "d2",
        },
        {
            "source_revision": "  ",
            "controller_revision": "d",
            "contract_revision": None,
            "contract_hash": "d2",
        },
        {"contract": contract},
        {"contract": {**contract, "source_revision": " ", "contract_revision": None}},
        {"contract": {"current_source_revision": "c-cur", "current_contract_hash": "c-cur-hash"}},
        {},
        {"controller_revision": 0, "contract_hash": False},
    ]
    for case in cases:
        _emit({"attempt_id": "a", "request": request, **case})
    _emit({
        "attempt_id": "a",
        "request": {"controller_revision": "r-ctrl", "contract_hash": "r-hash"},
    })
    assert [(k["source_revision"], k["contract_revision"]) for k in builder] == [
        ("e", "e2"),
        ("d", "d2"),
        ("c-src", "c-rev"),
        ("c-ctrl", "c-hash"),
        ("c-cur", "c-cur-hash"),
        ("r-src", "r-rev"),
        ("0", "False"),
        ("r-ctrl", "r-hash"),
    ]


def test_emit_sequence_failure_propagates_before_anything_else(
    monkeypatch: pytest.MonkeyPatch, builder: list[Any], events: list[Any]
) -> None:
    error = OSError("tail unreadable")
    monkeypatch.setattr(service_module, "NexusEventBus", FakeBus(events, sequence_error=error))
    with pytest.raises(OSError) as info:
        _emit({"attempt_id": "a", "do_not_repeat": 1})
    assert info.value is error and builder == []


def test_emit_append_failure_propagates(
    monkeypatch: pytest.MonkeyPatch, builder: list[Any], events: list[Any]
) -> None:
    error = ValueError("attempt transition sequence must be contiguous")
    monkeypatch.setattr(service_module, "NexusEventBus", FakeBus(events, emit_error=error))
    with pytest.raises(ValueError) as info:
        _emit({"attempt_id": "a"})
    assert info.value is error
    assert [e[0] for e in events] == [
        "bus.next_attempt_sequence",
        "build",
        "bus.emit_attempt_transition",
    ]


def test_emit_real_bus_persists_ordered_attempt_events(real_bus: Path) -> None:
    _emit({
        "task_id": "t",
        "attempt_id": "a",
        "status": "RUNNING",
        "source_revision": "s",
        "contract_revision": "c",
    })
    _emit({
        "task_id": "t",
        "attempt_id": "a",
        "status": "REJECTED",
        "error": "boom",
        "do_not_repeat": ["p"],
        "source_revision": "s",
        "contract_revision": "c",
    })
    _emit({"task_id": "other", "attempt_id": "a", "status": "RUNNING"})
    rows = SelfHostedTaskService.read_canonical_attempt_events("t", "a")
    payloads = [row["payload"] for row in rows]
    assert [p["sequence"] for p in payloads] == [1, 2]
    assert [p["state"] for p in payloads] == ["RUNNING", "REJECTED"]
    assert [p["continuity_event_type"] for p in payloads] == [
        "OBSERVATION_RECORDED",
        "ATTEMPT_REJECTED",
    ]
    assert payloads[1]["do_not_repeat"] == ["p"]
    assert payloads[1]["reason"] == "boom"
    assert all(row["event_type"] == "attempt_transition" for row in rows)
    decoded = SelfHostedTaskService.read_canonical_attempt_continuity("t", "a")
    assert [event.event_type for event in decoded] == ["OBSERVATION_RECORDED", "ATTEMPT_REJECTED"]


# ---------------------------------------------------------------------------
# read_canonical_attempt_events / read_canonical_attempt_continuity


def _row(task_id: str, attempt_id: str, n: int) -> dict[str, Any]:
    return {
        "event_type": "attempt_transition",
        "seq": n,
        "payload": {"task_id": task_id, "attempt_id": attempt_id, "n": n},
    }


def test_read_events_without_root_syncs_store_path_and_filters(
    monkeypatch: pytest.MonkeyPatch, events: list[Any]
) -> None:
    rows = [_row("t", "a", 1), _row("t", "b", 2), _row("u", "a", 3), _row("t", "a", 4)]
    fake = FakeBus(events, records=rows)
    monkeypatch.setattr(service_module, "NexusEventBus", fake)
    got = SelfHostedTaskService.read_canonical_attempt_events("t", "a")
    assert got == [rows[0], rows[3]]
    assert got[0] is not rows[0]
    assert events == [
        ("store.set", "event_log_path", Path("/bus/path")),
        ("store.read_recent", {"event_type": "attempt_transition", "limit": 10_000}),
    ]


def test_read_events_with_root_binds_read_only_production_first(
    monkeypatch: pytest.MonkeyPatch, events: list[Any], tmp_path: Path
) -> None:
    fake = FakeBus(events, records=[_row("t", "a", 1)])
    fake._log_store.__dict__["event_log_path"] = Path("/bus/path")
    monkeypatch.setattr(service_module, "NexusEventBus", fake)
    SelfHostedTaskService.read_canonical_attempt_events("t", "a", project_root=tmp_path)
    assert events == [
        ("bus.configure", tmp_path, False, True),
        ("store.read_recent", {"event_type": "attempt_transition", "limit": 10_000}),
    ]


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([], "attempt continuity stream is empty"),
        ([_row("t", "b", 1), _row("u", "a", 2)], "attempt continuity stream is empty"),
        ([{"payload": "x"}, _row("t", "a", 1)], "attempt transition payload is missing"),
        (
            [_row("t", "a", 1), {"event_type": "attempt_transition"}],
            "attempt transition payload is missing",
        ),
        ([["not", "a", "mapping"]], "attempt transition payload is missing"),
    ],
)
def test_read_events_fail_closed(
    rows: list[Any], message: str, monkeypatch: pytest.MonkeyPatch, events: list[Any]
) -> None:
    monkeypatch.setattr(service_module, "NexusEventBus", FakeBus(events, records=rows))
    with pytest.raises(ValueError, match=message):
        SelfHostedTaskService.read_canonical_attempt_events("t", "a")


def test_read_events_preserves_store_integrity_error(
    monkeypatch: pytest.MonkeyPatch, events: list[Any]
) -> None:
    error = ValueError("tampered event log")
    monkeypatch.setattr(service_module, "NexusEventBus", FakeBus(events, read_error=error))
    with pytest.raises(ValueError) as info:
        SelfHostedTaskService.read_canonical_attempt_events("t", "a")
    assert info.value is error


def test_read_continuity_resolves_service_class_and_decoder_through_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    original = SelfHostedTaskService.read_canonical_attempt_continuity

    class Probe:
        @staticmethod
        def read_canonical_attempt_events(
            task_id: str, attempt_id: str, **kwargs: Any
        ) -> list[Any]:
            calls.append(("read", task_id, attempt_id, kwargs))
            return ["r1"]

    def decode(records: Any, **kwargs: Any) -> list[Any]:
        calls.append(("decode", records, kwargs))
        return ["decoded"]

    monkeypatch.setattr(service_module, "SelfHostedTaskService", Probe)
    monkeypatch.setattr(service_module, "events_from_attempt_records", decode)
    assert original("t", "a") == ["decoded"]
    assert calls == [
        ("read", "t", "a", {}),
        ("decode", ["r1"], {"task_id": "t", "attempt_id": "a"}),
    ]


# ---------------------------------------------------------------------------
# rehydrate_task_continuation


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch, events: list[Any]) -> list[Any]:
    """Facade-patched continuity pipeline recording its calls."""

    def decode(records: Any, **kwargs: Any) -> list[Any]:
        events.append(("decode", records, kwargs))
        return ["decoded"]

    def project(evts: Any) -> Any:
        events.append(("project", list(evts)))
        return "snapshot"

    class Projection:
        def __init__(self, kwargs: dict[str, Any]) -> None:
            self.kwargs = kwargs

        def to_dict(self) -> dict[str, Any]:
            events.append(("to_dict",))
            return {"projection": True, "requested": self.kwargs["requested_attempt_id"]}

    def build(**kwargs: Any) -> Any:
        events.append(("build_projection", kwargs))
        return Projection(kwargs)

    def continuity(self: Any, task_id: str, attempt_id: str) -> list[Any]:
        events.append(("continuity", task_id, attempt_id))
        return ["c-event"]

    def canonical_events(task_id: str, attempt_id: str, *, project_root: Any = None) -> list[Any]:
        events.append(("canonical_events", task_id, attempt_id, project_root))
        return ["raw"]

    monkeypatch.setattr(service_module, "events_from_attempt_records", decode)
    monkeypatch.setattr(service_module, "project", project)
    monkeypatch.setattr(service_module, "build_rehydration_projection", build)
    monkeypatch.setattr(SelfHostedTaskService, "read_canonical_attempt_continuity", continuity)
    monkeypatch.setattr(
        SelfHostedTaskService, "read_canonical_attempt_events", staticmethod(canonical_events)
    )
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_task_action_envelope",
        classmethod(
            lambda cls, state: events.append(("envelope", state.get("task_id"))) or {"envelope": 1}
        ),
    )
    return events


def test_rehydrate_unknown_task(service: SelfHostedTaskService) -> None:
    with pytest.raises(KeyError, match="unknown task: nope"):
        service.rehydrate_task_continuation("nope")


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"state_valid": False}, "REHYDRATION_MALFORMED_STATE: state is invalid"),
        (
            {"state_valid": False, "blocker": {"detail": "bad json"}},
            "REHYDRATION_MALFORMED_STATE: bad json",
        ),
        ({"state_valid": False, "blocker": "str"}, "REHYDRATION_MALFORMED_STATE: state is invalid"),
        (
            {"status": "BLOCKED_INVALID_STATE", "blocker": {"detail": ""}},
            "REHYDRATION_MALFORMED_STATE: state is invalid",
        ),
        ({"candidate": "x"}, "REHYDRATION_MALFORMED_STATE: candidate must be a mapping"),
        (
            {"promotion_packet": []},
            "REHYDRATION_MALFORMED_STATE: promotion_packet must be a mapping",
        ),
        (
            {"verified_receipt": 1},
            "REHYDRATION_MALFORMED_STATE: verified_receipt must be a mapping",
        ),
        (
            {"contract": "c", "candidate": "x"},
            "REHYDRATION_MALFORMED_STATE: candidate must be a mapping",
        ),
        ({"work_claim": "w"}, "REHYDRATION_WORK_CLAIM_MISMATCH: work_claim must be a mapping"),
        (
            {"work_claim": {"identity": "i"}},
            "REHYDRATION_WORK_CLAIM_MISMATCH: work_claim identity must be a mapping",
        ),
        (
            {"work_claim": {}},
            "REHYDRATION_WORK_CLAIM_MISMATCH: work_claim identity must be a mapping",
        ),
        ({"attempt_id": ""}, "REHYDRATION_ATTEMPT_ID_REQUIRED"),
        (
            {"state_valid": False, "candidate": "x", "work_claim": "w", "attempt_id": None},
            "REHYDRATION_MALFORMED_STATE: state is invalid",
        ),
        (
            {"candidate": "x", "work_claim": "w", "attempt_id": None},
            "REHYDRATION_MALFORMED_STATE: candidate",
        ),
        ({"work_claim": "w", "attempt_id": None}, "REHYDRATION_WORK_CLAIM_MISMATCH"),
    ],
)
def test_rehydrate_denials_in_order(
    extra: dict[str, Any], message: str, service: SelfHostedTaskService, pipeline: list[Any]
) -> None:
    state = {"task_id": "t", "attempt_id": "a", "status": "FINAL_BLOCK", **extra}
    with pytest.raises(ValueError, match=f"^{message}"):
        service.rehydrate_task_continuation("t", _state=state)
    assert pipeline == []


def test_rehydrate_non_mapping_state(service: SelfHostedTaskService) -> None:
    with pytest.raises(
        ValueError, match="^REHYDRATION_MALFORMED_STATE: task state must be a mapping$"
    ):
        service.rehydrate_task_continuation("t", _state=["x"])  # type: ignore[arg-type]


def test_rehydrate_ephemeral_reads_continuity_and_builds_projection(
    monkeypatch: pytest.MonkeyPatch,
    service: SelfHostedTaskService,
    state_dir: Path,
    pipeline: list[Any],
) -> None:
    _seed(service, "t", status="FINAL_BLOCK", attempt_id="state-attempt")
    before = _disk_bytes(state_dir)
    pipeline.clear()
    recorder = Recorder(monkeypatch, pipeline)
    result = service.rehydrate_task_continuation("t")
    assert result == {"projection": True, "requested": None}
    names = [e if isinstance(e, str) else e[0] for e in pipeline]
    # the snapshot read attaches the persisted task_action (first envelope call)
    assert names == [
        "_read_state_snapshot",
        "envelope",
        "continuity",
        "project",
        "envelope",
        "build_projection",
        "to_dict",
    ]
    assert pipeline[2] == ("continuity", "t", "state-attempt")
    assert pipeline[3] == ("project", ["c-event"])
    build = pipeline[5][1]
    assert set(build) == {
        "task_state",
        "continuity_snapshot",
        "task_action_envelope",
        "requested_attempt_id",
    }
    assert build["continuity_snapshot"] == "snapshot" and build["task_action_envelope"] == {
        "envelope": 1
    }
    assert (
        build["task_state"]["attempt_id"] == "state-attempt"
        and build["requested_attempt_id"] is None
    )
    assert "lock+" not in recorder.io()
    assert _disk_bytes(state_dir) == before


def test_rehydrate_requested_attempt_is_stringified_for_reads_only(
    service: SelfHostedTaskService, pipeline: list[Any]
) -> None:
    state = {"task_id": "t", "attempt_id": "state-attempt", "status": "X"}
    result = service.rehydrate_task_continuation("t", 7, _state=state)  # type: ignore[arg-type]
    assert pipeline[0] == ("continuity", "t", "7")
    assert result == {"projection": True, "requested": 7}
    assert pipeline[3][1]["task_state"] is state


def test_rehydrate_canonical_service_reads_events_from_canonical_root(
    monkeypatch: pytest.MonkeyPatch,
    service: SelfHostedTaskService,
    pipeline: list[Any],
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical"
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(canonical))
    monkeypatch.setattr(service, "ephemeral", False)
    service.rehydrate_task_continuation("t", "a", _state={"task_id": "t", "attempt_id": "x"})
    assert pipeline[:2] == [
        ("canonical_events", "t", "a", canonical.resolve()),
        ("decode", ["raw"], {"task_id": "t", "attempt_id": "a"}),
    ]
    assert [e[0] for e in pipeline] == [
        "canonical_events",
        "decode",
        "project",
        "envelope",
        "build_projection",
        "to_dict",
    ]


def test_rehydrate_real_pipeline_round_trip(
    real_bus: Path, service: SelfHostedTaskService, state_dir: Path
) -> None:
    _seed(
        service,
        "t",
        status="FINAL_BLOCK",
        attempt_id="a",
        source_revision="s",
        contract_revision="c",
    )
    _emit({
        "task_id": "t",
        "attempt_id": "a",
        "status": "RUNNING",
        "source_revision": "s",
        "contract_revision": "c",
    })
    before = _disk_bytes(state_dir)
    result = service.rehydrate_task_continuation("t")
    assert result["task_identity"] == {"task_id": "t", "attempt_id": "a"}
    assert _disk_bytes(state_dir) == before
    snapshot = SelfHostedTaskService.rehydrate_task_continuation_snapshot(
        service._read_state_snapshot("t") or {},
        SelfHostedTaskService.read_canonical_attempt_continuity("t", "a"),
    )
    assert snapshot == result
    with pytest.raises(ValueError, match="attempt continuity stream is empty"):
        service.rehydrate_task_continuation("t", "other-attempt")


# ---------------------------------------------------------------------------
# rehydrate_task_continuation(_project_entry=True)


def _entry(service: SelfHostedTaskService, state: dict[str, Any], **kwargs: Any) -> Any:
    return service.rehydrate_task_continuation(
        "t", "a", _project_entry=True, _state={"task_id": "t", "attempt_id": "a", **state}, **kwargs
    )


@pytest.fixture
def authority(monkeypatch: pytest.MonkeyPatch, events: list[Any]) -> dict[str, Any]:
    """Facade-patched authority helpers; ``control`` steers their results."""
    control: dict[str, Any] = {"binding": None, "effective_binding": None, "validated": None}

    def hints(request: Any) -> None:
        events.append(("hints", dict(request)))
        if request.get("hint_error"):
            raise ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_REQUIRED")

    def validate(request: Any, *, repository: Any = None, issue_number: Any = None) -> Any:
        events.append(("validate", dict(request), repository, issue_number))
        if repository is None and issue_number is None:
            return control["effective_binding"]
        return control["binding"]

    def validated(request: Any) -> Any:
        events.append(("validated_action_request", dict(request)))
        return control["validated"]

    def request_hash(payload: Any) -> str:
        events.append(("canonical_request_hash", dict(payload)))
        return "h-" + ",".join(sorted(payload))

    monkeypatch.setattr(service_module, "_reject_unbound_project_entry_authority_hints", hints)
    monkeypatch.setattr(service_module, "_validate_project_entry_authority_binding", validate)
    monkeypatch.setattr(service_module, "_validated_action_request", validated)
    monkeypatch.setattr(service_module, "canonical_request_hash", request_hash)
    return control


def _names(events: list[Any]) -> list[str]:
    return [e if isinstance(e, str) else e[0] for e in events]


def test_entry_without_request_mapping_checks_state_hints(
    service: SelfHostedTaskService, pipeline: list[Any], authority: dict[str, Any]
) -> None:
    assert _entry(service, {"request": "x"}) == {
        "continuation": {"projection": True, "requested": "a"},
        "authority_binding": None,
    }
    assert _names(pipeline)[-1] == "hints" and pipeline[-1][1]["request"] == "x"
    with pytest.raises(
        ValueError,
        match="^PROJECT_ENTRY_AUTHORITY_BINDING_INVALID: PROJECT_ENTRY_AUTHORITY_BINDING_REQUIRED$",
    ):
        _entry(service, {"hint_error": True})


def test_entry_unbound_plain_request_checks_request_then_state_hints(
    service: SelfHostedTaskService, pipeline: list[Any], authority: dict[str, Any]
) -> None:
    result = _entry(service, {"request": {"repository": "r", "issue": 3}})
    assert result["authority_binding"] is None
    tail = [e for e in pipeline if e[0] in {"hints", "validate", "canonical_request_hash"}]
    assert tail == [
        ("hints", {"repository": "r", "issue": 3}),
        ("validate", {"repository": "r", "issue": 3}, "r", 3),
        ("hints", {"task_id": "t", "attempt_id": "a", "request": {"repository": "r", "issue": 3}}),
    ]


def test_entry_selector_arguments_default_from_request(
    service: SelfHostedTaskService, pipeline: list[Any], authority: dict[str, Any]
) -> None:
    _entry(service, {"request": {"issue_number": "9"}})
    _entry(
        service,
        {"request": {"repository": "r", "issue": "4"}},
        _project_entry_repository="explicit",
        _project_entry_issue=11,
    )
    _entry(service, {"request": {}})
    validates = [e for e in pipeline if e[0] == "validate"]
    assert [(e[2], e[3]) for e in validates] == [("", 9), ("explicit", 11), ("", 0)]


def test_entry_binding_requires_persisted_hash(
    service: SelfHostedTaskService, pipeline: list[Any], authority: dict[str, Any]
) -> None:
    authority["binding"] = {"goal_id": "g", "coordination_scope_id": "s"}
    with pytest.raises(
        ValueError,
        match="^PROJECT_ENTRY_AUTHORITY_BINDING_INVALID: PROJECT_ENTRY_REQUEST_HASH_MISSING$",
    ):
        _entry(service, {"request": {"repository": "r"}})


def test_entry_plain_request_hash_excludes_embedded_hash(
    service: SelfHostedTaskService, pipeline: list[Any], authority: dict[str, Any]
) -> None:
    binding = {"goal_id": "g", "coordination_scope_id": "s"}
    authority["binding"] = binding
    request = {"repository": "r", "action_request_hash": "embedded"}
    ok = _entry(service, {"request": request, "action_request_hash": "h-repository"})
    assert ok == {
        "continuation": {"projection": True, "requested": "a"},
        "authority_binding": binding,
    }
    assert ("canonical_request_hash", {"repository": "r"}) in pipeline
    with pytest.raises(
        ValueError,
        match="^PROJECT_ENTRY_AUTHORITY_BINDING_INVALID: PROJECT_ENTRY_REQUEST_HASH_MISMATCH$",
    ):
        _entry(service, {"request": request, "action_request_hash": "other"})


def test_entry_unbound_request_with_hash_still_verified(
    service: SelfHostedTaskService, pipeline: list[Any], authority: dict[str, Any]
) -> None:
    assert (
        _entry(service, {"request": {"x": 1}, "action_request_hash": "h-x"})["authority_binding"]
        is None
    )
    with pytest.raises(ValueError, match="PROJECT_ENTRY_REQUEST_HASH_MISMATCH"):
        _entry(service, {"request": {"x": 1}, "action_request_hash": "nope"})


@pytest.mark.parametrize("key", ["action", "bound_action_request"])
def test_entry_action_request_path(
    key: str, service: SelfHostedTaskService, pipeline: list[Any], authority: dict[str, Any]
) -> None:
    binding = {"goal_id": "g", "coordination_scope_id": "s"}
    effective = dict(binding)
    authority["binding"] = binding
    authority["effective_binding"] = effective
    authority["validated"] = ({"effective": "request"}, {"request_hash": "rh"})
    request = {key: {}, "repository": "r"}
    result = _entry(service, {"request": request, "action_request_hash": "rh"})
    assert result["authority_binding"] is effective
    assert ("validated_action_request", request) in pipeline
    assert ("validate", {"effective": "request"}, None, None) in pipeline
    assert not any(e[0] == "canonical_request_hash" for e in pipeline)


@pytest.mark.parametrize(
    ("validated", "effective", "message"),
    [
        (
            ({"e": 1}, {"request_hash": "other"}),
            {"goal_id": "g", "coordination_scope_id": "s"},
            "PROJECT_ENTRY_REQUEST_HASH_MISMATCH",
        ),
        (
            ({"e": 1}, ["not", "mapping"]),
            {"goal_id": "g", "coordination_scope_id": "s"},
            "PROJECT_ENTRY_REQUEST_HASH_MISMATCH",
        ),
        (
            ({"e": 1}, {"request_hash": "rh"}),
            {"goal_id": "other", "coordination_scope_id": "s"},
            "PROJECT_ENTRY_AUTHORITY_BINDING_DUPLICATE_MISMATCH",
        ),
        (
            ({"e": 1}, {"request_hash": "rh"}),
            None,
            "PROJECT_ENTRY_AUTHORITY_BINDING_DUPLICATE_MISMATCH",
        ),
    ],
)
def test_entry_action_request_denials(
    validated: Any,
    effective: Any,
    message: str,
    service: SelfHostedTaskService,
    pipeline: list[Any],
    authority: dict[str, Any],
) -> None:
    authority["binding"] = {"goal_id": "g", "coordination_scope_id": "s"}
    authority["effective_binding"] = effective
    authority["validated"] = validated
    with pytest.raises(ValueError, match=f"^PROJECT_ENTRY_AUTHORITY_BINDING_INVALID: {message}$"):
        _entry(service, {"request": {"action": {}}, "action_request_hash": "rh"})


@pytest.mark.parametrize(
    "state",
    [
        {"authority_goal_id": "other"},
        {"autonomy_goal_id": "other"},
        {"authority_coordination_scope_id": "other"},
        {"autonomy_submission_binding": {"goal_id": "other"}},
    ],
)
def test_entry_bound_duplicates_must_match(
    state: dict[str, Any],
    service: SelfHostedTaskService,
    pipeline: list[Any],
    authority: dict[str, Any],
) -> None:
    authority["binding"] = {"goal_id": "g", "coordination_scope_id": "s"}
    with pytest.raises(
        ValueError,
        match="^PROJECT_ENTRY_AUTHORITY_BINDING_INVALID: PROJECT_ENTRY_AUTHORITY_DUPLICATE_MISMATCH$",
    ):
        _entry(service, {"request": {"r": 1}, "action_request_hash": "h-r", **state})


def test_entry_bound_matching_duplicates_pass_and_skip_state_hints(
    service: SelfHostedTaskService, pipeline: list[Any], authority: dict[str, Any]
) -> None:
    binding = {"goal_id": "g", "coordination_scope_id": "s"}
    authority["binding"] = binding
    result = _entry(
        service,
        {
            "request": {"r": 1},
            "action_request_hash": "h-r",
            "authority_goal_id": "g",
            "autonomy_goal_id": None,
            "authority_coordination_scope_id": "s",
            "autonomy_submission_binding": {"goal_id": None},
        },
    )
    assert result["authority_binding"] is binding
    assert [e[0] for e in pipeline if e[0] == "hints"] == ["hints"]  # request only, never state


def test_entry_type_errors_are_wrapped_key_errors_are_not(
    service: SelfHostedTaskService, pipeline: list[Any], authority: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_BINDING_INVALID: int"):
        _entry(service, {"request": {"issue": [1]}})
    authority["binding"] = {"coordination_scope_id": "s"}
    with pytest.raises(KeyError):
        _entry(
            service, {"request": {"r": 1}, "action_request_hash": "h-r", "authority_goal_id": "g"}
        )


def test_entry_real_authority_helpers(service: SelfHostedTaskService, pipeline: list[Any]) -> None:
    values = {
        "repository": "James3014/Nexus-new",
        "issue_number": 7,
        "goal_id": "goal",
        "coordination_scope_id": "scope",
        "canonical_remote": "https://github.com/James3014/Nexus-new.git",
        "intended_action_family": "TASK_SUBMIT",
    }
    binding = {**values, "binding_hash": canonical_request_hash(values)}
    request = {
        "repository": "James3014/Nexus-new",
        "issue": 7,
        "project_entry_authority_binding": binding,
    }
    persisted = canonical_request_hash(request)
    result = _entry(
        service, {"request": request, "action_request_hash": persisted, "authority_goal_id": "goal"}
    )
    assert result["authority_binding"] == {**values, "issue_number": "7"}
    with pytest.raises(
        ValueError,
        match="^PROJECT_ENTRY_AUTHORITY_BINDING_INVALID: PROJECT_ENTRY_AUTHORITY_REPOSITORY_MISMATCH$",
    ):
        _entry(
            service,
            {"request": request, "action_request_hash": persisted},
            _project_entry_repository="x/y",
        )
    with pytest.raises(
        ValueError,
        match="^PROJECT_ENTRY_AUTHORITY_BINDING_INVALID: PROJECT_ENTRY_AUTHORITY_BINDING_REQUIRED$",
    ):
        _entry(service, {"request": {"repository": "r", "standing_grant_id": "g"}})
    with pytest.raises(
        ValueError,
        match="^PROJECT_ENTRY_AUTHORITY_BINDING_INVALID: PROJECT_ENTRY_AUTHORITY_BINDING_REQUIRED$",
    ):
        _entry(service, {"request": {"repository": "r"}, "execution_lane": "governed"})


# ---------------------------------------------------------------------------
# rehydrate_project_entry


@pytest.fixture
def delegated(monkeypatch: pytest.MonkeyPatch, events: list[Any]) -> list[Any]:
    def rehydrate(self: Any, task_id: str, attempt_id: Any = None, **kwargs: Any) -> dict[str, Any]:
        events.append(("rehydrate", task_id, attempt_id, kwargs))
        return {"delegated": True}

    monkeypatch.setattr(SelfHostedTaskService, "rehydrate_task_continuation", rehydrate)
    return events


def test_project_entry_invalid_state_passes_selectors_and_fails_in_rehydration(
    service: SelfHostedTaskService, state_dir: Path
) -> None:
    _seed(service, "t", request="not-a-mapping", repository="other", issue="02")
    before = _disk_bytes(state_dir)
    with pytest.raises(
        ValueError, match="^REHYDRATION_MALFORMED_STATE: state request must be an object$"
    ):
        service.rehydrate_project_entry("t", "a", repository="r", issue_number=1)
    assert _disk_bytes(state_dir) == before


def test_project_entry_unknown_task(service: SelfHostedTaskService, delegated: list[Any]) -> None:
    with pytest.raises(KeyError, match="unknown task: nope"):
        service.rehydrate_project_entry("nope", None, repository="r", issue_number=1)
    assert delegated == []


@pytest.mark.parametrize(
    "extra",
    [
        {"request": {"repository": "other", "issue": 1}},
        {"request": {"repository": "r", "issue": 2}},
        {"request": {"repository": "r", "issue_number": "2"}},
        {"request": {"issue": "1"}},  # request present, repository missing
        {"request": {"repository": "r", "issue": "1", "issue_number": 3}},
        {"repository": "other"},
        {"issue": 2},
        {"issue": "02"},
    ],
)
def test_project_entry_selector_mismatch(
    extra: dict[str, Any], service: SelfHostedTaskService, delegated: list[Any]
) -> None:
    _seed(service, "t", **extra)
    with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_SELECTOR_MISMATCH$"):
        service.rehydrate_project_entry("t", "a", repository="r", issue_number=1)
    assert delegated == []


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"request": {"repository": "r"}},
        {"request": {"repository": "r", "issue": "1", "issue_number": 1}},
        {"request": {"repository": "", "issue": "", "issue_number": 0, "x": 1}},
        {"repository": "", "issue": 0, "request": {"repository": "r", "issue": 1}},
        {"repository": "r", "issue": "1"},
    ],
)
def test_project_entry_delegates_with_one_snapshot(
    extra: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    service: SelfHostedTaskService,
    delegated: list[Any],
) -> None:
    _seed(service, "t", **extra)
    recorder = Recorder(monkeypatch, delegated)
    assert service.rehydrate_project_entry("t", "a", repository="r", issue_number=1) == {
        "delegated": True
    }
    assert _names(delegated) == ["_read_state_snapshot", "rehydrate"]
    _, task_id, attempt_id, kwargs = delegated[1]
    assert (task_id, attempt_id) == ("t", "a")
    assert set(kwargs) == {
        "_project_entry",
        "_state",
        "_project_entry_repository",
        "_project_entry_issue",
    }
    assert kwargs["_project_entry"] is True
    assert kwargs["_project_entry_repository"] == "r" and kwargs["_project_entry_issue"] == 1
    assert kwargs["_state"]["task_id"] == "t"
    assert "lock+" not in recorder.io()


# ---------------------------------------------------------------------------
# rehydrate_task_continuation_snapshot


def test_continuation_snapshot_is_pure_projection(
    monkeypatch: pytest.MonkeyPatch, pipeline: list[Any], service: SelfHostedTaskService
) -> None:
    recorder = Recorder(monkeypatch, pipeline)
    state = {"task_id": "t"}
    assert SelfHostedTaskService.rehydrate_task_continuation_snapshot(
        state, iter(["e1", "e2"])
    ) == {
        "projection": True,
        "requested": None,
    }
    assert service.rehydrate_task_continuation_snapshot(state, [], attempt_id="x") == {
        "projection": True,
        "requested": "x",
    }
    assert _names(pipeline) == ["project", "envelope", "build_projection", "to_dict"] * 2
    assert pipeline[0] == ("project", ["e1", "e2"])
    assert pipeline[2][1]["task_state"] is state
    assert recorder.io() == []


# ---------------------------------------------------------------------------
# _record_direct_failure / record_canonical_action_failure


def test_record_direct_failure_marks_reconcile_then_emits_after_lock(
    monkeypatch: pytest.MonkeyPatch,
    service: SelfHostedTaskService,
    fixed_now: str,
    events: list[Any],
) -> None:
    _seed(
        service,
        "t",
        status="DIRECT_RUNNING",
        canonical_action={"kind": "assist", "reconciliation": {"status": "OLD", "keep": 1}},
        status_history=[{"status": "DIRECT_RUNNING", "at": "T0"}],
    )
    emitted: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_emit_bound_attempt_transition",
        lambda self, result, task_id: emitted.append((dict(result), task_id)),
    )
    recorder = Recorder(monkeypatch, events)
    result = service._record_direct_failure("t", "PROVIDER_TIMEOUT", "timed out")
    assert result is not None
    assert result["status"] == "DIRECT_RECONCILE_REQUIRED"
    assert result["error"] == "timed out"
    assert result["reconciliation_required"] is True
    assert result["updated_at"] == FIXED_NOW
    assert result["canonical_action"] == {
        "kind": "assist",
        "reconciliation": {
            "status": "REQUIRED",
            "keep": 1,
            "blocker": "PROVIDER_TIMEOUT",
            "error": "timed out",
            "at": FIXED_NOW,
        },
    }
    assert result["status_history"][-1] == {"status": "DIRECT_RECONCILE_REQUIRED", "at": FIXED_NOW}
    assert len(result["status_history"]) == 2
    assert recorder.names() == ["_mutate_state", "lock+", "lock-", "_emit_bound_attempt_transition"]
    assert emitted == [(dict(result), "t")]
    assert service._read_state_snapshot("t") is not None


def test_record_direct_failure_defaults_error_to_blocker(
    monkeypatch: pytest.MonkeyPatch, service: SelfHostedTaskService, fixed_now: str
) -> None:
    _seed(service, "t", status="DIRECT_RUNNING")
    monkeypatch.setattr(
        SelfHostedTaskService, "_emit_bound_attempt_transition", lambda self, r, t: None
    )
    result = service._record_direct_failure("t", "BLOCK")
    assert result is not None
    assert result["error"] == "BLOCK"
    assert result["canonical_action"] == {
        "reconciliation": {"status": "REQUIRED", "blocker": "BLOCK", "error": "", "at": FIXED_NOW}
    }
    assert result["status_history"] == [{"status": "DIRECT_RECONCILE_REQUIRED", "at": FIXED_NOW}]


def test_record_direct_failure_keeps_direct_completed_but_still_emits(
    monkeypatch: pytest.MonkeyPatch, service: SelfHostedTaskService, state_dir: Path, fixed_now: str
) -> None:
    _seed(service, "t", status="DIRECT_COMPLETED")
    before = service._read_state_snapshot("t")
    emitted: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_emit_bound_attempt_transition",
        lambda self, r, t: emitted.append((r, t)),
    )
    result = service._record_direct_failure("t", "LATE", "late")
    assert result is not None and result["status"] == "DIRECT_COMPLETED"
    assert "canonical_action" not in result and "reconciliation_required" not in result
    assert service._read_state_snapshot("t") == before
    assert len(emitted) == 1 and emitted[0][1] == "t"


def test_record_direct_failure_missing_task_emits_none(
    monkeypatch: pytest.MonkeyPatch, service: SelfHostedTaskService, state_dir: Path
) -> None:
    emitted: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_emit_bound_attempt_transition",
        lambda self, r, t: emitted.append((r, t)),
    )
    assert service._record_direct_failure("missing", "B") is None
    assert emitted == [(None, "missing")]
    assert _disk_bytes(state_dir) == {}


def test_record_direct_failure_event_failure_keeps_state_and_records_debt(
    monkeypatch: pytest.MonkeyPatch,
    service: SelfHostedTaskService,
    fixed_now: str,
    builder: list[Any],
    events: list[Any],
) -> None:
    _seed(service, "t", status="DIRECT_RUNNING", attempt_id="a")
    error = OSError("append failed")
    monkeypatch.setattr(service_module, "NexusEventBus", FakeBus(events, emit_error=error))
    with pytest.raises(OSError) as info:
        service._record_direct_failure("t", "B", "e")
    assert info.value is error
    state = service._read_state_snapshot("t")
    assert state is not None
    assert state["status"] == "DIRECT_RECONCILE_REQUIRED"
    assert state["event_reconciliation_required"] is True
    assert (
        state["event_append_failure"]["error_sha256"]
        == hashlib.sha256(b"append failed").hexdigest()
    )
    (kwargs,) = builder
    assert kwargs["state"] == "DIRECT_RECONCILE_REQUIRED" and kwargs["reason"] == "e"


def test_record_direct_failure_real_bus_emits_reconcile_event(
    real_bus: Path, service: SelfHostedTaskService, fixed_now: str
) -> None:
    _seed(service, "t", status="DIRECT_RUNNING", attempt_id="a")
    service._record_direct_failure("t", "B", "e")
    service.record_canonical_action_failure("t", "B2")
    payloads = [
        row["payload"] for row in SelfHostedTaskService.read_canonical_attempt_events("t", "a")
    ]
    assert [(p["sequence"], p["state"], p["reason"]) for p in payloads] == [
        (1, "DIRECT_RECONCILE_REQUIRED", "e"),
        (2, "DIRECT_RECONCILE_REQUIRED", "B2"),
    ]


def test_record_canonical_action_failure_delegates(
    monkeypatch: pytest.MonkeyPatch, service: SelfHostedTaskService
) -> None:
    calls: list[Any] = []

    def record(self: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append((args, kwargs))
        return {"recorded": len(calls)}

    monkeypatch.setattr(SelfHostedTaskService, "_record_direct_failure", record)
    assert service.record_canonical_action_failure("t", "B") == {"recorded": 1}
    assert service.record_canonical_action_failure("t", "B", "E") == {"recorded": 2}
    assert calls == [(("t", "B", ""), {}), (("t", "B", "E"), {})]


# ---------------------------------------------------------------------------
# facade bindings


def test_facade_bindings_are_the_collaborator_objects() -> None:
    from nexus.core import task_continuity
    from nexus.events import contracts as event_contracts
    from nexus.events import transport

    assert service_module.NexusEventBus is transport.NexusEventBus
    assert (
        service_module.build_attempt_transition_event
        is event_contracts.build_attempt_transition_event
    )
    assert service_module.events_from_attempt_records is task_continuity.events_from_attempt_records
    assert service_module.project is task_continuity.project
    assert (
        service_module.build_rehydration_projection is task_continuity.build_rehydration_projection
    )
    assert service_module.canonical_request_hash is canonical_request_hash


def test_state_snapshot_json_round_trip_is_untouched_by_reads(
    service: SelfHostedTaskService, state_dir: Path, pipeline: list[Any]
) -> None:
    _seed(service, "t", status="FINAL_BLOCK", request={"repository": "r", "issue": 1})
    raw = (state_dir / "t.json").read_bytes()
    service.rehydrate_task_continuation("t")
    service.rehydrate_project_entry("t", None, repository="r", issue_number=1)
    assert (state_dir / "t.json").read_bytes() == raw
    assert json.loads(raw)["task_id"] == "t"
