"""Characterization of the module-level retry helpers of SHTS (split S5).

Big-file split step S5 moves eight module-level helpers out of
``nexus/orchestrator/self_hosted_task_service.py`` into a part module.  These tests pin
their behaviour before the move and must pass unchanged after it:

* ``_retry_request`` (the fresh attempt-scoped transport identity of a retry, for a plain
  and for an action-bound request, every denial and its order, the minted identity and
  the recomputed request hashes, input never mutated);
* ``_retry_semantic_payload`` and ``_terminal_retry_semantic_payload`` (exactly which
  transport / revision fields are dropped, the validate -> dispatch-validate -> strip
  order, the dispatch envelope copy);
* ``_terminal_retry_inherited_worktree_time_allowed``,
  ``_terminal_retry_pre_provider_state_allowed``, ``_terminal_retry_released_lease_proof``
  and ``_terminal_retry_verifier_static_failure_allowed`` (every guard, which ones are
  checked before the worktree-manager / lease-proof collaborators run, the exact
  collaborator calls and arguments, which exceptions are swallowed);
* ``_validate_retry_predecessor`` (every denial and its order);
* that every facade-module name the helpers read (including the helpers themselves when
  one calls another) is resolved through the facade at call time, so patches on
  ``nexus.orchestrator.self_hosted_task_service`` keep taking effect, also for the
  late-bound ``runtime_retry_bridge`` accessor and the facade's own callers.
"""

from __future__ import annotations

import copy
import inspect
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.contracts.lifecycle_action import LifecycleActionEnvelope, canonical_request_hash
from nexus.orchestrator import runtime_retry_bridge

# ---------------------------------------------------------------------------
# member table

MEMBERS = {
    "_retry_request": "(state: 'Mapping[str, Any]') -> 'dict[str, Any]'",
    "_retry_semantic_payload": "(request: 'Mapping[str, Any]') -> 'dict[str, Any]'",
    "_terminal_retry_semantic_payload": "(request: 'Mapping[str, Any]') -> 'dict[str, Any]'",
    "_terminal_retry_inherited_worktree_time_allowed": "(state: 'Mapping[str, Any]') -> 'bool'",
    "_terminal_retry_pre_provider_state_allowed": "(state: 'Mapping[str, Any]') -> 'bool'",
    "_terminal_retry_released_lease_proof": "(state: 'Mapping[str, Any]') -> 'bool'",
    "_terminal_retry_verifier_static_failure_allowed": "(state: 'Mapping[str, Any]') -> 'bool'",
    "_validate_retry_predecessor": (
        "(request: 'Mapping[str, Any]', predecessor: 'Optional[Mapping[str, Any]]') -> 'None'"
    ),
}


@pytest.mark.parametrize("name", sorted(MEMBERS))
def test_member_is_a_plain_function_with_pinned_signature(name: str) -> None:
    value = getattr(service_module, name)
    assert inspect.isfunction(value)
    assert value.__name__ == name
    assert str(inspect.signature(value)) == MEMBERS[name]


def test_retryable_statuses_are_pinned() -> None:
    assert service_module.RETRYABLE_TASK_STATUSES == frozenset({"FINAL_BLOCK", "CANCELLED"})


class Recorder:
    """Callable that records its arguments and returns (or raises) a fixed value."""

    def __init__(self, log: list[Any], name: str, result: Any = None, raises: Any = None) -> None:
        self.log, self.name, self.result, self.raises = log, name, result, raises

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.log.append((self.name, args, kwargs))
        if self.raises is not None:
            raise self.raises
        return self.result


# ---------------------------------------------------------------------------
# _retry_request

TOOL_HASH = "0" * 64


