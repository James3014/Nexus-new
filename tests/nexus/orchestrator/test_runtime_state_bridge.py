from pathlib import Path

import pytest

from nexus.orchestrator.runtime_state_bridge import RuntimeStateBridge


def _validate(task_id, payload, path):
    if payload.get("task_id") != task_id or not payload.get("status"):
        return {"task_id": task_id, "status": "BLOCKED_INVALID_STATE", "state_valid": False}
    return dict(payload)


def test_bridge_roundtrip_and_in_place_mutation(tmp_path: Path):
    bridge = RuntimeStateBridge(tmp_path / "state", validator=_validate)
    bridge.write("task", {"task_id": "task", "status": "RUNNING"})
    bridge.mutate("task", lambda state: state.update(status="DONE"))
    assert bridge.read("task")["status"] == "DONE"


def test_bridge_authorization_precedes_mutation_and_write(tmp_path: Path):
    bridge = RuntimeStateBridge(tmp_path / "state", validator=_validate)
    bridge.write("task", {"task_id": "task", "status": "RUNNING"})
    before = (tmp_path / "state" / "task.json").read_bytes()

    def deny():
        raise PermissionError("owner denied")

    with pytest.raises(PermissionError, match="owner denied"):
        bridge.mutate("task", lambda state: state.update(status="DONE"), authorize=deny)
    assert (tmp_path / "state" / "task.json").read_bytes() == before
