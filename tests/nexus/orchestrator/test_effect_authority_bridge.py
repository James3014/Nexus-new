"""#2344: record-backed EffectAuthorityPort, shadow by default, strict opt-in."""

from __future__ import annotations

import logging

import pytest
from nexus_runtime.execution_coordination import EffectAuthorization, EffectAuthorizationError

from nexus.orchestrator import effect_authority as ea
from nexus.orchestrator import runtime_coordination_bridge as bridge


def _auth(**over):
    data = {
        "authority_id": "bootstrap_agent",
        "authority_ref": "ref-1",
        "operation_id": "op-1",
        "attempt_id": "att-1",
        "repository": "James3014/Nexus-new",
        "effects": {"filesystem.write_paths": {"paths": ["a.py"]}},
    }
    data.update(over)
    return EffectAuthorization.build(**data)


def _record(**over):
    rec = {
        "authority_id": "bootstrap_agent",
        "repository": "James3014/Nexus-new",
        "effects": {"filesystem.write_paths": {"paths": ["a.py"]}},
    }
    rec.update(over)
    return rec


def _lookup(record):
    return lambda ref: record if ref == "ref-1" else None


def test_exact_record_match_is_accepted():
    assert ea.evaluate_authorization(_auth(), _lookup(_record())) == (True, "RECORD_MATCH")


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        (None, "NO_RECORD_FOR_AUTHORITY_REF"),
        (_record(authority_id="someone_else"), "AUTHORITY_ID_MISMATCH"),
        (_record(repository="James3014/other"), "REPOSITORY_MISMATCH"),
        (_record(effects={}), "EFFECT_BROADER_THAN_RECORD:filesystem.write_paths"),
        (
            _record(effects={"filesystem.write_paths": {"paths": ["b.py"]}}),
            "EFFECT_CONSTRAINTS_DIFFER_FROM_RECORD:filesystem.write_paths",
        ),
    ],
)
def test_self_signed_or_broader_authorization_is_refused(record, reason):
    accepted, got = ea.evaluate_authorization(_auth(), _lookup(record))
    assert accepted is False
    assert got == reason


def test_lookup_error_backs_nothing():
    def boom(_ref):
        raise OSError("unreadable")

    assert ea.evaluate_authorization(_auth(), boom) == (False, "RECORD_LOOKUP_FAILED:OSError")


def test_default_is_shadow_no_port_attached(monkeypatch):
    monkeypatch.delenv(ea.STRICT_ENV, raising=False)
    assert bridge._effect_authority_kwargs() == {}


@pytest.mark.parametrize("value", ["", "0", "true", "yes", " 2"])
def test_only_exact_one_enables_strict(monkeypatch, value):
    monkeypatch.setenv(ea.STRICT_ENV, value)
    assert bridge._effect_authority_kwargs() == {}


def test_strict_attaches_port_and_requires_authority(monkeypatch):
    monkeypatch.setenv(ea.STRICT_ENV, "1")
    kwargs = bridge._effect_authority_kwargs()
    assert kwargs["require_effect_authority"] is True
    assert kwargs["effect_authority"] is not None


def test_shadow_records_would_refuse_without_authorization(monkeypatch, caplog):
    monkeypatch.delenv(ea.STRICT_ENV, raising=False)
    with caplog.at_level(logging.INFO, logger=bridge.logger.name):
        decision = bridge._record_effect_authority_shadow("t1", "a1", {"task": "x"})
    assert decision["decision"] == ea.DECISION_WOULD_REFUSE
    assert decision["reason"] == "NO_EFFECT_AUTHORIZATION_ON_REQUEST"
    assert decision["mode"] == "SHADOW"
    assert ea.SHADOW_FIELD in caplog.text


def test_shadow_never_raises(monkeypatch):
    def broken(_request):
        raise RuntimeError("bug in shadow path")

    monkeypatch.setattr(ea, "shadow_decision", broken)
    assert bridge._record_effect_authority_shadow("t1", "a1", {"task": "x"}) is None


def test_shadow_skips_when_no_request():
    assert bridge._record_effect_authority_shadow("t1", "a1", None) is None


def test_record_backed_port_refuses_mismatch_and_accepts_exact():
    # M9: verify through the port itself, not only evaluate_authorization.
    port = ea.record_backed_port(_lookup(_record(repository="James3014/other")))
    with pytest.raises(EffectAuthorizationError):
        port.verify(_auth())
    ea.record_backed_port(_lookup(_record())).verify(_auth())


