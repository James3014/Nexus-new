"""Characterization of ``SelfHostedTaskService.record_operator_outcome`` (split S7).

Big-file split step S7 moves ``record_operator_outcome`` out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin.  It appends one
privacy-bounded operator outcome receipt to the existing task state.  These tests pin the
behaviour before the move and must pass unchanged after it:

* the member table (descriptor kind, signature, docstring);
* the accepted inputs (a receipt model or a mapping) and the persisted bytes of a first
  append, a supersession chain and an idempotent replay (which rewrites identical bytes and
  returns the *latest* receipt, not the replayed one);
* every refusal, in precedence order, and that each one leaves the state file untouched:
  unknown task (``KeyError``), archive-only task (``AttributeError`` from the ``None`` the
  store returns), the pre-lock receipt identity checks (task / attempt / lifecycle /
  freshness, then action id, source revision and runtime receipt hash, with the
  ``contract.controller_revision`` fallback), the same checks repeated under the lock
  against the current state, the persisted-history tamper checks, the persisted
  supersession checks, idempotency conflicts and the new receipt's supersession checks;
* that the lifecycle is never changed (only ``operator_outcome_receipts``,
  ``operator_outcome_receipt`` and the derived ``task_action`` are written);
* the lock / I/O order: one locked ``_read_state``, the pre-lock checks outside the lock,
  then one ``_mutate_state`` whose checks run while the ``flock`` is held, no nested lock,
  the lock released on every refusal, a concurrent holder blocks the append, two concurrent
  appends serialise; no EventBus write and no file besides the state file and the lock;
* that the facade-module name the method reads (``validate_operator_outcome_receipt``) is
  resolved through the facade at call time, and that class and instance patches of
  ``_read_state`` / ``_mutate_state`` are reached.

Self-deadlocks fail fast instead of hanging CI: every test that waits on another thread
uses a daemon thread and a bounded ``join``; an autouse fixture bounds the runtime store's
blocking ``flock`` (it polls ``LOCK_EX | LOCK_NB`` and raises ``TimeoutError`` after 15 s,
so a nested state lock fails the test and releases the outer lock); and an autouse
``faulthandler`` watchdog aborts the run if a test still hangs for 120 s.
"""

from __future__ import annotations

import copy
import faulthandler
import fcntl
import hashlib
import inspect
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import nexus_runtime.execution_state.store as store_module
import pytest

import nexus.contracts.operator_outcome_receipt as receipt_module
import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.contracts.operator_outcome_receipt import (
    OperatorOutcomeReceipt,
    build_operator_outcome_receipt,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

NOW = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
SOURCE = "a" * 40
RUNTIME = "b" * 64
SIGNATURE = (
    "(self, task_id: 'str', receipt: 'OperatorOutcomeReceipt | Mapping[str, Any]') "
    "-> 'dict[str, Any]'"
)
DOC = (
    "Persist one privacy-bounded outcome in the existing task state.\n\n"
    "Idempotent replays return the original receipt.  A key reused with a\n"
    "different payload, a cross-attempt supersession, or a cycle fails\n"
    "closed; this method never changes task authority or lifecycle status."
)


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        return NOW if tz is None else NOW.astimezone(tz)


@pytest.fixture(autouse=True)
def _watchdog() -> Iterator[None]:
    # a self-deadlock (for example a nested state lock) must fail fast, not hang CI
    faulthandler.dump_traceback_later(120, exit=True)
    try:
        yield
    finally:
        faulthandler.cancel_dump_traceback_later()


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
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    # the freshness check reads datetime.now() in the receipt contract module
    monkeypatch.setattr(receipt_module, "datetime", _FixedDatetime)


@pytest.fixture
def service(tmp_path: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)


def _provenance(kind: str = "operator") -> dict[str, dict[str, str]]:
    source = (
        {"source_ref": "authenticated-submission"}
        if kind == "operator"
        else {"source_hash": "c" * 64}
    )
    return {
        field: {"provenance": kind, **source}
        for field in (
            "observed_outcome",
            "observation_basis",
            "reason_code",
            "observed_at",
            "source_revision",
            "runtime_receipt_hash",
        )
    }


def _receipt(**overrides: Any) -> OperatorOutcomeReceipt:
    values: dict[str, Any] = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "action_id": "action-1",
        "lifecycle_revision": "life-1",
        "source_revision": SOURCE,
        "runtime_receipt_hash": RUNTIME,
        "observed_outcome": "SUCCESS",
        "observation_basis": "OPERATOR_REPORT",
        "reason_code": "OPERATOR_CONFIRMED",
        "idempotency_key": "idem-1",
        "field_provenance": _provenance(),
        "observed_at": NOW - timedelta(seconds=60),
        "recorded_at": NOW - timedelta(seconds=30),
    }
    values.update(overrides)
    return build_operator_outcome_receipt(**values)


def _state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": "task-1",
        "status": "SUBMITTED",
        "attempt_id": "attempt-1",
        "action_id": "action-1",
        "lifecycle_revision": "life-1",
        "controller_revision": SOURCE,
        "runtime_receipt_hash": RUNTIME,
        "status_history": [{"status": "SUBMITTED", "at": "2026-10-18T11:00:00Z"}],
    }
    state.update(overrides)
    return {k: v for k, v in state.items() if v is not _DROP}


