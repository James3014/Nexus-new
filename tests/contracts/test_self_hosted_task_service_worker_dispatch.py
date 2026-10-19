"""Characterization of the dispatch / worker-context cluster of ``SelfHostedTaskService`` (S9).

Big-file split step S9 moves these class members out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin:

* ``_select_initial_provider`` and ``_next_ready_provider`` (worker preflight walk);
* the static ``_assert_persisted_workforce_dispatch`` (persisted Workforce dispatch
  binding versus the request and the fresh binding);
* ``_revalidate_tracked_dispatch_task_card`` and ``_revalidate_provider_boundary`` (the
  governed identity re-read immediately before provider-side work);
* the static ``_replace_failed_target`` (escalation: replace a failed Target lease);
* ``_worker_context_materialization`` (the frozen Planner projection and its evidence
  journal before a WorkerRegistry call);
* ``_run_default_resumable`` and ``_run_default`` (the default runner, through
  ``RuntimeCoordinationBridge``).

These tests pin the behaviour before the move and must pass unchanged after it:

* the member table (descriptor kind, signature, docstring);
* every refusal of every member, in its order, with its exact message, and every
  pass-through; the call order of the collaborators (registry preflight, Target manager,
  controller, the task-card validators, ``RuntimeCoordinationBridge``);
* ``_worker_context_materialization``: the exact arguments of every collaborator
  (context package builder, capability invokers, evidence materializer, prompt
  composer), the persisted STARTED / COMPLETE journal records, the replay checks of a
  resumed attempt, the lock scope (both journal writes under the state ``flock``, the
  capability materialization outside it) and every readback refusal;
* that every facade-module name the moved code reads is resolved through the facade at
  call time (patched after a first call that reached the same site), and that instance,
  class and subclass patches of the members it reaches through ``self`` are honoured,
  also from the runtime coordination bridge.

No test launches a worker, leases an account or runs git: the registry, the Target
manager, the controller, the lifecycle identity resolver and ``RuntimeCoordinationBridge``
are recorders.  Self-deadlocks fail fast: an autouse fixture bounds the runtime store's
blocking ``flock`` to 15 s.  No test asserts on inode numbers, file modes or other
platform details.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import inspect
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, cast

import nexus_runtime.execution_state.store as store_module
import nexus_runtime.task_context as task_context_module
import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
import nexus.orchestrator.self_hosted_task_service_parts.worker_dispatch as worker_dispatch_module
import nexus.services.mainchain_entry as mainchain_module
import nexus.services.unified_runtime as unified_runtime_module
from nexus.contracts.lifecycle_action import ContractKind
from nexus.orchestrator import runtime_coordination_bridge
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

TRACKED = ContractKind.TRACKED_TASK_CARD.value
MEMBERS = (
    "_select_initial_provider",
    "_next_ready_provider",
    "_assert_persisted_workforce_dispatch",
    "_revalidate_tracked_dispatch_task_card",
    "_revalidate_provider_boundary",
    "_replace_failed_target",
    "_worker_context_materialization",
    "_run_default_resumable",
    "_run_default",
)
MATERIALIZATION_DOC = (
    "Materialize the frozen Planner projection before a WorkerRegistry call.\n\n"
    "The evidence journal is derived state kept beside the signed request and\n"
    "action.  A resumed attempt may consume a completed journal only; it may\n"
    "never execute an absent or incomplete journal a second time."
)
MEMBER_TABLE = {
    "_select_initial_provider": (
        "function",
        "(self, contract: 'ArchitectTaskContract', *, before_preflight: "
        "'Callable[[str], None]') -> 'tuple[str, Any]'",
        None,
    ),
    "_next_ready_provider": (
        "function",
        "(self, policy: 'WorkerEscalationPolicy', attempts: "
        "'Sequence[WorkerExecutionReceipt]', *, before_preflight: "
        "'Callable[[str], None]') -> 'Optional[str]'",
        None,
    ),
    "_assert_persisted_workforce_dispatch": (
        "staticmethod",
        "(state: 'Mapping[str, Any]', request: 'Mapping[str, Any]', binding: "
        "'Optional[Mapping[str, Any]]', *, active_provider: 'Optional[str]' = None) -> 'None'",
        None,
    ),
    "_revalidate_tracked_dispatch_task_card": (
        "function",
        "(self, contract: 'ArchitectTaskContract', request: 'Mapping[str, Any]', state: "
        "'Mapping[str, Any]', binding: 'Optional[Mapping[str, Any]]') -> 'None'",
        "Re-read the tracked card immediately before provider-side work.",
    ),
    "_revalidate_provider_boundary": (
        "function",
        "(self, contract: 'ArchitectTaskContract', request: 'Mapping[str, Any]', task_id: "
        "'str', binding: 'Optional[Mapping[str, Any]]', *, active_provider: "
        "'Optional[str]' = None) -> 'None'",
        "Re-read all governed identity immediately before provider-side work.",
    ),
    "_replace_failed_target": (
        "staticmethod",
        "(manager: 'WorktreeManager', controller: 'SelfHostedDevelopmentController', "
        "contract: 'ArchitectTaskContract', lease: 'TargetWorktreeLease', *, task_states: "
        "'Optional[Mapping[str, dict]]' = None) -> 'TargetWorktreeLease'",
        None,
    ),
    "_worker_context_materialization": (
        "function",
        "(self, *, request: 'Mapping[str, Any]', state: 'Mapping[str, Any]', task_id: "
        "'str', attempt_id: 'str', fresh_submission: 'bool', contract: "
        "'ArchitectTaskContract', lease: 'TargetWorktreeLease', base_prompt: 'str', "
        "actual_provider: 'str', actual_model: 'str | None') -> "
        "'tuple[str, dict[str, Any]] | None'",
        MATERIALIZATION_DOC,
    ),
    "_run_default_resumable": (
        "function",
        "(self, contract: 'ArchitectTaskContract', request: 'Mapping[str, Any]', update: "
        "'Callable[[str, dict[str, Any]], None]', *, task_id: 'str', attempt_id: 'str') "
        "-> 'dict[str, Any]'",
        None,
    ),
    "_run_default": ("function", "(self, contract, request, update)", None),
}

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
def _no_real_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    # the default runner must never reach a real RuntimeCoordinationBridge (worker launch)
    class _Refuse:
        def __init__(self, service: Any) -> None:
            raise AssertionError("a test reached the real RuntimeCoordinationBridge")

    monkeypatch.setattr(runtime_coordination_bridge, "RuntimeCoordinationBridge", _Refuse)


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def service(state_dir: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)


def _lock_held(state_dir: Path) -> bool:
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


class _CallRecorder:
    """Wraps a callable (or a class / module): every call is logged by name."""

    def __init__(self, log: list[str], name: str, real: Any) -> None:
        self.log, self.name, self.real = log, name, real

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.log.append(self.name)
        return self.real(*args, **kwargs)

    def __getattr__(self, attr: str) -> Any:
        value = getattr(self.real, attr)
        return _CallRecorder(self.log, f"{self.name}.{attr}", value) if callable(value) else value


# ---------------------------------------------------------------------------
# member table


def test_member_table() -> None:
    table = {}
    for name in MEMBERS:
        static = inspect.getattr_static(SelfHostedTaskService, name)
        func = static.__func__ if isinstance(static, staticmethod) else static
        # cleandoc: Python 3.13+ strips docstring indentation at compile time, 3.12 does not
        doc = inspect.cleandoc(func.__doc__) if func.__doc__ else func.__doc__
        table[name] = (type(static).__name__, str(inspect.signature(func)), doc)
    assert table == MEMBER_TABLE


def test_default_runner_is_the_bound_run_default(service) -> None:
    assert service.runner == service._run_default
    assert service.runner.__func__ is inspect.getattr_static(SelfHostedTaskService, "_run_default")


# ---------------------------------------------------------------------------
# provider selection


class _Registry:
    def __init__(self, ready: dict[str, bool], log: list[Any]) -> None:
        self.ready, self.log = ready, log

    def preflight(self, provider: str) -> Any:
        self.log.append(("preflight", provider))
        return SimpleNamespace(
            ready=self.ready.get(provider, False), reason=f"{provider}-not-ready", provider=provider
        )


def _selection_contract(order: Any = None, preferred: Any = None) -> Any:
    return SimpleNamespace(provider_order=order, preferred_provider=preferred)


@pytest.mark.parametrize(
    ("order", "preferred", "ready", "expected", "walk"),
    [
        (["codex", "gemini"], "x", {"codex": True}, "codex", ["codex"]),
        (["codex", "gemini"], "x", {"gemini": True}, "gemini", ["codex", "gemini"]),
        (None, "gemini", {"gemini": True}, "gemini", ["gemini"]),
        ([], "agy", {"agy": True}, "agy", ["agy"]),
        (None, None, {"codex": True}, "codex", ["codex"]),
        (None, "", {"codex": True}, "codex", ["codex"]),
        (("claude", "codex"), None, {"claude": True, "codex": True}, "claude", ["claude"]),
    ],
)
def test_select_initial_provider(service, order, preferred, ready, expected, walk) -> None:
    log: list[Any] = []
    service.worker_registry = _Registry(ready, log)
    provider, preflight = service._select_initial_provider(
        _selection_contract(order, preferred),
        before_preflight=lambda p: log.append(("before", p)),
    )
    assert provider == expected
    assert preflight.provider == expected and preflight.ready is True
    assert log == [entry for p in walk for entry in (("before", p), ("preflight", p))]


def test_select_initial_provider_refuses_with_every_reason(service) -> None:
    log: list[Any] = []
    service.worker_registry = _Registry({}, log)
    with pytest.raises(
        RuntimeError,
        match=r"^worker preflight failed: codex: codex-not-ready; agy: agy-not-ready$",
    ):
        service._select_initial_provider(
            _selection_contract(["codex", "agy"]), before_preflight=lambda p: log.append(p)
        )
    assert log == ["codex", ("preflight", "codex"), "agy", ("preflight", "agy")]


def test_select_initial_provider_before_preflight_can_abort(service) -> None:
    log: list[Any] = []
    service.worker_registry = _Registry({"codex": True}, log)

    def stop(provider: str) -> None:
        raise LookupError(f"stop:{provider}")

    with pytest.raises(LookupError, match="^stop:codex$"):
        service._select_initial_provider(_selection_contract(["codex"]), before_preflight=stop)
    assert log == []


@pytest.mark.parametrize(
    ("order", "strong", "attempted", "ready", "expected", "walk"),
    [
        (("codex", "gemini", "agy"), "x", ["codex"], {"gemini": True}, "gemini", ["gemini"]),
        (("codex", "gemini", "agy"), "x", ["codex"], {"agy": True}, "agy", ["gemini", "agy"]),
        (("codex", "gemini"), "x", ["codex", "gemini"], {"codex": True}, None, []),
        ((), "claude", [], {"claude": True}, "claude", ["claude"]),
        (None, "claude", ["claude"], {"claude": True}, None, []),
        (("codex",), "x", [], {}, None, ["codex"]),
        (("codex", "gemini"), "x", ["gemini", "gemini"], {"codex": True}, "codex", ["codex"]),
    ],
)
def test_next_ready_provider(service, order, strong, attempted, ready, expected, walk) -> None:
    log: list[Any] = []
    service.worker_registry = _Registry(ready, log)
    policy = SimpleNamespace(provider_order=order, strong_provider=strong)
    attempts = [SimpleNamespace(provider=p) for p in attempted]
    assert (
        service._next_ready_provider(
            cast(Any, policy), attempts, before_preflight=lambda p: log.append(("before", p))
        )
        == expected
    )
    assert log == [entry for p in walk for entry in (("before", p), ("preflight", p))]


def test_provider_selection_reads_the_instance_registry(service) -> None:
    # the registry is read through self at call time (no cached reference)
    first: list[Any] = []
    second: list[Any] = []
    service.worker_registry = _Registry({"codex": True}, first)
    service._select_initial_provider(
        _selection_contract(["codex"]), before_preflight=lambda p: None
    )
    service.worker_registry = _Registry({"codex": True}, second)
    service._select_initial_provider(
        _selection_contract(["codex"]), before_preflight=lambda p: None
    )
    policy = SimpleNamespace(provider_order=("codex",), strong_provider="x")
    service._next_ready_provider(cast(Any, policy), [], before_preflight=lambda p: None)
    assert first == [("preflight", "codex")]
    assert second == [("preflight", "codex"), ("preflight", "codex")]


# ---------------------------------------------------------------------------
# _assert_persisted_workforce_dispatch

DEMANDS = ({"role": "implementer", "count": 1},)
ADMISSION = {"overall_decision": "ALLOW", "records": ("r1",)}
BINDING = {
    "worker_id": "worker-1",
    "provider": "codex",
    "model": "model-1",
    "policy_hash": "p" * 64,
    "binding_hash": "b" * 64,
    "aggregate_binding_hash": "g" * 64,
}
ENVELOPE_IDENTITY = {
    "task_id": "t1",
    "attempt_id": "attempt-1",
    "task_card_path": "/cards/t1.md",
    "task_card_hash": "h" * 64,
}


def _persisted(**extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "workforce_dispatch": {
            "demands": [{"role": "implementer", "count": 1}],
            "admission": {"overall_decision": "ALLOW", "records": ["r1"]},
        },
        "selected_worker_id": "worker-1",
        "selected_provider": "codex",
        "selected_model": "model-1",
        "workforce_policy_hash": "p" * 64,
        "workforce_binding_hash": "b" * 64,
        "workforce_aggregate_binding_hash": "g" * 64,
    }
    state.update(extra)
    return state


def _dispatch_request(**extra: Any) -> dict[str, Any]:
    request: dict[str, Any] = {"workforce_demands": DEMANDS, "workforce_admission": ADMISSION}
    request.update(extra)
    return request


def _with_envelope() -> tuple[dict[str, Any], dict[str, Any]]:
    envelope = {**ENVELOPE_IDENTITY, "provider": "codex", "model": "model-1"}
    binding = {**BINDING, "canonical_dispatch_envelope": envelope}
    state = _persisted(canonical_dispatch_envelope=dict(envelope), **ENVELOPE_IDENTITY)
    return binding, state


assert_dispatch = SelfHostedTaskService._assert_persisted_workforce_dispatch


def test_assert_dispatch_without_binding_accepts_anything() -> None:
    assert assert_dispatch({}, {}, None) is None
    assert (
        assert_dispatch({"workforce_dispatch": 7}, {"canonical_dispatch_envelope": 1}, None) is None
    )
    assert assert_dispatch({}, {}, None, active_provider="other") is None


def test_assert_dispatch_accepts_the_matching_binding() -> None:
    # tuples in the request are compared after the facade's _jsonable projection
    assert assert_dispatch(_persisted(), _dispatch_request(), BINDING) is None
    assert (
        assert_dispatch(_persisted(), _dispatch_request(), BINDING, active_provider="codex") is None
    )
    binding, state = _with_envelope()
    assert assert_dispatch(state, _dispatch_request(), binding) is None
    assert assert_dispatch(state, _dispatch_request(), binding, active_provider="codex") is None


def test_assert_dispatch_reads_the_planner_and_admission_fallbacks() -> None:
    request = {
        "planner_output": {
            "workforce_admission": ADMISSION,
            "signal_snapshot": {"workforce_demands": DEMANDS},
        }
    }
    assert assert_dispatch(_persisted(), request, BINDING) is None
    request = {
        "planner": {"signal_snapshot": {"workforce_demands": DEMANDS}},
        "admission_binding": ADMISSION,
    }
    assert assert_dispatch(_persisted(), request, BINDING) is None


def test_assert_dispatch_field_values_compare_as_strings() -> None:
    state = _persisted(selected_worker_id=None)
    assert assert_dispatch(state, _dispatch_request(), {**BINDING, "worker_id": ""}) is None
    assert (
        assert_dispatch(
            _persisted(selected_provider="7"), _dispatch_request(), {**BINDING, "provider": 7}
        )
        is None
    )
    assert (
        assert_dispatch(
            _persisted(),
            _dispatch_request(),
            {**BINDING, "provider": "codex"},
            active_provider=cast(Any, "codex"),
        )
        is None
    )


STATE_DRIFT_CASES = [
    ("no persisted dispatch", lambda s, r: s.pop("workforce_dispatch")),
    ("persisted dispatch not a mapping", lambda s, r: s.update(workforce_dispatch=["x"])),
    ("demands drifted", lambda s, r: s["workforce_dispatch"].update(demands=[])),
    ("admission drifted", lambda s, r: s["workforce_dispatch"].update(admission={})),
    ("request demands drifted", lambda s, r: r.update(workforce_demands=({"role": "x"},))),
    (
        "request admission drifted",
        lambda s, r: r.update(workforce_admission={"overall_decision": "DENY"}),
    ),
    ("worker drifted", lambda s, r: s.update(selected_worker_id="worker-2")),
    ("provider drifted", lambda s, r: s.update(selected_provider="gemini")),
    ("model drifted", lambda s, r: s.update(selected_model="model-2")),
    ("policy hash drifted", lambda s, r: s.update(workforce_policy_hash="x")),
    ("binding hash drifted", lambda s, r: s.update(workforce_binding_hash="x")),
    ("aggregate hash drifted", lambda s, r: s.pop("workforce_aggregate_binding_hash")),
]


@pytest.mark.parametrize(
    ("label", "tamper"), STATE_DRIFT_CASES, ids=[c[0] for c in STATE_DRIFT_CASES]
)
def test_assert_dispatch_state_drift(label, tamper) -> None:
    state, request = _persisted(), _dispatch_request()
    tamper(state, request)
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_STATE_DRIFT$"):
        assert_dispatch(state, request, BINDING, active_provider="other")


def test_assert_dispatch_missing_binding_field_is_a_key_error() -> None:
    binding = dict(BINDING)
    binding.pop("aggregate_binding_hash")
    with pytest.raises(KeyError, match="aggregate_binding_hash"):
        assert_dispatch(_persisted(), _dispatch_request(), binding)


ENVELOPE_CASES = [
    (
        "binding envelope missing but request names one",
        "ENVELOPE_STATE",
        lambda b, s, r: (
            b.pop("canonical_dispatch_envelope"),
            r.update(canonical_dispatch_envelope={}),
        ),
    ),
    (
        "binding envelope not a mapping",
        "ENVELOPE_STATE",
        lambda b, s, r: (
            b.update(canonical_dispatch_envelope=["x"]),
            r.update(canonical_dispatch_envelope={}),
        ),
    ),
    (
        "persisted envelope missing",
        "ENVELOPE_STATE",
        lambda b, s, r: s.pop("canonical_dispatch_envelope"),
    ),
    (
        "persisted envelope differs",
        "ENVELOPE_STATE",
        lambda b, s, r: s["canonical_dispatch_envelope"].update(model="m2"),
    ),
    (
        "persisted envelope has an extra key",
        "ENVELOPE_STATE",
        lambda b, s, r: s["canonical_dispatch_envelope"].update(extra=1),
    ),
    ("task id drifted", "ENVELOPE_IDENTITY", lambda b, s, r: s.update(task_id="t2")),
    ("attempt drifted", "ENVELOPE_IDENTITY", lambda b, s, r: s.update(attempt_id="attempt-2")),
    (
        "card path drifted",
        "ENVELOPE_IDENTITY",
        lambda b, s, r: s.update(task_card_path="/cards/other.md"),
    ),
    ("card hash missing", "ENVELOPE_IDENTITY", lambda b, s, r: s.pop("task_card_hash")),
]


@pytest.mark.parametrize(
    ("label", "code", "tamper"), ENVELOPE_CASES, ids=[c[0] for c in ENVELOPE_CASES]
)
def test_assert_dispatch_envelope_drift(label, code, tamper) -> None:
    binding, state = _with_envelope()
    binding = copy.deepcopy(binding)
    request = _dispatch_request()
    tamper(binding, state, request)
    with pytest.raises(RuntimeError, match=f"^WORKFORCE_DISPATCH_{code}_DRIFT$"):
        assert_dispatch(state, request, binding, active_provider="other")


def test_assert_dispatch_envelope_check_needs_an_envelope_somewhere() -> None:
    # neither the binding nor the request carries an envelope: no envelope check at all
    state = _persisted(canonical_dispatch_envelope={"stale": True}, task_id="whatever")
    assert assert_dispatch(state, _dispatch_request(), BINDING) is None


def test_assert_dispatch_active_provider_drift_is_checked_last() -> None:
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_ACTIVE_PROVIDER_DRIFT$"):
        assert_dispatch(_persisted(), _dispatch_request(), BINDING, active_provider="gemini")
    binding, state = _with_envelope()
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_ACTIVE_PROVIDER_DRIFT$"):
        assert_dispatch(state, _dispatch_request(), binding, active_provider="")
    state["task_id"] = "t2"
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_ENVELOPE_IDENTITY_DRIFT$"):
        assert_dispatch(state, _dispatch_request(), binding, active_provider="gemini")


def test_assert_dispatch_is_reached_by_the_runtime_bridge_and_dispatch_binding(
    service, monkeypatch
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(
        service, "_assert_persisted_workforce_dispatch", lambda *a, **k: calls.append((a, k))
    )
    runtime_coordination_bridge._Contract(service).assert_persisted_dispatch(
        1, 2, 3, active_provider="p"
    )
    assert calls == [((1, 2, 3), {"active_provider": "p"})]
    source = inspect.getsource(service_module._recover_pre_provider_cli_envelope_drift)
    assert "_service_module().SelfHostedTaskService._assert_persisted_workforce_dispatch(" in source


# ---------------------------------------------------------------------------
# _revalidate_tracked_dispatch_task_card


class _Card:
    """A tracked-card scenario; the facade's card validators are recorders."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, log: list[Any]) -> None:
        card = tmp_path / "tasks" / "t1.md"
        card.parent.mkdir(parents=True, exist_ok=True)
        card.write_text("task_id: `t1`\n", encoding="utf-8")
        self.card_path = str(card)
        self.resolved = str(card.resolve())
        self.card_hash = "h" * 64
        self.contract = SimpleNamespace(task_id="t1")
        self.request: dict[str, Any] = {
            "contract_kind": TRACKED,
            "attempt_id": "attempt-1",
            "task_card_path": self.card_path,
            "task_card_hash": self.card_hash,
        }
        identity = {
            "task_id": "t1",
            "attempt_id": "attempt-1",
            "task_card_path": self.card_path,
            "task_card_hash": self.card_hash,
        }
        self.state: dict[str, Any] = {**identity, "contract_kind": TRACKED}
        self.binding: dict[str, Any] = {"canonical_dispatch_envelope": dict(identity)}
        self.identity: dict[str, Any] = {
            "contract_kind": TRACKED,
            "task_card_path": self.resolved,
            "task_card_hash": self.card_hash,
        }
        self.log = log

        def validate(contract: Any, request: Any, *, is_ephemeral: bool = False) -> None:
            log.append((
                "validate_task_card_binding",
                contract.task_id,
                dict(request),
                is_ephemeral,
            ))

        def resolve(contract: Any, request: Any, *, is_ephemeral: bool = False) -> dict[str, Any]:
            log.append((
                "resolve_lifecycle_identity",
                contract.task_id,
                dict(request),
                is_ephemeral,
            ))
            return dict(self.identity)

        monkeypatch.setattr(service_module, "validate_task_card_binding", validate)
        monkeypatch.setattr(service_module, "resolve_lifecycle_identity", resolve)

    def run(self, service: SelfHostedTaskService, binding: Any = "default") -> None:
        return service._revalidate_tracked_dispatch_task_card(
            cast(Any, self.contract),
            self.request,
            self.state,
            self.binding if binding == "default" else binding,
        )