def test_execute_calls_effect_authority_shadow(monkeypatch):
    # M12: the shadow hook must sit on the real execute() path.
    calls = []

    class _Service:
        def _bridge_validate_claim(self, *_a, **_k):
            return None

    class _Stop(Exception):
        pass

    def fake_shadow(task_id, attempt_id, request):
        calls.append((task_id, attempt_id, request))

    def stop(self, *_a, **_k):
        raise _Stop

    monkeypatch.setattr(bridge, "_record_effect_authority_shadow", fake_shadow)
    monkeypatch.setattr(bridge.RuntimeCoordinationBridge, "_coordinator", stop)
    with pytest.raises(_Stop):
        bridge.RuntimeCoordinationBridge(_Service()).execute("t1", "a1", request={"k": 1})
    assert calls == [("t1", "a1", {"k": 1})]


# --- #2344 step 1: the shadow decision is persisted on the task state ---------


def _owned_service(tmp_path, runner):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    from tests.nexus.orchestrator.test_self_hosted_task_service import _request

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=runner, ephemeral=True, auto_reconcile=False
    )
    request = _request(tmp_path)
    task_id = request["task_id"]
    service._write_state(
        task_id,
        {
            "task_id": task_id,
            "request": request,
            "status": "SUBMITTED",
            "attempt_id": "attempt-1",
            "attempts": [{"attempt_id": "attempt-1"}],
            "worker_pid": None,
            "status_history": [],
        },
    )
    return service, task_id


def _ok_runner(contract, request, update):
    return {"promotion_status": "PENDING_HUMAN_APPROVAL"}


def _read(service, task_id) -> dict:
    state = service._read_state(task_id)
    assert state is not None
    return state


def _run(tmp_path, monkeypatch, runner=_ok_runner):
    monkeypatch.delenv(ea.STRICT_ENV, raising=False)
    service, task_id = _owned_service(tmp_path, runner)
    service._run_owned_task(task_id, "attempt-1")
    return _read(service, task_id), task_id


def test_owned_attempt_persists_would_refuse_shadow_on_task_state(tmp_path, monkeypatch):
    state, task_id = _run(tmp_path, monkeypatch)
    shadow = state[ea.SHADOW_FIELD]
    assert shadow["decision"] == ea.DECISION_WOULD_REFUSE
    assert shadow["reason"] == "NO_EFFECT_AUTHORIZATION_ON_REQUEST"
    assert shadow["task_id"] == task_id
    assert shadow["attempt_id"] == "attempt-1"
    assert shadow["mode"] == "SHADOW"
    assert shadow["recorded_at"]
    assert state["attempts"][0][ea.SHADOW_FIELD] == shadow
    # Observation only: the run still reached its normal outcome.
    assert state["status"] == "PENDING_HUMAN_APPROVAL"


def test_persisted_shadow_is_visible_through_get_task(tmp_path, monkeypatch):
    monkeypatch.delenv(ea.STRICT_ENV, raising=False)
    service, task_id = _owned_service(tmp_path, _ok_runner)
    service._run_owned_task(task_id, "attempt-1")
    task = service.get_task(task_id)
    assert task is not None
    assert task[ea.SHADOW_FIELD]["decision"] == ea.DECISION_WOULD_REFUSE


def test_shadow_decision_failure_does_not_change_outcome(tmp_path, monkeypatch):
    baseline, _ = _run(tmp_path / "a", monkeypatch)

    def broken(_request, *_a, **_k):
        raise RuntimeError("bug in shadow path")

    monkeypatch.setattr(ea, "shadow_decision", broken)
    state, _ = _run(tmp_path / "b", monkeypatch)
    assert ea.SHADOW_FIELD not in state
    assert state["status"] == baseline["status"] == "PENDING_HUMAN_APPROVAL"


def test_shadow_persist_failure_does_not_change_outcome(tmp_path, monkeypatch):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    real_mutate = SelfHostedTaskService._mutate_state

    def mutate(self, task_id, mutator):
        if getattr(mutator, "__qualname__", "").startswith("_persist_effect_authority_shadow"):
            raise OSError("state store unavailable")
        return real_mutate(self, task_id, mutator)

    monkeypatch.setattr(SelfHostedTaskService, "_mutate_state", mutate)
    state, _ = _run(tmp_path, monkeypatch)
    assert ea.SHADOW_FIELD not in state
    assert state["status"] == "PENDING_HUMAN_APPROVAL"


def test_shadow_failure_does_not_change_failing_outcome(tmp_path, monkeypatch):
    def failing(contract, request, update):
        raise RuntimeError("deliberate terminal failure")

    baseline, _ = _run(tmp_path / "a", monkeypatch, failing)
    monkeypatch.setattr(ea, "shadow_decision", lambda *_a, **_k: 1 / 0)
    state, _ = _run(tmp_path / "b", monkeypatch, failing)
    assert state["status"] == baseline["status"]
    assert state.get("error") == baseline.get("error")


def test_shadow_never_writes_into_another_attempts_state(tmp_path, monkeypatch):
    monkeypatch.delenv(ea.STRICT_ENV, raising=False)
    service, task_id = _owned_service(tmp_path, _ok_runner)
    decision = {"decision": ea.DECISION_WOULD_REFUSE, "attempt_id": "stale-attempt"}
    bridge._persist_effect_authority_shadow(service, task_id, "stale-attempt", decision)
    assert ea.SHADOW_FIELD not in _read(service, task_id)