_DROP = object()


def _seed(service: SelfHostedTaskService, task_id: str = "task-1", **overrides: Any) -> Path:
    service._write_state(task_id, _state(task_id=task_id, **overrides))
    return service._state_path(task_id)


def _tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _must(value: dict[str, Any] | None) -> dict[str, Any]:
    assert value is not None
    return value


def _dump(receipt: OperatorOutcomeReceipt) -> dict[str, Any]:
    return receipt.model_dump(mode="json")


def _lock_free(path: Path) -> bool:
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return True


def _refused(
    service: SelfHostedTaskService,
    receipt: Any,
    error: type[BaseException],
    message: str,
    task_id: str = "task-1",
) -> BaseException:
    before = _tree(service.state_dir)
    with pytest.raises(error) as caught:
        service.record_operator_outcome(task_id, receipt)
    assert str(caught.value) == message
    assert _tree(service.state_dir) == before
    lock = service.state_dir / ".state.lock"
    assert not lock.exists() or _lock_free(lock)
    return caught.value


# ---------------------------------------------------------------------------
# member table


def test_member_kind_signature_and_docstring() -> None:
    static = inspect.getattr_static(SelfHostedTaskService, "record_operator_outcome")
    assert type(static).__name__ == "function"
    assert str(inspect.signature(static)) == SIGNATURE
    assert inspect.getdoc(static) == DOC
    assert static.__name__ == "record_operator_outcome"


# ---------------------------------------------------------------------------
# success, persisted bytes, idempotency


EXPECTED_FIRST_SHA256 = "d8ae853c9bd683561691b7168b0af329b6ea88b3a5efc53f4625fde183e9e842"


def test_first_append_persists_both_fields_and_returns_the_receipt(
    service: SelfHostedTaskService,
) -> None:
    path = _seed(service)
    before = json.loads(path.read_text())
    receipt = _receipt()
    result = service.record_operator_outcome("task-1", receipt)
    assert result == _dump(receipt)
    after = json.loads(path.read_text())
    assert after["operator_outcome_receipts"] == [_dump(receipt)]
    assert after["operator_outcome_receipt"] == _dump(receipt)
    changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
    assert changed == {"operator_outcome_receipts", "operator_outcome_receipt"}
    # lifecycle and authority untouched
    for key in (
        "status",
        "status_history",
        "attempt_id",
        "lifecycle_revision",
        "action_id",
        "task_action",
    ):
        assert after[key] == before[key], key
    raw = path.read_bytes()
    assert (
        raw.endswith(b"}\n")
        and raw == (json.dumps(after, sort_keys=True, indent=2) + "\n").encode()
    )
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_FIRST_SHA256
    assert sorted(p.name for p in service.state_dir.iterdir()) == [".state.lock", "task-1.json"]
    # the return value is a fresh dict
    result["observed_outcome"] = "FAILURE"
    assert (
        _must(service._read_state("task-1"))["operator_outcome_receipt"]["observed_outcome"]
        == "SUCCESS"
    )


def test_mapping_input_is_equivalent_to_the_model(
    service: SelfHostedTaskService, tmp_path: Path
) -> None:
    other = SelfHostedTaskService(
        state_dir=tmp_path / "other", auto_reconcile=False, ephemeral=True
    )
    _seed(service)
    _seed(other)
    receipt = _receipt()
    assert service.record_operator_outcome("task-1", receipt) == other.record_operator_outcome(
        "task-1", _dump(receipt)
    )
    assert service._state_path("task-1").read_bytes() == other._state_path("task-1").read_bytes()


