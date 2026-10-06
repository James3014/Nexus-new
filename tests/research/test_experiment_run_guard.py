from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from nexus.research.experiment_run_guard import (
    ControllerDigestMismatch,
    ExperimentRunContract,
    ExperimentRunGuard,
    RunContractConflict,
    WorkspaceOwnershipConflict,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contract(
    workspace: Path,
    controller: Path,
    *,
    run_id: str = "run-1",
    owner_id: str = "owner-a",
    subject_id: str = "subject-a",
) -> ExperimentRunContract:
    return ExperimentRunContract(
        experiment_id="experiment-1",
        run_id=run_id,
        workspace_realpath=str(workspace),
        owner_id=owner_id,
        subject_id=subject_id,
        controller_path=str(controller),
        controller_sha256=_sha(controller),
        prompt_sha256="a" * 64,
        verifier_sha256="b" * 64,
        experiment_contract_sha256="c" * 64,
    )


def test_same_run_same_contract_is_reusable_after_release(tmp_path: Path) -> None:
    state = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(state)
    contract = _contract(workspace, controller)

    first = guard.acquire(contract)
    assert first.disposition == "CREATED"
    first.release()

    second = guard.acquire(contract)
    assert second.disposition == "REUSED"
    assert guard.read(contract.run_id)["contract_sha256"] == second.contract_sha256
    second.release()


def test_same_run_id_with_changed_contract_fails_closed(tmp_path: Path) -> None:
    state = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(state)

    first = guard.acquire(_contract(workspace, controller))
    first.release()

    with pytest.raises(RunContractConflict, match="RUN_CONTRACT_CONFLICT"):
        guard.acquire(
            _contract(
                workspace,
                controller,
                owner_id="owner-b",
            )
        )


def test_second_live_owner_on_same_workspace_fails_closed(tmp_path: Path) -> None:
    state = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(state)

    first = guard.acquire(_contract(workspace, controller, run_id="run-1"))
    try:
        with pytest.raises(
            WorkspaceOwnershipConflict,
            match="WORKSPACE_OWNERSHIP_CONFLICT",
        ):
            guard.acquire(
                _contract(
                    workspace,
                    controller,
                    run_id="run-2",
                    owner_id="owner-b",
                )
            )
    finally:
        first.release()


def test_same_run_id_with_different_workspace_realpath_fails_closed(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    workspace_a.mkdir()
    workspace_b.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(state)

    first = guard.acquire(_contract(workspace_a, controller))
    first.release()

    with pytest.raises(RunContractConflict, match="RUN_CONTRACT_CONFLICT"):
        guard.acquire(_contract(workspace_b, controller))


def test_controller_pre_effect_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('before')\n", encoding="utf-8")
    contract = _contract(workspace, controller)
    controller.write_text("print('after')\n", encoding="utf-8")

    with pytest.raises(
        ControllerDigestMismatch,
        match="CONTROLLER_PRE_EFFECT_SHA256_MISMATCH",
    ):
        ExperimentRunGuard(tmp_path / "state").acquire(contract)


def test_controller_post_effect_drift_requires_fresh_reverification(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('before')\n", encoding="utf-8")
    guard = ExperimentRunGuard(tmp_path / "state")
    lease = guard.acquire(_contract(workspace, controller))
    try:
        controller.write_text("print('drift')\n", encoding="utf-8")

        fence = lease.verify_controller()

        assert fence.status == "CONTROLLER_DRIFT_REVERIFY_REQUIRED"
        assert fence.same_workspace_continuation_allowed is False
        assert fence.required_next_gate == "FRESH_REVERIFY_IMMUTABLE_RESPONSE"
        assert fence.expected_sha256 != fence.observed_sha256
    finally:
        lease.release()


def test_stable_controller_allows_same_run_continuation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(tmp_path / "state")

    with guard.acquire(_contract(workspace, controller)) as lease:
        fence = lease.verify_controller()

    assert fence.status == "CONTROLLER_STABLE"
    assert fence.same_workspace_continuation_allowed is True
    assert fence.required_next_gate is None
