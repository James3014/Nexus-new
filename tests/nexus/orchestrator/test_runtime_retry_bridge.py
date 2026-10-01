from __future__ import annotations

import json
from pathlib import Path

from nexus.orchestrator.runtime_retry_bridge import _Dispatch, _State, retry_task_via_runtime


class Owner:
    def __init__(self, path: Path):
        self.path, self.submitted = path, None

    def _read_state_snapshot(self, task_id):
        if not self.path.exists():
            return None
        value = json.loads(self.path.read_text())
        return value if value.get("task_id") == task_id else None

    def build_contract(self, request):
        return type("Contract", (), {"maximum_attempts_per_task": 3})()

    def _retry_request(self, state):
        value = dict(state["request"])
        value.update(attempt_id="a2", action_id="x2", idempotency_key="k2")
        return value

    def submit_task(self, request):
        self.submitted = dict(request)
        return {
            "task_id": request["task_id"],
            "attempt_id": request["attempt_id"],
            "action_id": request["action_id"],
            "idempotency_key": request["idempotency_key"],
            "attempts": [1, 2],
        }

    def _mutate_state(self, task_id, mutator):
        state = json.loads(self.path.read_text())
        mutator(state)
        self.path.write_text(json.dumps(state))


def test_bridge_preserves_runtime_retry_result_and_submit_payload(tmp_path):
    owner = Owner(tmp_path / "state.json")
    owner.path.write_text(
        json.dumps({
            "task_id": "t1",
            "status": "FINAL_BLOCK",
            "attempt_id": "a1",
            "cleanup_decision": "TARGET_CLEANED",
            "attempts": [],
            "request": {"task_id": "t1"},
        })
    )
    result = retry_task_via_runtime(owner, "t1")
    assert result["retry"]["decision"] == "REUSED_TASK_ID"
    assert owner.submitted["attempt_id"] == "a2"


def test_bridge_keeps_unknown_task_fail_closed(tmp_path):
    owner = Owner(tmp_path / "state.json")
    try:
        retry_task_via_runtime(owner, "missing")
    except KeyError as exc:
        assert "unknown task_id" in str(exc)
    else:
        raise AssertionError("unknown task must fail closed")


def test_state_persist_uses_callable_mutator_contract(tmp_path):
    owner = Owner(tmp_path / "state.json")
    owner.path.write_text(json.dumps({"task_id": "t1", "status": "FINAL_BLOCK"}))
    _State(owner).persist("t1", {"status": "RETRYING"})
    assert json.loads(owner.path.read_text())["status"] == "RETRYING"


def test_rebind_refreshes_nested_bound_action_hash(monkeypatch):
    import nexus.orchestrator.self_hosted_task_service as module

    class Envelope:
        def to_dict(self):
            return {"schema": "dispatch", "attempt_id": "a2"}

    monkeypatch.setattr(
        module,
        "build_canonical_dispatch_envelope",
        lambda *args, **kwargs: Envelope(),
    )
    request = {
        "task_id": "t1",
        "planner_output": {"route": "local"},
        "bound_action_request": {"task_id": "t1", "attempt_id": "a1"},
        "action": {"action_type": "TASK_RETRY", "request_hash": "old"},
    }
    result = _Dispatch(object()).rebind_fresh_attempt(request, {"provider": "codex"})
    assert result["bound_action_request"]["canonical_dispatch_envelope"] == {
        "schema": "dispatch",
        "attempt_id": "a2",
    }
    assert result["action"]["request_hash"] == result["action_request_hash"]