def test_idempotent_replay_rewrites_identical_bytes(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _seed(service)
    receipt = _receipt()
    first = service.record_operator_outcome("task-1", receipt)
    raw = path.read_bytes()
    replaced: list[str] = []
    real_replace = os.replace

    def _spy_replace(src, dst, *args, **kwargs):  # type: ignore[no-untyped-def]
        replaced.append(os.fspath(dst))
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", _spy_replace)
    assert service.record_operator_outcome("task-1", receipt) == first
    assert service.record_operator_outcome("task-1", _dump(receipt)) == first
    assert path.read_bytes() == raw
    # the store still replaces the file (atomic write of the unchanged state);
    # observed via os.replace, not the inode number, which Linux may reuse.
    assert replaced.count(os.fspath(path)) == 2
    assert json.loads(raw)["operator_outcome_receipts"] == [first]


def test_replay_of_an_older_receipt_returns_the_latest(service: SelfHostedTaskService) -> None:
    _seed(service)
    old = _receipt(idempotency_key="k-old")
    new = _receipt(
        idempotency_key="k-new",
        observed_at=NOW - timedelta(seconds=20),
        recorded_at=NOW - timedelta(seconds=10),
    )
    service.record_operator_outcome("task-1", old)
    service.record_operator_outcome("task-1", new)
    assert service.record_operator_outcome("task-1", old) == _dump(new)
    state = _must(service._read_state("task-1"))
    assert [r["idempotency_key"] for r in state["operator_outcome_receipts"]] == ["k-old", "k-new"]


def test_independent_receipts_append_in_order(service: SelfHostedTaskService) -> None:
    _seed(service)
    receipts = [
        _receipt(idempotency_key=f"k{i}", observed_outcome=outcome, reason_code=reason)
        for i, (outcome, reason) in enumerate([
            ("SUCCESS", "OPERATOR_CONFIRMED"),
            ("FAILURE", "OPERATOR_CONFIRMED"),
            ("PARTIAL", "REWORK_REQUIRED"),
        ])
    ]
    for receipt in receipts:
        assert service.record_operator_outcome("task-1", receipt) == _dump(receipt)
    state = _must(service._read_state("task-1"))
    assert state["operator_outcome_receipts"] == [_dump(r) for r in receipts]
    assert state["operator_outcome_receipt"] == _dump(receipts[-1])


EXPECTED_CHAIN_SHA256 = "7e22d44754d0b81916fe57ccf1c77a0f20601b4b5f851081888ab32c3b407833"


def test_supersession_chain_and_branching(service: SelfHostedTaskService) -> None:
    path = _seed(service)
    a = _receipt(
        idempotency_key="a",
        observed_at=NOW - timedelta(seconds=90),
        recorded_at=NOW - timedelta(seconds=80),
    )
    b = _receipt(
        idempotency_key="b",
        supersedes_receipt_id=a.receipt_id,
        observed_at=NOW - timedelta(seconds=70),
        recorded_at=NOW - timedelta(seconds=60),
    )
    c = _receipt(
        idempotency_key="c",
        supersedes_receipt_id=b.receipt_id,
        observed_at=NOW - timedelta(seconds=50),
        recorded_at=NOW - timedelta(seconds=40),
    )
    # a second child of a (branching) is not refused
    d = _receipt(
        idempotency_key="d",
        supersedes_receipt_id=a.receipt_id,
        observed_at=NOW - timedelta(seconds=30),
        recorded_at=NOW - timedelta(seconds=20),
    )
    for receipt in (a, b, c, d):
        assert service.record_operator_outcome("task-1", receipt) == _dump(receipt)
    state = json.loads(path.read_text())
    assert [r["idempotency_key"] for r in state["operator_outcome_receipts"]] == [
        "a",
        "b",
        "c",
        "d",
    ]
    assert state["operator_outcome_receipt"]["idempotency_key"] == "d"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED_CHAIN_SHA256


def test_optional_bindings_may_be_absent(service: SelfHostedTaskService) -> None:
    _seed(service, action_id=_DROP, controller_revision=_DROP, runtime_receipt_hash=_DROP)
    receipt = _receipt(action_id=None, source_revision=None, runtime_receipt_hash=None)
    result = service.record_operator_outcome("task-1", receipt)
    assert result["action_id"] is None and result["source_revision"] is None
    assert result["runtime_receipt_hash"] is None


def test_action_id_none_is_accepted_against_a_bound_state(service: SelfHostedTaskService) -> None:
    _seed(service)
    assert service.record_operator_outcome("task-1", _receipt(action_id=None))["action_id"] is None


def test_state_bindings_are_stripped_and_contract_revision_is_a_fallback(
    service: SelfHostedTaskService,
) -> None:
    _seed(
        service,
        action_id="  action-1  ",
        controller_revision=_DROP,
        contract={"controller_revision": f" {SOURCE} "},
        runtime_receipt_hash=f"\t{RUNTIME}\n",
    )
    assert service.record_operator_outcome("task-1", _receipt())["source_revision"] == SOURCE


def test_stale_persisted_history_is_accepted(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service)
    old = _receipt(idempotency_key="old")
    service.record_operator_outcome("task-1", old)

    class _Later(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
            return NOW + timedelta(days=3)

    monkeypatch.setattr(receipt_module, "datetime", _Later)
    fresh = _receipt(
        idempotency_key="new",
        observed_at=NOW + timedelta(days=3, seconds=-20),
        recorded_at=NOW + timedelta(days=3, seconds=-10),
    )
    assert service.record_operator_outcome("task-1", fresh) == _dump(fresh)
    # replaying the stale receipt is refused by the fresh-receipt check, not treated as a replay
    _refused(service, old, ValueError, "OPERATOR_OUTCOME_RECEIPT_STALE")


# ---------------------------------------------------------------------------
# refusals before the lock


def test_unknown_task_raises_key_error_without_creating_files(
    service: SelfHostedTaskService,
) -> None:
    with pytest.raises(KeyError) as caught:
        service.record_operator_outcome("task-1", _receipt())
    assert caught.value.args == ("unknown task: task-1",)
    assert not service.state_dir.exists() or _tree(service.state_dir) == {}


def test_archive_only_task_raises_attribute_error_and_writes_nothing(
    service: SelfHostedTaskService,
) -> None:
    archive = service._archive_root()
    archive.mkdir(parents=True)
    (archive / "task-1.json").write_text(json.dumps(_state()), encoding="utf-8")
    archived_bytes = (archive / "task-1.json").read_bytes()
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'get'"):
        service.record_operator_outcome("task-1", _receipt())
    assert (archive / "task-1.json").read_bytes() == archived_bytes
    assert not service._state_path("task-1").exists()


def test_invalid_state_file_is_refused_through_the_invalid_receipt(
    service: SelfHostedTaskService,
) -> None:
    # _read_state returns the BLOCKED_INVALID_STATE receipt (no attempt id), so the
    # identity check refuses; the locked read creates the (empty) lock file
    service.state_dir.mkdir(parents=True)
    service._state_path("task-1").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        service.record_operator_outcome("task-1", _receipt())
    assert str(caught.value) == "OPERATOR_OUTCOME_ATTEMPT_ID_MISMATCH"
    assert service._state_path("task-1").read_text(encoding="utf-8") == "{"
    assert sorted(p.name for p in service.state_dir.iterdir()) == [".state.lock", "task-1.json"]
    assert _lock_free(service.state_dir / ".state.lock")
    # a structurally invalid state (non-object contract) is refused the same way
    _seed(service, "task-2", contract="not-a-mapping")
    _refused(
        service,
        _receipt(task_id="task-2"),
        ValueError,
        "OPERATOR_OUTCOME_ATTEMPT_ID_MISMATCH",
        "task-2",
    )


@pytest.mark.parametrize(
    ("state_overrides", "receipt_overrides", "message"),
    [
        ({}, {"task_id": "task-2"}, "OPERATOR_OUTCOME_TASK_ID_MISMATCH"),
        ({}, {"attempt_id": "attempt-2"}, "OPERATOR_OUTCOME_ATTEMPT_ID_MISMATCH"),
        ({"attempt_id": _DROP}, {}, "OPERATOR_OUTCOME_ATTEMPT_ID_MISMATCH"),
        ({}, {"lifecycle_revision": "life-2"}, "OPERATOR_OUTCOME_LIFECYCLE_REVISION_MISMATCH"),
        ({"lifecycle_revision": _DROP}, {}, "OPERATOR_OUTCOME_LIFECYCLE_REVISION_MISMATCH"),
        (
            {},
            {
                "observed_at": NOW - timedelta(seconds=301),
                "recorded_at": NOW - timedelta(seconds=30),
            },
            "OPERATOR_OUTCOME_RECEIPT_STALE",
        ),
        (
            {},
            {"observed_at": NOW - timedelta(seconds=10), "recorded_at": NOW + timedelta(seconds=1)},
            "OPERATOR_OUTCOME_RECEIPT_STALE",
        ),
        ({}, {"action_id": "action-2"}, "OPERATOR_OUTCOME_ACTION_ID_MISMATCH"),
        ({"action_id": _DROP}, {}, "OPERATOR_OUTCOME_ACTION_ID_MISMATCH"),
        ({"action_id": "  "}, {}, "OPERATOR_OUTCOME_ACTION_ID_MISMATCH"),
        ({}, {"source_revision": "c" * 40}, "OPERATOR_OUTCOME_SOURCE_REVISION_MISMATCH"),
        ({"controller_revision": _DROP}, {}, "OPERATOR_OUTCOME_SOURCE_REVISION_MISMATCH"),
        (
            {"controller_revision": "c" * 40, "contract": {"controller_revision": SOURCE}},
            {},
            "OPERATOR_OUTCOME_SOURCE_REVISION_MISMATCH",
        ),
        ({}, {"runtime_receipt_hash": "c" * 64}, "OPERATOR_OUTCOME_RUNTIME_RECEIPT_HASH_MISMATCH"),
        ({"runtime_receipt_hash": _DROP}, {}, "OPERATOR_OUTCOME_RUNTIME_RECEIPT_HASH_MISMATCH"),
        # precedence: identity, then action id, then source revision, then runtime hash
        (
            {},
            {"attempt_id": "attempt-2", "action_id": "action-2", "source_revision": "c" * 40},
            "OPERATOR_OUTCOME_ATTEMPT_ID_MISMATCH",
        ),
        (
            {},
            {
                "action_id": "action-2",
                "source_revision": "c" * 40,
                "runtime_receipt_hash": "c" * 64,
            },
            "OPERATOR_OUTCOME_ACTION_ID_MISMATCH",
        ),
        (
            {},
            {"source_revision": "c" * 40, "runtime_receipt_hash": "c" * 64},
            "OPERATOR_OUTCOME_SOURCE_REVISION_MISMATCH",
        ),
    ],
)
def test_pre_lock_refusals_never_reach_the_mutation(
    service: SelfHostedTaskService,
    monkeypatch: pytest.MonkeyPatch,
    state_overrides: dict[str, Any],
    receipt_overrides: dict[str, Any],
    message: str,
) -> None:
    _seed(service, **state_overrides)
    calls: list[str] = []
    real = service._mutate_state
    monkeypatch.setattr(
        service, "_mutate_state", lambda *a, **k: (calls.append("mutate"), real(*a, **k))[1]
    )
    _refused(service, _receipt(**receipt_overrides), ValueError, message)
    assert calls == []


def test_malformed_mapping_is_refused_by_the_model(service: SelfHostedTaskService) -> None:
    _seed(service)
    payload = _dump(_receipt())
    payload["observed_outcome"] = "FAILURE"
    error = _refused(service, payload, ValueError, str(_model_error(payload)))
    assert "OPERATOR_OUTCOME_PAYLOAD_HASH_MISMATCH" in str(error)
    extra = {**_dump(_receipt()), "operator": "alice"}
    error = _refused(service, extra, ValueError, str(_model_error(extra)))
    assert "extra_forbidden" in str(error) or "Extra inputs" in str(error)


def _model_error(payload: dict[str, Any]) -> BaseException:
    try:
        OperatorOutcomeReceipt.model_validate(payload)
    except ValueError as exc:
        return exc
    raise AssertionError("payload unexpectedly valid")


# ---------------------------------------------------------------------------
# refusals repeated under the lock (the state changed after the first read)


@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ({"attempt_id": "attempt-2"}, "OPERATOR_OUTCOME_ATTEMPT_ID_MISMATCH"),
        ({"lifecycle_revision": "life-2"}, "OPERATOR_OUTCOME_LIFECYCLE_REVISION_MISMATCH"),
        ({"action_id": "action-2"}, "OPERATOR_OUTCOME_ACTION_ID_MISMATCH"),
        ({"action_id": _DROP}, "OPERATOR_OUTCOME_ACTION_ID_MISMATCH"),
        ({"controller_revision": "c" * 40}, "OPERATOR_OUTCOME_SOURCE_REVISION_MISMATCH"),
        ({"controller_revision": _DROP}, "OPERATOR_OUTCOME_SOURCE_REVISION_MISMATCH"),
        ({"runtime_receipt_hash": "c" * 64}, "OPERATOR_OUTCOME_RUNTIME_RECEIPT_HASH_MISMATCH"),
        ({"runtime_receipt_hash": _DROP}, "OPERATOR_OUTCOME_RUNTIME_RECEIPT_HASH_MISMATCH"),
        (
            {"attempt_id": "attempt-2", "action_id": "action-2"},
            "OPERATOR_OUTCOME_ATTEMPT_ID_MISMATCH",
        ),
        (
            {"action_id": "action-2", "runtime_receipt_hash": "c" * 64},
            "OPERATOR_OUTCOME_ACTION_ID_MISMATCH",
        ),
    ],
)
def test_checks_are_repeated_against_the_current_state_under_the_lock(
    service: SelfHostedTaskService,
    monkeypatch: pytest.MonkeyPatch,
    drift: dict[str, Any],
    message: str,
) -> None:
    _seed(service, **drift)
    # the first (unlocked-path) read sees the original state; the locked mutation sees the drift
    monkeypatch.setattr(service, "_read_state", lambda task_id: _state(task_id=task_id))
    _refused(service, _receipt(), ValueError, message)