@pytest.fixture
def card(tmp_path, monkeypatch) -> _Card:
    return _Card(tmp_path, monkeypatch, [])


def test_tracked_card_accepts_the_matching_card(service, card) -> None:
    assert card.run(service) is None
    request = dict(card.request)
    assert card.log == [
        ("validate_task_card_binding", "t1", request, True),
        ("resolve_lifecycle_identity", "t1", request, True),
    ]


def test_tracked_card_passes_the_instance_ephemeral_flag(service, card) -> None:
    # the flag is read from the instance at call time
    service.ephemeral = False
    card.run(service)
    assert [entry[3] for entry in card.log] == [False, False]


def test_tracked_card_without_binding(service, card) -> None:
    card.request["contract_kind"] = "OWNER_INLINE"
    card.state["contract_kind"] = ""
    assert card.run(service, binding=None) is None
    card.state["contract_kind"] = TRACKED
    with pytest.raises(RuntimeError, match="^WORKFORCE_ADMISSION_BINDING_MISSING$"):
        card.run(service, binding=None)
    card.state["contract_kind"] = ""
    card.request["contract_kind"] = TRACKED
    with pytest.raises(RuntimeError, match="^WORKFORCE_ADMISSION_BINDING_MISSING$"):
        card.run(service, binding=None)
    assert card.log == []


