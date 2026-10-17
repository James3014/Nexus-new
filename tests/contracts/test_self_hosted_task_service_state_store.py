"""Characterization of the state-store core of ``SelfHostedTaskService`` (split S6b).

Big-file split step S6b moves the state-store members of ``SelfHostedTaskService`` out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin.  Every task state write
goes through them.  These tests pin the behaviour before the move and must pass unchanged
after it:

* the paths (``_state_path``, ``_archive_root``, ``_archive_state_path``, ``_lock_path``,
  ``_archive_state_candidates``) and the task-id refusals of the runtime store;
* the invalid-state receipts (``_invalid_state_status``, ``_state_error_receipt``) and
  every refusal of ``_validate_state_payload``, in their precedence order;
* ``_load_state_path``, ``_latest_archived_state`` (archive selection),
  ``_read_state`` / ``_read_state_snapshot`` (lock-taking versus lock-free reads, archive
  fallback), ``_create_state`` (existing, archived and corrupt states are never
  overwritten), ``_reactivate_archived_state``, ``_mutate_state`` (every refusal leaves the
  file untouched) and ``_require_integrated_replacement`` (every refusal);
* ``_normalize_state_write`` / ``_write_state`` / ``_write_state_locked``: the persisted
  bytes (sorted keys, two-space indent, trailing newline, ``task_action`` computed from the
  normalised state), the file mode, no temporary file left behind;
* the state lock (an exclusive ``flock`` on ``<state>/.state.lock`` that another open file
  description cannot take while it is held, released on error) and the lock / store / I/O
  order of every state-store flow;
* that the facade-module names the moved code reads (``_jsonable``,
  ``DURABLE_SELF_HOSTED_STATUSES``, ``ExecutionStateStore``) are resolved through the facade
  at call time, that class, subclass and instance patches of one state-store member are
  reached from the others and from the facade's own callers, and which members the
  constructor binds into the runtime store (``_state_error_receipt`` and
  ``_normalize_state_write`` at construction, ``_validate_state_payload`` at call time).
"""

from __future__ import annotations

import enum
import fcntl
import hashlib
import inspect
import json
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator, cast

import pytest
from nexus_runtime import task_lifecycle
from nexus_runtime.execution_state import ExecutionStateStore

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

MEMBERS = {
    "_state_path": ("function", "(self, task_id: 'str') -> 'Path'"),
    "_archive_root": ("function", "(self) -> 'Path'"),
    "_archive_state_path": ("function", "(self, task_id: 'str') -> 'Path'"),
    "_archive_state_candidates": ("function", "(self, task_id: 'str') -> 'list[Path]'"),
    "_require_integrated_replacement": (
        "function",
        "(self, task_id: 'str', superseded_by: 'str') -> 'None'",
    ),
    "_invalid_state_status": (
        "classmethod",
        "(cls, task_id: 'str', *, code: 'str', detail: 'str', source_path: 'Path', "
        "approval_requirements_reasons: 'Sequence[str]' = ()) -> 'dict[str, Any]'",
    ),
    "_state_error_receipt": (
        "classmethod",
        "(cls, task_id: 'str', path: 'Path', error: 'BaseException') -> 'dict[str, Any]'",
    ),
    "_validate_state_payload": (
        "classmethod",
        "(cls, task_id: 'str', payload: 'Mapping[str, Any]', source_path: 'Path') "
        "-> 'dict[str, Any]'",
    ),
    "_load_state_path": (
        "classmethod",
        "(cls, path: 'Path', task_id: 'str') -> 'Optional[dict[str, Any]]'",
    ),
    "_latest_archived_state": (
        "function",
        "(self, task_id: 'str') -> 'tuple[Optional[Path], Optional[dict[str, Any]]]'",
    ),
    "_lock_path": ("function", "(self) -> 'Path'"),
    "_state_lock": ("function", "(self) -> 'Iterator[None]'"),
    "_write_state_locked": (
        "function",
        "(self, task_id: 'str', state: 'dict[str, Any]') -> 'dict[str, Any]'",
    ),
    "_normalize_state_write": (
        "function",
        "(self, task_id: 'str', state: 'Mapping[str, Any]') -> 'Mapping[str, Any]'",
    ),
    "_write_state": (
        "function",
        "(self, task_id: 'str', state: 'dict[str, Any]') -> 'dict[str, Any]'",
    ),
    "_create_state": (
        "function",
        "(self, task_id: 'str', state: 'dict[str, Any]') -> 'tuple[dict[str, Any], bool]'",
    ),
    "_read_state": ("function", "(self, task_id: 'str') -> 'Optional[dict[str, Any]]'"),
    "_read_state_snapshot": (
        "function",
        "(self, task_id: 'str') -> 'Optional[dict[str, Any]]'",
    ),
    "_reactivate_archived_state": (
        "function",
        "(self, task_id: 'str', state: 'dict[str, Any]') -> 'dict[str, Any]'",
    ),
    "_mutate_state": (
        "function",
        "(self, task_id: 'str', mutator: 'Callable[[dict[str, Any]], None]') "
        "-> 'Optional[dict[str, Any]]'",
    ),
}

BAD_TASK_IDS = ["", "  ", "a/b", "a\\b", "a*", "a?", "a[b]", "a\0b", "..", "..x", "."]


@pytest.fixture
def service(tmp_path: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)


def _envelope(state: dict[str, Any]) -> dict[str, Any]:
    return SelfHostedTaskService._task_action_envelope(state)


def _with_action(state: dict[str, Any]) -> dict[str, Any]:
    return {**state, "task_action": _envelope(state)}