def test_contract_fallback_is_used_under_the_lock_too(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service, controller_revision=_DROP, contract={"controller_revision": SOURCE})
    monkeypatch.setattr(service, "_read_state", lambda task_id: _state(task_id=task_id))
    assert service.record_operator_outcome("task-1", _receipt())["source_revision"] == SOURCE
    _seed(service, "task-2", controller_revision=_DROP, contract=["not", "a", "mapping"])
    monkeypatch.setattr(service, "_read_state", lambda task_id: _state(task_id=task_id))
    _refused(
        service,
        _receipt(task_id="task-2"),
        ValueError,
        "OPERATOR_OUTCOME_SOURCE_REVISION_MISMATCH",
        "task-2",
    )


# ---------------------------------------------------------------------------
# persisted history: tamper and supersession checks


def _history(*receipts: OperatorOutcomeReceipt) -> dict[str, Any]:
    dumped = [_dump(r) for r in receipts]
    return {
        "operator_outcome_receipts": dumped,
        "operator_outcome_receipt": dumped[-1] if dumped else _DROP,
    }


def _later(seconds: int, **overrides: Any) -> OperatorOutcomeReceipt:
    return _receipt(
        observed_at=NOW - timedelta(seconds=seconds),
        recorded_at=NOW - timedelta(seconds=seconds - 5),
        **overrides,
    )