CARD_REFUSALS = [
    (
        "envelope missing",
        "WORKFORCE_DISPATCH_ENVELOPE_MISSING",
        False,
        lambda c: c.binding.pop("canonical_dispatch_envelope"),
    ),
    (
        "envelope not a mapping",
        "WORKFORCE_DISPATCH_ENVELOPE_MISSING",
        False,
        lambda c: c.binding.update(canonical_dispatch_envelope=[1]),
    ),
    (
        "request not tracked",
        "TASK_CARD_BINDING_MISMATCH: tracked dispatch card required",
        False,
        lambda c: c.request.update(contract_kind="OWNER_INLINE"),
    ),
    (
        "request kind missing",
        "TASK_CARD_BINDING_MISMATCH: tracked dispatch card required",
        False,
        lambda c: c.request.pop("contract_kind"),
    ),
    (
        "attempt missing",
        "TASK_CARD_BINDING_MISMATCH: tracked identity incomplete",
        True,
        lambda c: c.request.pop("attempt_id"),
    ),
    (
        "card path empty",
        "TASK_CARD_BINDING_MISMATCH: tracked identity incomplete",
        True,
        lambda c: c.request.update(task_card_path=""),
    ),
    (
        "card hash missing",
        "TASK_CARD_BINDING_MISMATCH: tracked identity incomplete",
        True,
        lambda c: c.request.pop("task_card_hash"),
    ),
    (
        "task id empty",
        "TASK_CARD_BINDING_MISMATCH: tracked identity incomplete",
        True,
        lambda c: setattr(c.contract, "task_id", ""),
    ),
    (
        "envelope task drifted",
        "TASK_CARD_BINDING_MISMATCH: dispatch envelope identity drifted",
        True,
        lambda c: c.binding["canonical_dispatch_envelope"].update(task_id="t2"),
    ),
    (
        "envelope hash drifted",
        "TASK_CARD_BINDING_MISMATCH: dispatch envelope identity drifted",
        True,
        lambda c: c.binding["canonical_dispatch_envelope"].update(task_card_hash="x"),
    ),
    (
        "envelope attempt missing",
        "TASK_CARD_BINDING_MISMATCH: dispatch envelope identity drifted",
        True,
        lambda c: c.binding["canonical_dispatch_envelope"].pop("attempt_id"),
    ),
    (
        "persisted attempt drifted",
        "TASK_CARD_BINDING_MISMATCH: persisted card identity drifted",
        True,
        lambda c: c.state.update(attempt_id="attempt-2"),
    ),
    (
        "persisted path missing",
        "TASK_CARD_BINDING_MISMATCH: persisted card identity drifted",
        True,
        lambda c: c.state.pop("task_card_path"),
    ),
    (
        "persisted kind missing",
        "TASK_CARD_BINDING_MISMATCH: persisted tracked contract missing",
        True,
        lambda c: c.state.pop("contract_kind"),
    ),
    (
        "identity kind drifted",
        "TASK_CARD_BINDING_MISMATCH: tracked card changed after submit",
        True,
        lambda c: c.identity.update(contract_kind="NONE"),
    ),
    (
        "identity path drifted",
        "TASK_CARD_BINDING_MISMATCH: tracked card changed after submit",
        True,
        lambda c: c.identity.update(task_card_path=c.card_path + ".old"),
    ),
    (
        "identity path missing",
        "TASK_CARD_BINDING_MISMATCH: tracked card changed after submit",
        True,
        lambda c: c.identity.pop("task_card_path"),
    ),
    (
        "identity hash drifted",
        "TASK_CARD_BINDING_MISMATCH: tracked card changed after submit",
        True,
        lambda c: c.identity.update(task_card_hash="x"),
    ),
]


@pytest.mark.parametrize(
    ("label", "message", "validated", "tamper"), CARD_REFUSALS, ids=[c[0] for c in CARD_REFUSALS]
)
def test_tracked_card_refusals_in_order(service, card, label, message, validated, tamper) -> None:
    tamper(card)
    with pytest.raises(RuntimeError) as caught:
        card.run(service)
    assert str(caught.value) == message
    assert [entry[0] for entry in card.log] == (
        ["validate_task_card_binding", "resolve_lifecycle_identity"] if validated else []
    )


def test_tracked_card_validator_errors_propagate_before_the_identity(
    service, card, monkeypatch
) -> None:
    def refuse(contract: Any, request: Any, *, is_ephemeral: bool = False) -> None:
        card.log.append("validate")
        raise RuntimeError("TASK_CARD_BINDING_MISMATCH: from validator")

    monkeypatch.setattr(service_module, "validate_task_card_binding", refuse)
    card.binding["canonical_dispatch_envelope"]["task_id"] = "t2"  # would also fail later
    with pytest.raises(RuntimeError, match="^TASK_CARD_BINDING_MISMATCH: from validator$"):
        card.run(service)
    assert card.log == ["validate"]


def test_tracked_card_compares_the_identity_path_to_the_resolved_card(
    service, card, tmp_path, monkeypatch
) -> None:
    # a relative card path resolves against the cwd first, else against CANONICAL_SOURCE_ROOT
    monkeypatch.chdir(tmp_path)
    for side in (card.request, card.state, card.binding["canonical_dispatch_envelope"]):
        side["task_card_path"] = "tasks/t1.md"
    assert card.run(service) is None
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", tmp_path / "canonical")
    for side in (card.request, card.state, card.binding["canonical_dispatch_envelope"]):
        side["task_card_path"] = "tasks/absent.md"
    card.identity["task_card_path"] = str((tmp_path / "canonical/tasks/absent.md").resolve())
    assert card.run(service) is None


def test_tracked_card_stringifies_the_compared_fields(service, card) -> None:
    card.state["attempt_id"] = None
    with pytest.raises(RuntimeError, match="persisted card identity drifted"):
        card.run(service)
    card.state["attempt_id"] = "attempt-1"
    card.binding["canonical_dispatch_envelope"]["task_card_hash"] = None
    with pytest.raises(RuntimeError, match="dispatch envelope identity drifted"):
        card.run(service)


# ---------------------------------------------------------------------------
# _revalidate_provider_boundary


def _boundary_spies(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, log: list[Any]
) -> None:
    monkeypatch.setattr(
        service,
        "_revalidate_tracked_dispatch_task_card",
        lambda contract, request, state, binding: log.append((
            "card",
            contract,
            dict(request),
            dict(state),
            binding,
        )),
    )
    monkeypatch.setattr(
        service,
        "_assert_persisted_workforce_dispatch",
        lambda state, request, binding, *, active_provider=None: log.append((
            "dispatch",
            dict(state),
            dict(request),
            binding,
            active_provider,
        )),
    )


def test_provider_boundary_rereads_the_state_then_card_then_dispatch(service, monkeypatch) -> None:
    log: list[Any] = []
    _boundary_spies(service, monkeypatch, log)
    stored = service._write_state(
        "t1", {"task_id": "t1", "attempt_id": "a1", "status": "WORKER_RUNNING"}
    )
    reads: list[str] = []
    real_read = service._read_state
    monkeypatch.setattr(
        service, "_read_state", lambda task_id: (reads.append(task_id), real_read(task_id))[1]
    )
    binding = {"provider": "codex"}
    assert (
        service._revalidate_provider_boundary("C", {"r": 1}, "t1", binding, active_provider="codex")
        is None
    )
    assert reads == ["t1"]
    assert log == [
        ("card", "C", {"r": 1}, stored, binding),
        ("dispatch", stored, {"r": 1}, binding, "codex"),
    ]


def test_provider_boundary_defaults(service, monkeypatch) -> None:
    log: list[Any] = []
    _boundary_spies(service, monkeypatch, log)
    assert service._revalidate_provider_boundary("C", {}, "absent", None) is None
    assert log == [("card", "C", {}, {}, None), ("dispatch", {}, {}, None, None)]


@pytest.mark.parametrize(
    ("state", "request_", "message"),
    [
        (
            {"status": "BLOCKED_INVALID_STATE"},
            {},
            "WORKFORCE_ADMISSION_BINDING_MISSING: persisted state invalid",
        ),
        (
            {"status": "SUBMITTED", "state_valid": False},
            {},
            "WORKFORCE_ADMISSION_BINDING_MISSING: persisted state invalid",
        ),
        (
            {"status": "SUBMITTED", "contract_kind": TRACKED},
            {},
            "WORKFORCE_ADMISSION_BINDING_MISSING",
        ),
        (
            {"status": "SUBMITTED"},
            {"contract_kind": TRACKED},
            "WORKFORCE_ADMISSION_BINDING_MISSING",
        ),
    ],
)
def test_provider_boundary_refusals(service, monkeypatch, state, request_, message) -> None:
    log: list[Any] = []
    _boundary_spies(service, monkeypatch, log)
    monkeypatch.setattr(service, "_read_state", lambda task_id: dict(state))
    with pytest.raises(RuntimeError) as caught:
        service._revalidate_provider_boundary("C", request_, "t1", None, active_provider="codex")
    assert str(caught.value) == message
    assert log == []


def test_provider_boundary_invalid_state_refuses_even_with_a_binding(service, monkeypatch) -> None:
    log: list[Any] = []
    _boundary_spies(service, monkeypatch, log)
    monkeypatch.setattr(service, "_read_state", lambda task_id: {"state_valid": False})
    with pytest.raises(RuntimeError, match="persisted state invalid"):
        service._revalidate_provider_boundary("C", {}, "t1", {"provider": "codex"})
    monkeypatch.setattr(service, "_read_state", lambda task_id: {"state_valid": 0})
    service._revalidate_provider_boundary(
        "C", {"contract_kind": TRACKED}, "t1", {"provider": "codex"}
    )
    assert [entry[0] for entry in log] == ["card", "dispatch"]