@pytest.fixture
def token(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(service_module, "uuid4", lambda: SimpleNamespace(hex="tok"))
    return "tok"


def _bound(**over: Any) -> dict[str, Any]:
    return {
        "task_id": "t1",
        "attempt_id": "a1",
        "action_id": "act1",
        "idempotency_key": "k1",
        "action_type": "TASK_RUN",
        "contract_kind": "NONE",
        "allowed_files": ["src/a.py"],
        "what": "w",
        **over,
    }


def _action(bound: dict[str, Any], **over: Any) -> dict[str, Any]:
    return {
        "task_id": "t1",
        "attempt_id": "a1",
        "action_id": "act1",
        "idempotency_key": "k1",
        "action_type": "TASK_RUN",
        "tool_manifest_hash": TOOL_HASH,
        "request_hash": canonical_request_hash(bound),
        "allowed_paths": ["src/a.py"],
        **over,
    }


def _signed(bound: dict[str, Any], **outer: Any) -> dict[str, Any]:
    return {"action": _action(bound), "bound_action_request": bound, **outer}


@pytest.mark.parametrize("raw", [None, "x", ["task_id"], 1])
def test_retry_request_requires_a_mapping_request(raw: Any) -> None:
    state = {"task_id": "t1"} if raw is None else {"task_id": "t1", "request": raw}
    with pytest.raises(ValueError) as raised:
        service_module._retry_request(state)
    assert str(raised.value) == "RETRY_REQUEST_MISSING"


def test_retry_request_plain(token: str) -> None:
    request = {
        "task_id": "t1",
        "attempt_id": "a1",
        "action_id": "x1",
        "idempotency_key": "k1",
        "what": "w",
        "nested": {"a": [1, 2]},
        "action_request_hash": "stale",
    }
    state = {"task_id": "t1", "idempotency_key": "kstate:retry-old", "request": request}
    before = copy.deepcopy(state)
    result = service_module._retry_request(state)
    expected = {
        "task_id": "t1",
        "attempt_id": "attempt-tok",
        "action_id": "action-tok",
        "idempotency_key": "kstate:retry-tok",
        "what": "w",
        "nested": {"a": [1, 2]},
    }
    expected["action_request_hash"] = canonical_request_hash(expected)
    assert result == expected
    assert list(result)[-1] == "action_request_hash"
    assert state == before
    assert result["nested"] is not request["nested"]


def test_retry_request_plain_identity_falls_back_to_the_request(token: str) -> None:
    result = service_module._retry_request({"request": {"task_id": "t9", "idempotency_key": "rk"}})
    assert (result["task_id"], result["idempotency_key"]) == ("t9", "rk:retry-tok")
    result = service_module._retry_request({"request": {"task_id": "t9"}})
    assert result["idempotency_key"] == "t9:retry-tok"


def test_retry_request_json_round_trip_happens_before_minting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[Any] = []
    monkeypatch.setattr(service_module, "mint_retry_identity", Recorder(log, "mint"))
    with pytest.raises(TypeError):
        service_module._retry_request({"task_id": "t1", "request": {"x": object()}})
    assert log == []


def test_retry_request_mint_errors_come_before_the_bound_check(token: str) -> None:
    with pytest.raises(ValueError) as raised:
        service_module._retry_request({"request": {"action": {}}})
    assert str(raised.value) == "RETRY_TASK_ID_MISSING"


def test_retry_request_mints_with_state_copy_and_uuid_token(
    monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    log: list[Any] = []
    identity = SimpleNamespace(task_id="T", attempt_id="A", action_id="X", idempotency_key="K")

    def mint(*args: Any, **kwargs: Any) -> Any:
        log.append((args, copy.deepcopy(args[1]), kwargs))
        return identity

    monkeypatch.setattr(service_module, "mint_retry_identity", mint)
    state = {"task_id": "t1", "request": {"task_id": "t1", "v": 1}}
    result = service_module._retry_request(state)
    ((args, request_at_call, kwargs),) = log
    assert args[0] is state and kwargs == {"token": "tok"}
    assert request_at_call == {"task_id": "t1", "v": 1} and args[1] is not state["request"]
    # the plain path updates and returns that same working copy
    assert args[1] is result
    assert {k: result[k] for k in ("task_id", "attempt_id", "action_id", "idempotency_key")} == {
        "task_id": "T",
        "attempt_id": "A",
        "action_id": "X",
        "idempotency_key": "K",
    }


@pytest.mark.parametrize("raw_bound", [None, "x", ["a"]])
def test_retry_request_action_requires_bound(token: str, raw_bound: Any) -> None:
    request: dict[str, Any] = {"task_id": "t1", "action": {}}
    if raw_bound is not None:
        request["bound_action_request"] = raw_bound
    with pytest.raises(ValueError) as raised:
        service_module._retry_request({"task_id": "t1", "request": request})
    assert str(raised.value) == "RETRY_BOUND_ACTION_REQUEST_MISSING"


def test_retry_request_non_mapping_action_takes_the_plain_path(token: str) -> None:
    result = service_module._retry_request({
        "task_id": "t1",
        "request": {"task_id": "t1", "action": "x"},
    })
    assert result["action"] == "x" and result["attempt_id"] == "attempt-tok"
    assert "bound_action_request" not in result


def test_retry_request_invalid_action_envelope_is_not_wrapped(token: str) -> None:
    with pytest.raises(Exception) as raised:
        service_module._retry_request({
            "task_id": "t1",
            "request": {"action": {"task_id": "t1"}, "bound_action_request": {}},
        })
    assert type(raised.value).__name__ == "ValidationError"


def test_retry_request_action_bound(token: str) -> None:
    bound = _bound()
    request = _signed(bound, outer_only="o", action_request_hash="stale")
    state = {"task_id": "t1", "idempotency_key": "k1", "request": request}
    before = copy.deepcopy(state)
    result = service_module._retry_request(state)
    new_bound = {
        **bound,
        "task_id": "t1",
        "attempt_id": "attempt-tok",
        "action_id": "action-tok",
        "idempotency_key": "k1:retry-tok",
        "action_type": "TASK_RETRY",
    }
    action = LifecycleActionEnvelope.model_validate(_action(bound)).model_dump(mode="json")
    action.update(
        attempt_id="attempt-tok",
        action_id="action-tok",
        idempotency_key="k1:retry-tok",
        action_type="TASK_RETRY",
        request_hash=canonical_request_hash(new_bound),
    )
    assert result == {
        **new_bound,
        "action": action,
        "bound_action_request": new_bound,
        "task_id": "t1",
        "attempt_id": "attempt-tok",
        "action_id": "action-tok",
        "idempotency_key": "k1:retry-tok",
        "action_request_hash": canonical_request_hash(new_bound),
    }
    # the outer request's own keys are dropped: the result is built from the bound copy
    assert "outer_only" not in result
    assert result["action"]["allowed_paths"] == ["src/a.py"]
    assert result["action"]["schema"] == "nexus.lifecycle_action.v1"
    assert state == before
    assert result["bound_action_request"] is not bound


def test_retry_request_action_bound_result_validates_as_a_task_retry(token: str) -> None:
    result = service_module._retry_request({"task_id": "t1", "request": _signed(_bound())})
    effective, envelope = service_module._validated_action_request(result)
    assert envelope is not None and envelope["action_type"] == "TASK_RETRY"
    assert effective["attempt_id"] == "attempt-tok"


def test_retry_request_revalidates_the_retry_envelope(
    monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    log: list[Any] = []
    real = service_module.LifecycleActionEnvelope

    class Envelope:
        @staticmethod
        def model_validate(raw: Any) -> Any:
            log.append(dict(raw))
            return real.model_validate(raw)

    monkeypatch.setattr(service_module, "LifecycleActionEnvelope", Envelope)
    service_module._retry_request({"task_id": "t1", "request": _signed(_bound())})
    assert len(log) == 2
    assert log[0]["attempt_id"] == "a1" and log[1]["attempt_id"] == "attempt-tok"
    assert log[1]["action_type"] == "TASK_RETRY"


# ---------------------------------------------------------------------------
# _retry_semantic_payload / _terminal_retry_semantic_payload

TRANSPORT = {
    "attempt_id": "a",
    "action_id": "x",
    "idempotency_key": "k",
    "action_request_hash": "h",
    "action_type": "TASK_RUN",
}


def test_retry_semantic_payload_drops_only_transport_fields() -> None:
    request = {**TRANSPORT, "task_id": "t", "controller_revision": "c", "nested": {"a": 1}}
    payload = service_module._retry_semantic_payload(request)
    assert payload == {"task_id": "t", "controller_revision": "c", "nested": {"a": 1}}
    assert payload["nested"] is not request["nested"]
    assert request["attempt_id"] == "a"


def test_retry_semantic_payload_prefers_the_bound_request() -> None:
    request = {"task_id": "outer", "bound_action_request": {**TRANSPORT, "task_id": "bound"}}
    assert service_module._retry_semantic_payload(request) == {"task_id": "bound"}
    request = {"task_id": "outer", "bound_action_request": "x"}
    assert service_module._retry_semantic_payload(request) == {
        "task_id": "outer",
        "bound_action_request": "x",
    }


def test_retry_semantic_payload_rejects_non_json() -> None:
    with pytest.raises(TypeError):
        service_module._retry_semantic_payload({"x": object()})


def test_terminal_semantic_payload_plain() -> None:
    request = {
        **TRANSPORT,
        "task_id": "t",
        "controller_revision": "c",
        "target_base_revision": "b",
        "canonical_dispatch_envelope": {"attempt_id": "a", "planner": "p"},
    }
    before = copy.deepcopy(request)
    payload = service_module._terminal_retry_semantic_payload(request)
    assert payload == {"task_id": "t", "canonical_dispatch_envelope": {"planner": "p"}}
    assert request == before


def test_terminal_semantic_payload_non_mapping_envelope_kept() -> None:
    payload = service_module._terminal_retry_semantic_payload({
        "task_id": "t",
        "canonical_dispatch_envelope": "e",
    })
    assert payload == {"task_id": "t", "canonical_dispatch_envelope": "e"}


def test_terminal_semantic_payload_action_bound_uses_the_effective_request() -> None:
    bound = _bound(canonical_dispatch_envelope={"attempt_id": "a1", "p": 1})
    payload = service_module._terminal_retry_semantic_payload(_signed(bound, outer="o"))
    assert payload == {
        "task_id": "t1",
        "contract_kind": "NONE",
        "allowed_files": ["src/a.py"],
        "what": "w",
        "canonical_dispatch_envelope": {"p": 1},
    }


def test_terminal_semantic_payload_action_errors_propagate() -> None:
    bound = _bound()
    request = _signed(bound)
    request["action"]["request_hash"] = "1" * 64
    with pytest.raises(ValueError) as raised:
        service_module._terminal_retry_semantic_payload(request)
    assert str(raised.value) == "BOUND_ACTION_REQUEST_HASH_MISMATCH"


@pytest.mark.parametrize("key", ["workforce_demands", "workforce_admission"])
def test_terminal_semantic_payload_order_and_dispatch_validation(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    log: list[Any] = []
    effective = {key: "d", "task_id": "t", "attempt_id": "a", "controller_revision": "c"}
    monkeypatch.setattr(
        service_module, "_validated_action_request", Recorder(log, "validate", (effective, None))
    )
    monkeypatch.setattr(
        service_module, "validate_workforce_dispatch_binding", Recorder(log, "dispatch", {"x": 1})
    )
    monkeypatch.setattr(
        service_module,
        "_retry_semantic_payload",
        Recorder(log, "strip", {"controller_revision": "c", "k": 1}),
    )
    request = {"task_id": "raw"}
    assert service_module._terminal_retry_semantic_payload(request) == {"k": 1}
    assert [entry[0] for entry in log] == ["validate", "dispatch", "strip"]
    assert log[0][1] == (request,) and log[0][2] == {}
    assert log[1][1][0] is effective and log[1][2] == {"require_binding": True}
    assert log[2][1] == (effective,)


def test_terminal_semantic_payload_dispatch_errors_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service_module,
        "validate_workforce_dispatch_binding",
        Recorder([], "dispatch", raises=ValueError("WORKFORCE_DISPATCH_BINDING_REQUIRED")),
    )
    with pytest.raises(ValueError) as raised:
        service_module._terminal_retry_semantic_payload({"workforce_demands": {}})
    assert str(raised.value) == "WORKFORCE_DISPATCH_BINDING_REQUIRED"


def test_terminal_semantic_payload_skips_dispatch_without_workforce_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[Any] = []
    monkeypatch.setattr(
        service_module, "validate_workforce_dispatch_binding", Recorder(log, "dispatch")
    )
    service_module._terminal_retry_semantic_payload({"task_id": "t", "admission_binding": "b"})
    assert log == []


# ---------------------------------------------------------------------------
# _terminal_retry_inherited_worktree_time_allowed

PREV_START = "2026-09-10T17:49:33.803740+00:00"
PREV_FINISH = "2026-09-10T17:49:36.818839+00:00"
CUR_START = "2026-09-10T22:59:19.279029+00:00"
CUR_FINISH = "2026-09-10T22:59:21.873106+00:00"
EFFECT_FIELDS = (
    "execution",
    "execution_outcome",
    "candidate",
    "candidate_commit_sha",
    "candidate_ref",
    "candidate_state_hash",
    "verified_receipt",
    "verified_receipt_hash",
    "provider_receipt",
    "worker_receipt",
)


def _timing_state(tmp_path: Path) -> dict[str, Any]:
    controller = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller.mkdir(exist_ok=True)
    target_root.mkdir(exist_ok=True)
    target = target_root / "task"
    return {
        "task_id": "inherited-timing-task",
        "status": "FINAL_BLOCK",
        "error": "existing task branch candidate lacks durable protection",
        "cleanup_decision": "ALREADY_REMOVED",
        "target_created_at": None,
        "target_worktree": str(target),
        "lease": None,
        "execution": None,
        "executions": None,
        "active_provider": None,
        "worker_preflight": None,
        "worker_child_pgid": None,
        "candidate": None,
        "candidate_commit_sha": None,
        "candidate_ref": None,
        "candidate_state_hash": None,
        "verified_receipt": None,
        "verified_receipt_hash": None,
        "candidate_status": None,
        "promotion_status": "NOT_CREATED",
        "merge_performed": False,
        "push_performed": False,
        "worker_started_at": CUR_START,
        "worker_finished_at": CUR_FINISH,
        "attempt_id": "attempt-current",
        "attempts": [
            {
                "attempt_id": "attempt-previous",
                "started_at": PREV_START,
                "finished_at": PREV_FINISH,
                "last_status": "FINAL_BLOCK",
            },
            {
                "attempt_id": "attempt-current",
                "started_at": CUR_START,
                "finished_at": CUR_FINISH,
                "last_status": "FINAL_BLOCK",
            },
        ],
        "status_history": [
            {"status": "SUBMITTED", "at": PREV_START},
            {"status": "TARGET_LEASED", "at": "2026-09-10T17:49:35.516136+00:00"},
            {"status": "WORKER_RUNNING", "at": "2026-09-10T17:49:35.523858+00:00"},
            {"status": "FINAL_BLOCK", "at": PREV_FINISH},
            {"status": "ATTEMPT_INCREMENTED", "at": CUR_START},
            {"status": "FINAL_BLOCK", "at": CUR_FINISH},
        ],
        "telemetry": {
            "provider_calls": 0,
            "provider_attempts": 0,
            "provider_time_ms": 0,
            "worktree_time_ms": 1429,
            "verifier_time_ms": 0,
        },
        "contract": {
            "controller_repo_root": str(controller),
            "target_worktree_root": str(target_root),
            "target_repo_root": str(target),
            "target_base_revision": "b" * 40,
        },
    }


class FakeManager:
    """Stands in for WorktreeManager on the facade; records every call in order."""

    log: list[Any] = []
    ownership: Path | None = None
    entry: Any = None
    active: Any = ()
    branch_head: str = "h" * 40
    git_raises: dict[str, BaseException] = {}
    init_raises: BaseException | None = None
    released: Any = True

    def __init__(self, **kwargs: Any) -> None:
        type(self).log.append(("init", kwargs))
        raised = type(self).init_raises
        if raised is not None:
            raise raised

    def _ownership_record_path(self, controller_root: Path, task_id: str) -> Path:
        type(self).log.append(("ownership", controller_root, task_id))
        return type(self).ownership or Path("/nonexistent-nexus-s5/ownership.json")

    def _worktree_entry(self, controller_root: Path, target: Path) -> Any:
        type(self).log.append(("entry", controller_root, target))
        return type(self).entry

    def _active_target_worktrees(self, controller_root: Path, target: Path) -> Any:
        type(self).log.append(("active", controller_root, target))
        return type(self).active

    def _run_git(self, args: list[str], cwd: Path) -> str:
        type(self).log.append(("git", tuple(args), cwd))
        raised = type(self).git_raises.get(args[0])
        if raised is not None:
            raise raised
        return type(self).branch_head if args[0] == "rev-parse" else ""

    def released_lease_proof(self, controller_root: Path, **kwargs: Any) -> Any:
        type(self).log.append(("released", controller_root, kwargs))
        raised = type(self).init_raises
        if raised is not None:
            raise raised
        return type(self).released


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> type[FakeManager]:
    fake = type("Fake", (FakeManager,), {"log": [], "git_raises": {}})
    monkeypatch.setattr(service_module, "WorktreeManager", fake)
    return fake


def test_inherited_time_accepts_the_known_shape_and_calls_the_manager_in_order(
    tmp_path: Path, manager: type[FakeManager]
) -> None:
    state = _timing_state(tmp_path)
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is True
    controller = Path(state["contract"]["controller_repo_root"])
    target = Path(state["target_worktree"])
    assert manager.log == [
        (
            "init",
            {"root_dir": Path(state["contract"]["target_worktree_root"]), "create_root": False},
        ),
        ("ownership", controller, "inherited-timing-task"),
        ("entry", controller, target),
        ("active", controller, target),
        (
            "git",
            ("rev-parse", "--verify", "refs/heads/nexus/task/inherited-timing-task"),
            controller,
        ),
        ("git", ("merge-base", "--is-ancestor", "h" * 40, "b" * 40), controller),
    ]


@pytest.mark.parametrize(
    "telemetry",
    [
        None,
        "x",
        {},
        {"worktree_time_ms": True},
        {"worktree_time_ms": 1.0},
        {"worktree_time_ms": "1"},
    ],
)
def test_inherited_time_requires_integer_worktree_time(
    tmp_path: Path, manager: type[FakeManager], telemetry: Any
) -> None:
    state = _timing_state(tmp_path)
    state["telemetry"] = telemetry
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is False
    assert manager.log == []


def test_inherited_time_zero_is_accepted_without_any_other_check(
    manager: type[FakeManager],
) -> None:
    assert service_module._terminal_retry_inherited_worktree_time_allowed({
        "telemetry": {"worktree_time_ms": 0}
    })
    assert manager.log == []


def test_inherited_time_negative_is_rejected(tmp_path: Path, manager: type[FakeManager]) -> None:
    state = _timing_state(tmp_path)
    state["telemetry"]["worktree_time_ms"] = -1
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is False


def _set(path: str, value: Any) -> Any:
    def mutate(state: dict[str, Any]) -> None:
        target: Any = state
        keys = path.split(".")
        for key in keys[:-1]:
            target = target[int(key)] if isinstance(target, list) else target[key]
        last = keys[-1]
        if isinstance(target, list):
            target[int(last)] = value
        elif value is DELETE:
            del target[last]
        else:
            target[last] = value

    return mutate


DELETE = object()
PRE_MANAGER_DENIALS = {
    "error": _set("error", "other"),
    "attempt_id missing": _set("attempt_id", ""),
    "attempts not list": _set("attempts", ({}, {})),
    "one attempt": lambda s: s.__setitem__("attempts", s["attempts"][-1:]),
    "history not list": _set("status_history", ()),
    "history item not mapping": lambda s: s["status_history"].append("x"),
    "current not mapping": _set("attempts.1", "x"),
    "previous not mapping": _set("attempts.0", None),
    "current id differs": _set("attempts.1.attempt_id", "other"),
    "previous id equals current": _set("attempts.0.attempt_id", "attempt-current"),
    "current not FINAL_BLOCK": _set("attempts.1.last_status", "CANCELLED"),
    "current started missing": _set("attempts.1.started_at", ""),
    "current finished missing": _set("attempts.1.finished_at", None),
    "previous started missing": _set("attempts.0.started_at", DELETE),
    "previous finished missing": _set("attempts.0.finished_at", ""),
    "history at missing": _set("status_history.2", {"status": "WORKER_RUNNING"}),
    "history at invalid": _set("status_history.2", {"status": "WORKER_RUNNING", "at": "nope"}),
    "current started invalid": _set("attempts.1.started_at", "nope"),
    "previous finished invalid": _set("attempts.0.finished_at", "nope"),
    # previous started_at is first parsed inside the previous-window comprehension
    "previous started invalid": _set("attempts.0.started_at", "nope"),
    "previous started naive": _set("attempts.0.started_at", "2026-09-10T17:49:33.803740"),
    "previous finished naive": _set("attempts.0.finished_at", "2026-09-10T17:49:36.818839"),
    "history not monotonic": _set(
        "status_history.1", {"status": "TARGET_LEASED", "at": PREV_FINISH + "x"}
    ),
    "history goes backwards": _set("status_history.3", {"status": "FINAL_BLOCK", "at": PREV_START}),
    "mixed timezone": _set(
        "status_history.1", {"status": "TARGET_LEASED", "at": "2026-09-10T17:49:35.516136"}
    ),
    "no current start": _set("status_history.4", {"status": "RETRYING", "at": CUR_START}),
    "current start not equal text": _set(
        "attempts.1.started_at", "2026-09-10T22:59:19.279029+00:00 "
    ),
    "two current starts": lambda s: s["status_history"].insert(
        4, {"status": "ATTEMPT_INCREMENTED", "at": CUR_START}
    ),
    "current segment extra": lambda s: s["status_history"].append({
        "status": "FINAL_BLOCK",
        "at": CUR_FINISH,
    }),
    "current segment wrong": _set("status_history.5", {"status": "CANCELLED", "at": CUR_FINISH}),
    "current segment short": lambda s: s["status_history"].pop(),
    "previous window wrong": _set(
        "status_history.1", {"status": "WORKER_RUNNING", "at": "2026-09-10T17:49:35.516136+00:00"}
    ),
    "previous window short": lambda s: s["status_history"].pop(2),
    "previous window extra": lambda s: s["status_history"].insert(
        1, {"status": "SUBMITTED", "at": PREV_START}
    ),
    "finished at differs": _set("attempts.1.finished_at", "2026-09-10T22:59:21.873106Z"),
    "previous finished after current start": _set(
        "attempts.0.finished_at", "2026-09-10T23:00:00+00:00"
    ),
    "contract not mapping": _set("contract", "x"),
    "target worktree empty": _set("target_worktree", "   "),
    "target worktree missing": _set("target_worktree", None),
    "controller not a dir": _set(
        "contract.controller_repo_root", "/nonexistent-nexus-s5/controller"
    ),
    "target root not a dir": _set("contract.target_worktree_root", "/nonexistent-nexus-s5/targets"),
    "target is the root": lambda s: (
        s.__setitem__("target_worktree", s["contract"]["target_worktree_root"]),
        s["contract"].__setitem__("target_repo_root", s["contract"]["target_worktree_root"]),
    ),
    "target outside the root": lambda s: (
        s.__setitem__("target_worktree", "/nonexistent-nexus-s5/task"),
        s["contract"].__setitem__("target_repo_root", "/nonexistent-nexus-s5/task"),
    ),
    "target_repo_root differs": _set("contract.target_repo_root", "/x"),
    "lease": _set("lease", {}),
    "executions": _set("executions", [{}]),
    "promotion_packet": _set("promotion_packet", {"x": 1}),
    **{f"effect field {field}": _set(field, {}) for field in EFFECT_FIELDS},
}


@pytest.mark.parametrize("label", sorted(PRE_MANAGER_DENIALS))
def test_inherited_time_denials_before_the_manager(
    tmp_path: Path, manager: type[FakeManager], label: str
) -> None:
    state = _timing_state(tmp_path)
    PRE_MANAGER_DENIALS[label](state)
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is False
    assert manager.log == []


@pytest.mark.parametrize("value", [None, []])
def test_inherited_time_tolerates_empty_executions(
    tmp_path: Path, manager: type[FakeManager], value: Any
) -> None:
    state = _timing_state(tmp_path)
    state["executions"] = value
    state["promotion_packet"] = {}
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is True


def test_inherited_time_rejects_a_present_target(
    tmp_path: Path, manager: type[FakeManager]
) -> None:
    state = _timing_state(tmp_path)
    target = Path(state["target_worktree"])
    target.symlink_to(tmp_path / "missing")
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is False
    assert manager.log == []


def test_inherited_time_rejects_a_present_target_directory(
    tmp_path: Path, manager: type[FakeManager]
) -> None:
    state = _timing_state(tmp_path)
    Path(state["target_worktree"]).mkdir()
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is False
    assert manager.log == []


def test_inherited_time_empty_controller_root_is_the_cwd(
    tmp_path: Path, manager: type[FakeManager], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    state = _timing_state(tmp_path)
    state["contract"]["controller_repo_root"] = ""
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is True
    assert manager.log[1] == ("ownership", Path(""), "inherited-timing-task")


def test_inherited_time_expands_user_paths(
    tmp_path: Path, manager: type[FakeManager], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    state = _timing_state(tmp_path)
    state["contract"]["controller_repo_root"] = "~/controller"
    state["contract"]["target_worktree_root"] = "~/targets"
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is True
    assert manager.log[0] == ("init", {"root_dir": tmp_path / "targets", "create_root": False})
    assert manager.log[1][1] == tmp_path / "controller"


def _manager_denial(name: str):
    def apply(fake: type[FakeManager], tmp_path: Path, state: dict[str, Any]) -> int:
        if name == "ownership exists":
            fake.ownership = tmp_path / "own.json"
            fake.ownership.write_text("{}")
            return 2
        if name == "ownership dangling symlink":
            fake.ownership = tmp_path / "own.json"
            fake.ownership.symlink_to(tmp_path / "nothing")
            return 2
        if name == "worktree entry":
            fake.entry = {"path": "x"}
            return 3
        if name == "active targets":
            fake.active = [1]
            return 4
        if name == "no target base":
            state["contract"]["target_base_revision"] = ""
            return 4
        if name == "no branch head":
            fake.branch_head = ""
            return 5
        if name == "branch not ancestor":
            fake.git_raises = {"merge-base": RuntimeError("not ancestor")}
            return 6
        for exc in (OSError, RuntimeError, ValueError, TypeError):
            if name == f"rev-parse {exc.__name__}":
                fake.git_raises = {"rev-parse": exc("x")}
                return 5
            if name == f"init {exc.__name__}":
                fake.init_raises = exc("x")
                return 1
        raise AssertionError(name)

    return apply


MANAGER_DENIALS = [
    "ownership exists",
    "ownership dangling symlink",
    "worktree entry",
    "active targets",
    "no target base",
    "no branch head",
    "branch not ancestor",
    *(f"rev-parse {e}" for e in ("OSError", "RuntimeError", "ValueError", "TypeError")),
    *(f"init {e}" for e in ("OSError", "RuntimeError", "ValueError", "TypeError")),
]


@pytest.mark.parametrize("label", MANAGER_DENIALS)
def test_inherited_time_manager_denials_stop_at_their_step(
    tmp_path: Path, manager: type[FakeManager], label: str
) -> None:
    state = _timing_state(tmp_path)
    calls = _manager_denial(label)(manager, tmp_path, state)
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is False
    assert len(manager.log) == calls, manager.log


@pytest.mark.parametrize("step", ["init", "rev-parse", "merge-base"])
def test_inherited_time_other_manager_errors_propagate(
    tmp_path: Path, manager: type[FakeManager], step: str
) -> None:
    state = _timing_state(tmp_path)
    if step == "init":
        manager.init_raises = KeyError("k")
    else:
        manager.git_raises = {step: KeyError("k")}
    with pytest.raises(KeyError):
        service_module._terminal_retry_inherited_worktree_time_allowed(state)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_inherited_time_with_the_real_worktree_manager(tmp_path: Path) -> None:
    state = _timing_state(tmp_path)
    controller = Path(state["contract"]["controller_repo_root"])
    _git(controller, "init", "-q")
    _git(controller, "config", "user.email", "test@example.invalid")
    _git(controller, "config", "user.name", "Test")
    (controller / "f.txt").write_text("old\n")
    _git(controller, "add", "f.txt")
    _git(controller, "commit", "-qm", "old")
    _git(controller, "branch", "nexus/task/inherited-timing-task")
    (controller / "f.txt").write_text("new\n")
    _git(controller, "commit", "-qam", "new")
    state["contract"]["target_base_revision"] = _git(controller, "rev-parse", "HEAD")
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is True
    assert service_module._terminal_retry_pre_provider_state_allowed(state) is True
    # a branch that is not an ancestor of the target base
    _git(controller, "checkout", "-q", "nexus/task/inherited-timing-task")
    (controller / "g.txt").write_text("side\n")
    _git(controller, "add", "g.txt")
    _git(controller, "commit", "-qm", "side")
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is False
    _git(controller, "checkout", "-q", "-")
    _git(controller, "branch", "-q", "-D", "nexus/task/inherited-timing-task")
    assert service_module._terminal_retry_inherited_worktree_time_allowed(state) is False


# ---------------------------------------------------------------------------
# _terminal_retry_pre_provider_state_allowed


@pytest.fixture
def inherited(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    log: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "_terminal_retry_inherited_worktree_time_allowed",
        Recorder(log, "inherited", "INHERITED-RESULT"),
    )
    return log


def _pre_provider_state() -> dict[str, Any]:
    return {
        "status": "FINAL_BLOCK",
        "cleanup_decision": "REMOVED",
        "target_created_at": None,
        "active_provider": None,
        "worker_preflight": None,
        "worker_child_pgid": None,
        "worker_started_at": CUR_START,
        "worker_finished_at": CUR_FINISH,
        "promotion_status": "NOT_CREATED",
        "telemetry": {
            "provider_calls": 0,
            "provider_attempts": 0,
            "provider_time_ms": 0,
            "verifier_time_ms": 0,
        },
    }


def test_pre_provider_returns_the_inherited_time_result(inherited: list[Any]) -> None:
    state = _pre_provider_state()
    assert service_module._terminal_retry_pre_provider_state_allowed(state) == "INHERITED-RESULT"
    assert inherited == [("inherited", (state,), {})]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cleanup_decision", "ALREADY_REMOVED"),
        ("cleanup_decision", "TARGET_CLEANED"),
        ("active_provider", ""),
        ("candidate_status", ""),
        ("merge_performed", 0),
        ("push_performed", False),
        ("promotion_packet", {"other": 1, "candidate_commit_sha": None}),
        ("candidate_ref", None),
    ],
)
def test_pre_provider_tolerated_values(inherited: list[Any], field: str, value: Any) -> None:
    state = _pre_provider_state()
    state[field] = value
    assert service_module._terminal_retry_pre_provider_state_allowed(state) == "INHERITED-RESULT"


PRE_PROVIDER_DENIALS: list[tuple[str, Any]] = [
    ("status", "CANCELLED"),
    ("status", None),
    ("cleanup_decision", None),
    ("cleanup_decision", "RETAINED"),
    ("target_created_at", "t"),
    ("active_provider", "codex"),
    ("worker_preflight", {}),
    ("worker_child_pgid", 0),
    ("worker_started_at", None),
    ("worker_finished_at", None),
    ("execution", {}),
    ("execution_outcome", "x"),
    *(
        (field, {})
        for field in (
            "candidate",
            "candidate_commit_sha",
            "candidate_ref",
            "candidate_state_hash",
            "verified_receipt",
            "verified_receipt_hash",
        )
    ),
    ("promotion_packet", "x"),
    ("promotion_packet", []),
    *(
        ("promotion_packet", {field: "v"})
        for field in (
            "candidate_commit_sha",
            "candidate_tree_sha",
            "candidate_state_hash",
            "verified_receipt_hash",
            "approval_binding",
        )
    ),
    ("candidate_status", "PENDING"),
    ("promotion_status", None),
    ("promotion_status", "CREATED"),
    ("merge_performed", True),
    ("push_performed", "no"),
    ("telemetry", None),
    ("telemetry", "x"),
    *(
        ("telemetry", {**_pre_provider_state()["telemetry"], field: value})
        for field in ("provider_calls", "provider_attempts", "provider_time_ms", "verifier_time_ms")
        for value in (1, False, 0.0, None)
    ),
    *(
        ("telemetry", {k: v for k, v in _pre_provider_state()["telemetry"].items() if k != field})
        for field in ("provider_calls", "provider_attempts", "provider_time_ms", "verifier_time_ms")
    ),
]


@pytest.mark.parametrize(("field", "value"), PRE_PROVIDER_DENIALS)
def test_pre_provider_denials_never_reach_inherited_time(
    inherited: list[Any], field: str, value: Any
) -> None:
    state = _pre_provider_state()
    state[field] = value
    assert service_module._terminal_retry_pre_provider_state_allowed(state) is False
    assert inherited == []


def test_pre_provider_does_not_check_worktree_time_itself(inherited: list[Any]) -> None:
    state = _pre_provider_state()
    state["telemetry"]["worktree_time_ms"] = "anything"
    assert service_module._terminal_retry_pre_provider_state_allowed(state) == "INHERITED-RESULT"


# ---------------------------------------------------------------------------
# _terminal_retry_released_lease_proof


def _lease_state(tmp_path: Path) -> dict[str, Any]:
    controller = tmp_path / "controller"
    controller.mkdir(exist_ok=True)
    return {
        "task_id": "t1",
        "attempt_id": "a1",
        "lease": {"lease_id": "L1", "target_worktree": str(tmp_path / "targets" / "t1")},
        "contract": {"controller_repo_root": str(controller)},
    }


def test_released_lease_proof_arguments_and_result(
    tmp_path: Path, manager: type[FakeManager]
) -> None:
    sentinel = object()
    manager.released = sentinel
    state = _lease_state(tmp_path)
    assert service_module._terminal_retry_released_lease_proof(state) is sentinel
    assert manager.log == [
        ("init", {"create_root": False}),
        (
            "released",
            (tmp_path / "controller").resolve(strict=True),
            {
                "task_id": "t1",
                "attempt_id": "a1",
                "lease_id": "L1",
                "target_worktree": tmp_path / "targets" / "t1",
                "task_state": state,
            },
        ),
    ]
    assert manager.log[1][2]["task_state"] is state


def test_released_lease_proof_resolves_the_controller_symlink(
    tmp_path: Path, manager: type[FakeManager]
) -> None:
    state = _lease_state(tmp_path)
    (tmp_path / "link").symlink_to(tmp_path / "controller")
    state["contract"]["controller_repo_root"] = str(tmp_path / "link")
    service_module._terminal_retry_released_lease_proof(state)
    assert manager.log[1][1] == (tmp_path / "controller").resolve()


def test_released_lease_proof_defaults(tmp_path: Path, manager: type[FakeManager]) -> None:
    state = _lease_state(tmp_path)
    state["attempt_id"] = ""
    del state["task_id"]
    state["lease"] = {}
    service_module._terminal_retry_released_lease_proof(state)
    kwargs = manager.log[1][2]
    assert kwargs["task_id"] == "" and kwargs["attempt_id"] is None and kwargs["lease_id"] == ""
    # an empty target becomes Path(".") (a Path is always truthy): the manager decides
    assert kwargs["target_worktree"] == Path(".")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.__setitem__("lease", None),
        lambda s: s.__setitem__("lease", "x"),
        lambda s: s.__setitem__("contract", None),
        lambda s: s["contract"].__setitem__("controller_repo_root", "/nonexistent-nexus-s5"),
    ],
)
def test_released_lease_proof_guards(
    tmp_path: Path, manager: type[FakeManager], mutate: Any
) -> None:
    state = _lease_state(tmp_path)
    mutate(state)
    assert service_module._terminal_retry_released_lease_proof(state) is False
    assert manager.log == []


@pytest.mark.parametrize("exc", [OSError, RuntimeError, ValueError, TypeError])
def test_released_lease_proof_swallows_known_errors(
    tmp_path: Path, manager: type[FakeManager], exc: type[BaseException]
) -> None:
    manager.init_raises = exc("x")
    assert service_module._terminal_retry_released_lease_proof(_lease_state(tmp_path)) is False


def test_released_lease_proof_other_errors_propagate(
    tmp_path: Path, manager: type[FakeManager]
) -> None:
    manager.init_raises = KeyError("x")
    with pytest.raises(KeyError):
        service_module._terminal_retry_released_lease_proof(_lease_state(tmp_path))


def test_released_lease_proof_with_the_real_manager_and_no_tombstone(tmp_path: Path) -> None:
    state = _lease_state(tmp_path)
    _git(tmp_path / "controller", "init", "-q")
    assert service_module._terminal_retry_released_lease_proof(state) is False


def test_released_lease_proof_does_not_swallow_git_process_errors(tmp_path: Path) -> None:
    # the controller is a directory but not a git repository: the real manager's git
    # call raises CalledProcessError, which is not one of the swallowed error types
    with pytest.raises(subprocess.CalledProcessError):
        service_module._terminal_retry_released_lease_proof(_lease_state(tmp_path))


def test_released_lease_proof_empty_controller_root_is_the_cwd(
    tmp_path: Path, manager: type[FakeManager], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    state = _lease_state(tmp_path)
    state["contract"]["controller_repo_root"] = ""
    assert service_module._terminal_retry_released_lease_proof(state) is True
    assert manager.log[1][1] == tmp_path.resolve()


# ---------------------------------------------------------------------------
# _terminal_retry_verifier_static_failure_allowed


def _static_state() -> dict[str, Any]:
    return {
        "task_id": "static-verifier-recovery",
        "status": "FINAL_BLOCK",
        "error": "invalid verifier contract: invalid verifier argument",
        "cleanup_decision": "REMOVED",
        "cleanup_performed": True,
        "cleanup_performed_at": "2026-09-10T17:49:36+00:00",
        "cleanup_eligible": True,
        "cleanup_blocker": None,
        "lease": {"lease_id": "lease", "task_id": "static-verifier-recovery"},
        "target_created_at": "2026-09-10T17:49:35+00:00",
        "active_provider": "codex",
        "worker_preflight": {"provider": "codex", "ready": True},
        "worker_started_at": "2026-09-10T17:49:33+00:00",
        "worker_finished_at": "2026-09-10T17:49:36+00:00",
        "worker_child_pgid": None,
        "execution": None,
        "execution_outcome": None,
        "executions": [],
        "promotion_status": "NOT_CREATED",
        "candidate_status": None,
        "merge_performed": False,
        "push_performed": False,
        "telemetry": {
            "provider_calls": 0,
            "provider_attempts": 0,
            "provider_time_ms": 0,
            "verifier_time_ms": 0,
        },
    }


@pytest.fixture
def proof(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder([], "proof", True)
    monkeypatch.setattr(service_module, "_terminal_retry_released_lease_proof", recorder)
    return recorder


def test_static_failure_accepts_the_known_shape(proof: Recorder) -> None:
    state = _static_state()
    assert service_module._terminal_retry_verifier_static_failure_allowed(state) is True
    assert proof.log == [("proof", (state,), {})]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cleanup_blocker", ""),
        ("executions", None),
        ("candidate_status", ""),
        ("merge_performed", 0),
        ("push_performed", None),
        ("telemetry", {**_static_state()["telemetry"], "worktree_time_ms": 99}),
    ],
)
def test_static_failure_tolerated_values(proof: Recorder, field: str, value: Any) -> None:
    state = _static_state()
    state[field] = value
    assert service_module._terminal_retry_verifier_static_failure_allowed(state) is True


BEFORE_PROOF: list[tuple[str, Any]] = [
    ("status", "CANCELLED"),
    ("error", "invalid verifier contract"),
    ("cleanup_decision", "ALREADY_REMOVED"),
    ("cleanup_performed", 1),
    ("cleanup_performed", None),
    ("cleanup_performed_at", ""),
    ("cleanup_blocker", "x"),
    ("cleanup_eligible", 1),
    ("cleanup_eligible", None),
]


@pytest.mark.parametrize(("field", "value"), BEFORE_PROOF)
def test_static_failure_denials_before_the_lease_proof(
    proof: Recorder, field: str, value: Any
) -> None:
    state = _static_state()
    state[field] = value
    assert service_module._terminal_retry_verifier_static_failure_allowed(state) is False
    assert proof.log == []


def test_static_failure_requires_the_lease_proof(proof: Recorder) -> None:
    proof.result = 0
    assert service_module._terminal_retry_verifier_static_failure_allowed(_static_state()) is False
    assert len(proof.log) == 1


AFTER_PROOF: list[tuple[str, Any]] = [
    ("lease", None),
    ("lease", {"task_id": "static-verifier-recovery"}),
    ("lease", {"lease_id": "", "task_id": "static-verifier-recovery"}),
    ("lease", {"lease_id": "lease", "task_id": "other"}),
    ("target_created_at", None),
    ("active_provider", ""),
    ("worker_preflight", None),
    ("worker_preflight", "x"),
    ("worker_started_at", None),
    ("worker_finished_at", None),
    ("worker_child_pgid", 1),
    ("execution", {}),
    ("execution_outcome", "x"),
    ("executions", [{}]),
    ("promotion_status", "CREATED"),
    ("candidate_status", "X"),
    ("merge_performed", True),
    ("push_performed", 1),
    *(
        (field, {})
        for field in (
            "candidate",
            "candidate_commit_sha",
            "candidate_ref",
            "candidate_state_hash",
            "verified_receipt",
            "verified_receipt_hash",
            "promotion_packet",
            "provider_receipt",
            "worker_receipt",
        )
    ),
    ("telemetry", None),
    *(
        ("telemetry", {**_static_state()["telemetry"], field: value})
        for field in ("provider_calls", "provider_attempts", "provider_time_ms", "verifier_time_ms")
        for value in (1, False, None)
    ),
]


@pytest.mark.parametrize(("field", "value"), AFTER_PROOF)
def test_static_failure_denials_after_the_lease_proof(
    proof: Recorder, field: str, value: Any
) -> None:
    state = _static_state()
    state[field] = value
    assert service_module._terminal_retry_verifier_static_failure_allowed(state) is False
    assert len(proof.log) == 1


# ---------------------------------------------------------------------------
# _validate_retry_predecessor


def _plain(**over: Any) -> dict[str, Any]:
    return {"task_id": "t1", "what": "w", **over}


def _predecessor(**over: Any) -> dict[str, Any]:
    return {
        "status": "FINAL_BLOCK",
        "cleanup_decision": "REMOVED",
        "attempt_id": "a1",
        "action_id": "x1",
        "idempotency_key": "k1",
        "attempts": [
            {"attempt_id": "a0", "action_id": "x0", "idempotency_key": "k0"},
            "not-a-mapping",
        ],
        "request": _plain(
            attempt_id="a1", action_id="x1", idempotency_key="k1", controller_revision="c1"
        ),
        **over,
    }


FRESH = {"attempt_id": "a2", "action_id": "x2", "idempotency_key": "k2"}


@pytest.mark.parametrize("cleanup", ["REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"])
@pytest.mark.parametrize("status", ["FINAL_BLOCK", "CANCELLED"])
def test_predecessor_accepts_a_fresh_attempt(status: str, cleanup: str) -> None:
    request = _plain(**FRESH, controller_revision="c2", target_base_revision="b2")
    assert (
        service_module._validate_retry_predecessor(
            request, _predecessor(status=status, cleanup_decision=cleanup)
        )
        is None
    )


@pytest.mark.parametrize(
    ("request_", "predecessor", "message"),
    [
        (_plain(**FRESH), None, "RETRY_REQUIRES_EXISTING_TASK"),
        (
            _plain(**FRESH),
            _predecessor(status="RETAINED_FOR_REVIEW"),
            "RETRY_REQUIRES_TERMINAL_TASK",
        ),
        (_plain(**FRESH), _predecessor(status=None), "RETRY_REQUIRES_TERMINAL_TASK"),
        # status is checked before the target disposition
        (
            _plain(**FRESH),
            _predecessor(status="RUNNING", cleanup_decision=None),
            "RETRY_REQUIRES_TERMINAL_TASK",
        ),
        (
            _plain(**FRESH),
            _predecessor(cleanup_decision="RETAINED"),
            "RETRY_TARGET_DISPOSITION_REQUIRED",
        ),
        (_plain(**FRESH), _predecessor(cleanup_decision=None), "RETRY_TARGET_DISPOSITION_REQUIRED"),
        # disposition before identity reuse
        (
            _plain(**{**FRESH, "attempt_id": "a1"}),
            _predecessor(cleanup_decision="X"),
            "RETRY_TARGET_DISPOSITION_REQUIRED",
        ),
        (_plain(**{**FRESH, "attempt_id": "a1"}), _predecessor(), "RETRY_ATTEMPT_ID_REUSED"),
        (_plain(**{**FRESH, "attempt_id": "a0"}), _predecessor(), "RETRY_ATTEMPT_ID_REUSED"),
        (_plain(**{**FRESH, "action_id": "x1"}), _predecessor(), "RETRY_ACTION_ID_REUSED"),
        (_plain(**{**FRESH, "action_id": "x0"}), _predecessor(), "RETRY_ACTION_ID_REUSED"),
        (
            _plain(**{**FRESH, "idempotency_key": "k1"}),
            _predecessor(),
            "RETRY_IDEMPOTENCY_KEY_REUSED",
        ),
        (
            _plain(**{**FRESH, "idempotency_key": "k0"}),
            _predecessor(),
            "RETRY_IDEMPOTENCY_KEY_REUSED",
        ),
        # attempt before action before key
        (
            _plain(attempt_id="a0", action_id="x0", idempotency_key="k0"),
            _predecessor(),
            "RETRY_ATTEMPT_ID_REUSED",
        ),
        (
            _plain(attempt_id="a9", action_id="x0", idempotency_key="k0"),
            _predecessor(),
            "RETRY_ACTION_ID_REUSED",
        ),
        # a missing id is "" and the predecessor always contributes its own (possibly empty) id
        (
            _plain(action_id="x2", idempotency_key="k2"),
            _predecessor(attempt_id=None),
            "RETRY_ATTEMPT_ID_REUSED",
        ),
        (
            _plain(attempt_id="a2", idempotency_key="k2"),
            _predecessor(action_id=""),
            "RETRY_ACTION_ID_REUSED",
        ),
        (
            _plain(attempt_id="a2", action_id="x2"),
            _predecessor(idempotency_key=None),
            "RETRY_IDEMPOTENCY_KEY_REUSED",
        ),
        (_plain(**FRESH), _predecessor(request=None), "RETRY_PREDECESSOR_REQUEST_MISSING"),
        (_plain(**FRESH), _predecessor(request="x"), "RETRY_PREDECESSOR_REQUEST_MISSING"),
        # identity reuse before the missing request
        (
            _plain(**{**FRESH, "attempt_id": "a1"}),
            _predecessor(request=None),
            "RETRY_ATTEMPT_ID_REUSED",
        ),
        (_plain(**FRESH, what="other"), _predecessor(), "RETRY_SEMANTIC_TASK_MISMATCH"),
        (_plain(**FRESH, extra=1), _predecessor(), "RETRY_SEMANTIC_TASK_MISMATCH"),
    ],
)
def test_predecessor_denials_in_order(request_: Any, predecessor: Any, message: str) -> None:
    with pytest.raises(ValueError) as raised:
        service_module._validate_retry_predecessor(request_, predecessor)
    assert str(raised.value) == message


def test_predecessor_without_attempt_records() -> None:
    predecessor = _predecessor(attempts=None)
    assert (
        service_module._validate_retry_predecessor(
            _plain(attempt_id="a0", action_id="x0", idempotency_key="k0"), predecessor
        )
        is None
    )


def test_predecessor_compares_terminal_semantics_request_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[Any] = []

    def payload(request: Any) -> dict[str, Any]:
        log.append(request)
        return {"same": True}

    monkeypatch.setattr(service_module, "_terminal_retry_semantic_payload", payload)
    request = _plain(**FRESH, what="differs")
    predecessor = _predecessor()
    assert service_module._validate_retry_predecessor(request, predecessor) is None
    assert log == [request, predecessor["request"]]
    assert log[0] is request and log[1] is predecessor["request"]


def test_predecessor_semantic_errors_propagate() -> None:
    request = _plain(**FRESH, action={"x": 1})
    with pytest.raises(ValueError) as raised:
        service_module._validate_retry_predecessor(request, _predecessor())
    assert str(raised.value) == "BOUND_ACTION_REQUEST_REQUIRED"


def test_predecessor_with_action_bound_requests() -> None:
    first = _bound()
    retry_bound = _bound(
        attempt_id="a2", action_id="x2", idempotency_key="k2", action_type="TASK_RETRY"
    )
    retry = _signed(
        retry_bound,
    )
    retry["action"].update(
        attempt_id="a2", action_id="x2", idempotency_key="k2", action_type="TASK_RETRY"
    )
    predecessor = _predecessor(
        attempt_id="a1", action_id="act1", idempotency_key="k1", request=_signed(first)
    )
    assert service_module._validate_retry_predecessor(retry, predecessor) is None
    tampered = _signed(_bound(attempt_id="a2", action_id="x2", idempotency_key="k2", what="other"))
    tampered["action"].update(attempt_id="a2", action_id="x2", idempotency_key="k2")
    with pytest.raises(ValueError) as raised:
        service_module._validate_retry_predecessor(tampered, predecessor)
    assert str(raised.value) == "RETRY_SEMANTIC_TASK_MISMATCH"


# ---------------------------------------------------------------------------
# late binding: every facade-module name the helpers read is resolved at call time


def test_patch_uuid4_and_mint_reach_retry_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "uuid4", lambda: SimpleNamespace(hex="patched"))
    assert (
        service_module._retry_request({"request": {"task_id": "t"}})["attempt_id"]
        == "attempt-patched"
    )
    log: list[Any] = []
    identity = SimpleNamespace(task_id="T", attempt_id="A", action_id="X", idempotency_key="K")
    monkeypatch.setattr(service_module, "mint_retry_identity", Recorder(log, "mint", identity))
    assert service_module._retry_request({"request": {"task_id": "t"}})["attempt_id"] == "A"
    assert len(log) == 1