@pytest.mark.parametrize(
    ("history", "message"),
    [
        ({"operator_outcome_receipts": None}, "OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED"),
        ({"operator_outcome_receipts": {}}, "OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED"),
        ({"operator_outcome_receipts": "[]"}, "OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED"),
        ({"operator_outcome_receipts": [1]}, "OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED"),
        ({"operator_outcome_receipts": [[]]}, "OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED"),
        ({"operator_outcome_receipt": {"x": 1}}, "OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED"),
    ],
)
def test_malformed_history_containers_are_refused(
    service: SelfHostedTaskService, history: dict[str, Any], message: str
) -> None:
    _seed(service, **history)
    _refused(service, _receipt(), ValueError, message)


def test_history_and_singular_projection_must_agree(service: SelfHostedTaskService) -> None:
    a, b = _later(200, idempotency_key="a"), _later(150, idempotency_key="b")
    cases = [
        {"operator_outcome_receipts": [_dump(a)]},  # singular missing
        {"operator_outcome_receipts": [_dump(a)], "operator_outcome_receipt": None},
        {"operator_outcome_receipts": [_dump(a)], "operator_outcome_receipt": "x"},
        {"operator_outcome_receipts": [_dump(a), _dump(b)], "operator_outcome_receipt": _dump(a)},
        {"operator_outcome_receipts": [], "operator_outcome_receipt": _dump(a)},
    ]
    for index, history in enumerate(cases):
        task_id = f"task-{index}"
        _seed(service, task_id, **history)
        _refused(
            service,
            _receipt(task_id=task_id),
            ValueError,
            "OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED",
            task_id,
        )


