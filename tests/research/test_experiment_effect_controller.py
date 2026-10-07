from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.research.experiment_effect_controller import (
    EffectArtifacts,
    ExperimentEffectController,
    ExperimentEffectOutcomeUnknown,
    run_guarded_effect,
)
from nexus.research.experiment_run_guard import (
    ExperimentRunContract,
    ExperimentRunGuard,
    RunEffectConflict,
    sha256_file,
)


def _contract(tmp_path: Path) -> ExperimentRunContract:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("# issue1540-shaped controller\n", encoding="utf-8")
    return ExperimentRunContract(
        experiment_id="ISSUE1541-REGRESSION",
        run_id="ISSUE1541-REGRESSION/X2/crossmodel",
        workspace_realpath=str(workspace),
        owner_id="test-owner",
        subject_id="issue1540-x2",
        controller_path=str(controller),
        controller_sha256=sha256_file(controller),
    )


def _artifacts(tmp_path: Path, operation: dict[str, object]) -> EffectArtifacts:
    op = str(operation["operation_id"])
    response = json.dumps({"operation": op, "result": "ok"}, sort_keys=True).encode() + b"\n"
    receipt = json.dumps({"operation": op, "terminal": True}, sort_keys=True).encode() + b"\n"
    return EffectArtifacts(
        response_path=tmp_path / "responses" / "X2-crossmodel.json",
        response_bytes=response,
        receipt_path=tmp_path / "receipts" / "X2-crossmodel.json",
        receipt_bytes=receipt,
    )


def test_issue1540_sequential_replay_is_fenced_before_second_provider_launch(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path)
    launches: list[str] = []

    def launch() -> str:
        launches.append("launch")
        return "agyop_canonical"

    def status(operation_id: str) -> dict[str, object]:
        return {"status": "COMPLETED", "operation_id": operation_id}

    result = run_guarded_effect(
        state_root=tmp_path / "guard-state",
        contract=contract,
        launch_effect=launch,
        read_status=status,
        reconcile_effect=status,
        build_artifacts=lambda operation: _artifacts(tmp_path, dict(operation)),
        poll_interval_seconds=0,
    )
    assert result.operation_id == "agyop_canonical"
    assert launches == ["launch"]

    with pytest.raises(RunEffectConflict, match="RUN_EFFECT_ALREADY_TERMINAL"):
        run_guarded_effect(
            state_root=tmp_path / "guard-state",
            contract=contract,
            launch_effect=launch,
            read_status=status,
            reconcile_effect=status,
            build_artifacts=lambda operation: _artifacts(tmp_path, dict(operation)),
            poll_interval_seconds=0,
        )
    assert launches == ["launch"]


def test_outcome_unknown_reconciles_same_operation_without_relaunch(tmp_path: Path) -> None:
    guard = ExperimentRunGuard(tmp_path / "guard-state")
    contract = _contract(tmp_path)
    with guard.acquire(contract) as first:
        first.begin_effect()
        first.bind_operation("agyop_existing")
        first.mark_outcome_unknown(operation_id="agyop_existing")

    launch_called = False

    def forbidden_launch() -> str:
        nonlocal launch_called
        launch_called = True
        raise AssertionError("replacement effect must not launch")

    def status(operation_id: str) -> dict[str, object]:
        assert operation_id == "agyop_existing"
        return {"status": "OUTCOME_UNKNOWN", "operation_id": operation_id}

    def reconcile(operation_id: str) -> dict[str, object]:
        return {"status": "COMPLETED", "operation_id": operation_id}

    with guard.acquire(contract) as replay:
        result = ExperimentEffectController(replay).run(
            launch_effect=forbidden_launch,
            read_status=status,
            reconcile_effect=reconcile,
            build_artifacts=lambda operation: _artifacts(tmp_path, dict(operation)),
            poll_interval_seconds=0,
        )
    assert result.operation_id == "agyop_existing"
    assert launch_called is False


def test_unresolved_effect_without_operation_id_never_relaunches(tmp_path: Path) -> None:
    guard = ExperimentRunGuard(tmp_path / "guard-state")
    contract = _contract(tmp_path)
    with guard.acquire(contract) as first:
        first.begin_effect()
        first.mark_outcome_unknown()

    with guard.acquire(contract) as replay:
        with pytest.raises(
            ExperimentEffectOutcomeUnknown,
            match="RUN_EFFECT_OPERATION_UNKNOWN_RECONCILIATION_ONLY",
        ):
            ExperimentEffectController(replay).run(
                launch_effect=lambda: "agyop_forbidden",
                read_status=lambda _: {"status": "COMPLETED"},
                reconcile_effect=lambda _: {"status": "COMPLETED"},
                build_artifacts=lambda operation: _artifacts(tmp_path, dict(operation)),
                poll_interval_seconds=0,
            )


@pytest.mark.parametrize(
    ("reconciled_status", "expected_reason"),
    [
        ("RUNNING", "PROVIDER_EFFECT_STILL_RUNNING_AFTER_RECONCILE"),
        ("QUEUED", "PROVIDER_EFFECT_STILL_RUNNING_AFTER_RECONCILE"),
        ("UNRECOGNIZED_STATUS", "PROVIDER_EFFECT_STATUS_UNRECOGNIZED"),
    ],
)
def test_outcome_unknown_reconcile_requires_explicit_terminal_status(
    tmp_path: Path,
    reconciled_status: str,
    expected_reason: str,
) -> None:
    guard = ExperimentRunGuard(tmp_path / "guard-state")
    contract = _contract(tmp_path)
    with guard.acquire(contract) as first:
        first.begin_effect()
        first.bind_operation("agyop_existing")
        first.mark_outcome_unknown(operation_id="agyop_existing")

    build_called = False

    def forbidden_launch() -> str:
        raise AssertionError("replacement effect must not launch")

    def status(operation_id: str) -> dict[str, object]:
        assert operation_id == "agyop_existing"
        return {"status": "OUTCOME_UNKNOWN", "operation_id": operation_id}

    def reconcile(operation_id: str) -> dict[str, object]:
        assert operation_id == "agyop_existing"
        return {"status": reconciled_status, "operation_id": operation_id}

    def build(operation: dict[str, object]) -> EffectArtifacts:
        nonlocal build_called
        build_called = True
        return _artifacts(tmp_path, operation)

    with guard.acquire(contract) as replay:
        with pytest.raises(ExperimentEffectOutcomeUnknown, match=expected_reason):
            ExperimentEffectController(replay).run(
                launch_effect=forbidden_launch,
                read_status=status,
                reconcile_effect=reconcile,
                build_artifacts=build,
                poll_interval_seconds=0,
            )

    assert build_called is False
    with guard.acquire(contract) as readback:
        assert readback.effect_record()["state"] == "OUTCOME_UNKNOWN"


@pytest.mark.parametrize("terminal_status", ["FAILED", "CANCELLED"])
def test_explicit_terminal_failure_statuses_remain_terminal(
    tmp_path: Path,
    terminal_status: str,
) -> None:
    contract = _contract(tmp_path)

    result = run_guarded_effect(
        state_root=tmp_path / "guard-state",
        contract=contract,
        launch_effect=lambda: "agyop_terminal_failure",
        read_status=lambda operation_id: {
            "status": terminal_status,
            "operation_id": operation_id,
        },
        reconcile_effect=lambda _: pytest.fail("terminal status must not reconcile"),
        build_artifacts=lambda operation: _artifacts(tmp_path, dict(operation)),
        poll_interval_seconds=0,
    )

    assert result.terminal_record["status"] == terminal_status
