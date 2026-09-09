from __future__ import annotations

import json
from pathlib import Path

from nexus.orchestrator.runtime_retry_bridge import retry_task_via_runtime


class Owner:
    def __init__(self, path: Path): self.path, self.submitted = path, None
    def _read_state_snapshot(self, task_id):
        if not self.path.exists(): return None
        value = json.loads(self.path.read_text()); return value if value.get("task_id") == task_id else None
    def build_contract(self, request):
        return type("Contract", (), {"maximum_attempts_per_task": 3})()
    def _retry_request(self, state):
        value = dict(state["request"]); value.update(attempt_id="a2", action_id="x2", idempotency_key="k2"); return value
    def submit_task(self, request):
        self.submitted = dict(request)
        return {"task_id": request["task_id"], "attempt_id": request["attempt_id"], "action_id": request["action_id"], "idempotency_key": request["idempotency_key"], "attempts": [1, 2]}
    def _mutate_state(self, task_id, state): self.path.write_text(json.dumps(state))


def test_bridge_preserves_runtime_retry_result_and_submit_payload(tmp_path):
    owner = Owner(tmp_path / "state.json")
    owner.path.write_text(json.dumps({"task_id": "t1", "status": "FINAL_BLOCK", "attempt_id": "a1", "cleanup_decision": "TARGET_CLEANED", "attempts": [], "request": {"task_id": "t1"}}))
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