def test_empty_history_without_singular_is_accepted(service: SelfHostedTaskService) -> None:
    _seed(service, operator_outcome_receipts=[])
    assert service.record_operator_outcome("task-1", _receipt()) == _dump(_receipt())


def test_forged_persisted_item_is_tampered(service: SelfHostedTaskService) -> None:
    forged = {**_dump(_later(200, idempotency_key="a")), "observed_outcome": "FAILURE"}
    _seed(service, operator_outcome_receipts=[forged], operator_outcome_receipt=forged)
    error = _refused(service, _receipt(), ValueError, "OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED")
    assert isinstance(error.__cause__, ValueError)
    assert "OPERATOR_OUTCOME_PAYLOAD_HASH_MISMATCH" in str(error.__cause__)


def test_persisted_item_of_another_task_is_tampered(service: SelfHostedTaskService) -> None:
    foreign = _dump(_later(200, idempotency_key="f", task_id="task-x"))
    _seed(service, operator_outcome_receipts=[foreign], operator_outcome_receipt=foreign)
    error = _refused(service, _receipt(), ValueError, "OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED")
    assert str(error.__cause__) == "OPERATOR_OUTCOME_TASK_ID_MISMATCH"


def test_duplicate_persisted_receipt_ids_are_tampered(service: SelfHostedTaskService) -> None:
    a = _later(200, idempotency_key="a")
    _seed(
        service, operator_outcome_receipts=[_dump(a), _dump(a)], operator_outcome_receipt=_dump(a)
    )
    _refused(service, _receipt(), ValueError, "OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED")


def _chain(task_id: str, *specs: tuple[str, int, str | None, str]) -> list[OperatorOutcomeReceipt]:
    """Build receipts from (key, age in seconds, parent key or raw id, attempt) specs."""
    built: dict[str, OperatorOutcomeReceipt] = {}
    for key, age, parent, attempt in specs:
        parent_id = built[parent].receipt_id if parent in built else parent
        built[key] = _later(
            age,
            idempotency_key=key,
            task_id=task_id,
            attempt_id=attempt,
            supersedes_receipt_id=parent_id,
        )
    return list(built.values())


@pytest.mark.parametrize(
    ("specs", "order", "message"),
    [
        (
            [("a", 200, None, "attempt-1"), ("b", 150, "d" * 64, "attempt-1")],
            None,
            "OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_TARGET_MISSING",
        ),
        (
            [("a", 200, None, "attempt-1"), ("b", 150, "a", "attempt-0")],
            None,
            "OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_ATTEMPT_MISMATCH",
        ),
        (
            [("a", 200, None, "attempt-1"), ("b", 200, "a", "attempt-1")],
            None,
            "OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_ORDER_INVALID",
        ),
        (
            [("a", 150, None, "attempt-1"), ("b", 200, "a", "attempt-1")],
            None,
            "OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_ORDER_INVALID",
        ),
        # the child listed before its parent is still checked against it
        (
            [("a", 200, None, "attempt-1"), ("b", 200, "a", "attempt-1")],
            [1, 0],
            "OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_ORDER_INVALID",
        ),
        # a missing parent is reported before a later item's order violation
        (
            [
                ("a", 200, None, "attempt-1"),
                ("b", 150, "d" * 64, "attempt-1"),
                ("c", 200, "a", "attempt-1"),
            ],
            None,
            "OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_TARGET_MISSING",
        ),
        # attempt mismatch is checked before order
        (
            [("a", 150, None, "attempt-1"), ("b", 200, "a", "attempt-0")],
            None,
            "OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_ATTEMPT_MISMATCH",
        ),
    ],
)
def test_persisted_supersession_checks(
    service: SelfHostedTaskService,
    specs: list[tuple[str, int, str | None, str]],
    order: list[int] | None,
    message: str,
) -> None:
    receipts = _chain("task-1", *specs)
    if order is not None:
        receipts = [receipts[i] for i in order]
    _seed(service, **_history(*receipts))
    _refused(service, _receipt(idempotency_key="new"), ValueError, message)


def test_valid_persisted_chain_with_a_prior_attempt_is_accepted(
    service: SelfHostedTaskService,
) -> None:
    receipts = _chain(
        "task-1",
        ("a", 250, None, "attempt-0"),
        ("b", 200, "a", "attempt-0"),
        ("c", 150, None, "attempt-1"),
    )
    _seed(service, **_history(*receipts))
    fresh = _receipt(idempotency_key="new", supersedes_receipt_id=receipts[-1].receipt_id)
    assert service.record_operator_outcome("task-1", fresh) == _dump(fresh)


