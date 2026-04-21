from pathlib import Path
from unittest.mock import MagicMock

from nexus.core.state_contracts import NexusState
from nexus.engine.repair_setup_service import RepairSetupService


def test_repair_setup_service_rejects_when_validator_fails(tmp_path: Path):
    validator = MagicMock()
    validator.validate_code.return_value = {"passed": False}
    swarm_planner = MagicMock()
    federation = MagicMock()
    detect = MagicMock(return_value=["pytest -q"])
    svc = RepairSetupService(
        project_root=tmp_path,
        hardened_validator=validator,
        swarm_planner=swarm_planner,
        federation=federation,
        detect_verify_commands_fn=detect,
    )
    state = NexusState(task_id="setup-1")
    state.metadata["generated_code"] = "bad code"

    out = svc.prepare(state=state)

    assert out["proceed"] is False
    assert out["reason"] == "validator_rejected"
    assert state.metadata["lewm_sim_status"] == "REJECTED"
    detect.assert_not_called()


def test_repair_setup_service_swarm_and_quorum_and_verify(tmp_path: Path):
    validator = MagicMock()
    validator.validate_code.return_value = {"passed": True}
    swarm_planner = MagicMock()
    swarm_planner.get_ready_tasks.return_value = ["p1", "p2"]
    swarm_planner.create_virtual_workspace.return_value = "/tmp/ws"
    federation = MagicMock()
    federation.quorum_check.return_value = True
    federation.select_node.return_value = "node-a"
    detect = MagicMock(return_value=["pytest -q"])
    svc = RepairSetupService(
        project_root=tmp_path,
        hardened_validator=validator,
        swarm_planner=swarm_planner,
        federation=federation,
        detect_verify_commands_fn=detect,
    )
    state = NexusState(task_id="setup-2")
    state.metadata["generated_code"] = "ok"
    state.metadata["swarm_mode"] = True
    state.metadata["task_description"] = "fix service"

    out = svc.prepare(state=state)

    assert out["proceed"] is True
    assert out["verify_cmds"] == ["pytest -q"]
    assert out["skip_pregate"] is False
    assert state.metadata["task_graph_nodes"] == 3
    assert state.metadata["orchestration_pattern"] == "DAG_ORCHESTRATOR"
    assert swarm_planner.add_task.call_count == 3
    federation.select_node.assert_called_once()


def test_repair_setup_service_marks_skip_when_no_verify_and_no_git(tmp_path: Path):
    validator = MagicMock()
    validator.validate_code.return_value = {"passed": True}
    swarm_planner = MagicMock()
    federation = MagicMock()
    federation.quorum_check.return_value = False
    detect = MagicMock(return_value=[])
    svc = RepairSetupService(
        project_root=tmp_path,
        hardened_validator=validator,
        swarm_planner=swarm_planner,
        federation=federation,
        detect_verify_commands_fn=detect,
    )
    state = NexusState(task_id="setup-3")
    state.metadata["generated_code"] = "ok"

    out = svc.prepare(state=state)

    assert out["proceed"] is True
    assert out["verify_cmds"] == []
    assert out["skip_pregate"] is True