def test_provider_boundary_end_to_end_with_real_members(service, card, monkeypatch) -> None:
    binding, persisted = _with_envelope()
    state = {
        **persisted,
        **card.state,
        "task_id": "t1",
        "attempt_id": "attempt-1",
        "status": "WORKER_RUNNING",
    }
    state["canonical_dispatch_envelope"] = {
        **binding["canonical_dispatch_envelope"],
        "task_card_path": card.card_path,
    }
    binding = {**binding, "canonical_dispatch_envelope": dict(state["canonical_dispatch_envelope"])}
    service._write_state("t1", state)
    request = {**card.request, **_dispatch_request()}
    assert (
        service._revalidate_provider_boundary(
            cast(Any, card.contract), request, "t1", binding, active_provider="codex"
        )
        is None
    )
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_ACTIVE_PROVIDER_DRIFT$"):
        service._revalidate_provider_boundary(
            cast(Any, card.contract), request, "t1", binding, active_provider="gemini"
        )
    assert [entry[0] for entry in card.log] == [
        "validate_task_card_binding",
        "resolve_lifecycle_identity",
    ] * 2
    port = runtime_coordination_bridge._Contract(service)
    assert port.revalidate_provider_boundary(card.contract, request, "t1", binding, "codex") is None
    assert port.revalidate_task_card(card.contract, request, state, binding) is None


# ---------------------------------------------------------------------------
# _replace_failed_target


class _Manager:
    def __init__(self, log: list[Any], head: str = "head-0") -> None:
        self.log, self.head = log, head

    def verify_controller_unchanged(self, contract: Any, *, expected_status_sha256: Any) -> None:
        self.log.append(("verify_controller_unchanged", contract.task_id, expected_status_sha256))

    def _run_git(self, args: list[str], *, cwd: Any) -> str:
        self.log.append(("_run_git", list(args), cwd))
        return self.head

    def cleanup(self, task_id: str, *, force: bool = False) -> None:
        self.log.append(("cleanup", task_id, force))


class _ControllerWithStates:
    def __init__(self, log: list[Any]) -> None:
        self.log = log

    def prepare_task(self, contract: Any, task_states: Any = None) -> str:
        self.log.append(("prepare_task", contract.task_id, task_states))
        return "NEW-LEASE"


class _ControllerPlain:
    def __init__(self, log: list[Any]) -> None:
        self.log = log

    def prepare_task(self, contract: Any) -> str:
        self.log.append(("prepare_task", contract.task_id))
        return "PLAIN-LEASE"


LEASE = SimpleNamespace(
    controller_status_sha256="s" * 64, target_worktree="/targets/t1", initial_head="head-0"
)
CONTRACT = SimpleNamespace(task_id="t1")


def test_replace_failed_target_with_task_states() -> None:
    log: list[Any] = []
    states = {"t0": {"status": "SUBMITTED"}}
    result = SelfHostedTaskService._replace_failed_target(
        cast(Any, _Manager(log)),
        cast(Any, _ControllerWithStates(log)),
        cast(Any, CONTRACT),
        cast(Any, LEASE),
        task_states=states,
    )
    assert result == "NEW-LEASE"
    assert log == [
        ("verify_controller_unchanged", "t1", "s" * 64),
        ("_run_git", ["rev-parse", "HEAD"], "/targets/t1"),
        ("cleanup", "t1", True),
        ("prepare_task", "t1", states),
    ]


def test_replace_failed_target_default_task_states_is_none() -> None:
    log: list[Any] = []
    SelfHostedTaskService._replace_failed_target(
        cast(Any, _Manager(log)),
        cast(Any, _ControllerWithStates(log)),
        cast(Any, CONTRACT),
        cast(Any, LEASE),
    )
    assert log[-1] == ("prepare_task", "t1", None)


def test_replace_failed_target_legacy_prepare_task_signature() -> None:
    log: list[Any] = []
    result = SelfHostedTaskService._replace_failed_target(
        cast(Any, _Manager(log)),
        cast(Any, _ControllerPlain(log)),
        cast(Any, CONTRACT),
        cast(Any, LEASE),
        task_states={"x": {}},
    )
    assert result == "PLAIN-LEASE"
    assert log[-1] == ("prepare_task", "t1")


def test_replace_failed_target_refuses_a_moved_head() -> None:
    log: list[Any] = []
    with pytest.raises(
        RuntimeError, match="^failed worker changed Target HEAD; escalation is blocked$"
    ):
        SelfHostedTaskService._replace_failed_target(
            cast(Any, _Manager(log, head="head-1")),
            cast(Any, _ControllerWithStates(log)),
            cast(Any, CONTRACT),
            cast(Any, LEASE),
        )
    assert [entry[0] for entry in log] == ["verify_controller_unchanged", "_run_git"]


def test_replace_failed_target_controller_drift_stops_first() -> None:
    log: list[Any] = []

    class Drifted(_Manager):
        def verify_controller_unchanged(
            self, contract: Any, *, expected_status_sha256: Any
        ) -> None:
            raise RuntimeError("controller drifted")

    with pytest.raises(RuntimeError, match="^controller drifted$"):
        SelfHostedTaskService._replace_failed_target(
            cast(Any, Drifted(log)),
            cast(Any, _ControllerWithStates(log)),
            cast(Any, CONTRACT),
            cast(Any, LEASE),
        )
    assert log == []


def test_replace_failed_target_through_the_runtime_bridge(service, monkeypatch) -> None:
    log: list[Any] = []
    monkeypatch.setattr(
        service, "_bridge_validate_claim", lambda *a, **k: log.append(("claim", a, k))
    )
    monkeypatch.setattr(service, "_workspace_task_states", lambda: {"w": {}})
    monkeypatch.setattr(service_module, "WorktreeManager", lambda root_dir: _Manager(log))
    monkeypatch.setattr(
        service_module,
        "SelfHostedDevelopmentController",
        lambda worktree_manager: _ControllerWithStates(log),
    )
    contract = SimpleNamespace(task_id="t1", target_worktree_root="/targets")
    preparation = runtime_coordination_bridge._Target(service)
    result = preparation.replace_failed_lease(
        contract, LEASE, {"task_id": "t1", "attempt_id": "a1"}
    )
    assert result == "NEW-LEASE"
    assert log[0] == ("claim", ("t1", "a1"), {"operation": "TARGET_REPLACE_LEASE"})
    assert log[-1] == ("prepare_task", "t1", {"w": {}})
    monkeypatch.setattr(
        service, "_replace_failed_target", lambda *a, **k: ("PATCHED", a[2].task_id, k)
    )
    assert preparation.replace_failed_lease(
        contract, LEASE, {"task_id": "t1", "attempt_id": "a1"}
    ) == (
        "PATCHED",
        "t1",
        {"task_states": {"w": {}}},
    )


# ---------------------------------------------------------------------------
# _worker_context_materialization

ENVELOPE = {
    "task_id": "ctx-1",
    "attempt_id": "attempt-1",
    "workspace_revision": "w" * 40,
    "planner_decision_hash": " " + "d" * 64 + " ",
    "planner_plan_hash": "p" * 64,
    "worker_id": "worker-1",
    "provider": "codex",
    "model": "model-1",
}
PLANNER = {
    "decision_hash": "d" * 64,
    "plan_hash": "p" * 64,
    "selected_capabilities": ["memory", "codeintel"],
    "context": {"codeintel": {"allowed_files": ["a.py"], "verify_commands": ["true"]}},
}
BUNDLE = {"bundle": "B", "capabilities": {"memory": {"status": "SUCCEEDED"}}}