def test_patch_canonical_request_hash_reaches_retry_request_and_predecessor(
    monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    log: list[Any] = []
    monkeypatch.setattr(service_module, "canonical_request_hash", Recorder(log, "hash", "f" * 64))
    assert (
        service_module._retry_request({"request": {"task_id": "t"}})["action_request_hash"]
        == "f" * 64
    )
    result = service_module._retry_request({"task_id": "t1", "request": _signed(_bound())})
    assert result["action_request_hash"] == "f" * 64
    count = len(log)
    service_module._validate_retry_predecessor(_plain(**FRESH, what="differs"), _predecessor())
    assert len(log) == count + 2


def test_patch_lifecycle_action_type_reaches_retry_request(
    monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    seen: list[str] = []
    real = service_module.LifecycleActionType

    class Types:
        @property
        def TASK_RETRY(self) -> Any:
            seen.append("TASK_RETRY")
            return real.TASK_RETRY

        def __getattr__(self, name: str) -> Any:
            return getattr(real, name)

    monkeypatch.setattr(service_module, "LifecycleActionType", Types())
    service_module._retry_request({"task_id": "t1", "request": _signed(_bound())})
    assert seen == ["TASK_RETRY", "TASK_RETRY"]


def test_patch_worktree_manager_reaches_inherited_time(
    tmp_path: Path, manager: type[FakeManager]
) -> None:
    # ``manager`` patches ``WorktreeManager`` on the facade
    assert service_module._terminal_retry_inherited_worktree_time_allowed(_timing_state(tmp_path))
    assert [entry[0] for entry in manager.log] == [
        "init",
        "ownership",
        "entry",
        "active",
        "git",
        "git",
    ]


def test_patch_worktree_manager_reaches_released_lease_proof(
    tmp_path: Path, manager: type[FakeManager]
) -> None:
    manager.released = "PROOF"
    assert service_module._terminal_retry_released_lease_proof(_lease_state(tmp_path)) == "PROOF"
    assert [entry[0] for entry in manager.log] == ["init", "released"]


def test_patch_retryable_statuses_reach_predecessor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "RETRYABLE_TASK_STATUSES", frozenset({"PATCHED"}))
    with pytest.raises(ValueError) as raised:
        service_module._validate_retry_predecessor(_plain(**FRESH), _predecessor())
    assert str(raised.value) == "RETRY_REQUIRES_TERMINAL_TASK"
    assert (
        service_module._validate_retry_predecessor(_plain(**FRESH), _predecessor(status="PATCHED"))
        is None
    )


def test_patch_validators_and_strip_reach_terminal_semantic_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "_validated_action_request",
        Recorder(log, "validate", ({"workforce_admission": 1}, None)),
    )
    monkeypatch.setattr(
        service_module, "validate_workforce_dispatch_binding", Recorder(log, "dispatch")
    )
    monkeypatch.setattr(service_module, "_retry_semantic_payload", Recorder(log, "strip", {}))
    assert service_module._terminal_retry_semantic_payload({}) == {}
    assert [entry[0] for entry in log] == ["validate", "dispatch", "strip"]


