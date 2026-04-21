from pathlib import Path
from unittest.mock import MagicMock

from nexus.core.state_contracts import NexusState
from nexus.engine.repair_loop_service import RepairLoopService


def test_repair_loop_service_returns_success_when_settlement_succeeds(tmp_path: Path):
    repair_attempt = MagicMock()
    attempt_settlement = MagicMock()
    repair_attempt.execute_attempt.return_value = {
        "status": "ok",
        "passed": True,
        "gate_results": [{"cmd": "pytest -q", "passed": True, "exit_code": 0}],
    }
    attempt_settlement.settle_attempt.return_value = "success"
    svc = RepairLoopService(
        project_root=tmp_path,
        repair_attempt=repair_attempt,
        attempt_settlement=attempt_settlement,
    )
    state = NexusState(task_id="loop-1")

    ok = svc.run(
        task_id="loop-1",
        task_desc="fix loop",
        skill_id="nexus:bug",
        state=state,
        verify_cmds=["pytest -q"],
        run_dir=tmp_path,
        skip_pregate_for_isolated_workspace=False,
    )

    assert ok is True
    assert state.current_phase == "R"
    repair_attempt.execute_attempt.assert_called_once()
    attempt_settlement.settle_attempt.assert_called_once()


def test_repair_loop_service_returns_false_when_writeback_pending(tmp_path: Path):
    repair_attempt = MagicMock()
    attempt_settlement = MagicMock()
    repair_attempt.execute_attempt.return_value = {
        "status": "ok",
        "passed": True,
        "gate_results": [{"cmd": "pytest -q", "passed": True, "exit_code": 0}],
    }
    attempt_settlement.settle_attempt.return_value = "writeback_pending"
    svc = RepairLoopService(
        project_root=tmp_path,
        repair_attempt=repair_attempt,
        attempt_settlement=attempt_settlement,
    )
    state = NexusState(task_id="loop-2")

    ok = svc.run(
        task_id="loop-2",
        task_desc="fix loop",
        skill_id="nexus:bug",
        state=state,
        verify_cmds=["pytest -q"],
        run_dir=tmp_path,
        skip_pregate_for_isolated_workspace=False,
    )

    assert ok is False
    repair_attempt.execute_attempt.assert_called_once()
    attempt_settlement.settle_attempt.assert_called_once()


def test_repair_loop_service_aborts_after_abort_signal(tmp_path: Path):
    repair_attempt = MagicMock()
    attempt_settlement = MagicMock()
    repair_attempt.execute_attempt.return_value = {"status": "abort", "passed": False, "gate_results": []}
    svc = RepairLoopService(
        project_root=tmp_path,
        repair_attempt=repair_attempt,
        attempt_settlement=attempt_settlement,
    )
    state = NexusState(task_id="loop-3")

    ok = svc.run(
        task_id="loop-3",
        task_desc="fix loop",
        skill_id="nexus:bug",
        state=state,
        verify_cmds=["pytest -q"],
        run_dir=tmp_path,
        skip_pregate_for_isolated_workspace=False,
    )

    assert ok is False
    repair_attempt.execute_attempt.assert_called_once()
    attempt_settlement.settle_attempt.assert_not_called()