class _Stubs:
    """Recorders for the four collaborators of the materialization."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, state_dir: Path) -> None:
        self.log: list[Any] = []
        self.state_dir = state_dir
        self.package_status = "PASS"
        self.bundle: Any = BUNDLE
        self.during_materialize: Any = None
        stubs = self

        def build_worker_context_package(request: Any) -> dict[str, Any]:
            stubs.log.append(("package", copy.deepcopy(dict(request))))
            planner = request.get("planner_output") or {}
            return {
                "status": stubs.package_status,
                "selected_capability_ids": tuple(planner.get("selected_capabilities", ())),
                "n": len([e for e in stubs.log if e[0] == "package"]),
            }

        def append_model_context_to_prompt(prompt: str, package: Any) -> str:
            stubs.log.append(("append", prompt, copy.deepcopy(package)))
            return f"{prompt}|package-{package['n']}"

        def build_mainchain_capability_invokers(**kwargs: Any) -> dict[str, Any]:
            stubs.log.append(("invokers", copy.deepcopy(kwargs)))
            return {"memory": "INVOKER"}

        def materialize_selected_capability_evidence(**kwargs: Any) -> Any:
            stubs.log.append(("materialize", copy.deepcopy(kwargs), _lock_held(stubs.state_dir)))
            if stubs.during_materialize is not None:
                stubs.during_materialize()
            return {"ignored": True}, stubs.bundle

        monkeypatch.setattr(
            task_context_module, "build_worker_context_package", build_worker_context_package
        )
        monkeypatch.setattr(
            task_context_module, "append_model_context_to_prompt", append_model_context_to_prompt
        )
        monkeypatch.setattr(
            mainchain_module,
            "build_mainchain_capability_invokers",
            build_mainchain_capability_invokers,
        )
        monkeypatch.setattr(
            unified_runtime_module,
            "materialize_selected_capability_evidence",
            materialize_selected_capability_evidence,
        )

    def kinds(self) -> list[str]:
        return [entry[0] for entry in self.log]


@pytest.fixture
def stubs(monkeypatch, state_dir) -> _Stubs:
    return _Stubs(monkeypatch, state_dir)


class _Ctx:
    def __init__(self, service: SelfHostedTaskService, tmp_path: Path) -> None:
        self.service = service
        self.target = tmp_path / "target"
        self.target.mkdir(exist_ok=True)
        self.request: dict[str, Any] = {
            "task_id": "ctx-1",
            "attempt_id": "attempt-1",
            "workspace_revision": "w" * 40,
            "what": "bounded worker context",
            "planner_output": copy.deepcopy(PLANNER),
            "canonical_dispatch_envelope": dict(ENVELOPE),
            "rie_knowledge_identity": {"repo": "r"},
            "planner": {"p": 1},
            "unrelated": "kept",
        }
        self.state: dict[str, Any] = {
            "task_id": "ctx-1",
            "attempt_id": "attempt-1",
            "status": "SUBMITTED",
            "action_request_hash": " " + "a" * 64 + " ",
            "controller_revision": "c" * 40,
            "canonical_dispatch_envelope": dict(ENVELOPE),
        }
        service._write_state("ctx-1", copy.deepcopy(self.state))
        self.contract = SimpleNamespace(controller_revision="C" * 40, target_base_revision="T" * 40)
        self.lease = SimpleNamespace(target_worktree=str(self.target), initial_head="h" * 40)

    def run(self, **overrides: Any) -> Any:
        kwargs: dict[str, Any] = dict(
            request=self.request,
            state=self.state,
            task_id="ctx-1",
            attempt_id="attempt-1",
            fresh_submission=True,
            contract=self.contract,
            lease=self.lease,
            base_prompt="BASE",
            actual_provider="codex",
            actual_model="model-1",
        )
        kwargs.update(overrides)
        return self.service._worker_context_materialization(**kwargs)

    def stored(self) -> dict[str, Any]:
        return cast(dict, self.service._read_state("ctx-1"))


@pytest.fixture
def ctx(service, tmp_path) -> _Ctx:
    return _Ctx(service, tmp_path)


def _started(ctx: _Ctx) -> dict[str, Any]:
    target = str(ctx.target.resolve())
    return {
        "schema": "nexus.worker_model_context_materialization.v1",
        "status": "STARTED",
        "task_id": "ctx-1",
        "attempt_id": "attempt-1",
        "action_request_hash": "a" * 64,
        "revision": "c" * 40,
        "controller_revision": "c" * 40,
        "target_revision": "h" * 40,
        "target_worktree": target,
        "planner_decision_id": "d" * 64,
        "planner_plan_hash": "p" * 64,
        "selected_capabilities": ["memory", "codeintel"],
    }


def _complete(ctx: _Ctx, bundle: Any = BUNDLE) -> dict[str, Any]:
    return {
        **_started(ctx),
        "status": "COMPLETE",
        "bundle_hash": service_module._sha256_json(bundle),
        "bundle": copy.deepcopy(bundle),
        "capability_observations": {},
        "capability_observations_hash": service_module._sha256_json({}),
        "producer_revision": "c" * 40,
    }


class _TopLevelJsonable:
    """A facade ``_jsonable`` stand-in that logs top-level calls on journal records only.

    The real ``_jsonable`` recurses through the facade name (and the state store's write
    path projects the whole state through it), so only depth-1 calls are the call sites.
    """

    SCHEMA = "nexus.worker_model_context_materialization.v1"

    def __init__(self, real: Any, on_record: Any) -> None:
        self.real, self.on_record, self.depth = real, on_record, 0

    def __call__(self, value: Any) -> Any:
        self.depth += 1
        try:
            result = self.real(value)
        finally:
            self.depth -= 1
        if self.depth == 0 and isinstance(value, dict) and value.get("schema") == self.SCHEMA:
            result = self.on_record(value, result)
        return result


def test_materialization_fresh_submission_exact_flow(ctx, stubs) -> None:
    original = copy.deepcopy(ctx.request)
    prompt, package = ctx.run()
    target = str(ctx.target.resolve())
    assert prompt == "BASE|package-2"
    assert package == {"status": "PASS", "selected_capability_ids": ("memory", "codeintel"), "n": 2}
    assert ctx.request == original
    assert stubs.kinds() == ["package", "invokers", "materialize", "package", "append"]
    preliminary = stubs.log[0][1]
    assert preliminary == {
        "task_id": "ctx-1",
        "attempt_id": "attempt-1",
        "what": "bounded worker context",
        "planner_output": PLANNER,
        "canonical_dispatch_envelope": ENVELOPE,
    }
    assert stubs.log[1][1] == {
        "codeintel": PLANNER["context"]["codeintel"],
        "include_postflight_gates": True,
    }
    materialize = stubs.log[2][1]
    assert materialize == {
        "planner_output": PLANNER,
        "selected_capabilities": ["memory", "codeintel"],
        "task_id": "ctx-1",
        "task_statement": "bounded worker context",
        "workspace_revision": "w" * 40,
        "plan_hash": "p" * 64,
        "planner_decision_id": "d" * 64,
        "capability_invokers": {"memory": "INVOKER"},
        "capability_context": {
            "task_id": "ctx-1",
            "workspace_revision": "w" * 40,
            "planner": {"p": 1},
            "rie_knowledge_identity": {"repo": "r"},
            "workspace_root": target,
            "target_worktree": target,
            "target_revision": "h" * 40,
            "controller_revision": "c" * 40,
        },
        "codeintel": PLANNER["context"]["codeintel"],
    }
    assert list(materialize["capability_context"]) == [
        "task_id",
        "workspace_revision",
        "planner",
        "rie_knowledge_identity",
        "workspace_root",
        "target_worktree",
        "target_revision",
        "controller_revision",
    ]
    assert stubs.log[2][2] is False  # capability work runs outside the state lock
    final_request = stubs.log[3][1]
    assert final_request == {
        **original,
        "task_id": "ctx-1",
        "attempt_id": "attempt-1",
        "workspace_revision": "w" * 40,
        "task_statement": "bounded worker context",
        "planner_output": {**PLANNER, "capability_evidence_bundle": BUNDLE},
        "canonical_dispatch_envelope": ENVELOPE,
    }
    assert stubs.log[4][1] == "BASE"
    record = ctx.stored()["worker_model_context_materialization"]
    assert record == _complete(ctx)
    assert record["bundle_hash"] == service_module._sha256_json(BUNDLE)
    assert (
        record["bundle_hash"]
        == hashlib.sha256(
            json.dumps(BUNDLE, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
    )


def test_materialization_writes_the_started_record_first_under_the_lock(
    ctx, stubs, state_dir, monkeypatch
) -> None:
    seen: list[Any] = []

    def during() -> None:
        current = ctx.stored()["worker_model_context_materialization"]
        seen.append(dict(current))

    stubs.during_materialize = during
    jsonable_locked: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "_jsonable",
        _TopLevelJsonable(
            service_module._jsonable,
            lambda value, result: (
                jsonable_locked.append((value["status"], _lock_held(state_dir))),
                result,
            )[1],
        ),
    )
    ctx.run()
    assert seen == [_started(ctx)]
    assert jsonable_locked == [("STARTED", True), ("COMPLETE", True)]


def test_materialization_resume_consumes_a_complete_journal_without_replay(ctx, stubs) -> None:
    first = ctx.run()
    stubs.log.clear()
    second = ctx.run(state=ctx.stored(), fresh_submission=False)
    assert second == (
        "BASE|package-2",
        {"status": "PASS", "selected_capability_ids": ("memory", "codeintel"), "n": 2},
    )
    assert first[0] == second[0]
    assert stubs.kinds() == ["package", "package", "append"]
    assert stubs.log[1][1]["planner_output"]["capability_evidence_bundle"] == BUNDLE


def test_materialization_resume_uses_the_persisted_bundle(ctx, stubs) -> None:
    other = {"other": "bundle"}
    state = {**ctx.state, "worker_model_context_materialization": _complete(ctx, other)}
    ctx.run(state=state, fresh_submission=False)
    assert stubs.log[1][1]["planner_output"]["capability_evidence_bundle"] == other
    assert "worker_model_context_materialization" not in ctx.stored()


@pytest.mark.parametrize(
    ("request_patch", "state_patch", "result"),
    [
        (
            {"planner_output": None, "canonical_dispatch_envelope": None},
            {"canonical_dispatch_envelope": None},
            None,
        ),
        (
            {
                "planner_output": None,
                "canonical_dispatch_envelope": None,
                "worker_candidate_ingress": False,
            },
            {"canonical_dispatch_envelope": {}, "workforce_dispatch": {}},
            None,
        ),
        (
            {
                "planner_output": None,
                "canonical_dispatch_envelope": None,
                "worker_candidate_ingress": True,
            },
            {"canonical_dispatch_envelope": None},
            "worker_context_binding_missing",
        ),
        (
            {"planner_output": "x", "canonical_dispatch_envelope": None},
            {"canonical_dispatch_envelope": None, "workforce_dispatch": {"x": 1}},
            "worker_context_binding_missing",
        ),
        (
            {"canonical_dispatch_envelope": None},
            {"canonical_dispatch_envelope": None},
            "worker_context_binding_missing",
        ),
        ({"planner_output": None}, {}, "worker_context_binding_missing"),
        ({"planner_output": [1]}, {}, "worker_context_binding_missing"),
    ],
)
def test_materialization_binding_presence(ctx, stubs, request_patch, state_patch, result) -> None:
    ctx.request.update(request_patch)
    ctx.state.update(state_patch)
    if result is None:
        assert ctx.run() is None
    else:
        with pytest.raises(RuntimeError) as caught:
            ctx.run()
        assert str(caught.value) == result
    assert stubs.log == []


def test_materialization_envelope_prefers_the_state_and_falls_back_to_the_request(
    ctx, stubs
) -> None:
    ctx.state["canonical_dispatch_envelope"] = {**ENVELOPE, "planner_plan_hash": "q" * 64}
    ctx.run()
    assert stubs.log[0][1]["canonical_dispatch_envelope"]["planner_plan_hash"] == "q" * 64
    stubs.log.clear()
    # an empty persisted envelope falls back to the request's (whose plan hash differs from
    # the journal written above)
    with pytest.raises(
        RuntimeError, match="^worker_context_materialization_planner_plan_hash_mismatch$"
    ):
        ctx.run(fresh_submission=False, state={**ctx.stored(), "canonical_dispatch_envelope": {}})
    assert stubs.log[0][1]["canonical_dispatch_envelope"] == ENVELOPE


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("task_id", "other", "worker_context_task_substitution"),
        ("attempt_id", "attempt-2", "worker_context_attempt_substitution"),
    ],
)
def test_materialization_substitution_refusals(ctx, stubs, field, value, message) -> None:
    ctx.request[field] = value
    with pytest.raises(RuntimeError, match=f"^{message}$"):
        ctx.run()
    assert stubs.log == []


@pytest.mark.parametrize("empty", [None, ""])
def test_materialization_empty_request_identity_is_allowed(ctx, stubs, empty) -> None:
    ctx.request["task_id"] = empty
    ctx.request["attempt_id"] = empty
    ctx.run()
    assert stubs.log[0][1]["task_id"] == "ctx-1" and stubs.log[0][1]["attempt_id"] == "attempt-1"
    assert stubs.log[3][1]["task_id"] == "ctx-1" and stubs.log[3][1]["attempt_id"] == "attempt-1"


@pytest.mark.parametrize(
    ("request_codeintel", "planner_context", "expected"),
    [
        ({"explicit": True}, {"codeintel": {"planner": True}}, {"explicit": True}),
        (None, {"codeintel": {"planner": True}}, {"planner": True}),
        ("not-a-mapping", {"codeintel": {"planner": True}}, {"planner": True}),
        (None, {"codeintel": "x"}, None),
        (None, "not-a-mapping", None),
        (None, None, None),
    ],
)
def test_materialization_codeintel_precedence(
    ctx, stubs, request_codeintel, planner_context, expected
) -> None:
    if request_codeintel is not None:
        ctx.request["codeintel"] = request_codeintel
    ctx.request["planner_output"]["context"] = planner_context
    ctx.run()
    assert stubs.log[1][1]["codeintel"] == expected
    assert stubs.log[2][1]["codeintel"] == expected


@pytest.mark.parametrize(
    ("request_patch", "state_patch", "workspace", "statement"),
    [
        ({}, {}, "w" * 40, "bounded worker context"),
        (
            {"workspace_revision": "", "controller_revision": " r1 "},
            {},
            "r1",
            "bounded worker context",
        ),
        ({"workspace_revision": None}, {}, "c" * 40, "bounded worker context"),
        (
            {"workspace_revision": None, "what": "", "task_statement": "ts"},
            {"controller_revision": ""},
            "",
            "ts",
        ),
        ({"what": None}, {}, "w" * 40, ""),
    ],
)
def test_materialization_workspace_revision_and_statement(
    ctx, stubs, request_patch, state_patch, workspace, statement
) -> None:
    ctx.request.update(request_patch)
    ctx.state.update(state_patch)
    ctx.run()
    assert stubs.log[0][1]["what"] == statement
    assert stubs.log[2][1]["workspace_revision"] == workspace
    assert stubs.log[2][1]["task_statement"] == statement
    assert stubs.log[3][1]["workspace_revision"] == workspace
    assert stubs.log[3][1]["task_statement"] == statement


def test_materialization_preflight_package_must_pass(ctx, stubs) -> None:
    stubs.package_status = "BLOCKED"
    with pytest.raises(RuntimeError, match="^worker_context_preflight_invalid$"):
        ctx.run()
    assert stubs.kinds() == ["package"]
    assert "worker_model_context_materialization" not in ctx.stored()


@pytest.mark.parametrize(
    ("provider", "model"),
    [("gemini", "model-1"), ("codex", "model-2"), ("codex", None), (" codex", "model-1")],
)
def test_materialization_provider_model_substitution(ctx, stubs, provider, model) -> None:
    with pytest.raises(RuntimeError, match="^worker_context_provider_model_substitution$"):
        ctx.run(actual_provider=provider, actual_model=model)
    assert stubs.kinds() == ["package"]


def test_materialization_envelope_provider_and_model_are_stripped(ctx, stubs) -> None:
    ctx.state["canonical_dispatch_envelope"] = {**ENVELOPE, "provider": " codex ", "model": None}
    ctx.run(actual_model=None)
    ctx.state["canonical_dispatch_envelope"] = {**ENVELOPE, "model": ""}
    with pytest.raises(RuntimeError, match="^worker_context_provider_model_substitution$"):
        ctx.run(actual_model="None")


def test_materialization_revision_fallbacks(ctx, stubs) -> None:
    ctx.state["controller_revision"] = None
    ctx.lease.initial_head = ""
    ctx.run()
    record = ctx.stored()["worker_model_context_materialization"]
    assert (
        record["controller_revision"]
        == record["revision"]
        == record["producer_revision"]
        == "C" * 40
    )
    assert record["target_revision"] == "T" * 40
    assert stubs.log[2][1]["capability_context"]["controller_revision"] == "C" * 40
    assert stubs.log[2][1]["capability_context"]["target_revision"] == "T" * 40


def test_materialization_selected_capabilities_are_strings(ctx, stubs) -> None:
    ctx.request["planner_output"]["selected_capabilities"] = [1, "memory"]
    ctx.run()
    assert stubs.log[2][1]["selected_capabilities"] == ["1", "memory"]
    assert ctx.stored()["worker_model_context_materialization"]["selected_capabilities"] == [
        "1",
        "memory",
    ]


def test_materialization_codeintel_lookup_context(ctx, stubs) -> None:
    (ctx.target / "mod.py").write_text("x = 1\n", encoding="utf-8")
    ctx.request["codeintel_lookup"] = {"target_symbol": "mod.x", "search_paths": ["mod.py"]}
    ctx.run()
    context = stubs.log[2][1]["capability_context"]
    expected = service_module._codeintel_lookup_context(
        ctx.request["codeintel_lookup"], str(ctx.target.resolve())
    )
    assert expected and all(context[key] == value for key, value in expected.items())
    assert context["workspace_root"] == str(ctx.target.resolve())


def test_materialization_passes_allowed_files_as_xray_targets(ctx, stubs) -> None:
    """#2688: xray scanned a default file on the worker path; it now gets the task's files."""
    (ctx.target / "nexus").mkdir()
    (ctx.target / "nexus" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (ctx.target / "nexus" / "b.py").write_text("y = 2\n", encoding="utf-8")
    # nexus/new.py does not exist yet (the task creates it): xray would block on it.
    ctx.request["allowed_files"] = ["nexus/a.py", "nexus/new.py", "nexus/b.py"]
    ctx.run()
    context = stubs.log[2][1]["capability_context"]
    assert context["xray_targets"] == ["nexus/a.py", "nexus/b.py"]
    assert "target_files" not in context  # other executors keep their inputs


def test_materialization_passes_empty_xray_targets_when_no_allowed_file_exists(ctx, stubs) -> None:
    ctx.request["allowed_files"] = ["nexus/new.py"]
    ctx.run()
    assert stubs.log[2][1]["capability_context"]["xray_targets"] == []


def test_capability_observations_keep_trigger_store_and_outputs() -> None:
    """#2688 witnesses could not see trigger_source or store paths: the runtime bundle
    entries drop them. The raw stage results keep them under response."""
    results = {
        "xray": {
            "status": "INVOKED",
            "response": {
                "trigger_source": "planner_task_signal:xray_signal",
                "response": {
                    "outcome": {
                        "semantic_status": "SUCCEEDED",
                        "output_paths": ["/tmp/nexus-xray-x/xray_report_full.md"],
                        "scan_targets": ["/wt/pkg/a.py"],
                        "result": {"report_preview": "secret prompt text not kept"},
                    }
                },
            },
        },
        "memory": {
            "status": "INVOKED",
            "response": {"response": {"outcome": {"hit_count": 0, "result": {"root": "/state"}}}},
        },
        "belief": {
            "status": "INVOKED",
            "response": {
                "response": {"outcome": {"confidence": 0.7, "state_file": "/state/.nexus/b.json"}}
            },
        },
        "pregate": {"status": "SKIPPED", "skip_reason": "SKIPPED_POLICY_NOT_TRIGGERED"},
        "broken": "not-a-mapping",
    }

    observed = worker_dispatch_module._capability_observations(results)

    assert observed["xray"] == {
        "status": "INVOKED",
        "skip_reason": "",
        "trigger_source": "planner_task_signal:xray_signal",
        "semantic_status": "SUCCEEDED",
        "output_paths": ["/tmp/nexus-xray-x/xray_report_full.md"],
        "scan_targets": ["/wt/pkg/a.py"],
    }
    assert observed["memory"]["store_root"] == "/state" and observed["memory"]["hit_count"] == 0
    assert observed["belief"]["state_file"] == "/state/.nexus/b.json"
    assert observed["pregate"]["skip_reason"] == "SKIPPED_POLICY_NOT_TRIGGERED"
    assert "broken" not in observed
    assert worker_dispatch_module._capability_observations(None) == {}


def test_capability_observations_are_bounded_json_safe_and_message_free() -> None:
    """#2719 Codex: unbounded, nested or non-JSON values and raw error text."""
    huge = "x" * 300_000
    results = {
        "xray": {
            "status": "INVOKED",
            "response": {
                "trigger_source": huge,
                "response": {
                    "outcome": {
                        "output_paths": [huge] * 100 + [{"nested": "dict"}, 3],
                        "scan_targets": {"a", "b"},
                        "confidence": float("nan"),
                        "hit_count": float("inf"),
                        "findings_hit_count": float("-inf"),
                        "resolved_run_root": 10**400,
                        "error": "SECRET_TOKEN",
                        "result": {"root": {"nested": True}},
                    }
                },
            },
        }
    }

    observed = worker_dispatch_module._capability_observations(results)
    xray = observed["xray"]

    assert len(xray["trigger_source"]) == 512
    assert len(xray["output_paths"]) == 16 and all(len(p) == 512 for p in xray["output_paths"])
    assert not {
        "scan_targets",
        "confidence",
        "hit_count",
        "findings_hit_count",
        "store_root",
        "resolved_run_root",
    } & set(xray)
    assert xray["error_present"] is True and "SECRET" not in json.dumps(observed)
    json.dumps(observed, allow_nan=False)  # strict JSON
    assert len(json.dumps(observed)) < 20_000


def test_resume_rejects_tampered_capability_observations(ctx, stubs) -> None:
    record = _complete(ctx)
    record["capability_observations"] = {"xray": {"status": "INVOKED"}}  # hash still of {}
    ctx.state["worker_model_context_materialization"] = record
    with pytest.raises(RuntimeError, match="worker_context_observations_hash_mismatch"):
        ctx.run(fresh_submission=False)


def test_resume_accepts_a_record_written_before_observations(ctx, stubs) -> None:
    record = _complete(ctx)
    record.pop("capability_observations")
    record.pop("capability_observations_hash")
    ctx.state["worker_model_context_materialization"] = record
    ctx.run(fresh_submission=False)


def test_materialization_derives_a_codeintel_lookup_from_the_task(ctx, stubs) -> None:
    """#2721: without codeintel_lookup, codeintel refused every worker-path task."""
    (ctx.target / "mod.py").write_text(
        "def bounded_worker_context():\n    return 1\n", encoding="utf-8"
    )
    ctx.request["allowed_files"] = ["mod.py"]
    ctx.run()
    context = stubs.log[2][1]["capability_context"]
    assert context["target_symbol"] == "mod.bounded_worker_context"
    assert list(context["search_paths"]) == ["mod.py"]


def test_materialization_keeps_an_explicit_codeintel_lookup(ctx, stubs) -> None:
    (ctx.target / "mod.py").write_text(
        "x = 1\ndef bounded_worker_context():\n    return 1\n", encoding="utf-8"
    )
    ctx.request["allowed_files"] = ["mod.py"]
    ctx.request["codeintel_lookup"] = {"target_symbol": "mod.x", "search_paths": ["mod.py"]}
    ctx.run()
    assert stubs.log[2][1]["capability_context"]["target_symbol"] == "mod.x"


def test_materialization_passes_existing_allowed_files_to_belief(ctx, stubs) -> None:
    (ctx.target / "nexus").mkdir()
    (ctx.target / "nexus" / "a.py").write_text("x = 1\n", encoding="utf-8")
    ctx.request["allowed_files"] = ["nexus/a.py"]
    ctx.run()
    assert stubs.log[2][1]["capability_context"]["belief_target_files"] == ["nexus/a.py"]


@pytest.mark.parametrize(
    "allowed",
    [["nexus/new.py", "nexus/a.py"], ["nexus/a.py", "nexus/b.py"], ["nexus/new.py"], ["nexus"]],
)
def test_materialization_withholds_belief_target_when_ambiguous(ctx, stubs, allowed) -> None:
    (ctx.target / "nexus").mkdir()
    for name in ("a.py", "b.py"):
        (ctx.target / "nexus" / name).write_text("x = 1\n", encoding="utf-8")
    ctx.request["allowed_files"] = allowed
    ctx.run()
    assert "belief_target_files" not in stubs.log[2][1]["capability_context"]


def test_materialization_withholds_belief_target_through_escaping_symlink(
    ctx, stubs, tmp_path
) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    (ctx.target / "nexus").mkdir()
    (ctx.target / "nexus" / "link.py").symlink_to(outside)
    ctx.request["allowed_files"] = ["nexus/link.py"]
    ctx.run()
    assert "belief_target_files" not in stubs.log[2][1]["capability_context"]


def test_materialization_resume_without_journal_is_unknown(ctx, stubs) -> None:
    with pytest.raises(
        RuntimeError, match="^OUTCOME_UNKNOWN:worker_context_materialization_missing$"
    ):
        ctx.run(fresh_submission=False)
    assert stubs.kinds() == ["package"]


@pytest.mark.parametrize(
    "record",
    [{"status": "STARTED"}, {"status": "FAILED"}, ["COMPLETE"], "COMPLETE", {}],
)
def test_materialization_incomplete_journal_is_unknown(ctx, stubs, record) -> None:
    ctx.state["worker_model_context_materialization"] = record
    for fresh in (True, False):
        with pytest.raises(
            RuntimeError, match="^OUTCOME_UNKNOWN:worker_context_materialization_incomplete$"
        ):
            ctx.run(fresh_submission=fresh)
    assert stubs.kinds() == ["package", "package"]


RECORD_KEYS = [
    "task_id",
    "attempt_id",
    "action_request_hash",
    "revision",
    "planner_decision_id",
    "planner_plan_hash",
    "selected_capabilities",
    "controller_revision",
    "target_revision",
    "target_worktree",
]


@pytest.mark.parametrize("key", RECORD_KEYS)
def test_materialization_journal_mismatch_in_key_order(ctx, stubs, key) -> None:
    record = _complete(ctx)
    for later in RECORD_KEYS[RECORD_KEYS.index(key) :]:
        record[later] = "tampered"
    ctx.state["worker_model_context_materialization"] = record
    with pytest.raises(RuntimeError, match=f"^worker_context_materialization_{key}_mismatch$"):
        ctx.run(fresh_submission=False)


def test_materialization_journal_bundle_checks(ctx, stubs) -> None:
    record = _complete(ctx)
    record["bundle"] = ["not", "a", "mapping"]
    record["bundle_hash"] = ""
    ctx.state["worker_model_context_materialization"] = record
    with pytest.raises(RuntimeError, match="^OUTCOME_UNKNOWN:worker_context_bundle_missing$"):
        ctx.run(fresh_submission=False)
    record["bundle"] = dict(BUNDLE)
    with pytest.raises(RuntimeError, match="^worker_context_bundle_hash_mismatch$"):
        ctx.run(fresh_submission=False)
    record["bundle_hash"] = service_module._sha256_json({"other": 1})
    with pytest.raises(RuntimeError, match="^worker_context_bundle_hash_mismatch$"):
        ctx.run(fresh_submission=False)
    record["bundle_hash"] = service_module._sha256_json(BUNDLE)
    assert ctx.run(fresh_submission=False)[0] == "BASE|package-5"


def test_materialization_claim_refusals(ctx, stubs, service) -> None:
    service._mutate_state("ctx-1", lambda s: s.update(attempt_id="attempt-2"))
    with pytest.raises(RuntimeError, match="^worker_context_materialization_attempt_changed$"):
        ctx.run()
    service._mutate_state(
        "ctx-1",
        lambda s: s.update(
            attempt_id="attempt-1", worker_model_context_materialization={"status": "x"}
        ),
    )
    with pytest.raises(
        RuntimeError, match="^OUTCOME_UNKNOWN:worker_context_materialization_replay$"
    ):
        ctx.run()
    assert "materialize" not in stubs.kinds()


def test_materialization_claim_on_a_missing_state(ctx, stubs, service, state_dir) -> None:
    (state_dir / "ctx-1.json").unlink()
    with pytest.raises(
        RuntimeError, match="^OUTCOME_UNKNOWN:worker_context_materialization_claim$"
    ):
        ctx.run()
    assert stubs.kinds() == ["package"]


def _tampered_mutate(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch, which: int, tamper: Any
) -> list[int]:
    real = service._mutate_state
    calls: list[int] = []

    def mutate(task_id: str, mutator: Any) -> Any:
        calls.append(1)
        result = real(task_id, mutator)
        return tamper(result) if len(calls) == which else result

    monkeypatch.setattr(service, "_mutate_state", mutate)
    return calls


@pytest.mark.parametrize(
    ("which", "tamper", "message"),
    [
        (1, lambda r: None, "OUTCOME_UNKNOWN:worker_context_materialization_claim"),
        (1, lambda r: [r], "OUTCOME_UNKNOWN:worker_context_materialization_claim"),
        (
            1,
            lambda r: {**r, "worker_model_context_materialization": {"status": "COMPLETE"}},
            "OUTCOME_UNKNOWN:worker_context_materialization_claim_readback",
        ),
        (
            1,
            lambda r: {**r, "worker_model_context_materialization": None},
            "OUTCOME_UNKNOWN:worker_context_materialization_claim_readback",
        ),
        (2, lambda r: None, "OUTCOME_UNKNOWN:worker_context_materialization_write"),
        (
            2,
            lambda r: {**r, "worker_model_context_materialization": {"status": "STARTED"}},
            "OUTCOME_UNKNOWN:worker_context_materialization_readback",
        ),
        (
            2,
            lambda r: {**r, "worker_model_context_materialization": "COMPLETE"},
            "OUTCOME_UNKNOWN:worker_context_materialization_readback",
        ),
        (
            2,
            lambda r: {
                **r,
                "worker_model_context_materialization": {"status": "COMPLETE", "bundle": [1]},
            },
            "OUTCOME_UNKNOWN:worker_context_bundle_readback",
        ),
    ],
)
def test_materialization_readback_refusals(
    ctx, stubs, service, monkeypatch, which, tamper, message
) -> None:
    _tampered_mutate(service, monkeypatch, which, tamper)
    with pytest.raises(RuntimeError) as caught:
        ctx.run()
    assert str(caught.value) == message
    assert stubs.kinds() == (["package"] if which == 1 else ["package", "invokers", "materialize"])


def test_materialization_uses_the_readback_bundle(ctx, stubs, service, monkeypatch) -> None:
    readback = {"readback": True}
    _tampered_mutate(
        service,
        monkeypatch,
        2,
        lambda r: {
            **r,
            "worker_model_context_materialization": {"status": "COMPLETE", "bundle": readback},
        },
    )
    ctx.run()
    assert stubs.log[3][1]["planner_output"]["capability_evidence_bundle"] == readback


@pytest.mark.parametrize(
    ("during", "message"),
    [
        (
            lambda s: s.update(attempt_id="attempt-9"),
            "worker_context_materialization_attempt_changed",
        ),
        (
            lambda s: s.update(worker_model_context_materialization=None),
            "OUTCOME_UNKNOWN:worker_context_materialization_replay",
        ),
        (
            lambda s: s["worker_model_context_materialization"].update(status="COMPLETE"),
            "OUTCOME_UNKNOWN:worker_context_materialization_replay",
        ),
        (
            lambda s: s["worker_model_context_materialization"].update(target_revision="x"),
            "worker_context_materialization_binding_changed",
        ),
        (
            lambda s: s["worker_model_context_materialization"].pop("selected_capabilities"),
            "worker_context_materialization_binding_changed",
        ),
    ],
)
def test_materialization_persist_refusals(ctx, stubs, service, during, message) -> None:
    stubs.during_materialize = lambda: service._mutate_state("ctx-1", during)
    with pytest.raises(RuntimeError) as caught:
        ctx.run()
    assert str(caught.value) == message
    assert stubs.kinds() == ["package", "invokers", "materialize"]


def test_materialization_persist_tolerates_extra_started_keys(ctx, stubs, service) -> None:
    stubs.during_materialize = lambda: service._mutate_state(
        "ctx-1", lambda s: s["worker_model_context_materialization"].update(extra="kept?")
    )
    ctx.run()
    record = ctx.stored()["worker_model_context_materialization"]
    assert "extra" not in record and record["status"] == "COMPLETE"


def test_materialization_bundle_is_copied(ctx, stubs) -> None:
    class Bundle(dict):
        pass

    stubs.bundle = Bundle(BUNDLE)
    ctx.run()
    final_bundle = stubs.log[3][1]["planner_output"]["capability_evidence_bundle"]
    assert type(final_bundle) is dict and final_bundle == BUNDLE


def test_materialization_state_files(ctx, stubs, state_dir) -> None:
    ctx.run()
    assert sorted(p.name for p in state_dir.rglob("*")) == [".state.lock", "ctx-1.json"]


def test_materialization_with_the_real_context_builders(service, tmp_path, monkeypatch) -> None:
    # the real nexus_runtime package builder and prompt composer, a recorded materializer
    ctx = _Ctx(service, tmp_path)
    ctx.request["planner_output"]["selected_capabilities"] = ["memory"]
    from nexus.services.capability_evidence_bundle import build_capability_evidence_bundle

    bundle = build_capability_evidence_bundle(
        task_id="ctx-1",
        workspace_revision="w" * 40,
        task_statement=ctx.request["what"],
        plan_payload=ctx.request["planner_output"],
        plan_hash="p" * 64,
        planner_decision_id="d" * 64,
        capability_results={
            "memory": {
                "task_id": "ctx-1",
                "invoked": True,
                "gate_passed": True,
                "status": "SUCCEEDED",
                "evidence_refs": ["evidence:memory"],
                "consumer_payload": {"fields": {"summary": "S9_CHARACTERIZATION_PAYLOAD"}},
            }
        },
        selected_capabilities=["memory"],
    )
    monkeypatch.setattr(mainchain_module, "build_mainchain_capability_invokers", lambda **k: {})
    monkeypatch.setattr(
        unified_runtime_module, "materialize_selected_capability_evidence", lambda **k: ({}, bundle)
    )
    prompt, package = ctx.run()
    assert prompt.startswith("BASE\n\n[NEXUS MODEL CONTEXT]\n")
    assert "S9_CHARACTERIZATION_PAYLOAD" in prompt
    assert package["status"] == "PASS" and package["selected_capability_ids"] == ["memory"]
    again = ctx.run(state=ctx.stored(), fresh_submission=False)
    assert again == (prompt, package)


def test_materialization_through_the_runtime_bridge(ctx, stubs, monkeypatch, service) -> None:
    port = runtime_coordination_bridge._Contract(service)
    kwargs = dict(
        request=ctx.request,
        state=ctx.state,
        task_id="ctx-1",
        attempt_id="attempt-1",
        fresh_submission=True,
        contract=ctx.contract,
        lease=ctx.lease,
        base_prompt="BASE",
        actual_provider="codex",
        actual_model="model-1",
    )
    assert port.materialize_worker_context(**kwargs)[0] == "BASE|package-2"
    monkeypatch.setattr(
        service, "_worker_context_materialization", lambda **k: ("PATCHED", sorted(k))
    )
    assert port.materialize_worker_context(**kwargs) == ("PATCHED", sorted(kwargs))


# ---------------------------------------------------------------------------
# _run_default_resumable / _run_default


class _BridgeRecorder:
    log: list[Any] = []

    def __init__(self, service: Any) -> None:
        _BridgeRecorder.log.append(("init", service))

    def execute(self, task_id: str, attempt_id: str, **kwargs: Any) -> dict[str, Any]:
        _BridgeRecorder.log.append(("execute", task_id, attempt_id, kwargs))
        return {"status": "EXECUTED", "task_id": task_id}


@pytest.fixture
def bridge(monkeypatch) -> list[Any]:
    _BridgeRecorder.log = []
    monkeypatch.setattr(runtime_coordination_bridge, "RuntimeCoordinationBridge", _BridgeRecorder)
    return _BridgeRecorder.log


def test_run_default_resumable_executes_through_the_bridge(service, bridge) -> None:
    def update(status: str, values: dict[str, Any]) -> None:
        return None

    result = service._run_default_resumable("C", {"r": 1}, update, task_id="t1", attempt_id="a1")
    assert result == {"status": "EXECUTED", "task_id": "t1"}
    assert bridge == [
        ("init", service),
        ("execute", "t1", "a1", {"contract": "C", "request": {"r": 1}, "update": update}),
    ]


@pytest.mark.parametrize(
    ("stored", "attempt"),
    [
        ({"task_id": "t1", "attempt_id": "a7", "status": "SUBMITTED"}, "a7"),
        ({"task_id": "t1", "status": "SUBMITTED"}, ""),
        ({"task_id": "t1", "attempt_id": 5, "status": "SUBMITTED"}, "5"),
        ({"task_id": "t1", "attempt_id": None, "status": "SUBMITTED"}, "None"),
        (None, ""),
    ],
)
def test_run_default_reads_the_attempt_from_the_state(service, bridge, stored, attempt) -> None:
    if stored is not None:
        service._write_state("t1", stored)
    contract = SimpleNamespace(task_id="t1")
    assert service._run_default(contract, {"r": 2}, "U") == {"status": "EXECUTED", "task_id": "t1"}
    assert bridge[1] == (
        "execute",
        "t1",
        attempt,
        {"contract": contract, "request": {"r": 2}, "update": "U"},
    )


def test_run_default_dispatches_through_self(service, monkeypatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(
        service,
        "_read_state",
        lambda task_id: (calls.append(("read", task_id)), {"attempt_id": "a3"})[1],
    )
    monkeypatch.setattr(
        service,
        "_run_default_resumable",
        lambda contract, request, update, *, task_id, attempt_id: (
            calls.append(("resumable", contract.task_id, request, update, task_id, attempt_id)),
            "R",
        )[1],
    )
    assert service._run_default(SimpleNamespace(task_id="t9"), {"q": 1}, "U") == "R"
    assert calls == [("read", "t9"), ("resumable", "t9", {"q": 1}, "U", "t9", "a3")]


def test_run_default_is_the_runner_used_by_the_runtime(service, bridge, monkeypatch) -> None:
    hits: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_run_default_resumable",
        lambda self, *a, **k: (hits.append(k), "CLS")[1],
    )
    fresh = SelfHostedTaskService(state_dir=service.state_dir, auto_reconcile=False, ephemeral=True)
    assert cast(Any, fresh).runner(SimpleNamespace(task_id="t1"), {}, None) == "CLS"
    assert hits == [{"task_id": "t1", "attempt_id": ""}]


# ---------------------------------------------------------------------------
# late binding: every facade name the moved code reads, patched after a first call


def test_late_contract_kind_at_all_three_sites(service, card, monkeypatch) -> None:
    card.run(service)  # a first call that reaches every site
    late = SimpleNamespace(TRACKED_TASK_CARD=SimpleNamespace(value="PATCHED"))
    monkeypatch.setattr(service_module, "ContractKind", late)
    # site 1 (request kind): the real tracked kind is no longer the tracked kind
    with pytest.raises(
        RuntimeError, match="^TASK_CARD_BINDING_MISMATCH: tracked dispatch card required$"
    ):
        card.run(service)
    # site 2 (persisted kind)
    card.request["contract_kind"] = "PATCHED"
    with pytest.raises(
        RuntimeError, match="^TASK_CARD_BINDING_MISMATCH: persisted tracked contract missing$"
    ):
        card.run(service)
    # site 3 (identity kind)
    card.state["contract_kind"] = "PATCHED"
    with pytest.raises(
        RuntimeError, match="^TASK_CARD_BINDING_MISMATCH: tracked card changed after submit$"
    ):
        card.run(service)
    card.identity["contract_kind"] = "PATCHED"
    assert card.run(service) is None


def test_late_card_validators(service, card, monkeypatch, tmp_path) -> None:
    card.run(service)
    log: list[str] = []
    for name in ("validate_task_card_binding", "resolve_lifecycle_identity"):
        monkeypatch.setattr(
            service_module, name, _CallRecorder(log, name, getattr(service_module, name))
        )
    card.run(service)
    assert log == ["validate_task_card_binding", "resolve_lifecycle_identity"]
    monkeypatch.setattr(
        service_module, "_resolve_task_card_path", lambda value: tmp_path / "late-card.md"
    )
    with pytest.raises(RuntimeError, match="tracked card changed after submit"):
        card.run(service)
    card.identity["task_card_path"] = str(tmp_path / "late-card.md")
    assert card.run(service) is None


def test_late_tracked_dispatch_required_in_the_card_check(service, card, monkeypatch) -> None:
    card.request["contract_kind"] = "OWNER_INLINE"
    card.state["contract_kind"] = ""
    assert card.run(service, binding=None) is None
    monkeypatch.setattr(
        service_module, "_tracked_dispatch_required", lambda request, state=None: True
    )
    with pytest.raises(RuntimeError, match="^WORKFORCE_ADMISSION_BINDING_MISSING$"):
        card.run(service, binding=None)


def test_late_tracked_dispatch_required_in_the_provider_boundary(service, monkeypatch) -> None:
    log: list[Any] = []
    _boundary_spies(service, monkeypatch, log)
    service._revalidate_provider_boundary("C", {}, "absent", None)
    assert [entry[0] for entry in log] == ["card", "dispatch"]
    log.clear()
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "_tracked_dispatch_required",
        lambda request, state=None: (seen.append(dict(state or {})), True)[1],
    )
    with pytest.raises(RuntimeError, match="^WORKFORCE_ADMISSION_BINDING_MISSING$"):
        service._revalidate_provider_boundary("C", {}, "absent", None)
    assert log == [] and seen == [{}]