def test_patch_terminal_semantic_payload_reaches_predecessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = iter([{"a": 1}, {"a": 2}])
    monkeypatch.setattr(
        service_module, "_terminal_retry_semantic_payload", lambda request: next(values)
    )
    with pytest.raises(ValueError) as raised:
        service_module._validate_retry_predecessor(_plain(**FRESH), _predecessor())
    assert str(raised.value) == "RETRY_SEMANTIC_TASK_MISMATCH"


def test_patch_inherited_time_reaches_pre_provider(inherited: list[Any]) -> None:
    assert (
        service_module._terminal_retry_pre_provider_state_allowed(_pre_provider_state())
        == "INHERITED-RESULT"
    )
    assert len(inherited) == 1


def test_patch_lease_proof_by_dotted_path_reaches_static_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service._terminal_retry_released_lease_proof",
        lambda _: True,
    )
    assert service_module._terminal_retry_verifier_static_failure_allowed(_static_state()) is True
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service._terminal_retry_released_lease_proof",
        lambda _: False,
    )
    assert service_module._terminal_retry_verifier_static_failure_allowed(_static_state()) is False


def test_patch_retry_request_reaches_the_retry_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    log: list[Any] = []
    monkeypatch.setattr(service_module, "_retry_request", Recorder(log, "retry", {"r": 1}))
    owner = SimpleNamespace()
    state = {"task_id": "t"}
    assert runtime_retry_bridge._Contract(owner).build_retry_request(state) == {"r": 1}
    assert log == [("retry", (state,), {})]


