from pathlib import Path
from unittest.mock import MagicMock

from nexus.core.state_contracts import NexusState
from nexus.engine.repair_attempt_service import RepairAttemptService


def test_repair_attempt_service_aborts_on_sim_lewm_rejected(tmp_path: Path):
    run_cli = MagicMock(return_value=(True, [{"passed": True}]))
    lewm_instance = MagicMock()
    lewm_instance.simulate.return_value = {"status": "REJECTED", "cost": 7}
    lewm_cls = MagicMock(return_value=lewm_instance)
    svc = RepairAttemptService(
        project_root=tmp_path,
        run_cli_pregate_fn=run_cli,
        lewm_cls=lewm_cls,
    )
    state = NexusState(task_id="r-1")
    state.metadata["task_description"] = "fix"
    state.metadata["sim_lewm"] = True

    out = svc.execute_attempt(
        task_id="r-1",
        task_desc="fix",
        state=state,
        attempt=1,
        verify_cmds=["pytest -q"],
        run_dir=tmp_path,
        skip_pregate_for_isolated_workspace=False,
    )

    assert out["status"] == "abort"
    assert out["passed"] is False
    assert state.metadata["lewm_sim_status"] == "REJECTED"
    assert state.metadata["lewm_rejected_cost"] == 7
    run_cli.assert_not_called()


def test_repair_attempt_service_returns_synthetic_pass_for_isolated_skip(tmp_path: Path):
    run_cli = MagicMock(return_value=(False, []))
    svc = RepairAttemptService(project_root=tmp_path, run_cli_pregate_fn=run_cli)
    state = NexusState(task_id="r-2")

    out = svc.execute_attempt(
        task_id="r-2",
        task_desc="fix",
        state=state,
        attempt=1,
        verify_cmds=[],
        run_dir=tmp_path,
        skip_pregate_for_isolated_workspace=True,
    )

    assert out["status"] == "ok"
    assert out["passed"] is True
    assert out["gate_results"][0]["pregate_skip"] is True
    run_cli.assert_not_called()


def test_repair_attempt_service_runs_default_pregate(tmp_path: Path):
    run_cli = MagicMock(return_value=(True, [{"cmd": "pytest -q", "passed": True, "exit_code": 0}]))
    svc = RepairAttemptService(project_root=tmp_path, run_cli_pregate_fn=run_cli)
    state = NexusState(task_id="r-3")

    out = svc.execute_attempt(
        task_id="r-3",
        task_desc="fix",
        state=state,
        attempt=1,
        verify_cmds=["pytest -q"],
        run_dir=tmp_path,
        skip_pregate_for_isolated_workspace=False,
    )

    assert out["status"] == "ok"
    assert out["passed"] is True
    assert out["gate_results"][0]["cmd"] == "pytest -q"
    run_cli.assert_called_once()
