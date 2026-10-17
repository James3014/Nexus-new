"""Characterization of the work-claim cluster of ``SelfHostedTaskService`` (split S1).

Big-file split step S1 moves the work-claim methods out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin.  These tests pin the
behaviour before the move and must pass unchanged after it:

* every claim method's result, including each error / denial path and the order of the
  checks that produce them;
* the call order of the state lock, state reads/writes and claim validators (recording
  probes on the class, so they also work once the methods live in a mixin);
* the #2374 / #2498 durable attempt binding of the stale fence (binding at acquisition,
  legacy adoption, cache vs persisted binding, recovery re-binding, fresh service
  instances);
* that facade-module names the moved code reads (``_utc_now``, ``_jsonable``,
  ``_bounded_failure_text``, ``uuid4``, ``TERMINAL_STATUSES`` and the module attribute
  ``SelfHostedTaskService`` used inside ``_claim_request``) are still resolved through
  the facade at call time, so patches on the facade keep taking effect.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

FIXED_NOW = "2026-10-17T00:00:00+00:00"

# Members of the claim cluster; each one is exercised below.
CLAIM_MEMBERS = (
    "PUBLIC_WORK_CLAIM_SCHEMA",
    "PUBLIC_WORK_CLAIM_CEILING",
    "_claim_identity",
    "_claim_hash",
    "_claim_request",
    "_validate_claim_record",
    "_validate_claim_enclosure",
    "_attempt_binding",
    "_bindings_of",
    "_validate_claim_locked",
    "acquire_work_claim",
    "claim_work",
    "_bridge_validate_claim",
    "validate_work_claim",
    "release_work_claim",
    "recover_work_claim",
    "renew_work_claim",
    "_project_public_claim",
    "read_work_claim",
    "read_claim",
    "list_active_work_claims",
    "list_active_claims",
)


# ---------------------------------------------------------------------------
# helpers


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def service(state_dir: Path) -> SelfHostedTaskService:
    return _service(state_dir)


def _service(state_dir: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)


def _request(task_id: str = "task-1", attempt_id: str = "attempt-1", **extra: Any) -> dict:
    values: dict[str, Any] = {
        "repository": "James3014/Nexus-new",
        "issue": "129",
        "task_id": task_id,
        "attempt_id": attempt_id,
        "action_id": "action-1",
        "worker_id": "worker-a",
        "provider": "codex",
        "model": "gpt-x",
        "role": "PRIMARY_PRODUCER",
        "claim_ceiling": "CLAIM_PROTOCOL_CANDIDATE_PR_ONLY",
        "base_revision": "b" * 40,
        "source_hash": "s" * 64,
        "task_card_path": "tasks/t.yaml",
        "allowed_files": ["nexus/a.py"],
        "workforce_admission": {"admission_id": "adm-1"},
        "provider_preflight": {"preflight_id": "pre-1"},
    }
    values.update(extra)
    return values


def _seed(
    service: SelfHostedTaskService,
    task_id: str = "task-1",
    *,
    attempt_id: str = "attempt-1",
    status: str = "SUBMITTED",
    **extra: Any,
) -> None:
    state: dict[str, Any] = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "status": status,
        "contract": {
            "task_id": task_id,
            "target_base_revision": "b" * 40,
            "controller_revision": "s" * 64,
        },
    }
    state.update(extra)
    service._write_state(task_id, state)


def _disk(service: SelfHostedTaskService, task_id: str = "task-1") -> dict:
    return json.loads(service._state_path(task_id).read_text(encoding="utf-8"))


def _put(service: SelfHostedTaskService, task_id: str, state: dict) -> None:
    service._write_state(task_id, state)


def _claimed(service: SelfHostedTaskService, task_id: str = "task-1", **extra: Any) -> tuple:
    """Seed a task, acquire its claim and return ``(claim, fenced request)``."""

    attempt_id = extra.pop("attempt_id", "attempt-1")
    _seed(service, task_id, attempt_id=attempt_id)
    result = service.acquire_work_claim(_request(task_id, attempt_id, **extra))
    assert result["status"] == "CLAIMED"
    claim = result["claim"]
    fenced = {
        **_request(task_id, attempt_id, **extra),
        "claim_id": claim["claim_id"],
        "generation": claim["generation"],
        "fencing_token": claim["fencing_token"],
    }
    return claim, fenced


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _valid_record(**overrides: Any) -> dict:
    identity = {"task_id": "task-1", "attempt_id": "attempt-1", "repository": "r"}
    record: dict[str, Any] = {
        "identity": identity,
        "identity_hash": SelfHostedTaskService._claim_hash(identity),
        "claim_id": "cid",
        "generation": 1,
        "fencing_token": "cid:1",
        "status": "CLAIMED",
    }
    record.update(overrides)
    return record


class Recorder:
    """Class-level recording probes for the state lock, I/O and claim validators."""

    FUNCTIONS = ("_state_path", "_write_state_locked", "_read_state", "_project_public_claim")
    STATIC = ("_claim_identity", "_attempt_binding", "_bindings_of")
    CLASS = (
        "_claim_hash",
        "_validate_claim_record",
        "_validate_claim_enclosure",
        "_validate_claim_locked",
    )

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
        for name in self.STATIC:
            func = inspect.getattr_static(cls, name).__func__
            monkeypatch.setattr(cls, name, staticmethod(self._wrap_plain(name, func)))
        for name in self.CLASS:
            func = inspect.getattr_static(cls, name).__func__
            monkeypatch.setattr(cls, name, classmethod(self._wrap_class(name, func)))

    def _wrap_function(self, name: str, func: Any) -> Any:
        events = self.events

        def wrapped(self_: Any, *args: Any, **kwargs: Any) -> Any:
            events.append(name)
            return func(self_, *args, **kwargs)

        return wrapped

    def _wrap_plain(self, name: str, func: Any) -> Any:
        events = self.events

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            events.append(name)
            return func(*args, **kwargs)

        return wrapped

    def _wrap_class(self, name: str, func: Any) -> Any:
        events = self.events

        def wrapped(cls: Any, *args: Any, **kwargs: Any) -> Any:
            events.append(name)
            return func(cls, *args, **kwargs)

        return wrapped

    def without(self, *names: str) -> list[str]:
        return [event for event in self.events if event not in names]


def _raises(code: str, call: Any) -> None:
    with pytest.raises(RuntimeError) as caught:
        call()
    assert str(caught.value) == code


# ---------------------------------------------------------------------------
# surface


def test_claim_members_kinds_and_aliases() -> None:
    cls = SelfHostedTaskService
    kinds = {name: type(inspect.getattr_static(cls, name)).__name__ for name in CLAIM_MEMBERS}
    assert kinds == {
        "PUBLIC_WORK_CLAIM_SCHEMA": "str",
        "PUBLIC_WORK_CLAIM_CEILING": "str",
        "_claim_identity": "staticmethod",
        "_claim_hash": "classmethod",
        "_claim_request": "staticmethod",
        "_validate_claim_record": "classmethod",
        "_validate_claim_enclosure": "classmethod",
        "_attempt_binding": "staticmethod",
        "_bindings_of": "staticmethod",
        "_validate_claim_locked": "classmethod",
        "acquire_work_claim": "function",
        "claim_work": "function",
        "_bridge_validate_claim": "function",
        "validate_work_claim": "function",
        "release_work_claim": "function",
        "recover_work_claim": "function",
        "renew_work_claim": "function",
        "_project_public_claim": "function",
        "read_work_claim": "function",
        "read_claim": "function",
        "list_active_work_claims": "function",
        "list_active_claims": "function",
    }
    assert cls.PUBLIC_WORK_CLAIM_SCHEMA == "nexus.orchestrator.work_claim_view.v1"
    assert cls.PUBLIC_WORK_CLAIM_CEILING == "PROJECTION_READ_ONLY_REPO_ENFORCED"
    static = inspect.getattr_static
    assert static(cls, "claim_work") is static(cls, "acquire_work_claim")
    assert static(cls, "renew_work_claim") is static(cls, "validate_work_claim")
    assert static(cls, "read_claim") is static(cls, "read_work_claim")
    assert static(cls, "list_active_claims") is static(cls, "list_active_work_claims")


# ---------------------------------------------------------------------------
# _claim_identity / _claim_hash / _claim_request


def test_claim_identity_canonical_fields_and_hashes() -> None:
    request = _request(allowed_files=["b.py", " a.py ", "b.py", "", "  "])
    identity = SelfHostedTaskService._claim_identity(request)
    assert list(identity) == [
        "repository",
        "issue",
        "task_id",
        "attempt_id",
        "action_id",
        "worker_id",
        "provider",
        "model",
        "role",
        "claim_ceiling",
        "base_revision",
        "source_hash",
        "task_card_path",
        "allowed_files",
        "admission_identity",
        "provider_preflight_identity",
    ]
    assert identity["allowed_files"] == ["a.py", "b.py"]
    assert identity["admission_identity"] == _sha({"admission_id": "adm-1"})
    assert identity["provider_preflight_identity"] == _sha({"preflight_id": "pre-1"})
    assert identity["repository"] == "James3014/Nexus-new"
    assert identity["issue"] == "129"


def test_claim_identity_aliases_and_stripping() -> None:
    identity = SelfHostedTaskService._claim_identity({
        "repo": " o/r ",
        "issue_number": 7,
        "task_id": " t ",
        "attempt_id": " a ",
        "action_id": " x ",
        "worker": " w ",
        "provider": " p ",
        "model": " m ",
        "worker_role": " role ",
        "claim_ceiling": " c ",
        "target_base_revision": " base ",
        "source_revision": " src ",
        "task_card_path": " card ",
        "mutation_domain": "single.py",
        "admission_binding": {"k": 1},
        "realm_preflight": ["p"],
    })
    assert identity == {
        "repository": "o/r",
        "issue": "7",
        "task_id": "t",
        "attempt_id": "a",
        "action_id": "x",
        "worker_id": "w",
        "provider": "p",
        "model": "m",
        "role": "role",
        "claim_ceiling": "c",
        "base_revision": "base",
        "source_hash": "src",
        "task_card_path": "card",
        "allowed_files": ["single.py"],
        "admission_identity": _sha({"k": 1}),
        "provider_preflight_identity": _sha(["p"]),
    }


def test_claim_identity_primary_keys_win_over_aliases() -> None:
    identity = SelfHostedTaskService._claim_identity({
        "repository": "primary",
        "repo": "alias",
        "workforce_admission": {"a": 1},
        "admission_binding": {"a": 2},
        "provider_preflight": {"p": 1},
        "realm_preflight": {"p": 2},
        "allowed_files": ["x.py"],
        "mutation_domain": ["y.py"],
    })
    assert identity["repository"] == "primary"
    assert identity["admission_identity"] == _sha({"a": 1})
    assert identity["provider_preflight_identity"] == _sha({"p": 1})
    assert identity["allowed_files"] == ["x.py"]


def test_claim_identity_passthrough_identities_and_empty_defaults() -> None:
    passthrough = SelfHostedTaskService._claim_identity({
        "admission_identity": " adm ",
        "provider_preflight_identity": " pre ",
    })
    assert passthrough["admission_identity"] == "adm"
    assert passthrough["provider_preflight_identity"] == "pre"
    # A present admission object wins over a passthrough identity.
    hashed = SelfHostedTaskService._claim_identity({
        "admission_identity": "adm",
        "workforce_admission": {"z": 1},
        "provider_preflight_identity": "pre",
        "realm_preflight": {"z": 2},
    })
    assert hashed["admission_identity"] == _sha({"z": 1})
    assert hashed["provider_preflight_identity"] == _sha({"z": 2})
    # Explicit None objects hash to the empty identity.
    empty = SelfHostedTaskService._claim_identity({"workforce_admission": None})
    assert empty["admission_identity"] == ""
    assert empty["provider_preflight_identity"] == ""
    assert all(value in ("", []) for value in empty.values())


def test_claim_hash_is_canonical_json_sha256() -> None:
    identity = {"b": [1, 2], "a": "x"}
    assert SelfHostedTaskService._claim_hash(identity) == _sha({"a": "x", "b": [1, 2]})


def test_claim_hash_and_identity_read_facade_jsonable(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []
    real = service_module._jsonable

    def recording(value: Any) -> Any:
        seen.append(value)
        return real(value)

    monkeypatch.setattr(service_module, "_jsonable", recording)
    SelfHostedTaskService._claim_hash({"k": 1})
    assert seen[0] == {"k": 1}
    seen.clear()
    SelfHostedTaskService._claim_identity({
        "workforce_admission": {"a": 1},
        "realm_preflight": {"b": 2},
    })
    top_level = [value for value in seen if isinstance(value, dict)]
    assert top_level == [{"a": 1}, {"b": 2}]


def test_claim_request_defaults_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "uuid4", lambda: "uuid-probe")
    built = SelfHostedTaskService._claim_request(_request())
    identity = SelfHostedTaskService._claim_identity(_request())
    assert built == {
        "identity": identity,
        "identity_hash": SelfHostedTaskService._claim_hash(identity),
        "claim_id": "uuid-probe",
        "generation": 1,
        "fencing_token": "",
    }
    explicit = SelfHostedTaskService._claim_request(
        _request(claim_id="cid", generation="4", fencing_token=7)
    )
    assert (explicit["claim_id"], explicit["generation"], explicit["fencing_token"]) == (
        "cid",
        4,
        "7",
    )
    with pytest.raises(ValueError):
        SelfHostedTaskService._claim_request(_request(generation="x"))


def test_claim_request_resolves_service_class_through_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    claim_request = SelfHostedTaskService._claim_request

    class Probe:
        @staticmethod
        def _claim_identity(request: Any) -> dict:
            calls.append("identity")
            return {"probe": True}

        @staticmethod
        def _claim_hash(identity: Any) -> str:
            calls.append("hash")
            return "probe-hash"

    monkeypatch.setattr(service_module, "SelfHostedTaskService", Probe)
    built = claim_request({"claim_id": "c"})
    assert calls == ["identity", "hash"]
    assert built["identity"] == {"probe": True}
    assert built["identity_hash"] == "probe-hash"


# ---------------------------------------------------------------------------
# _validate_claim_record / _validate_claim_enclosure / _attempt_binding / _bindings_of


def test_validate_claim_record_accepts_valid_record() -> None:
    assert SelfHostedTaskService._validate_claim_record(_valid_record()) is None


@pytest.mark.parametrize(
    ("record", "code"),
    [
        (None, "WORK_CLAIM_MALFORMED"),
        (["x"], "WORK_CLAIM_MALFORMED"),
        ({"identity": "x"}, "WORK_CLAIM_MALFORMED"),
        ({"identity": {}}, "WORK_CLAIM_MALFORMED"),
        (_valid_record(identity_hash=None), "WORK_CLAIM_TAMPERED"),
        (_valid_record(identity_hash="0" * 64), "WORK_CLAIM_TAMPERED"),
        (_valid_record(generation=True), "WORK_CLAIM_MALFORMED"),
        (_valid_record(generation=0), "WORK_CLAIM_MALFORMED"),
        (_valid_record(generation="1"), "WORK_CLAIM_MALFORMED"),
        (_valid_record(claim_id=""), "WORK_CLAIM_MALFORMED"),
        (_valid_record(claim_id=5), "WORK_CLAIM_MALFORMED"),
        (_valid_record(status="RELEASED"), "WORK_CLAIM_MALFORMED"),
        (_valid_record(fencing_token="cid:2"), "WORK_CLAIM_STALE_FENCE"),
        (_valid_record(fencing_token=None), "WORK_CLAIM_STALE_FENCE"),
        # check order: tampered hash is reported before malformed generation/status/fence
        (_valid_record(identity_hash="0" * 64, generation=0, status="X"), "WORK_CLAIM_TAMPERED"),
        # malformed generation before wrong status / fence
        (_valid_record(generation=0, status="X", fencing_token="bad"), "WORK_CLAIM_MALFORMED"),
        (_valid_record(status="X", fencing_token="bad"), "WORK_CLAIM_MALFORMED"),
    ],
)
def test_validate_claim_record_denials(record: Any, code: str) -> None:
    _raises(code, lambda: SelfHostedTaskService._validate_claim_record(record))


@pytest.mark.parametrize(
    ("state", "identity", "expected", "code"),
    [
        ({"task_id": "t", "attempt_id": "a"}, {"task_id": "t", "attempt_id": "a"}, "", None),
        ({"task_id": "t"}, {"task_id": "t", "attempt_id": "other"}, "", None),
        ({"task_id": " t ", "attempt_id": ""}, {"task_id": "t"}, "t", None),
        ({}, {"task_id": ""}, "", "WORK_CLAIM_TAMPERED"),
        ({"task_id": "t"}, {"task_id": "u"}, "", "WORK_CLAIM_TAMPERED"),
        ({"task_id": "t"}, {"task_id": "t"}, "u", "WORK_CLAIM_TAMPERED"),
        (
            {"task_id": "t", "attempt_id": "a"},
            {"task_id": "t", "attempt_id": "b"},
            "",
            "WORK_CLAIM_TAMPERED",
        ),
        ({"task_id": "t", "attempt_id": "a"}, {"task_id": "t"}, "t", "WORK_CLAIM_TAMPERED"),
    ],
)
def test_validate_claim_enclosure(
    state: dict, identity: dict, expected: str, code: str | None
) -> None:
    def call() -> None:
        return SelfHostedTaskService._validate_claim_enclosure(
            state, {"identity": identity}, expected_task_id=expected
        )

    if code is None:
        assert call() is None
    else:
        _raises(code, call)


def test_validate_claim_enclosure_treats_missing_identity_as_empty() -> None:
    _raises(
        "WORK_CLAIM_TAMPERED",
        lambda: SelfHostedTaskService._validate_claim_enclosure(
            {"task_id": "t"}, {"identity": None}
        ),
    )


def test_attempt_binding_overrides_identity_and_carries_fence() -> None:
    record = _valid_record(identity={"task_id": "x", "attempt_id": "y", "repository": "r"})
    assert SelfHostedTaskService._attempt_binding(record, "t", "a") == {
        "task_id": "t",
        "attempt_id": "a",
        "repository": "r",
        "claim_id": "cid",
        "generation": 1,
        "fencing_token": "cid:1",
    }
    assert SelfHostedTaskService._attempt_binding(
        {"identity": None, "claim_id": "c", "generation": 2, "fencing_token": "f"}, "t", "a"
    ) == {
        "task_id": "t",
        "attempt_id": "a",
        "claim_id": "c",
        "generation": 2,
        "fencing_token": "f",
    }
    with pytest.raises(KeyError):
        SelfHostedTaskService._attempt_binding({"identity": {}}, "t", "a")


def test_bindings_of() -> None:
    assert SelfHostedTaskService._bindings_of({}) == {}
    assert SelfHostedTaskService._bindings_of({"attempt_claim_bindings": None}) == {}
    raw = {"a": {"g": 1}}
    copied = SelfHostedTaskService._bindings_of({"attempt_claim_bindings": raw})
    assert copied == raw and copied is not raw
    for corrupt in (["x"], "x", 0):
        _raises(
            "WORK_CLAIM_BINDINGS_CORRUPT",
            lambda corrupt=corrupt: SelfHostedTaskService._bindings_of({
                "attempt_claim_bindings": corrupt
            }),
        )


# ---------------------------------------------------------------------------
# _validate_claim_locked


def _locked_fixture() -> tuple[dict, dict]:
    request = _request("t", "a")
    built = SelfHostedTaskService._claim_request({**request, "claim_id": "cid"})
    record = {**built, "generation": 3, "fencing_token": "cid:3", "status": "CLAIMED"}
    state = {"task_id": "t", "attempt_id": "a", "work_claim": record}
    fenced = {**request, "claim_id": "cid", "generation": 3, "fencing_token": "cid:3"}
    return state, fenced


def test_validate_claim_locked_returns_the_stored_record_and_call_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, fenced = _locked_fixture()
    recorder = Recorder(monkeypatch)
    assert SelfHostedTaskService._validate_claim_locked(state, fenced) is state["work_claim"]
    assert recorder.events == [
        "_validate_claim_locked",
        "_validate_claim_record",
        "_claim_hash",
        "_validate_claim_enclosure",
        "_claim_identity",
        "_claim_hash",
    ]


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda s, r: s.pop("work_claim"), "WORK_CLAIM_MALFORMED"),
        (lambda s, r: r.update(task_id="other"), "WORK_CLAIM_TAMPERED"),
        (lambda s, r: s.update(attempt_id="b"), "WORK_CLAIM_TAMPERED"),
        (lambda s, r: r.update(model="other"), "WORK_CLAIM_FENCE_MISMATCH"),
        (lambda s, r: r.update(attempt_id="b"), "WORK_CLAIM_FENCE_MISMATCH"),
        (lambda s, r: r.pop("claim_id"), "WORK_CLAIM_STALE_FENCE"),
        (lambda s, r: r.update(claim_id="other"), "WORK_CLAIM_STALE_FENCE"),
        (lambda s, r: r.pop("generation"), "WORK_CLAIM_STALE_FENCE"),
        (lambda s, r: r.update(generation=True), "WORK_CLAIM_STALE_FENCE"),
        (lambda s, r: r.update(generation="3"), "WORK_CLAIM_STALE_FENCE"),
        (lambda s, r: r.update(generation=2), "WORK_CLAIM_STALE_FENCE"),
        (lambda s, r: r.pop("fencing_token"), "WORK_CLAIM_STALE_FENCE"),
        (lambda s, r: r.update(fencing_token="cid:2"), "WORK_CLAIM_STALE_FENCE"),
        (lambda s, r: s["work_claim"].update(fencing_token="cid:2"), "WORK_CLAIM_STALE_FENCE"),
    ],
)
def test_validate_claim_locked_denials(mutate: Any, code: str) -> None:
    state, fenced = _locked_fixture()
    mutate(state, fenced)
    _raises(code, lambda: SelfHostedTaskService._validate_claim_locked(state, fenced))


def test_validate_claim_locked_expected_task_id_comes_from_request() -> None:
    state, fenced = _locked_fixture()
    fenced["task_id"] = ""
    # Empty request task id: the enclosure check is skipped, but the identity hash differs.
    _raises(
        "WORK_CLAIM_FENCE_MISMATCH",
        lambda: SelfHostedTaskService._validate_claim_locked(state, fenced),
    )


# ---------------------------------------------------------------------------
# acquire_work_claim


def test_acquire_requires_task_id_before_taking_the_lock(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder(monkeypatch)
    assert service.acquire_work_claim(_request(task_id=" ")) == {
        "status": "BLOCKED",
        "reason": "TASK_ID_REQUIRED",
    }
    assert recorder.events == ["_claim_identity", "_claim_hash"]


def test_acquire_unknown_task(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder(monkeypatch)
    assert service.acquire_work_claim(_request()) == {
        "status": "BLOCKED",
        "reason": "TASK_NOT_FOUND",
    }
    assert recorder.events == ["_claim_identity", "_claim_hash", "lock+", "_state_path", "lock-"]


def test_acquire_success_record_binding_and_call_order(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service)
    monkeypatch.setattr(service_module, "_utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(service_module, "uuid4", lambda: "uuid-probe")
    recorder = Recorder(monkeypatch)
    result = service.acquire_work_claim(_request(generation=9, fencing_token="ignored"))
    identity = SelfHostedTaskService._claim_identity(_request())
    expected_claim = {
        "identity": identity,
        "identity_hash": SelfHostedTaskService._claim_hash(identity),
        "claim_id": "uuid-probe",
        "generation": 1,
        "fencing_token": "uuid-probe:1",
        "status": "CLAIMED",
        "claimed_at": FIXED_NOW,
    }
    assert result == {"status": "CLAIMED", "claim": expected_claim}
    assert recorder.without("_claim_identity", "_claim_hash") == [
        "lock+",
        "_state_path",
        "_bindings_of",
        "_attempt_binding",
        "_write_state_locked",
        "lock-",
    ]
    disk = _disk(service)
    assert disk["work_claim"] == expected_claim
    assert disk["attempt_claim_bindings"] == {
        "attempt-1": {
            **identity,
            "claim_id": "uuid-probe",
            "generation": 1,
            "fencing_token": "uuid-probe:1",
        }
    }


def test_acquire_without_attempt_id_writes_no_binding(service: SelfHostedTaskService) -> None:
    _seed(service, attempt_id="")
    result = service.acquire_work_claim(_request(attempt_id=""))
    assert result["status"] == "CLAIMED"
    assert "attempt_claim_bindings" not in _disk(service)


def test_acquire_keeps_existing_bindings(service: SelfHostedTaskService) -> None:
    _seed(service, attempt_claim_bindings={"old": {"generation": 1}})
    service.acquire_work_claim(_request())
    assert sorted(_disk(service)["attempt_claim_bindings"]) == ["attempt-1", "old"]


def test_acquire_corrupt_bindings_fail_closed_without_write(service: SelfHostedTaskService) -> None:
    _seed(service, attempt_claim_bindings=["corrupt"])
    _raises("WORK_CLAIM_BINDINGS_CORRUPT", lambda: service.acquire_work_claim(_request()))
    assert "work_claim" not in _disk(service)


def test_acquire_same_identity_is_idempotent(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    claim, _ = _claimed(service)
    recorder = Recorder(monkeypatch)
    assert service.acquire_work_claim(_request()) == {"status": "ALREADY_CLAIMED", "claim": claim}
    assert recorder.without("_claim_identity", "_claim_hash") == [
        "lock+",
        "_state_path",
        "_validate_claim_record",
        "lock-",
    ]


def test_acquire_other_identity_is_blocked(service: SelfHostedTaskService) -> None:
    claim, _ = _claimed(service)
    before = _disk(service)
    assert service.acquire_work_claim(_request(worker_id="worker-b")) == {
        "status": "BLOCKED",
        "reason": "ALREADY_CLAIMED",
        "claim": claim,
    }
    assert _disk(service) == before


def test_acquire_existing_tampered_claim_raises(service: SelfHostedTaskService) -> None:
    _claimed(service)
    state = _disk(service)
    state["work_claim"]["identity_hash"] = "0" * 64
    _put(service, "task-1", state)
    _raises("WORK_CLAIM_TAMPERED", lambda: service.acquire_work_claim(_request()))


def test_issue_uniqueness_not_enforced_by_default(service: SelfHostedTaskService) -> None:
    _claimed(service, "task-1")
    _seed(service, "task-2", attempt_id="attempt-2")
    assert service.acquire_work_claim(_request("task-2", "attempt-2"))["status"] == "CLAIMED"


@pytest.mark.parametrize("via", ["kwarg", "request"])
def test_issue_uniqueness_blocks_active_other_task(
    service: SelfHostedTaskService, via: str
) -> None:
    other_claim, _ = _claimed(service, "task-1")
    _seed(service, "task-2", attempt_id="attempt-2")
    if via == "kwarg":
        result = service.acquire_work_claim(
            _request("task-2", "attempt-2"), enforce_issue_uniqueness=True
        )
    else:
        result = service.acquire_work_claim(
            _request("task-2", "attempt-2", enforce_issue_uniqueness=True)
        )
    assert result == {"status": "BLOCKED", "reason": "ALREADY_CLAIMED", "claim": other_claim}
    assert "work_claim" not in _disk(service, "task-2")


@pytest.mark.parametrize("status", ["CANCELLED", *sorted(service_module.TERMINAL_STATUSES)[:3]])
def test_issue_uniqueness_ignores_terminal_and_cancelled_tasks(
    service: SelfHostedTaskService, status: str
) -> None:
    _claimed(service, "task-1")
    state = _disk(service, "task-1")
    state["status"] = status
    _put(service, "task-1", state)
    _seed(service, "task-2", attempt_id="attempt-2")
    result = service.acquire_work_claim(
        _request("task-2", "attempt-2"), enforce_issue_uniqueness=True
    )
    assert result["status"] == "CLAIMED"


def test_issue_uniqueness_reads_facade_terminal_statuses(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _claimed(service, "task-1")
    _seed(service, "task-2", attempt_id="attempt-2")
    monkeypatch.setattr(service_module, "TERMINAL_STATUSES", frozenset({"SUBMITTED"}))
    result = service.acquire_work_claim(
        _request("task-2", "attempt-2"), enforce_issue_uniqueness=True
    )
    assert result["status"] == "CLAIMED"


def test_issue_uniqueness_only_matches_same_repository_and_issue(
    service: SelfHostedTaskService,
) -> None:
    _claimed(service, "task-1")
    _seed(service, "task-2", attempt_id="attempt-2")
    _seed(service, "task-3", attempt_id="attempt-3")
    assert (
        service.acquire_work_claim(
            _request("task-2", "attempt-2", issue="130"), enforce_issue_uniqueness=True
        )["status"]
        == "CLAIMED"
    )
    assert (
        service.acquire_work_claim(
            _request("task-3", "attempt-3", repository="o/other"), enforce_issue_uniqueness=True
        )["status"]
        == "CLAIMED"
    )


def test_issue_uniqueness_skipped_without_repository_or_issue(
    service: SelfHostedTaskService,
) -> None:
    _claimed(service, "task-1", issue="", repository="")
    (service.state_dir / "broken.json").write_text("{", encoding="utf-8")
    _seed(service, "task-2", attempt_id="attempt-2")
    result = service.acquire_work_claim(
        _request("task-2", "attempt-2", issue=""), enforce_issue_uniqueness=True
    )
    assert result["status"] == "CLAIMED"


def test_issue_uniqueness_skips_dotfiles_unclaimed_and_own_state(
    service: SelfHostedTaskService,
) -> None:
    (service.state_dir).mkdir(parents=True, exist_ok=True)
    (service.state_dir / ".hidden.json").write_text("{", encoding="utf-8")
    _seed(service, "task-0", attempt_id="attempt-0")
    _seed(service, "task-2", attempt_id="attempt-2")
    result = service.acquire_work_claim(
        _request("task-2", "attempt-2"), enforce_issue_uniqueness=True
    )
    assert result["status"] == "CLAIMED"


@pytest.mark.parametrize(
    "other",
    [
        "{not json",
        "[1, 2]",
        json.dumps({"task_id": "task-1", "work_claim": ["x"]}),
        "tampered",
        "enclosure",
    ],
)
def test_issue_uniqueness_unknown_inventory_fails_closed(
    service: SelfHostedTaskService, other: str
) -> None:
    if other in ("tampered", "enclosure"):
        _claimed(service, "task-1")
        state = _disk(service, "task-1")
        if other == "tampered":
            state["work_claim"]["identity_hash"] = "0" * 64
        else:
            state["task_id"] = "task-x"
        (service.state_dir / "task-1.json").write_text(json.dumps(state), encoding="utf-8")
    else:
        service.state_dir.mkdir(parents=True, exist_ok=True)
        (service.state_dir / "task-1.json").write_text(other, encoding="utf-8")
    _seed(service, "task-2", attempt_id="attempt-2")
    _raises(
        "WORK_CLAIM_INVENTORY_UNKNOWN",
        lambda: service.acquire_work_claim(
            _request("task-2", "attempt-2"), enforce_issue_uniqueness=True
        ),
    )
    assert "work_claim" not in _disk(service, "task-2")


def test_issue_uniqueness_inventory_call_order(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _claimed(service, "task-1", issue="130")
    _seed(service, "task-2", attempt_id="attempt-2")
    recorder = Recorder(monkeypatch)
    service.acquire_work_claim(_request("task-2", "attempt-2"), enforce_issue_uniqueness=True)
    assert recorder.without("_claim_identity", "_claim_hash") == [
        "lock+",
        "_state_path",
        "_validate_claim_record",
        "_validate_claim_enclosure",
        "_bindings_of",
        "_attempt_binding",
        "_write_state_locked",
        "lock-",
    ]


# ---------------------------------------------------------------------------
# _bridge_validate_claim


def test_bridge_missing_state_returns_none(service: SelfHostedTaskService) -> None:
    assert service._bridge_validate_claim("missing", "a") is None


def test_bridge_non_issue_task_needs_no_claim_and_takes_no_extra_lock(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service)
    recorder = Recorder(monkeypatch)
    assert service._bridge_validate_claim("task-1", "attempt-1") is None
    assert recorder.events == ["_read_state", "_state_path", "lock+", "lock-"]


@pytest.mark.parametrize(
    "marker",
    [
        {"request": {"claim_required": True}},
        {"request": {"issue": "129"}},
        {"request": {"issue_number": 129}},
        {"request": {"project_entry_authority_binding": {"x": 1}}},
        {"contract": {"task_id": "task-1", "issue_number": 129}},
    ],
)
def test_bridge_issue_task_without_claim_is_refused(
    service: SelfHostedTaskService, marker: dict
) -> None:
    _seed(service, **marker)
    _raises(
        "WORK_CLAIM_REQUIRED:PROVIDER_INVOKE",
        lambda: service._bridge_validate_claim("task-1", "attempt-1", operation="PROVIDER_INVOKE"),
    )
    _raises(
        "WORK_CLAIM_REQUIRED:MUTATION",
        lambda: service._bridge_validate_claim("task-1", "attempt-1"),
    )


def test_bridge_ignores_non_mapping_request_and_contract(service: SelfHostedTaskService) -> None:
    _seed(service, request="issue", contract=["issue_number"])
    assert service._bridge_validate_claim("task-1", "attempt-1") is None


def test_bridge_success_call_order_and_returns_disk_record(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    claim, _ = _claimed(service)
    recorder = Recorder(monkeypatch)
    assert service._bridge_validate_claim("task-1", "attempt-1", operation="EXECUTE") == claim
    assert recorder.without("_claim_identity", "_claim_hash") == [
        "_read_state",
        "_state_path",
        "lock+",
        "lock-",
        "lock+",
        "_state_path",
        "_validate_claim_record",
        "_validate_claim_enclosure",
        "_bindings_of",
        "_validate_claim_locked",
        "_validate_claim_record",
        "_validate_claim_enclosure",
        "lock-",
    ]
    assert (
        service._bound_attempt_claims[("task-1", "attempt-1")]
        == _disk(service)["attempt_claim_bindings"]["attempt-1"]
    )


def test_bridge_state_vanishes_before_lock(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        service, "_read_state", lambda task_id: {"task_id": task_id, "work_claim": {"x": 1}}
    )
    _raises("WORK_CLAIM_NOT_FOUND", lambda: service._bridge_validate_claim("task-1", "a"))


def test_bridge_claim_removed_before_lock(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(service)
    monkeypatch.setattr(
        service, "_read_state", lambda task_id: {"task_id": task_id, "work_claim": {"x": 1}}
    )
    _raises(
        "WORK_CLAIM_REQUIRED:TARGET_LEASE",
        lambda: service._bridge_validate_claim("task-1", "a", operation="TARGET_LEASE"),
    )


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda s: s["work_claim"].update(status="X"), "WORK_CLAIM_MALFORMED"),
        (lambda s: s.update(attempt_id="attempt-9"), "WORK_CLAIM_TAMPERED"),
        (
            lambda s: s["contract"].update(target_base_revision="c" * 40),
            "WORK_CLAIM_BASE_REVISION_DRIFT",
        ),
        (
            lambda s: s["contract"].update(controller_revision="t" * 64),
            "WORK_CLAIM_SOURCE_REVISION_DRIFT",
        ),
        (
            lambda s: s["attempt_claim_bindings"].update({"attempt-1": "x"}),
            "WORK_CLAIM_STALE_FENCE",
        ),
        (lambda s: s.update(attempt_claim_bindings=["x"]), "WORK_CLAIM_BINDINGS_CORRUPT"),
        (
            lambda s: s["attempt_claim_bindings"]["attempt-1"].update(generation=7),
            "WORK_CLAIM_STALE_FENCE",
        ),
    ],
)
def test_bridge_denials(service: SelfHostedTaskService, mutate: Any, code: str) -> None:
    _claimed(service)
    state = _disk(service)
    mutate(state)
    _put(service, "task-1", state)
    before = _disk(service)
    _raises(code, lambda: service._bridge_validate_claim("task-1", "attempt-1"))
    assert _disk(service) == before
    assert service._bound_attempt_claims == {}


def test_bridge_drift_checks_skip_empty_revisions(service: SelfHostedTaskService) -> None:
    _claimed(service, base_revision="", source_hash="")
    state = _disk(service)
    state["contract"]["target_base_revision"] = "c" * 40
    state["contract"]["controller_revision"] = "t" * 64
    _put(service, "task-1", state)
    assert service._bridge_validate_claim("task-1", "attempt-1") is not None


def test_bridge_base_drift_reported_before_source_drift(service: SelfHostedTaskService) -> None:
    _claimed(service)
    state = _disk(service)
    state["contract"].update(target_base_revision="c" * 40, controller_revision="t" * 64)
    _put(service, "task-1", state)
    _raises(
        "WORK_CLAIM_BASE_REVISION_DRIFT",
        lambda: service._bridge_validate_claim("task-1", "attempt-1"),
    )


def test_bridge_legacy_attempt_adopts_current_generation_and_persists(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    claim, _ = _claimed(service)
    state = _disk(service)
    state.pop("attempt_claim_bindings")
    _put(service, "task-1", state)
    recorder = Recorder(monkeypatch)
    service._bridge_validate_claim("task-1", "attempt-1")
    assert recorder.without(
        "_claim_identity", "_claim_hash", "_validate_claim_record", "_validate_claim_enclosure"
    ) == [
        "_read_state",
        "_state_path",
        "lock+",
        "lock-",
        "lock+",
        "_state_path",
        "_bindings_of",
        "_attempt_binding",
        "_validate_claim_locked",
        "_write_state_locked",
        "lock-",
    ]
    expected = SelfHostedTaskService._attempt_binding(claim, "task-1", "attempt-1")
    assert _disk(service)["attempt_claim_bindings"] == {"attempt-1": expected}
    assert service._bound_attempt_claims[("task-1", "attempt-1")] == expected


def test_bridge_defaults_to_state_attempt(service: SelfHostedTaskService) -> None:
    _claimed(service)
    service._bridge_validate_claim("task-1")
    assert list(service._bound_attempt_claims) == [("task-1", "attempt-1")]


def test_bridge_without_any_attempt_binds_nothing(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _claimed(service, attempt_id="")
    recorder = Recorder(monkeypatch)
    assert service._bridge_validate_claim("task-1") is not None
    assert "_write_state_locked" not in recorder.events
    assert "_validate_claim_locked" not in recorder.events
    assert service._bound_attempt_claims == {}


def test_bridge_cache_only_binding_is_persisted(service: SelfHostedTaskService) -> None:
    claim, _ = _claimed(service)
    state = _disk(service)
    state.pop("attempt_claim_bindings")
    _put(service, "task-1", state)
    cached = SelfHostedTaskService._attempt_binding(claim, "task-1", "attempt-1")
    service._bound_attempt_claims[("task-1", "attempt-1")] = cached
    service._bridge_validate_claim("task-1", "attempt-1")
    assert _disk(service)["attempt_claim_bindings"]["attempt-1"] == cached
    assert service._bound_attempt_claims[("task-1", "attempt-1")] == cached
    assert service._bound_attempt_claims[("task-1", "attempt-1")] is not cached


def test_bridge_stale_cache_fails_even_when_persisted_binding_matches(
    service: SelfHostedTaskService,
) -> None:
    claim, _ = _claimed(service)
    stale = {
        **SelfHostedTaskService._attempt_binding(claim, "task-1", "attempt-1"),
        "generation": 5,
    }
    service._bound_attempt_claims[("task-1", "attempt-1")] = stale
    _raises("WORK_CLAIM_STALE_FENCE", lambda: service._bridge_validate_claim("task-1", "attempt-1"))


def test_bridge_persisted_binding_wins_over_cache(service: SelfHostedTaskService) -> None:
    claim, fenced = _claimed(service)
    service.recover_work_claim(fenced)  # generation 2; attempt-1 stays bound to generation 1
    _raises("WORK_CLAIM_STALE_FENCE", lambda: service._bridge_validate_claim("task-1", "attempt-1"))
    fresh = _service(service.state_dir)
    _raises("WORK_CLAIM_STALE_FENCE", lambda: fresh._bridge_validate_claim("task-1", "attempt-1"))


def test_bridge_unknown_attempt_is_fenced_by_identity(service: SelfHostedTaskService) -> None:
    _claimed(service)
    _raises(
        "WORK_CLAIM_FENCE_MISMATCH",
        lambda: service._bridge_validate_claim("task-1", "attempt-other"),
    )


# ---------------------------------------------------------------------------
# validate / release / recover


def test_validate_work_claim(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    claim, fenced = _claimed(service)
    recorder = Recorder(monkeypatch)
    assert service.validate_work_claim(fenced) == {"status": "CLAIMED", "claim": claim}
    assert service.renew_work_claim(fenced) == {"status": "CLAIMED", "claim": claim}
    assert recorder.without(
        "_claim_identity", "_claim_hash", "_validate_claim_record", "_validate_claim_enclosure"
    )[:4] == [
        "lock+",
        "_state_path",
        "_validate_claim_locked",
        "lock-",
    ]


def test_validate_work_claim_denials(service: SelfHostedTaskService) -> None:
    _raises("WORK_CLAIM_NOT_FOUND", lambda: service.validate_work_claim({"task_id": "missing"}))
    with pytest.raises(ValueError):  # the store refuses an empty task id
        service.validate_work_claim({})
    _, fenced = _claimed(service)
    _raises(
        "WORK_CLAIM_STALE_FENCE", lambda: service.validate_work_claim({**fenced, "generation": 2})
    )
    _raises(
        "WORK_CLAIM_FENCE_MISMATCH",
        lambda: service.validate_work_claim({**fenced, "worker_id": "x"}),
    )


def test_release_work_claim(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, fenced = _claimed(service)
    bindings = _disk(service)["attempt_claim_bindings"]
    recorder = Recorder(monkeypatch)
    assert service.release_work_claim(fenced) == {"status": "RELEASED", "task_id": "task-1"}
    assert recorder.without(
        "_claim_identity", "_claim_hash", "_validate_claim_record", "_validate_claim_enclosure"
    ) == [
        "lock+",
        "_state_path",
        "_validate_claim_locked",
        "_write_state_locked",
        "lock-",
    ]
    disk = _disk(service)
    assert "work_claim" not in disk
    assert disk["attempt_claim_bindings"] == bindings  # bindings survive the release
    # Released: a second release has no claim to validate.
    _raises("WORK_CLAIM_MALFORMED", lambda: service.release_work_claim(fenced))


def test_release_work_claim_denials(service: SelfHostedTaskService) -> None:
    with pytest.raises(KeyError):
        service.release_work_claim({})
    with pytest.raises(FileNotFoundError):
        service.release_work_claim({"task_id": "missing"})
    _, fenced = _claimed(service)
    before = _disk(service)
    _raises(
        "WORK_CLAIM_STALE_FENCE",
        lambda: service.release_work_claim({**fenced, "fencing_token": "x"}),
    )
    assert _disk(service) == before


def test_recover_work_claim_without_authorized_attempt(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    claim, fenced = _claimed(service)
    bindings = _disk(service)["attempt_claim_bindings"]
    monkeypatch.setattr(service_module, "_utc_now", lambda: FIXED_NOW)
    reasons: list[Any] = []
    real = service_module._bounded_failure_text
    monkeypatch.setattr(
        service_module,
        "_bounded_failure_text",
        lambda value, **kw: reasons.append(value) or real(value, **kw),
    )
    recorder = Recorder(monkeypatch)
    result = service.recover_work_claim(fenced, reason="  timed   out  ")
    assert reasons == ["  timed   out  "]
    expected = {
        **claim,
        "generation": 2,
        "fencing_token": f"{claim['claim_id']}:2",
        "recovery_reason": "timed out",
        "recovered_at": FIXED_NOW,
    }
    assert result == {"status": "CLAIMED", "claim": expected}
    assert recorder.without(
        "_claim_identity", "_claim_hash", "_validate_claim_record", "_validate_claim_enclosure"
    ) == [
        "lock+",
        "_state_path",
        "_validate_claim_locked",
        "_bindings_of",
        "_write_state_locked",
        "lock-",
    ]
    disk = _disk(service)
    assert disk["work_claim"] == expected
    assert disk["attempt_claim_bindings"] == bindings
    assert service._bound_attempt_claims == {}


def test_recover_default_reason(service: SelfHostedTaskService) -> None:
    _, fenced = _claimed(service)
    assert service.recover_work_claim(fenced)["claim"]["recovery_reason"] == "RECOVERY"


def test_recover_rebinds_the_authorized_same_attempt(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    claim, fenced = _claimed(service)
    recorder = Recorder(monkeypatch)
    result = service.recover_work_claim(fenced, authorized_attempt_id=" attempt-1 ")
    assert "_attempt_binding" in recorder.events
    assert result["claim"]["identity"] == claim["identity"]
    disk = _disk(service)
    binding = disk["attempt_claim_bindings"]["attempt-1"]
    assert binding["generation"] == 2
    assert binding["fencing_token"] == f"{claim['claim_id']}:2"
    assert service._bound_attempt_claims[("task-1", "attempt-1")] == binding
    assert disk["attempt_id"] == "attempt-1"
    service._bridge_validate_claim("task-1", "attempt-1")
    _service(service.state_dir)._bridge_validate_claim("task-1", "attempt-1")


def test_recover_hands_claim_to_new_attempt(service: SelfHostedTaskService) -> None:
    claim, fenced = _claimed(service)
    result = service.recover_work_claim(
        fenced, reason="TERMINAL_RETRY", authorized_attempt_id="attempt-2"
    )
    new_identity = {**claim["identity"], "attempt_id": "attempt-2"}
    disk = _disk(service)
    assert disk["work_claim"]["identity"] == new_identity
    assert disk["work_claim"]["identity_hash"] == SelfHostedTaskService._claim_hash(new_identity)
    assert disk["attempt_id"] == "attempt-2"
    assert result["claim"]["identity"] == new_identity
    assert sorted(disk["attempt_claim_bindings"]) == ["attempt-1", "attempt-2"]
    assert disk["attempt_claim_bindings"]["attempt-1"]["generation"] == 1
    assert disk["attempt_claim_bindings"]["attempt-2"]["generation"] == 2
    service._bridge_validate_claim("task-1", "attempt-2")
    with pytest.raises(RuntimeError, match="WORK_CLAIM_(STALE_FENCE|FENCE_MISMATCH)"):
        _service(service.state_dir)._bridge_validate_claim("task-1", "attempt-1")
    # The old fence no longer validates; the re-identified one does.
    _raises(
        "WORK_CLAIM_FENCE_MISMATCH",
        lambda: service.validate_work_claim({
            **fenced,
            "generation": 2,
            "fencing_token": f"{claim['claim_id']}:2",
        }),
    )
    assert (
        service.validate_work_claim({
            **fenced,
            "attempt_id": "attempt-2",
            "generation": 2,
            "fencing_token": f"{claim['claim_id']}:2",
        })["status"]
        == "CLAIMED"
    )


def test_recover_denials_leave_state_untouched(service: SelfHostedTaskService) -> None:
    with pytest.raises(KeyError):
        service.recover_work_claim({})
    _, fenced = _claimed(service)
    before = _disk(service)
    _raises(
        "WORK_CLAIM_STALE_FENCE", lambda: service.recover_work_claim({**fenced, "generation": 5})
    )
    assert _disk(service) == before
    state = _disk(service)
    state["attempt_claim_bindings"] = "corrupt"
    _put(service, "task-1", state)
    before = _disk(service)
    _raises(
        "WORK_CLAIM_BINDINGS_CORRUPT",
        lambda: service.recover_work_claim(fenced, authorized_attempt_id="attempt-1"),
    )
    assert _disk(service) == before
    assert service._bound_attempt_claims == {}


def test_recovery_cycle_increments_generation(service: SelfHostedTaskService) -> None:
    claim, fenced = _claimed(service)
    second = service.recover_work_claim(fenced)["claim"]
    third = service.recover_work_claim({
        **fenced,
        "generation": 2,
        "fencing_token": second["fencing_token"],
    })["claim"]
    assert (second["generation"], third["generation"]) == (2, 3)
    assert third["fencing_token"] == f"{claim['claim_id']}:3"


# ---------------------------------------------------------------------------
# read / list (public projection)


def _expected_projection(claim: dict, *, revision: int, now: str = FIXED_NOW) -> dict:
    identity = claim["identity"]
    identity_hash = claim["identity_hash"]
    generation = claim["generation"]
    view = hashlib.sha256(f"claim-view:{identity_hash}".encode()).hexdigest()
    fence = hashlib.sha256(f"claim-fence-view:{identity_hash}:{generation}".encode()).hexdigest()
    return {
        "schema": "nexus.orchestrator.work_claim_view.v1",
        "claim_ceiling": "PROJECTION_READ_ONLY_REPO_ENFORCED",
        "claim_enforcement_state": "REPO_ENFORCED",
        "claim_identity": f"urn:nexus:claim:{view}",
        "generation": generation,
        "fence_identity": f"urn:nexus:claim_fence:{fence}",
        "fence_hash": fence,
        "state": "CLAIMED",
        "holder": identity["worker_id"],
        "repository": identity["repository"],
        "issue": identity["issue"],
        "task_id": identity["task_id"],
        "attempt_id": identity["attempt_id"],
        "action_id": identity["action_id"],
        "worker_id": identity["worker_id"],
        "provider": identity["provider"],
        "model": identity["model"],
        "role": identity["role"],
        "allowed_files": identity["allowed_files"],
        "mutation_domain": identity["allowed_files"],
        "base_revision": identity["base_revision"],
        "source_hash": identity["source_hash"],
        "task_card_path": identity["task_card_path"],
        "admission_identity": identity["admission_identity"],
        "provider_preflight_identity": identity["provider_preflight_identity"],
        "identity_hash": identity_hash,
        "claimed_at": claim.get("claimed_at", ""),
        "recovered_at": claim.get("recovered_at", ""),
        "recovery_reason": claim.get("recovery_reason", ""),
        "observed_at": now,
        "canonical_revision": revision,
    }


def test_project_public_claim_exact_view(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    claim, _ = _claimed(service)
    monkeypatch.setattr(service_module, "_utc_now", lambda: FIXED_NOW)
    assert service._project_public_claim(claim, state={"revision": 4}) == _expected_projection(
        claim, revision=4
    )
    assert (
        service._project_public_claim(claim, state={"task_revision": 6})["canonical_revision"] == 6
    )
    assert service._project_public_claim(claim, state={})["canonical_revision"] == 1
    view = service._project_public_claim(claim, state={})
    assert "fencing_token" not in view and "claim_id" not in view


def test_project_public_claim_holder_fallback_and_class_constants(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = {"identity": {"role": "R", "provider": "P"}, "status": "CLAIMED"}
    view = service._project_public_claim(record, state={})
    assert view["holder"] == "R" and view["generation"] == 1 and view["allowed_files"] == []
    assert (
        service._project_public_claim({"identity": {"provider": "P"}, "status": "S"}, state={})[
            "holder"
        ]
        == "P"
    )
    assert service._project_public_claim({"status": "S"}, state={})["holder"] == ""
    with pytest.raises(KeyError):
        service._project_public_claim({"identity": {}}, state={})
    monkeypatch.setattr(SelfHostedTaskService, "PUBLIC_WORK_CLAIM_SCHEMA", "probe-schema")
    monkeypatch.setattr(SelfHostedTaskService, "PUBLIC_WORK_CLAIM_CEILING", "probe-ceiling")
    view = service._project_public_claim(record, state={})
    assert (view["schema"], view["claim_ceiling"]) == ("probe-schema", "probe-ceiling")


def test_read_work_claim_found_is_read_only(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    claim, _ = _claimed(service)
    raw = service._state_path("task-1").read_bytes()
    monkeypatch.setattr(service_module, "_utc_now", lambda: FIXED_NOW)
    recorder = Recorder(monkeypatch)
    result = service.read_work_claim({"task_id": " task-1 "})
    events = list(recorder.events)
    revision = int(_disk(service).get("revision") or _disk(service).get("task_revision") or 1)
    assert result == {
        "status": "FOUND",
        "found": True,
        "task_id": "task-1",
        "claim": {**_expected_projection(claim, revision=revision), "generation_status": "CURRENT"},
    }
    assert [event for event in events if event != "_claim_hash"] == [
        "_state_path",
        "_validate_claim_record",
        "_validate_claim_enclosure",
        "_project_public_claim",
    ]
    assert service.read_claim({"task_id": "task-1"})["status"] == "FOUND"
    assert service._state_path("task-1").read_bytes() == raw


def test_read_work_claim_not_found_paths(service: SelfHostedTaskService) -> None:
    assert service.read_work_claim({}) == {
        "status": "BLOCKED",
        "reason": "TASK_ID_REQUIRED",
        "found": False,
    }
    assert service.read_work_claim({"task_id": "missing"}) == {
        "status": "NOT_FOUND",
        "reason": "TASK_NOT_FOUND",
        "found": False,
        "task_id": "missing",
    }
    _seed(service)
    assert service.read_work_claim({"task_id": "task-1"}) == {
        "status": "NO_ACTIVE_CLAIM",
        "found": False,
        "task_id": "task-1",
    }
    service._state_path("task-1").write_text("{", encoding="utf-8")
    assert service.read_work_claim({"task_id": "task-1"}) == {
        "status": "BLOCKED",
        "reason": "WORK_CLAIM_STATE_UNREADABLE",
        "found": False,
        "task_id": "task-1",
    }


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda s: s.update(work_claim=["x"]), "WORK_CLAIM_MALFORMED"),
        (lambda s: s["work_claim"].update(identity_hash="0" * 64), "WORK_CLAIM_TAMPERED"),
        (lambda s: s["work_claim"].update(fencing_token="x"), "WORK_CLAIM_STALE_FENCE"),
        (lambda s: s.update(attempt_id="attempt-9"), "WORK_CLAIM_TAMPERED"),
    ],
)
def test_read_work_claim_invalid_claim_is_blocked(
    service: SelfHostedTaskService, mutate: Any, reason: str
) -> None:
    _claimed(service)
    state = _disk(service)
    mutate(state)
    _put(service, "task-1", state)
    assert service.read_work_claim({"task_id": "task-1"}) == {
        "status": "BLOCKED",
        "reason": reason,
        "found": False,
        "task_id": "task-1",
    }


def test_read_work_claim_generation_status(service: SelfHostedTaskService) -> None:
    claim, fenced = _claimed(service)
    service.recover_work_claim(fenced)

    def read(generation: Any) -> dict:
        return service.read_work_claim({"task_id": "task-1", "generation": generation})

    assert read(1)["claim"]["generation_status"] == "STALE_GENERATION"
    assert read(2)["claim"]["generation_status"] == "CURRENT"
    assert read(3)["claim"]["generation_status"] == "FUTURE_GENERATION"
    assert read(None)["claim"]["generation_status"] == "CURRENT"
    for invalid in (True, "2", 2.0):
        assert read(invalid) == {
            "status": "BLOCKED",
            "reason": "INVALID_GENERATION",
            "found": False,
        }


def test_list_active_work_claims_filters_and_order(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service_module, "_utc_now", lambda: FIXED_NOW)
    c2, _ = _claimed(service, "task-2", attempt_id="attempt-2", issue="130", worker_id="worker-b")
    c1, _ = _claimed(service, "task-1", attempt_id="attempt-1")
    _claimed(service, "task-3", attempt_id="attempt-3", repository="o/other")
    _seed(service, "task-4", attempt_id="attempt-4")
    (service.state_dir / ".hidden.json").write_text("{", encoding="utf-8")
    everything = service.list_active_work_claims()
    assert [view["task_id"] for view in everything] == ["task-1", "task-2", "task-3"]
    assert everything[0] == _expected_projection(c1, revision=everything[0]["canonical_revision"])

    def by(**spec: Any) -> list:
        return [v["task_id"] for v in service.list_active_work_claims(spec)]

    assert by(repository="James3014/Nexus-new") == ["task-1", "task-2"]
    assert by(repo="o/other") == ["task-3"]
    assert by(issue="130") == ["task-2"]
    assert by(issue_number="129") == ["task-1", "task-3"]
    assert by(worker_id="worker-b") == ["task-2"]
    assert by(worker="worker-a") == ["task-1", "task-3"]
    assert by(status="CLAIMED") == ["task-1", "task-2", "task-3"]
    assert by(status="RELEASED") == []
    assert by(repository=" ", issue="") == ["task-1", "task-2", "task-3"]
    assert service.list_active_claims({"issue": "130"})[0]["task_id"] == "task-2"
    assert c2["identity"]["issue"] == "130"


def test_list_active_work_claims_call_order_is_read_only(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _claimed(service)
    recorder = Recorder(monkeypatch)
    service.list_active_work_claims()
    assert recorder.without("_claim_hash") == [
        "_validate_claim_record",
        "_validate_claim_enclosure",
        "_project_public_claim",
    ]


def test_list_active_work_claims_missing_state_dir(
    service: SelfHostedTaskService, tmp_path: Path
) -> None:
    service.state_dir = tmp_path / "absent"
    assert not service.state_dir.exists()
    assert service.list_active_work_claims() == []


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("{", "WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_STATE_UNREADABLE"),
        (
            json.dumps({"task_id": "task-1", "work_claim": ["x"]}),
            "WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_MALFORMED",
        ),
        ("tampered", "WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_TAMPERED"),
        ("enclosure", "WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_TAMPERED"),
        ("fence", "WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_STALE_FENCE"),
    ],
)
def test_list_active_work_claims_fail_closed(
    service: SelfHostedTaskService, content: str, code: str
) -> None:
    _claimed(service, "task-0", attempt_id="attempt-0")
    if content in ("tampered", "enclosure", "fence"):
        _claimed(service, "task-1")
        state = _disk(service, "task-1")
        if content == "tampered":
            state["work_claim"]["identity_hash"] = "0" * 64
        elif content == "enclosure":
            state["attempt_id"] = "attempt-9"
        else:
            state["work_claim"]["fencing_token"] = "x"
        content = json.dumps(state)
    (service.state_dir / "task-1.json").write_text(content, encoding="utf-8")
    _raises(code, lambda: service.list_active_work_claims())


def test_list_enclosure_check_has_no_expected_task_id(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A state file whose name differs from its task id is still listed (no expected id).
    _claimed(service)
    state = _disk(service)
    (service.state_dir / "renamed.json").write_text(json.dumps(state), encoding="utf-8")
    service._state_path("task-1").unlink()
    seen: list[str] = []
    real = SelfHostedTaskService._validate_claim_enclosure.__func__

    def recording(cls: Any, state: Any, record: Any, *, expected_task_id: str = "") -> None:
        seen.append(expected_task_id)
        return real(cls, state, record, expected_task_id=expected_task_id)

    monkeypatch.setattr(SelfHostedTaskService, "_validate_claim_enclosure", classmethod(recording))
    assert [view["task_id"] for view in service.list_active_work_claims()] == ["task-1"]
    assert seen == [""]