def test_strict_off_attaches_no_port_on_owned_attempt(tmp_path, monkeypatch):
    # Strict-off behaviour unchanged: the coordinator gets no effect port and
    # no require_effect_authority, so nothing new is refused.
    seen = []
    real = bridge.ExecutionCoordinator

    def spy(*args, **kwargs):
        seen.append({k: kwargs.get(k) for k in ("effect_authority", "require_effect_authority")})
        return real(*args, **kwargs)

    monkeypatch.setattr(bridge, "ExecutionCoordinator", spy)
    state, _ = _run(tmp_path, monkeypatch)
    assert seen == [{"effect_authority": None, "require_effect_authority": None}]
    assert state["status"] == "PENDING_HUMAN_APPROVAL"
    assert state[ea.SHADOW_FIELD]["mode"] == "SHADOW"


def test_execute_persists_shadow_with_service(monkeypatch):
    persisted = []

    class _Service:
        def _bridge_validate_claim(self, *_a, **_k):
            return None

    class _Stop(Exception):
        pass

    def stop(self, *_a, **_k):
        raise _Stop

    monkeypatch.delenv(ea.STRICT_ENV, raising=False)
    monkeypatch.setattr(
        bridge,
        "_persist_effect_authority_shadow",
        lambda service, t, a, d: persisted.append((t, a, d["decision"])),
    )
    monkeypatch.setattr(bridge.RuntimeCoordinationBridge, "_coordinator", stop)
    with pytest.raises(_Stop):
        bridge.RuntimeCoordinationBridge(_Service()).execute("t1", "a1", request={"k": 1})
    assert persisted == [("t1", "a1", ea.DECISION_WOULD_REFUSE)]


# --- Codex r1: the shadow mirrors strict's freshness and identity checks ------


def _req(auth, **over):
    request = {
        "operation_id": "op-1",
        "repository": "James3014/Nexus-new",
        "effect_authorization": auth.to_dict(),
    }
    request.update(over)
    return request


def test_shadow_allows_fresh_matching_authorization_for_its_attempt():
    decision = ea.shadow_decision(_req(_auth()), _lookup(_record()), attempt_id="att-1")
    assert decision["decision"] == ea.DECISION_ALLOW
    assert decision["reason"] == "RECORD_MATCH"


def test_shadow_refuses_expired_authorization_even_with_record_match():
    expired = _auth(expires_at="2000-01-01T00:00:00Z")
    decision = ea.shadow_decision(_req(expired), _lookup(_record()), attempt_id="att-1")
    assert decision["decision"] == ea.DECISION_WOULD_REFUSE
    assert decision["reason"].startswith("AUTHORIZATION_INVALID:")


@pytest.mark.parametrize(
    ("attempt", "over", "prefix"),
    [
        ("other-attempt", {}, "IDENTITY_MISMATCH:"),
        ("att-1", {"operation_id": "op-2"}, "IDENTITY_MISMATCH:"),
        ("att-1", {"repository": "James3014/other"}, "IDENTITY_MISMATCH:"),
        ("att-1", {"operation_id": None}, "REQUEST_IDENTITY_MISSING"),
        ("att-1", {"repository": " "}, "REQUEST_IDENTITY_MISSING"),
    ],
)
def test_shadow_refuses_identity_mismatch(attempt, over, prefix):
    decision = ea.shadow_decision(_req(_auth(), **over), _lookup(_record()), attempt_id=attempt)
    assert decision["decision"] == ea.DECISION_WOULD_REFUSE
    assert decision["reason"].startswith(prefix)


def test_bridge_shadow_checks_identity_against_its_attempt(monkeypatch):
    monkeypatch.delenv(ea.STRICT_ENV, raising=False)
    # The identity check runs before any record lookup.
    decision = bridge._record_effect_authority_shadow("t1", "other-attempt", _req(_auth()))
    assert decision is not None
    assert decision["decision"] == ea.DECISION_WOULD_REFUSE
    assert decision["reason"].startswith("IDENTITY_MISMATCH:")


def test_shadow_record_bounds_caller_supplied_text(monkeypatch):
    monkeypatch.delenv(ea.STRICT_ENV, raising=False)
    huge = "x" * 1_000_000
    monkeypatch.setattr(
        ea,
        "shadow_decision",
        lambda *_a, **_k: {"decision": "WOULD_REFUSE", "reason": "R", "authority_ref": huge},
    )
    decision = bridge._record_effect_authority_shadow("t1", "a1", {"task": "x"})
    assert decision is not None
    assert len(decision["authority_ref"]) < 300
    assert "len=1000000" in decision["authority_ref"]