def _put(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
    return path


def _archive(service: SelfHostedTaskService, name: str, value: Any) -> Path:
    return _put(service._archive_root() / name, value)


def _invalid(task_id: str, code: str, detail: str, path: Path, reasons: list[str] | None = None):
    blocker: dict[str, Any] = {"code": code, "detail": detail, "source_path": str(path)}
    if reasons:
        blocker["approval_requirements_reasons"] = reasons
    return _with_action({
        "schema": "nexus.self_hosted_task_status.v1",
        "task_id": task_id,
        "status": "BLOCKED_INVALID_STATE",
        "found": True,
        "state_valid": False,
        "retry_authorized": False,
        "blocker": blocker,
    })


def _must(value: dict[str, Any] | None) -> dict[str, Any]:
    assert value is not None
    return value


def _tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# ---------------------------------------------------------------------------
# member table


def test_members_keep_descriptor_kinds_and_signatures() -> None:
    for name, (kind, signature) in MEMBERS.items():
        static = inspect.getattr_static(SelfHostedTaskService, name)
        assert type(static).__name__ == kind, name
        func = static.__func__ if isinstance(static, classmethod) else static
        assert str(inspect.signature(func)) == signature, name


def test_state_lock_is_a_generator_context_manager() -> None:
    static = inspect.getattr_static(SelfHostedTaskService, "_state_lock")
    assert inspect.isgeneratorfunction(static.__wrapped__)


# ---------------------------------------------------------------------------
# paths


def test_paths(service: SelfHostedTaskService, tmp_path: Path) -> None:
    root = (tmp_path / "state").resolve()
    assert service.state_dir == root
    assert service._state_path("t-1") == root / "t-1.json"
    assert service._archive_root() == root.parent / "nexus-state-archive"
    assert service._archive_state_path("t-1") == root.parent / "nexus-state-archive" / "t-1.json"
    assert service._lock_path() == root / ".state.lock"
    assert not root.exists()


@pytest.mark.parametrize("task_id", BAD_TASK_IDS)
def test_state_path_refuses_unsafe_task_ids(service: SelfHostedTaskService, task_id: str) -> None:
    with pytest.raises(ValueError, match="task_id must not"):
        service._state_path(task_id)
    with pytest.raises(ValueError, match="task_id must not"):
        service._archive_state_candidates(task_id)
    with pytest.raises(ValueError, match="task_id must not"):
        service._read_state_snapshot(task_id)
    with pytest.raises(ValueError, match="task_id must not"):
        service._latest_archived_state(task_id)


@pytest.mark.parametrize("task_id", [None, 5, b"t"])
def test_state_path_refuses_non_string_task_ids(
    service: SelfHostedTaskService, task_id: Any
) -> None:
    with pytest.raises(ValueError, match="task_id must be a string"):
        service._state_path(task_id)


def test_archive_paths_do_not_validate_the_task_id(service: SelfHostedTaskService) -> None:
    # _archive_state_path is a plain join (no runtime-store validation)
    assert service._archive_state_path("a/b") == service._archive_root() / "a/b.json"


def test_archive_state_candidates_order_and_existence(service: SelfHostedTaskService) -> None:
    assert service._archive_state_candidates("t") == []
    root = service._archive_root()
    _archive(service, "t--attempt-b.json", {})
    _archive(service, "t--attempt-a.json", {})
    _archive(service, "t-other.json", {})
    _archive(service, "tt--attempt-a.json", {})
    assert service._archive_state_candidates("t") == [
        root / "t--attempt-a.json",
        root / "t--attempt-b.json",
    ]
    _archive(service, "t.json", {})
    assert service._archive_state_candidates("t") == [
        root / "t.json",
        root / "t--attempt-a.json",
        root / "t--attempt-b.json",
    ]
    assert not service.state_dir.exists()


# ---------------------------------------------------------------------------
# invalid-state receipts


def test_invalid_state_status_shape(tmp_path: Path) -> None:
    result = SelfHostedTaskService._invalid_state_status(
        "t", code="C", detail="d", source_path=tmp_path / "x.json"
    )
    assert result == _invalid("t", "C", "d", tmp_path / "x.json")
    assert list(result) == [
        "schema",
        "task_id",
        "status",
        "found",
        "state_valid",
        "retry_authorized",
        "blocker",
        "task_action",
    ]
    assert list(result["blocker"]) == ["code", "detail", "source_path"]
    assert result["task_action"]["action_state"] == "FINAL_BLOCK"
    assert result["task_action"]["next_action"] == "inspect_lifecycle_state"


def test_invalid_state_status_reasons_are_sorted_and_deduplicated(tmp_path: Path) -> None:
    result = SelfHostedTaskService._invalid_state_status(
        "t",
        code="C",
        detail="d",
        source_path=tmp_path,
        approval_requirements_reasons=("b", "a", "b"),
    )
    assert result["blocker"] == {
        "code": "C",
        "detail": "d",
        "source_path": str(tmp_path),
        "approval_requirements_reasons": ["a", "b"],
    }
    empty = SelfHostedTaskService._invalid_state_status(
        "t", code="C", detail="d", source_path=tmp_path, approval_requirements_reasons=[]
    )
    assert "approval_requirements_reasons" not in empty["blocker"]


@pytest.mark.parametrize(
    ("error", "code", "detail"),
    [
        (
            json.JSONDecodeError("Expecting value", "\n\n  x", 4),
            "STATE_JSON_INVALID",
            "state JSON is invalid at line 3 column 3",
        ),
        (
            ValueError("state JSON must decode to an object"),
            "STATE_NOT_OBJECT",
            "state JSON must decode to an object",
        ),
        (
            ValueError("state JSON must decode to an object "),
            "STATE_READ_FAILED",
            "state file could not be read: ValueError",
        ),
        (ValueError("other"), "STATE_READ_FAILED", "state file could not be read: ValueError"),
        (
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"),
            "STATE_READ_FAILED",
            "state file could not be read: UnicodeDecodeError",
        ),
        (OSError("x"), "STATE_READ_FAILED", "state file could not be read: OSError"),
        (
            IsADirectoryError("x"),
            "STATE_READ_FAILED",
            "state file could not be read: IsADirectoryError",
        ),
        (KeyError("x"), "STATE_READ_FAILED", "state file could not be read: KeyError"),
    ],
)
def test_state_error_receipt(tmp_path: Path, error: BaseException, code: str, detail: str) -> None:
    path = tmp_path / "t.json"
    assert SelfHostedTaskService._state_error_receipt("t", path, error) == _invalid(
        "t", code, detail, path
    )


# ---------------------------------------------------------------------------
# _validate_state_payload


VALID = {"task_id": "t", "status": "SUBMITTED"}


@pytest.mark.parametrize(
    ("payload", "code", "detail", "reasons"),
    [
        (["x"], "STATE_NOT_OBJECT", "state JSON must decode to an object", None),
        ("x", "STATE_NOT_OBJECT", "state JSON must decode to an object", None),
        (
            {"status": "SUBMITTED"},
            "STATE_FIELD_INVALID",
            "state task_id is missing or does not match its filename",
            None,
        ),
        (
            {"task_id": "u", "status": "SUBMITTED"},
            "STATE_FIELD_INVALID",
            "state task_id is missing or does not match its filename",
            None,
        ),
        (
            {"task_id": 5, "status": "SUBMITTED"},
            "STATE_FIELD_INVALID",
            "state task_id is missing or does not match its filename",
            None,
        ),
        ({"task_id": "t"}, "STATE_FIELD_INVALID", "state status must be a non-empty string", None),
        (
            {"task_id": "t", "status": "  "},
            "STATE_FIELD_INVALID",
            "state status must be a non-empty string",
            None,
        ),
        (
            {"task_id": "t", "status": 3},
            "STATE_FIELD_INVALID",
            "state status must be a non-empty string",
            None,
        ),
        (
            {"task_id": "t", "status": "NOPE"},
            "STATE_FIELD_INVALID",
            "state status is invalid or unknown: 'NOPE'",
            None,
        ),
        (
            {"task_id": "t", "status": " SUBMITTED"},
            "STATE_FIELD_INVALID",
            "state status is invalid or unknown: ' SUBMITTED'",
            None,
        ),
        (
            {**VALID, "attempts": {}},
            "STATE_FIELD_INVALID",
            "state attempts must be a list of objects",
            None,
        ),
        (
            {**VALID, "attempts": None},
            "STATE_FIELD_INVALID",
            "state attempts must be a list of objects",
            None,
        ),
        (
            {**VALID, "attempts": [{}, 1]},
            "STATE_FIELD_INVALID",
            "state attempts must be a list of objects",
            None,
        ),
        (
            {**VALID, "executions": ({},)},
            "STATE_FIELD_INVALID",
            "state executions must be a list of objects",
            None,
        ),
        (
            {**VALID, "executions": ["x"], "attempts": ["y"]},
            "STATE_FIELD_INVALID",
            "state attempts must be a list of objects",
            None,
        ),
        ({**VALID, "action": "x"}, "STATE_FIELD_INVALID", "state action must be an object", []),
        (
            {**VALID, "attempt_resolution": 1},
            "STATE_FIELD_INVALID",
            "state attempt_resolution must be an object",
            [],
        ),
        ({**VALID, "contract": []}, "STATE_FIELD_INVALID", "state contract must be an object", []),
        ({**VALID, "lease": "x"}, "STATE_FIELD_INVALID", "state lease must be an object", []),
        ({**VALID, "request": 0}, "STATE_FIELD_INVALID", "state request must be an object", []),
        (
            {**VALID, "promotion_packet": "x"},
            "STATE_FIELD_INVALID",
            "state promotion_packet must be an object",
            ["malformed_source:promotion_packet:expected_mapping"],
        ),
        (
            {**VALID, "verified_receipt": False},
            "STATE_FIELD_INVALID",
            "state verified_receipt must be an object",
            ["malformed_source:verified_receipt:expected_mapping"],
        ),
        (
            {**VALID, "verified_receipt": 1, "promotion_packet": 1, "request": 1, "lease": 1},
            "STATE_FIELD_INVALID",
            "state lease must be an object",
            [
                "malformed_source:promotion_packet:expected_mapping",
                "malformed_source:verified_receipt:expected_mapping",
            ],
        ),
        # precedence: task_id before status before lists before objects
        (
            {"task_id": "u", "status": "NOPE", "attempts": 1, "lease": 1},
            "STATE_FIELD_INVALID",
            "state task_id is missing or does not match its filename",
            None,
        ),
        (
            {"task_id": "t", "status": "NOPE", "attempts": 1, "lease": 1},
            "STATE_FIELD_INVALID",
            "state status is invalid or unknown: 'NOPE'",
            None,
        ),
        (
            {"task_id": "t", "status": "SUBMITTED", "executions": 1, "lease": 1},
            "STATE_FIELD_INVALID",
            "state executions must be a list of objects",
            None,
        ),
    ],
)
def test_validate_state_payload_refusals(
    tmp_path: Path, payload: Any, code: str, detail: str, reasons: list[str] | None
) -> None:
    path = tmp_path / "t.json"
    frozen = json.dumps(payload, sort_keys=True, default=repr)
    result = SelfHostedTaskService._validate_state_payload("t", payload, path)
    assert result == _invalid("t", code, detail, path, reasons)
    assert json.dumps(payload, sort_keys=True, default=repr) == frozen


@pytest.mark.parametrize("status", sorted(task_lifecycle.DURABLE_SELF_HOSTED_STATUSES))
def test_validate_state_payload_accepts_every_durable_status(tmp_path: Path, status: str) -> None:
    payload = {"task_id": "t", "status": status}
    result = SelfHostedTaskService._validate_state_payload("t", payload, tmp_path)
    assert result == _with_action(payload)
    assert result is not payload and "task_action" not in payload


def test_validate_state_payload_accepts_none_objects_empty_lists_and_mappings(
    tmp_path: Path,
) -> None:
    payload = MappingProxyType({
        **VALID,
        "attempts": [],
        "executions": [MappingProxyType({})],
        "action": None,
        "attempt_resolution": None,
        "contract": {},
        "lease": MappingProxyType({}),
        "promotion_packet": None,
        "request": {},
        "verified_receipt": None,
        "task_action": {"stale": True},
        "other": "kept",
    })
    result = SelfHostedTaskService._validate_state_payload("t", payload, tmp_path)
    assert type(result) is dict
    expected = {key: value for key, value in payload.items() if key != "task_action"}
    assert result == _with_action(expected)
    assert result["task_action"] != {"stale": True}


def test_a_persisted_invalid_state_receipt_is_not_a_durable_status(tmp_path: Path) -> None:
    assert (
        service_module.DURABLE_SELF_HOSTED_STATUSES is task_lifecycle.DURABLE_SELF_HOSTED_STATUSES
    )
    assert "BLOCKED_INVALID_STATE" not in task_lifecycle.DURABLE_SELF_HOSTED_STATUSES
    receipt = SelfHostedTaskService._invalid_state_status(
        "t", code="C", detail="d", source_path=tmp_path
    )
    assert SelfHostedTaskService._validate_state_payload("t", receipt, tmp_path) == _invalid(
        "t",
        "STATE_FIELD_INVALID",
        "state status is invalid or unknown: 'BLOCKED_INVALID_STATE'",
        tmp_path,
    )


# ---------------------------------------------------------------------------
# _load_state_path / _latest_archived_state


def test_load_state_path(tmp_path: Path) -> None:
    load = SelfHostedTaskService._load_state_path
    assert load(tmp_path / "t.json", "t") is None
    good = _put(tmp_path / "t.json", {"task_id": "t", "status": "FINAL_BLOCK"})
    assert load(good, "t") == _with_action({"task_id": "t", "status": "FINAL_BLOCK"})
    # any file name: the task id is checked against the payload, not the file name
    other = _put(tmp_path / "other.json", {"task_id": "t", "status": "FINAL_BLOCK"})
    assert load(other, "t") == _with_action({"task_id": "t", "status": "FINAL_BLOCK"})
    bad = _put(tmp_path / "bad.json", "{\n")
    assert load(bad, "t") == _invalid(
        "t", "STATE_JSON_INVALID", "state JSON is invalid at line 2 column 1", bad
    )
    array = _put(tmp_path / "array.json", "[1]")
    assert load(array, "t") == _invalid(
        "t", "STATE_NOT_OBJECT", "state JSON must decode to an object", array
    )
    binary = tmp_path / "binary.json"
    binary.write_bytes(b"\xff\xfe")
    assert (
        _must(load(binary, "t"))["blocker"]["detail"]
        == "state file could not be read: UnicodeDecodeError"
    )
    folder = tmp_path / "dir.json"
    folder.mkdir()
    assert (
        _must(load(folder, "t"))["blocker"]["detail"]
        == "state file could not be read: IsADirectoryError"
    )
    wrong = _put(tmp_path / "wrong.json", {"task_id": "u", "status": "FINAL_BLOCK"})
    assert _must(load(wrong, "t"))["blocker"]["code"] == "STATE_FIELD_INVALID"
    with pytest.raises(ValueError, match="task_id must not"):
        load(good, "a/b")
    assert not (tmp_path / ".state.lock").exists()


def test_latest_archived_state_selection(service: SelfHostedTaskService) -> None:
    assert service._latest_archived_state("t") == (None, None)
    root = service._archive_root()
    a = _archive(
        service,
        "t.json",
        {"task_id": "t", "status": "FINAL_BLOCK", "updated_at": "2026-01-02", "n": 1},
    )
    b = _archive(
        service,
        "t--attempt-1.json",
        {"task_id": "t", "status": "FINAL_BLOCK", "updated_at": "2026-01-01", "n": 2},
    )
    os.utime(a, ns=(1_000_000_000, 1_000_000_000))
    os.utime(b, ns=(9_000_000_000, 9_000_000_000))
    path, state = service._latest_archived_state("t")
    assert path == root / "t.json" and state is not None and state["n"] == 1
    # equal updated_at: the newer mtime wins
    _put(b, {"task_id": "t", "status": "FINAL_BLOCK", "updated_at": "2026-01-02", "n": 2})
    os.utime(b, ns=(9_000_000_000, 9_000_000_000))
    path, state = service._latest_archived_state("t")
    assert path == b and state == _with_action({
        "task_id": "t",
        "status": "FINAL_BLOCK",
        "updated_at": "2026-01-02",
        "n": 2,
    })
    assert not service.state_dir.exists()


def test_latest_archived_state_includes_invalid_archives(service: SelfHostedTaskService) -> None:
    # an unreadable archive yields an invalid-state receipt (no updated_at) that still competes
    corrupt = _archive(service, "t--attempt-z.json", "{")
    os.utime(corrupt, ns=(9_000_000_000, 9_000_000_000))
    path, state = service._latest_archived_state("t")
    assert path == corrupt and state is not None and state["status"] == "BLOCKED_INVALID_STATE"
    good = _archive(service, "t.json", {"task_id": "t", "status": "FINAL_BLOCK", "updated_at": "1"})
    os.utime(good, ns=(1_000_000_000, 1_000_000_000))
    path, state = service._latest_archived_state("t")
    assert path == good and state is not None and state["status"] == "FINAL_BLOCK"


# ---------------------------------------------------------------------------
# the state lock


def _lock_free(path: Path) -> bool:
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return True


def test_state_lock_is_an_exclusive_flock_on_the_lock_file(service: SelfHostedTaskService) -> None:
    lock = service.state_dir / ".state.lock"
    assert not service.state_dir.exists()
    with service._state_lock():
        assert lock.is_file() and lock.read_bytes() == b""
        assert not _lock_free(lock)
    assert _lock_free(lock)
    assert sorted(p.name for p in service.state_dir.iterdir()) == [".state.lock"]


def test_state_lock_is_released_when_the_body_raises(service: SelfHostedTaskService) -> None:
    lock = service.state_dir / ".state.lock"
    with pytest.raises(RuntimeError, match="boom"), service._state_lock():
        raise RuntimeError("boom")
    assert _lock_free(lock)


def test_write_state_waits_for_another_holder(service: SelfHostedTaskService) -> None:
    import threading

    service.state_dir.mkdir(parents=True)
    lock = service.state_dir / ".state.lock"
    done = threading.Event()
    with lock.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        thread = threading.Thread(
            target=lambda: (
                service._write_state("t", {"task_id": "t", "status": "SUBMITTED"}),
                done.set(),
            )
        )
        thread.start()
        assert not done.wait(0.3)
        assert not service._state_path("t").exists()
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    thread.join(10)
    assert done.is_set() and service._state_path("t").exists()


# ---------------------------------------------------------------------------
# normalisation and the persisted bytes


class _Color(enum.Enum):
    RED = "red"


@dataclass
class _Point:
    x: int
    tags: tuple[str, ...]


class _Model:
    def model_dump(self, mode: str) -> dict[Any, Any]:
        return {"mode": mode, 1: _Color.RED}


class _Plain:
    def __init__(self) -> None:
        self.a = (1, 2)


def test_normalize_state_write(service: SelfHostedTaskService) -> None:
    state = {
        "task_id": "t",
        "status": "SUBMITTED",
        "color": _Color.RED,
        "point": _Point(1, ("a",)),
        "model": _Model(),
        "plain": _Plain(),
        "items": ("x", [_Color.RED]),
        3: "int key",
        "task_action": {"stale": True},
    }
    frozen = dict(state)
    normalized = service._normalize_state_write("t", state)
    assert type(normalized) is dict
    expected = {
        "task_id": "t",
        "status": "SUBMITTED",
        "color": "red",
        "point": {"x": 1, "tags": ["a"]},
        "model": {"mode": "json", "1": "red"},
        "plain": {"a": [1, 2]},
        "items": ["x", ["red"]],
        "3": "int key",
        "task_action": {"stale": True},
    }
    expected["task_action"] = _envelope(expected)
    assert normalized == expected
    assert list(normalized) == list(expected)
    assert state == frozen


def test_write_state_persisted_bytes(service: SelfHostedTaskService) -> None:
    state = {"task_id": "t", "status": "FINAL_BLOCK", "error": "x", "b": [1, {"z": 1, "a": None}]}
    written = service._write_state("t", state)
    path = service._state_path("t")
    expected = _with_action(state)
    assert written == expected
    assert path.read_bytes() == (json.dumps(expected, sort_keys=True, indent=2) + "\n").encode()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert sorted(p.name for p in service.state_dir.iterdir()) == [".state.lock", "t.json"]
    assert "task_action" not in state


def test_write_state_persisted_bytes_pinned(service: SelfHostedTaskService) -> None:
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED", "ü": "é", "n": 1.5})
    data = service._state_path("t").read_bytes()
    assert '"\\u00fc": "\\u00e9"'.encode() in data
    assert data.startswith(b'{\n  "n": 1.5,\n  "status": "SUBMITTED",\n  "task_action": {\n')
    assert data.endswith(b'\n  "task_id": "t",\n  "\\u00fc": "\\u00e9"\n}\n')
    assert hashlib.sha256(data).hexdigest() == (
        "40749bbb046921f132669313fc640f6b9ee7099c84fd5f34346e8af68c2529b3"
    )


def test_write_state_does_not_validate(service: SelfHostedTaskService) -> None:
    written = service._write_state("t", {"task_id": "other", "status": "NOPE", "lease": 1})
    assert written["status"] == "NOPE"
    assert _must(service._read_state("t"))["blocker"]["detail"] == (
        "state task_id is missing or does not match its filename"
    )


def test_write_state_overwrites_and_returns_the_normalized_state(
    service: SelfHostedTaskService,
) -> None:
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED", "old": 1})
    written = service._write_state("t", {"task_id": "t", "status": "FINAL_BLOCK"})
    assert "old" not in json.loads(service._state_path("t").read_text())
    assert written == json.loads(service._state_path("t").read_text())


@pytest.mark.parametrize("task_id", ["a/b", "..", ""])
def test_write_state_refuses_unsafe_task_ids_inside_the_lock(
    service: SelfHostedTaskService, task_id: str
) -> None:
    with pytest.raises(ValueError, match="task_id must not"):
        service._write_state(task_id, {"task_id": task_id, "status": "SUBMITTED"})
    assert sorted(p.name for p in service.state_dir.iterdir()) == [".state.lock"]
    assert _lock_free(service.state_dir / ".state.lock")


def test_write_state_locked_takes_no_lock(service: SelfHostedTaskService) -> None:
    written = service._write_state_locked("t", {"task_id": "t", "status": "SUBMITTED"})
    assert written == _with_action({"task_id": "t", "status": "SUBMITTED"})
    assert sorted(p.name for p in service.state_dir.iterdir()) == ["t.json"]


# ---------------------------------------------------------------------------
# create / read / snapshot


def test_create_state_new_and_existing(service: SelfHostedTaskService) -> None:
    created, fresh = service._create_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert fresh is True and created == _with_action({"task_id": "t", "status": "SUBMITTED"})
    before = service._state_path("t").read_bytes()
    again, fresh = service._create_state("t", {"task_id": "t", "status": "FINAL_BLOCK"})
    assert fresh is False and again == created
    assert service._state_path("t").read_bytes() == before


def test_create_state_returns_a_corrupt_state_without_overwriting(
    service: SelfHostedTaskService,
) -> None:
    path = _put(service._state_path("t"), "{")
    result, fresh = service._create_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert fresh is False
    assert result == _invalid(
        "t", "STATE_JSON_INVALID", "state JSON is invalid at line 1 column 2", path
    )
    assert path.read_text() == "{"


def test_create_state_returns_an_archived_state_without_writing(
    service: SelfHostedTaskService,
) -> None:
    _archive(service, "t--attempt-1.json", {"task_id": "t", "status": "FINAL_BLOCK", "a": 1})
    result, fresh = service._create_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert fresh is False
    assert result == _with_action({"task_id": "t", "status": "FINAL_BLOCK", "a": 1})
    assert not service._state_path("t").exists()
    corrupt = _archive(service, "u.json", "[]")
    result, fresh = service._create_state("u", {"task_id": "u", "status": "SUBMITTED"})
    assert fresh is False and result == _invalid(
        "u", "STATE_NOT_OBJECT", "state JSON must decode to an object", corrupt
    )
    assert not service._state_path("u").exists()


def test_read_state(service: SelfHostedTaskService) -> None:
    assert service._read_state("t") is None
    # a missing task takes no lock (the state root is not even created)
    assert not service.state_dir.exists()
    _archive(service, "t.json", {"task_id": "t", "status": "FINAL_BLOCK"})
    assert service._read_state("t") == _with_action({"task_id": "t", "status": "FINAL_BLOCK"})
    assert not service.state_dir.exists()
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert service._read_state("t") == _with_action({"task_id": "t", "status": "SUBMITTED"})
    _put(service._state_path("t"), "nope")
    assert _must(service._read_state("t"))["blocker"]["code"] == "STATE_JSON_INVALID"


def test_read_state_returns_none_when_the_file_vanishes_before_the_lock(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    _archive(service, "t.json", {"task_id": "t", "status": "FINAL_BLOCK"})
    real = inspect.getattr_static(SelfHostedTaskService, "_state_lock")

    @contextmanager
    def vanishing(self_: Any) -> Iterator[None]:
        service._state_path("t").unlink()
        with real(self_):
            yield

    monkeypatch.setattr(service, "_state_lock", vanishing.__get__(service))
    # no archive fallback once the lock is taken
    assert service._read_state("t") is None


def test_read_state_snapshot(service: SelfHostedTaskService) -> None:
    assert service._read_state_snapshot("t") is None
    _archive(service, "t.json", {"task_id": "t", "status": "FINAL_BLOCK"})
    assert service._read_state_snapshot("t") == _with_action({
        "task_id": "t",
        "status": "FINAL_BLOCK",
    })
    assert not service.state_dir.exists()
    service.state_dir.mkdir()
    _put(service._state_path("t"), "{")
    # an unreadable active state wins over the archive
    assert _must(service._read_state_snapshot("t"))["blocker"]["code"] == "STATE_JSON_INVALID"
    _put(service._state_path("t"), {"task_id": "t", "status": "SUBMITTED"})
    assert service._read_state_snapshot("t") == _with_action({
        "task_id": "t",
        "status": "SUBMITTED",
    })
    assert sorted(p.name for p in service.state_dir.iterdir()) == ["t.json"]


# ---------------------------------------------------------------------------
# reactivation


def test_reactivate_archived_state_writes_when_an_archive_exists(
    service: SelfHostedTaskService,
) -> None:
    _archive(service, "t--attempt-1.json", {"task_id": "t", "status": "FINAL_BLOCK"})
    result = service._reactivate_archived_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert result == _with_action({"task_id": "t", "status": "SUBMITTED"})
    assert json.loads(service._state_path("t").read_text()) == result


def test_reactivate_archived_state_refuses_without_an_archive(
    service: SelfHostedTaskService,
) -> None:
    with pytest.raises(RuntimeError, match=r"^archived task receipt disappeared before retry$"):
        service._reactivate_archived_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert sorted(p.name for p in service.state_dir.iterdir()) == [".state.lock"]


def test_reactivate_archived_state_returns_an_existing_state_unvalidated(
    service: SelfHostedTaskService,
) -> None:
    raw = {"task_id": "other", "status": "NOPE", "task_action": {"stale": True}}
    _put(service._state_path("t"), raw)
    result = service._reactivate_archived_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert result == {**raw, "task_action": _envelope({"task_id": "other", "status": "NOPE"})}
    assert json.loads(service._state_path("t").read_text()) == raw
    _put(service._state_path("t"), "{")
    with pytest.raises(json.JSONDecodeError):
        service._reactivate_archived_state("t", {"task_id": "t", "status": "SUBMITTED"})


# ---------------------------------------------------------------------------
# mutation


def test_mutate_state(service: SelfHostedTaskService) -> None:
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED", "n": 1})
    seen: list[dict[str, Any]] = []

    def mutate(value: dict[str, Any]) -> None:
        seen.append(dict(value))
        value["status"] = "FINAL_BLOCK"
        value["n"] += 1

    result = service._mutate_state("t", mutate)
    # the mutator sees the raw file (including the stale task_action)
    assert seen == [_with_action({"task_id": "t", "status": "SUBMITTED", "n": 1})]
    expected = _with_action({"task_id": "t", "status": "FINAL_BLOCK", "n": 2})
    assert result == expected
    assert json.loads(service._state_path("t").read_text()) == expected


def test_mutate_state_missing_and_archived_tasks_are_none(service: SelfHostedTaskService) -> None:
    calls: list[Any] = []
    assert service._mutate_state("t", calls.append) is None
    _archive(service, "t.json", {"task_id": "t", "status": "FINAL_BLOCK"})
    assert service._mutate_state("t", calls.append) is None
    assert calls == []
    assert sorted(p.name for p in service.state_dir.iterdir()) == [".state.lock"]


@pytest.mark.parametrize(
    ("content", "mutator", "error", "message"),
    [
        ('{"task_id": "t", "status": "SUBMITTED"}', lambda value: 1 / 0, ZeroDivisionError, ""),
        ("{", lambda value: None, json.JSONDecodeError, ""),
        ("[1]", lambda value: None, ValueError, "execution state must be an object"),
    ],
)
def test_mutate_state_refusals_leave_the_file_untouched(
    service: SelfHostedTaskService, content: str, mutator: Any, error: type, message: str
) -> None:
    path = _put(service._state_path("t"), content)
    with pytest.raises(error, match=message):
        service._mutate_state("t", mutator)
    assert path.read_text() == content
    assert sorted(p.name for p in service.state_dir.iterdir()) == [".state.lock", "t.json"]
    assert _lock_free(service.state_dir / ".state.lock")


def test_mutate_state_ignores_the_mutator_return_value(service: SelfHostedTaskService) -> None:
    # the runtime bridge wraps the mutator, so the store's "return None" check never fires
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    result = service._mutate_state("t", cast(Any, lambda value: value.update(n=1) or value))
    assert result == _with_action({"task_id": "t", "status": "SUBMITTED", "n": 1})


def test_mutate_state_does_not_validate(service: SelfHostedTaskService) -> None:
    _put(service._state_path("t"), {"task_id": "other", "status": "NOPE"})
    result = service._mutate_state("t", lambda value: value.update(lease=1))
    assert result is not None and result["lease"] == 1 and result["task_id"] == "other"


# ---------------------------------------------------------------------------
# _require_integrated_replacement


INTEGRATED = {
    "task_id": "r",
    "status": "INTEGRATED",
    "promotion_status": "INTEGRATED",
    "integration_result_sha": "a" * 40,
}
REPLACEMENT_ERROR = (
    "superseded_by must name an existing INTEGRATED self-hosted task "
    "with promotion_status=INTEGRATED and integration_result_sha"
)


def test_require_integrated_replacement_accepts(service: SelfHostedTaskService) -> None:
    service._write_state("r", INTEGRATED)
    assert service._require_integrated_replacement("t", "r") is None
    _archive(service, "q.json", {**INTEGRATED, "task_id": "q"})
    assert service._require_integrated_replacement("t", "q") is None


@pytest.mark.parametrize(
    ("replacement", "task_id"),
    [
        (None, "t"),
        (INTEGRATED, "r"),
        ({**INTEGRATED, "task_id": "x"}, "t"),
        ({**INTEGRATED, "status": "INTEGRATED_AND_CLEANED"}, "t"),
        ({**INTEGRATED, "promotion_status": "APPROVED"}, "t"),
        ({**INTEGRATED, "integration_result_sha": "  "}, "t"),
        ({**INTEGRATED, "integration_result_sha": None}, "t"),
        ({key: value for key, value in INTEGRATED.items() if key != "integration_result_sha"}, "t"),
        ("{", "t"),
    ],
)
def test_require_integrated_replacement_refusals(
    service: SelfHostedTaskService, replacement: Any, task_id: str
) -> None:
    if replacement is not None:
        _put(service._state_path("r"), replacement)
    with pytest.raises(RuntimeError) as raised:
        service._require_integrated_replacement(task_id, "r")
    assert str(raised.value) == REPLACEMENT_ERROR


# ---------------------------------------------------------------------------
# lock / store / I/O order


class StoreRecorder:
    """Records the state-store members, the state lock, the runtime store and file effects."""

    MEMBERS = tuple(name for name in MEMBERS if name != "_state_lock")
    STORE = (
        "write_locked",
        "mutate_locked",
        "read_raw",
        "load_path",
        "read_snapshot",
        "latest_archive",
        "archive_candidates",
    )

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.events: list[str] = []
        events = self.events
        cls = SelfHostedTaskService
        lock = inspect.getattr_static(cls, "_state_lock")

        @contextmanager
        def state_lock(self_: Any) -> Iterator[None]:
            events.append("lock+")
            with lock(self_):
                yield
            events.append("lock-")

        monkeypatch.setattr(cls, "_state_lock", state_lock)
        for name in self.MEMBERS:
            static = inspect.getattr_static(cls, name)
            func = static.__func__ if isinstance(static, classmethod) else static
            wrapped = self._wrap(name, func)
            monkeypatch.setattr(
                cls, name, classmethod(wrapped) if isinstance(static, classmethod) else wrapped
            )
        for name in self.STORE:
            monkeypatch.setattr(
                ExecutionStateStore,
                name,
                self._wrap(f"store.{name}", getattr(ExecutionStateStore, name)),
            )
        store_lock = ExecutionStateStore.lock

        @contextmanager
        def recorded_store_lock(self_: Any) -> Iterator[None]:
            events.append("store.lock+")
            with store_lock(self_):
                yield
            events.append("store.lock-")

        monkeypatch.setattr(ExecutionStateStore, "lock", recorded_store_lock)
        real_flock, real_fsync, real_replace, real_os_open = (
            fcntl.flock,
            os.fsync,
            Path.replace,
            os.open,
        )

        def flock(fd: int, operation: int) -> None:
            events.append(
                "flock:" + {fcntl.LOCK_EX: "EX", fcntl.LOCK_UN: "UN"}.get(operation, str(operation))
            )
            real_flock(fd, operation)

        def fsync(fd: int) -> None:
            events.append("fsync")
            real_fsync(fd)

        def replace(self_: Path, target: Any) -> Path:
            events.append(f"replace:{Path(target).name}")
            return real_replace(self_, target)

        def os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            events.append("os.open:" + ("write" if flags & (os.O_WRONLY | os.O_RDWR) else "read"))
            return real_os_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(fcntl, "flock", flock)
        monkeypatch.setattr(os, "fsync", fsync)
        monkeypatch.setattr(Path, "replace", replace)
        monkeypatch.setattr(os, "open", os_open)

    def _wrap(self, name: str, func: Any) -> Any:
        events = self.events

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            events.append(name)
            try:
                return func(*args, **kwargs)
            except BaseException as exc:
                events.append(f"raise:{name}:{type(exc).__name__}")
                raise

        return wrapped

    def take(self) -> list[str]:
        taken = list(self.events)
        self.events.clear()
        return taken


@pytest.fixture
def recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[SelfHostedTaskService, StoreRecorder]:
    # The service binds ``_normalize_state_write`` / ``_state_error_receipt`` into its
    # runtime store when it is constructed, so the recorder is installed first.
    recorder = StoreRecorder(monkeypatch)
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    recorder.take()
    return service, recorder


LOCK = ["lock+", "store.lock+", "flock:EX"]
UNLOCK = ["flock:UN", "store.lock-", "lock-"]
WRITE_TAIL = [
    "_write_state_locked",
    "store.write_locked",
    "_normalize_state_write",
    "os.open:write",
    "fsync",
    "replace:t.json",
    "os.open:read",
    "fsync",
]
LOAD = ["_load_state_path", "store.load_path", "_validate_state_payload"]


def test_write_and_create_order(recorded: tuple[SelfHostedTaskService, StoreRecorder]) -> None:
    service, recorder = recorded
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    write = recorder.take()
    service._create_state("u", {"task_id": "u", "status": "SUBMITTED"})
    create = recorder.take()
    service._create_state("u", {"task_id": "u", "status": "SUBMITTED"})
    again = recorder.take()
    assert write == ["_write_state", *LOCK, *WRITE_TAIL, *UNLOCK]
    tail_u = [event.replace("t.json", "u.json") for event in WRITE_TAIL]
    assert create == [
        "_create_state",
        *LOCK,
        "_state_path",
        "_latest_archived_state",
        "store.latest_archive",
        "store.archive_candidates",
        *tail_u,
        *UNLOCK,
    ]
    assert again == ["_create_state", *LOCK, "_state_path", *LOAD, *UNLOCK]


def test_create_from_archive_order(recorded: tuple[SelfHostedTaskService, StoreRecorder]) -> None:
    service, recorder = recorded
    _archive(service, "t.json", {"task_id": "t", "status": "FINAL_BLOCK"})
    recorder.take()
    service._create_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert recorder.take() == [
        "_create_state",
        *LOCK,
        "_state_path",
        "_latest_archived_state",
        "store.latest_archive",
        "store.archive_candidates",
        "store.load_path",
        "_validate_state_payload",
        *UNLOCK,
    ]


def test_read_orders(recorded: tuple[SelfHostedTaskService, StoreRecorder]) -> None:
    service, recorder = recorded
    service._read_state("t")
    missing = recorder.take()
    service._read_state_snapshot("t")
    snapshot_missing = recorder.take()
    service._write_state_locked("t", {"task_id": "t", "status": "SUBMITTED"})
    recorder.take()
    service._read_state("t")
    read = recorder.take()
    service._read_state_snapshot("t")
    snapshot = recorder.take()
    assert missing == [
        "_read_state",
        "_state_path",
        "_latest_archived_state",
        "store.latest_archive",
        "store.archive_candidates",
    ]
    assert snapshot_missing == [
        "_read_state_snapshot",
        "store.read_snapshot",
        "store.load_path",
        "store.latest_archive",
        "store.archive_candidates",
    ]
    assert read == ["_read_state", "_state_path", *LOCK, *LOAD, *UNLOCK]
    assert snapshot == [
        "_read_state_snapshot",
        "store.read_snapshot",
        "store.load_path",
        "_validate_state_payload",
    ]


def test_invalid_read_order(recorded: tuple[SelfHostedTaskService, StoreRecorder]) -> None:
    service, recorder = recorded
    service.state_dir.mkdir()
    _put(service._state_path("t"), "{")
    recorder.take()
    service._read_state("t")
    assert recorder.take() == [
        "_read_state",
        "_state_path",
        *LOCK,
        "_load_state_path",
        "store.load_path",
        "_state_error_receipt",
        "_invalid_state_status",
        *UNLOCK,
    ]
    service._read_state_snapshot("t")
    assert recorder.take() == [
        "_read_state_snapshot",
        "store.read_snapshot",
        "store.load_path",
        "_state_error_receipt",
        "_invalid_state_status",
    ]


def test_mutate_order(recorded: tuple[SelfHostedTaskService, StoreRecorder]) -> None:
    service, recorder = recorded
    service._write_state_locked("t", {"task_id": "t", "status": "SUBMITTED"})
    recorder.take()
    service._mutate_state("t", lambda value: recorder.events.append("mutator"))
    assert recorder.take() == [
        "_mutate_state",
        *LOCK,
        "store.mutate_locked",
        "store.read_raw",
        "mutator",
        "store.write_locked",
        "_normalize_state_write",
        "os.open:write",
        "fsync",
        "replace:t.json",
        "os.open:read",
        "fsync",
        *UNLOCK,
    ]
    with pytest.raises(ZeroDivisionError):
        service._mutate_state("t", cast(Any, lambda value: 1 / 0))
    assert recorder.take() == [
        "_mutate_state",
        *LOCK,
        "store.mutate_locked",
        "store.read_raw",
        "raise:store.mutate_locked:ZeroDivisionError",
        "flock:UN",
        "raise:_mutate_state:ZeroDivisionError",
    ]
    service._mutate_state("missing", lambda value: None)
    assert recorder.take() == ["_mutate_state", *LOCK, "store.mutate_locked", *UNLOCK]


def test_reactivate_order(recorded: tuple[SelfHostedTaskService, StoreRecorder]) -> None:
    service, recorder = recorded
    _archive(service, "t.json", {"task_id": "t", "status": "FINAL_BLOCK"})
    recorder.take()
    service._reactivate_archived_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert recorder.take() == [
        "_reactivate_archived_state",
        *LOCK,
        "_state_path",
        "_archive_state_candidates",
        "store.archive_candidates",
        *WRITE_TAIL,
        *UNLOCK,
    ]
    service._reactivate_archived_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert recorder.take() == ["_reactivate_archived_state", *LOCK, "_state_path", *UNLOCK]
    with pytest.raises(RuntimeError):
        service._reactivate_archived_state("u", {"task_id": "u", "status": "SUBMITTED"})
    assert recorder.take() == [
        "_reactivate_archived_state",
        *LOCK,
        "_state_path",
        "_archive_state_candidates",
        "store.archive_candidates",
        "flock:UN",
        "raise:_reactivate_archived_state:RuntimeError",
    ]


def test_replacement_and_archive_path_order(
    recorded: tuple[SelfHostedTaskService, StoreRecorder],
) -> None:
    service, recorder = recorded
    service._archive_state_path("t")
    assert recorder.take() == ["_archive_state_path", "_archive_root"]
    with pytest.raises(RuntimeError):
        service._require_integrated_replacement("t", "r")
    assert recorder.take() == [
        "_require_integrated_replacement",
        "_read_state",
        "_state_path",
        "_latest_archived_state",
        "store.latest_archive",
        "store.archive_candidates",
        "raise:_require_integrated_replacement:RuntimeError",
    ]


# ---------------------------------------------------------------------------
# facade-module names the moved code reads (late binding)


def test_facade_jsonable_is_reached_by_normalization(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []

    def jsonable(value: Any) -> dict[str, Any]:
        seen.append(value)
        return {"task_id": "t", "status": "SUBMITTED", "patched": True}

    monkeypatch.setattr(service_module, "_jsonable", jsonable)
    written = service._write_state("t", {"task_id": "t", "status": "FINAL_BLOCK"})
    assert seen == [{"task_id": "t", "status": "FINAL_BLOCK"}]
    assert written == _with_action({"task_id": "t", "status": "SUBMITTED", "patched": True})
    assert json.loads(service._state_path("t").read_text()) == written


def test_facade_durable_statuses_are_reached_by_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        service_module,
        "DURABLE_SELF_HOSTED_STATUSES",
        (task_lifecycle.DURABLE_SELF_HOSTED_STATUSES - {"SUBMITTED"}) | {"PATCHED"},
    )
    validate = SelfHostedTaskService._validate_state_payload
    assert validate("t", {"task_id": "t", "status": "SUBMITTED"}, tmp_path)["blocker"][
        "detail"
    ] == ("state status is invalid or unknown: 'SUBMITTED'")
    assert validate("t", {"task_id": "t", "status": "PATCHED"}, tmp_path)["status"] == "PATCHED"


def test_facade_execution_state_store_is_reached_by_load_state_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[tuple[Path, dict[str, Any]]] = []

    class Recording(ExecutionStateStore):
        def __init__(self, state_dir: Path, **kwargs: Any) -> None:
            built.append((state_dir, kwargs))
            super().__init__(state_dir, **kwargs)

    monkeypatch.setattr(service_module, "ExecutionStateStore", Recording)
    path = _put(tmp_path / "x" / "t.json", {"task_id": "t", "status": "SUBMITTED"})
    assert _must(SelfHostedTaskService._load_state_path(path, "t"))["status"] == "SUBMITTED"
    assert [(state_dir, sorted(kwargs)) for state_dir, kwargs in built] == [
        (path.parent, ["error_receipt", "validate_writes", "validator"])
    ]
    kwargs = built[0][1]
    assert kwargs["validate_writes"] is False
    assert kwargs["validator"] == SelfHostedTaskService._validate_state_payload
    assert kwargs["error_receipt"] == SelfHostedTaskService._state_error_receipt


# ---------------------------------------------------------------------------
# class / subclass / instance patches


def test_constructor_binds_normalize_and_error_receipt_but_not_the_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    store = service._runtime_state_bridge.store
    assert store.before_write == service._normalize_state_write
    assert store.error_receipt == service._state_error_receipt
    assert store.validate_writes is False
    # patched after construction: the validator is reached, normalisation and the error
    # receipt are not (they were bound when the service was built)
    monkeypatch.setattr(
        SelfHostedTaskService, "_validate_state_payload", classmethod(lambda cls, t, p, s: {"v": 1})
    )
    monkeypatch.setattr(
        SelfHostedTaskService, "_normalize_state_write", lambda self, t, s: {"n": 1}
    )
    monkeypatch.setattr(
        SelfHostedTaskService, "_state_error_receipt", classmethod(lambda cls, t, p, e: {"e": 1})
    )
    written = service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert "n" not in written and written["task_action"]["task_status"] == "SUBMITTED"
    assert service._read_state_snapshot("t") == {"v": 1}
    _put(service._state_path("u"), "{")
    assert _must(service._read_state_snapshot("u"))["status"] == "BLOCKED_INVALID_STATE"
    # _load_state_path builds its store per call: every class patch is reached
    assert service._read_state("u") == {"e": 1}
    later = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    assert later._write_state("w", {"task_id": "w"}) == {"n": 1}
    assert later._read_state_snapshot("u") == {"e": 1}


def test_class_patches_of_store_members_are_reached_from_the_others(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    cls = SelfHostedTaskService

    def spy(name: str) -> None:
        static = inspect.getattr_static(cls, name)
        func = static.__func__ if isinstance(static, classmethod) else static

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            calls.append(name)
            return func(*args, **kwargs)

        monkeypatch.setattr(
            cls, name, classmethod(wrapped) if isinstance(static, classmethod) else wrapped
        )

    for name in (
        "_state_path",
        "_load_state_path",
        "_latest_archived_state",
        "_write_state_locked",
        "_archive_state_candidates",
        "_archive_root",
        "_invalid_state_status",
        "_state_error_receipt",
        "_read_state",
        "_validate_state_payload",
    ):
        spy(name)
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    service._create_state("t", {"task_id": "t", "status": "SUBMITTED"})
    service._create_state("u", {"task_id": "u", "status": "SUBMITTED"})
    _archive(service, "a.json", {"task_id": "a", "status": "FINAL_BLOCK"})
    service._reactivate_archived_state("a", {"task_id": "a", "status": "SUBMITTED"})
    service._archive_state_path("a")
    cls._validate_state_payload("t", cast(Any, []), Path("x"))
    with pytest.raises(RuntimeError):
        service._require_integrated_replacement("t", "u")
    assert calls == [
        # _write_state
        "_write_state_locked",
        # _create_state of an existing task
        "_state_path",
        "_load_state_path",
        "_validate_state_payload",
        # _create_state of a new task
        "_state_path",
        "_latest_archived_state",
        "_write_state_locked",
        # the test's own archive helper
        "_archive_root",
        # _reactivate_archived_state
        "_state_path",
        "_archive_state_candidates",
        "_write_state_locked",
        # _archive_state_path
        "_archive_root",
        # _validate_state_payload of a non-mapping
        "_validate_state_payload",
        "_state_error_receipt",
        "_invalid_state_status",
        # _require_integrated_replacement
        "_read_state",
        "_state_path",
        "_load_state_path",
        "_validate_state_payload",
    ]


def test_subclass_overrides_reach_every_receipt_and_validation_branch(tmp_path: Path) -> None:
    class Invalid(SelfHostedTaskService):
        @classmethod
        def _invalid_state_status(cls, task_id: str, **kwargs: Any) -> dict[str, Any]:
            return {"cls": cls.__name__, "code": kwargs["code"]}

    class Receipt(SelfHostedTaskService):
        @classmethod
        def _state_error_receipt(
            cls, task_id: str, path: Path, error: BaseException
        ) -> dict[str, Any]:
            return {"cls": cls.__name__, "error": type(error).__name__}

    class Validate(SelfHostedTaskService):
        @classmethod
        def _validate_state_payload(
            cls, task_id: str, payload: Any, source_path: Path
        ) -> dict[str, Any]:
            return {"cls": cls.__name__, "payload": dict(payload)}

    def code(value: Any) -> Any:
        return value["code"]

    # every branch of _state_error_receipt dispatches _invalid_state_status through cls
    assert Invalid._state_error_receipt("t", tmp_path, json.JSONDecodeError("x", "{", 1)) == {
        "cls": "Invalid",
        "code": "STATE_JSON_INVALID",
    }
    assert (
        code(
            Invalid._state_error_receipt(
                "t", tmp_path, ValueError("state JSON must decode to an object")
            )
        )
        == "STATE_NOT_OBJECT"
    )
    assert code(Invalid._state_error_receipt("t", tmp_path, OSError())) == "STATE_READ_FAILED"
    # every refusal of _validate_state_payload dispatches through cls
    for payload, expected in (
        ([], "STATE_NOT_OBJECT"),
        ({"task_id": "u"}, "STATE_FIELD_INVALID"),
        ({"task_id": "t", "status": "NOPE"}, "STATE_FIELD_INVALID"),
        ({"task_id": "t", "status": "SUBMITTED", "attempts": 1}, "STATE_FIELD_INVALID"),
        ({"task_id": "t", "status": "SUBMITTED", "lease": 1}, "STATE_FIELD_INVALID"),
    ):
        assert Invalid._validate_state_payload("t", cast(Any, payload), tmp_path) == {
            "cls": "Invalid",
            "code": expected,
        }
    assert Receipt._validate_state_payload("t", cast(Any, []), tmp_path) == {
        "cls": "Receipt",
        "error": "ValueError",
    }
    # _load_state_path builds its runtime store from cls
    bad = _put(tmp_path / "bad.json", "{")
    good = _put(tmp_path / "good.json", {"task_id": "t", "status": "SUBMITTED"})
    assert Receipt._load_state_path(bad, "t") == {"cls": "Receipt", "error": "JSONDecodeError"}
    assert Validate._load_state_path(good, "t") == {
        "cls": "Validate",
        "payload": {"task_id": "t", "status": "SUBMITTED"},
    }
    # and so do the instance read paths of a subclass service
    service = Validate(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert _must(service._read_state("t"))["cls"] == "Validate"
    assert _must(service._read_state_snapshot("t"))["cls"] == "Validate"
    receipt_service = Receipt(state_dir=tmp_path / "r", auto_reconcile=False, ephemeral=True)
    receipt_service.state_dir.mkdir()
    _put(receipt_service._state_path("t"), "{")
    assert receipt_service._read_state("t") == {"cls": "Receipt", "error": "JSONDecodeError"}
    assert receipt_service._read_state_snapshot("t") == {
        "cls": "Receipt",
        "error": "JSONDecodeError",
    }


def test_subclass_overrides_are_dispatched_through_self_and_cls(tmp_path: Path) -> None:
    calls: list[str] = []

    class Sub(SelfHostedTaskService):
        @classmethod
        def _invalid_state_status(cls, task_id: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(f"invalid:{cls.__name__}")
            return {"sub": kwargs["code"]}

        def _archive_root(self) -> Path:
            calls.append("archive_root")
            return tmp_path / "custom-archive"

        def _write_state_locked(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
            calls.append("write_locked")
            return {"sub": task_id}

    service = Sub(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    assert Sub._state_error_receipt("t", tmp_path, OSError()) == {"sub": "STATE_READ_FAILED"}
    assert Sub._validate_state_payload("t", {"task_id": "u"}, tmp_path) == {
        "sub": "STATE_FIELD_INVALID"
    }
    assert service._archive_state_path("t") == tmp_path / "custom-archive" / "t.json"
    assert service._write_state("t", {}) == {"sub": "t"}
    assert service._create_state("t", {}) == ({"sub": "t"}, True)
    assert calls == ["invalid:Sub", "invalid:Sub", "archive_root", "write_locked", "write_locked"]


def test_instance_patch_of_the_state_lock_is_reached_by_every_locking_member(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken: list[str] = []
    real = service._state_lock

    @contextmanager
    def lock() -> Iterator[None]:
        taken.append("lock")
        with real():
            yield

    monkeypatch.setattr(service, "_state_lock", lock)
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    service._create_state("t", {"task_id": "t", "status": "SUBMITTED"})
    service._read_state("t")
    service._mutate_state("t", lambda value: None)
    _archive(service, "a.json", {"task_id": "a", "status": "FINAL_BLOCK"})
    service._reactivate_archived_state("a", {"task_id": "a", "status": "SUBMITTED"})
    service._read_state_snapshot("t")
    service._write_state_locked("t", {"task_id": "t", "status": "SUBMITTED"})
    assert taken == ["lock"] * 5


def test_instance_patch_of_the_state_lock_failing_blocks_every_write(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    before = _tree(service.state_dir.parent)

    @contextmanager
    def fail_lock() -> Iterator[None]:
        raise OSError("lock unavailable")
        yield  # pragma: no cover

    monkeypatch.setattr(service, "_state_lock", fail_lock)
    for call in (
        lambda: service._write_state("t", {"task_id": "t", "status": "FINAL_BLOCK"}),
        lambda: service._create_state("u", {"task_id": "u", "status": "SUBMITTED"}),
        lambda: service._read_state("t"),
        lambda: service._mutate_state("t", lambda value: value.update(status="FINAL_BLOCK")),
        lambda: service._reactivate_archived_state("t", {"task_id": "t", "status": "FINAL_BLOCK"}),
    ):
        with pytest.raises(OSError, match="lock unavailable"):
            call()
    assert _tree(service.state_dir.parent) == before


def test_instance_patches_are_reached_from_facade_callers(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        service, "_mutate_state", lambda task_id, mutator: calls.append(("mutate", task_id))
    )
    monkeypatch.setattr(service, "_read_state", lambda task_id: calls.append(("read", task_id)))
    monkeypatch.setattr(
        service, "_read_state_snapshot", lambda task_id: calls.append(("snapshot", task_id))
    )
    service._set_child_pgid("t", "a", 5)
    with pytest.raises(KeyError):
        service.cancel_task("c")
    assert service.get_receipt("g") is None
    service._write_state_locked("s", {"task_id": "s", "status": "SUBMITTED"})
    service.lifecycle_status()
    with pytest.raises(RuntimeError):
        service._require_integrated_replacement("t", "r")
    assert calls == [
        ("mutate", "t"),
        ("read", "c"),
        ("read", "g"),
        ("snapshot", "s"),
        ("read", "r"),
    ]


def test_class_patch_of_archive_root_is_reached_from_archive_states(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(SelfHostedTaskService, "_archive_root", lambda self: tmp_path / "elsewhere")
    result = service.archive_states(dry_run=True)
    assert result["manifest_path"].startswith(str(tmp_path / "elsewhere") + os.sep)


def test_class_patch_of_state_path_is_reached_from_claims(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[str] = []

    def state_path(self: Any, task_id: str) -> Path:
        seen.append(task_id)
        return tmp_path / "nowhere.json"

    monkeypatch.setattr(SelfHostedTaskService, "_state_path", state_path)
    assert service.read_work_claim({"task_id": " t "}) == {
        "status": "NOT_FOUND",
        "reason": "TASK_NOT_FOUND",
        "found": False,
        "task_id": "t",
    }
    assert seen == ["t"]


def test_monkeypatch_undo_restores_the_inherited_members(monkeypatch: pytest.MonkeyPatch) -> None:
    before = {name: inspect.getattr_static(SelfHostedTaskService, name) for name in MEMBERS}
    with monkeypatch.context() as patch:
        for name in MEMBERS:
            patch.setattr(SelfHostedTaskService, name, lambda *args, **kwargs: None)
    after = {name: inspect.getattr_static(SelfHostedTaskService, name) for name in MEMBERS}
    assert all(after[name] is before[name] for name in MEMBERS)
    owners = {
        name: next(klass for klass in SelfHostedTaskService.__mro__ if name in vars(klass))
        for name in MEMBERS
    }
    assert len(set(owners.values())) == 1