def test_persisted_checks_precede_idempotency(service: SelfHostedTaskService) -> None:
    receipt = _receipt()
    _seed(
        service,
        operator_outcome_receipts=[_dump(receipt), 1],
        operator_outcome_receipt=_dump(receipt),
    )
    _refused(service, receipt, ValueError, "OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED")


# ---------------------------------------------------------------------------
# idempotency conflicts and the new receipt's supersession checks


def test_idempotency_key_reused_with_a_different_payload(service: SelfHostedTaskService) -> None:
    _seed(service)
    service.record_operator_outcome("task-1", _receipt())
    _refused(
        service,
        _receipt(observed_outcome="FAILURE"),
        ValueError,
        "OPERATOR_OUTCOME_IDEMPOTENCY_CONFLICT",
    )


def test_new_supersession_target_missing(service: SelfHostedTaskService) -> None:
    _seed(service)
    _refused(
        service,
        _receipt(supersedes_receipt_id="d" * 64),
        ValueError,
        "OPERATOR_OUTCOME_SUPERSESSION_TARGET_MISSING",
    )


def test_new_supersession_of_a_prior_attempt(service: SelfHostedTaskService) -> None:
    prior = _later(200, idempotency_key="p", attempt_id="attempt-0")
    _seed(service, **_history(prior))
    _refused(
        service,
        _receipt(supersedes_receipt_id=prior.receipt_id),
        ValueError,
        "OPERATOR_OUTCOME_SUPERSESSION_ATTEMPT_MISMATCH",
    )


@pytest.mark.parametrize("delta", [0, 5])
def test_new_supersession_must_be_observed_later(
    service: SelfHostedTaskService, delta: int
) -> None:
    parent = _later(60, idempotency_key="p")
    _seed(service, **_history(parent))
    child = _receipt(
        idempotency_key="c",
        supersedes_receipt_id=parent.receipt_id,
        observed_at=NOW - timedelta(seconds=60 + delta),
        recorded_at=NOW - timedelta(seconds=1),
    )
    _refused(service, child, ValueError, "OPERATOR_OUTCOME_SUPERSESSION_ORDER_INVALID")


def test_idempotency_check_precedes_supersession_checks(service: SelfHostedTaskService) -> None:
    _seed(service)
    service.record_operator_outcome("task-1", _receipt(idempotency_key="k"))
    _refused(
        service,
        _receipt(idempotency_key="k", supersedes_receipt_id="d" * 64),
        ValueError,
        "OPERATOR_OUTCOME_IDEMPOTENCY_CONFLICT",
    )


# ---------------------------------------------------------------------------
# lock / I/O order, concurrency