def test_late_dispatch_inputs_and_jsonable(monkeypatch) -> None:
    state, request = _persisted(), _dispatch_request()
    assert_dispatch(state, request, BINDING)
    monkeypatch.setattr(
        service_module, "_workforce_dispatch_inputs", lambda r: (["late-d"], {"late": "a"})
    )
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_STATE_DRIFT$"):
        assert_dispatch(state, request, BINDING)
    state["workforce_dispatch"] = {"demands": ["late-d"], "admission": {"late": "a"}}
    assert assert_dispatch(state, request, BINDING) is None
    monkeypatch.setattr(service_module, "_jsonable", lambda value: ["late-jsonable", repr(value)])
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_STATE_DRIFT$"):
        assert_dispatch(state, request, BINDING)
    # both comparisons (demands and admission) go through the facade's _jsonable
    late_demands = ["late-jsonable", repr(["late-d"])]
    late_admission = ["late-jsonable", repr({"late": "a"})]
    state["workforce_dispatch"] = {"demands": late_demands, "admission": {"late": "a"}}
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_STATE_DRIFT$"):
        assert_dispatch(state, request, BINDING)
    state["workforce_dispatch"] = {"demands": ["late-d"], "admission": late_admission}
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_STATE_DRIFT$"):
        assert_dispatch(state, request, BINDING)
    state["workforce_dispatch"] = {"demands": late_demands, "admission": late_admission}
    assert assert_dispatch(state, request, BINDING) is None