def test_retry_bridge_uses_the_facade_helper_and_its_patched_names(
    monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    result: Any = runtime_retry_bridge._Contract(SimpleNamespace()).build_retry_request({
        "task_id": "t1",
        "request": {"task_id": "t1"},
    })
    assert result["attempt_id"] == "attempt-tok"
    assert runtime_retry_bridge._Contract(SimpleNamespace()).maximum_attempts({}) == (
        service_module.DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK
    )


def test_facade_callers_reach_patched_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    log: list[Any] = []
    monkeypatch.setattr(
        service_module, "_terminal_retry_pre_provider_state_allowed", Recorder(log, "pre", False)
    )
    monkeypatch.setattr(
        service_module,
        "_terminal_retry_verifier_static_failure_allowed",
        Recorder(log, "static", False),
    )
    existing = {"request": {"action": {}}}
    allowed = service_module.SelfHostedTaskService._terminal_retry_revision_refresh_allowed(
        existing, {}, cast(Any, SimpleNamespace())
    )
    assert allowed is False
    assert [entry[0] for entry in log] == ["pre", "static"]


def test_default_attempt_budget_is_the_runtime_object() -> None:
    import nexus_runtime.task_retry as runtime_retry

    assert (
        service_module.DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK
        is runtime_retry.DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK
    )