def test_call_order_lock_scope_and_validator_arguments(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    prior = _later(200, idempotency_key="p")
    _seed(service, **_history(prior))
    lock = service.state_dir / ".state.lock"
    events: list[Any] = []
    real_lock = service._state_lock
    depth = [0]

    from contextlib import contextmanager

    @contextmanager
    def recording_lock() -> Iterator[None]:
        if depth[0]:
            raise RuntimeError("nested state lock")  # fail fast instead of self-deadlocking
        depth[0] += 1
        events.append("lock+")
        try:
            with real_lock():
                yield
        finally:
            depth[0] -= 1
            events.append("lock-")

    real_validate = service_module.validate_operator_outcome_receipt

    def validate(receipt: Any, **kwargs: Any) -> Any:
        events.append((
            "validate",
            tuple(sorted(kwargs.items())),
            "held" if not _lock_free(lock) else "free",
        ))
        return real_validate(receipt, **kwargs)

    real_read, real_mutate = service._read_state, service._mutate_state
    monkeypatch.setattr(service, "_state_lock", recording_lock)
    monkeypatch.setattr(service_module, "validate_operator_outcome_receipt", validate)
    monkeypatch.setattr(
        service, "_read_state", lambda t: (events.append(("read", t)), real_read(t))[1]
    )
    monkeypatch.setattr(
        service, "_mutate_state", lambda t, m: (events.append(("mutate", t)), real_mutate(t, m))[1]
    )
    service.record_operator_outcome("task-1", _receipt())
    identity = (
        ("attempt_id", "attempt-1"),
        ("lifecycle_revision", "life-1"),
        ("task_id", "task-1"),
    )
    assert events == [
        ("read", "task-1"),
        "lock+",
        "lock-",
        ("validate", identity, "free"),
        ("mutate", "task-1"),
        "lock+",
        ("validate", identity, "held"),
        ("validate", (("check_freshness", False), ("task_id", "task-1")), "held"),
        "lock-",
    ]
    assert _lock_free(lock)


def test_lock_is_released_after_an_in_lock_refusal(service: SelfHostedTaskService) -> None:
    _seed(service)
    service.record_operator_outcome("task-1", _receipt())
    _refused(
        service,
        _receipt(observed_outcome="FAILURE"),
        ValueError,
        "OPERATOR_OUTCOME_IDEMPOTENCY_CONFLICT",
    )
    assert _lock_free(service.state_dir / ".state.lock")
    assert (
        service.record_operator_outcome("task-1", _receipt(idempotency_key="k2"))["idempotency_key"]
        == "k2"
    )


def test_a_concurrent_lock_holder_blocks_the_append(service: SelfHostedTaskService) -> None:
    path = _seed(service)
    before = path.read_bytes()
    done = threading.Event()
    errors: list[BaseException] = []

    def run() -> None:
        try:
            service.record_operator_outcome("task-1", _receipt())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            done.set()

    with (service.state_dir / ".state.lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        assert not done.wait(0.3)
        assert path.read_bytes() == before
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    thread.join(10)
    assert not thread.is_alive() and done.is_set() and errors == []
    assert json.loads(path.read_text())["operator_outcome_receipt"] == _dump(_receipt())


def test_concurrent_appends_serialise(service: SelfHostedTaskService) -> None:
    _seed(service)
    receipts = [_receipt(idempotency_key=f"k{i}") for i in range(6)]
    errors: list[BaseException] = []
    barrier = threading.Barrier(len(receipts))

    def run(receipt: OperatorOutcomeReceipt) -> None:
        try:
            barrier.wait(5)
            service.record_operator_outcome("task-1", receipt)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(r,), daemon=True) for r in receipts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert not any(t.is_alive() for t in threads) and errors == []
    state = _must(service._read_state("task-1"))
    assert sorted(r["idempotency_key"] for r in state["operator_outcome_receipts"]) == [
        f"k{i}" for i in range(6)
    ]
    assert state["operator_outcome_receipt"] == state["operator_outcome_receipts"][-1]


def test_no_event_bus_write_and_no_extra_files(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service)
    calls: list[str] = []
    bus = service_module.NexusEventBus
    for name, value in list(vars(bus).items()):
        if callable(value) and not name.startswith("__"):
            monkeypatch.setattr(bus, name, lambda *a, _n=name, **k: calls.append(_n))
    service.record_operator_outcome("task-1", _receipt())
    assert calls == []
    assert sorted(str(p.relative_to(service.state_dir)) for p in service.state_dir.rglob("*")) == [
        ".state.lock",
        "task-1.json",
    ]


# ---------------------------------------------------------------------------
# late binding and patches


def test_facade_validator_patch_is_reached_by_every_call_site(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    prior = _later(200, idempotency_key="p")
    _seed(service, **_history(prior))
    seen: list[dict[str, Any]] = []
    real = service_module.validate_operator_outcome_receipt

    def recorder(receipt: Any, **kwargs: Any) -> Any:
        seen.append(kwargs)
        return real(receipt, **kwargs)

    monkeypatch.setattr(service_module, "validate_operator_outcome_receipt", recorder)
    service.record_operator_outcome("task-1", _receipt())
    assert len(seen) == 3
    assert [s.get("check_freshness", True) for s in seen] == [True, True, False]


def test_facade_validator_patch_can_refuse(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service)

    def refuse(receipt: Any, **kwargs: Any) -> Any:
        raise ValueError("PATCHED_REFUSAL")

    monkeypatch.setattr(service_module, "validate_operator_outcome_receipt", refuse)
    _refused(service, _receipt(), ValueError, "PATCHED_REFUSAL")


def test_facade_validator_patch_result_is_what_gets_persisted(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service)
    substitute = _receipt(idempotency_key="substituted")
    monkeypatch.setattr(
        service_module, "validate_operator_outcome_receipt", lambda receipt, **kwargs: substitute
    )
    assert service.record_operator_outcome("task-1", _receipt()) == _dump(substitute)


def test_class_patch_of_read_state_is_reached(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(SelfHostedTaskService, "_read_state", lambda self, task_id: None)
    with pytest.raises(KeyError):
        service.record_operator_outcome("task-1", _receipt())


def test_class_patch_of_mutate_state_is_reached(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service)
    seen: list[Any] = []

    def fake(self: Any, task_id: str, mutator: Any) -> dict[str, Any]:
        value = copy.deepcopy(_state())
        mutator(value)
        seen.append(task_id)
        return value

    monkeypatch.setattr(SelfHostedTaskService, "_mutate_state", fake)
    before = _tree(service.state_dir)
    assert service.record_operator_outcome("task-1", _receipt()) == _dump(_receipt())
    assert seen == ["task-1"] and _tree(service.state_dir) == before


def test_mutate_returning_a_state_without_the_singular_falls_back_to_the_normalized_receipt(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service)
    monkeypatch.setattr(service, "_mutate_state", lambda task_id, mutator: {})
    assert service.record_operator_outcome("task-1", _receipt()) == _dump(_receipt())


def test_subclass_override_of_read_state_is_reached(tmp_path: Path) -> None:
    class Sub(SelfHostedTaskService):
        def _read_state(self, task_id: str) -> dict[str, Any] | None:
            raise LookupError(f"sub:{task_id}")

    sub = Sub(state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True)
    with pytest.raises(LookupError, match="sub:task-1"):
        sub.record_operator_outcome("task-1", _receipt())