def test_late_jsonable_in_both_journal_writes(ctx, stubs, service, monkeypatch) -> None:
    ctx.run()
    service._mutate_state("ctx-1", lambda s: s.pop("worker_model_context_materialization"))
    log: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "_jsonable",
        _TopLevelJsonable(
            service_module._jsonable,
            lambda value, result: (
                log.append(value["status"]),
                {**result, "late_marker": value["status"]},
            )[1],
        ),
    )
    ctx.run()
    assert log == ["STARTED", "COMPLETE"]
    assert ctx.stored()["worker_model_context_materialization"]["late_marker"] == "COMPLETE"


def test_late_sha256_json_at_both_sites(ctx, stubs, service, monkeypatch) -> None:
    ctx.run()
    ctx.run(state=ctx.stored(), fresh_submission=False)  # reaches the replay check
    service._mutate_state("ctx-1", lambda s: s.pop("worker_model_context_materialization"))
    real = service_module._sha256_json
    monkeypatch.setattr(service_module, "_sha256_json", lambda value: "late-" + real(value))
    ctx.run()
    record = ctx.stored()["worker_model_context_materialization"]
    assert record["bundle_hash"] == "late-" + real(BUNDLE)
    assert ctx.run(state=ctx.stored(), fresh_submission=False)[0].startswith("BASE|")
    monkeypatch.setattr(service_module, "_sha256_json", real)
    with pytest.raises(RuntimeError, match="^worker_context_bundle_hash_mismatch$"):
        ctx.run(state=ctx.stored(), fresh_submission=False)


def test_late_codeintel_lookup_context(ctx, stubs, service, monkeypatch) -> None:
    ctx.run()
    service._mutate_state("ctx-1", lambda s: s.pop("worker_model_context_materialization"))
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "_codeintel_lookup_context",
        lambda raw, root: (seen.append((raw, root)), {"lookup_marker": "late"})[1],
    )
    ctx.request["codeintel_lookup"] = {"k": 1}
    ctx.run()
    assert seen == [({"k": 1}, str(ctx.target.resolve()))]
    assert stubs.log[-3][1]["capability_context"]["lookup_marker"] == "late"


def test_late_inspect_in_replace_failed_target(monkeypatch) -> None:
    log: list[Any] = []
    SelfHostedTaskService._replace_failed_target(
        cast(Any, _Manager(log)),
        cast(Any, _ControllerWithStates(log)),
        cast(Any, CONTRACT),
        cast(Any, LEASE),
        task_states={"a": {}},
    )
    assert log[-1] == ("prepare_task", "t1", {"a": {}})
    seen: list[Any] = []
    late = SimpleNamespace(
        signature=lambda func: (seen.append(func.__name__), SimpleNamespace(parameters={}))[1]
    )
    monkeypatch.setattr(service_module, "inspect", late)
    SelfHostedTaskService._replace_failed_target(
        cast(Any, _Manager(log)),
        cast(Any, _ControllerWithStates(log)),
        cast(Any, CONTRACT),
        cast(Any, LEASE),
        task_states={"a": {}},
    )
    assert seen == ["prepare_task"]
    assert log[-1] == ("prepare_task", "t1", None)


def test_late_runtime_bridge_class_is_read_per_call(service, monkeypatch) -> None:
    first: list[Any] = []
    second: list[Any] = []

    def recorder(log: list[Any]) -> Any:
        class Bridge:
            def __init__(self, svc: Any) -> None:
                log.append("init")

            def execute(self, *args: Any, **kwargs: Any) -> str:
                log.append("execute")
                return "OK"

        return Bridge

    monkeypatch.setattr(runtime_coordination_bridge, "RuntimeCoordinationBridge", recorder(first))
    service._run_default_resumable("C", {}, None, task_id="t1", attempt_id="a1")
    monkeypatch.setattr(runtime_coordination_bridge, "RuntimeCoordinationBridge", recorder(second))
    service._run_default_resumable("C", {}, None, task_id="t1", attempt_id="a1")
    assert first == second == ["init", "execute"]


# ---------------------------------------------------------------------------
# self dispatch: instance, class and subclass patches


def test_class_patch_of_reached_members_and_undo(state_dir, monkeypatch) -> None:
    hits: list[str] = []
    real_card = inspect.getattr_static(
        SelfHostedTaskService, "_revalidate_tracked_dispatch_task_card"
    )
    mp = pytest.MonkeyPatch()
    mp.setattr(
        SelfHostedTaskService,
        "_revalidate_tracked_dispatch_task_card",
        lambda self, *a: hits.append("card"),
    )
    mp.setattr(
        SelfHostedTaskService,
        "_assert_persisted_workforce_dispatch",
        staticmethod(lambda *a, **k: hits.append("dispatch")),
    )
    svc = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    svc._revalidate_provider_boundary(cast(Any, "C"), {}, "t1", {"provider": "codex"})
    mp.undo()
    assert hits == ["card", "dispatch"]
    assert (
        inspect.getattr_static(SelfHostedTaskService, "_revalidate_tracked_dispatch_task_card")
        is real_card
    )


def test_class_patch_of_mutate_state_reaches_the_journal_writes(ctx, stubs, monkeypatch) -> None:
    hits: list[str] = []
    real = inspect.getattr_static(SelfHostedTaskService, "_mutate_state")
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_mutate_state",
        lambda self, task_id, mutator: (hits.append(task_id), real(self, task_id, mutator))[1],
    )
    ctx.run()
    assert hits == ["ctx-1", "ctx-1"]


def test_subclass_overrides_are_dispatched_through_self(state_dir, monkeypatch) -> None:
    class Sub(SelfHostedTaskService):
        def _read_state(self, task_id: str) -> Optional[dict[str, Any]]:
            return {"attempt_id": "sub-attempt", "status": "SUBMITTED"}

        def _revalidate_tracked_dispatch_task_card(
            self, contract: Any, request: Any, state: Any, binding: Any
        ) -> None:
            raise LookupError("sub-card")

        def _run_default_resumable(
            self, contract: Any, request: Any, update: Any, *, task_id: str, attempt_id: str
        ) -> Any:
            return ("sub-run", task_id, attempt_id)

    sub = Sub(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    with pytest.raises(LookupError, match="^sub-card$"):
        sub._revalidate_provider_boundary(cast(Any, "C"), {}, "t1", None)
    assert sub._run_default(SimpleNamespace(task_id="t1"), {}, None) == (
        "sub-run",
        "t1",
        "sub-attempt",
    )
    assert cast(Any, sub).runner(SimpleNamespace(task_id="t2"), {}, None) == (
        "sub-run",
        "t2",
        "sub-attempt",
    )


def test_subclass_override_of_a_moved_member_wins(state_dir) -> None:
    class Sub(SelfHostedTaskService):
        @staticmethod
        def _assert_persisted_workforce_dispatch(*args: Any, **kwargs: Any) -> None:
            raise LookupError("sub-dispatch")

    sub = Sub(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    with pytest.raises(LookupError, match="^sub-dispatch$"):
        runtime_coordination_bridge._Contract(sub).assert_persisted_dispatch({}, {}, None)


def test_static_members_are_the_same_through_class_and_instance(service) -> None:
    for name in ("_assert_persisted_workforce_dispatch", "_replace_failed_target"):
        assert getattr(service, name) is getattr(SelfHostedTaskService, name)
