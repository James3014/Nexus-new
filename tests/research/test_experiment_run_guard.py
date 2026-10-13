from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nexus.research.experiment_run_guard import (
    ControllerDigestMismatch,
    ExperimentRunContract,
    ExperimentRunGuard,
    ImmutableArtifactConflict,
    RunContractConflict,
    RunEffectConflict,
    WorkspaceOwnershipConflict,
    write_immutable_artifact,
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
    # Preserve the historical node ID for exact-base test provenance.  #1541
    # Reuse is read/reconciliation-only until begin_effect() explicitly consumes
    # the exact run's one provider-effect slot.
    state = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(state)
    contract = _contract(workspace, controller)

    first = guard.acquire(contract)
    assert first.disposition == "CREATED"
    assert first.effect_state == "NOT_STARTED"
    first.release()

    second = guard.acquire(contract)
    assert second.disposition == "REUSED"
    assert second.effect_state == "NOT_STARTED"
    second.release()

    record = guard.read(contract.run_id)
    assert record["contract_sha256"] == first.contract_sha256
    assert record["effect"]["state"] == "NOT_STARTED"


def test_terminal_effect_cannot_be_restarted(tmp_path: Path) -> None:
    state = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(state)
    contract = _contract(workspace, controller)

    with guard.acquire(contract) as lease:
        lease.begin_effect()
        lease.bind_operation("agyop_example")
        lease.mark_terminal(
            operation_id="agyop_example",
            response_sha256="d" * 64,
            receipt_sha256="e" * 64,
        )

    record = guard.read(contract.run_id)
    assert record["effect"] == {
        "effect_handle": contract.run_id,
        "operation_id": "agyop_example",
        "receipt_sha256": "e" * 64,
        "response_sha256": "d" * 64,
        "state": "TERMINAL",
    }

    with guard.acquire(contract) as replay:
        assert replay.effect_state == "TERMINAL"
        with pytest.raises(RunEffectConflict, match="RUN_EFFECT_ALREADY_TERMINAL"):
            replay.begin_effect()


def test_outcome_unknown_requires_same_effect_reconciliation(tmp_path: Path) -> None:
    state = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(state)
    contract = _contract(workspace, controller)

    with guard.acquire(contract) as lease:
        lease.begin_effect()
        lease.bind_operation("agyop_unknown")
        lease.mark_outcome_unknown(operation_id="agyop_unknown")

    record = guard.read(contract.run_id)
    assert record["effect"]["state"] == "OUTCOME_UNKNOWN"
    assert record["effect"]["operation_id"] == "agyop_unknown"

    with guard.acquire(contract) as replay:
        assert replay.effect_state == "OUTCOME_UNKNOWN"
        with pytest.raises(
            RunEffectConflict,
            match="RUN_EFFECT_OUTCOME_UNKNOWN_RECONCILE_SAME_EFFECT",
        ):
            replay.begin_effect()


def test_issue_1540_sequential_replay_is_fenced_before_duplicate_effect(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(state)
    contract = _contract(workspace, controller, run_id="issue-1540/X2/crossmodel")
    receipt = tmp_path / "receipts" / "X2-crossmodel.json"
    launches: list[str] = []

    with guard.acquire(contract) as first:
        first.begin_effect()
        launches.append("agyop_canonical")
        first.bind_operation("agyop_canonical")
        assert write_immutable_artifact(receipt, b'{"operation":"agyop_canonical"}\n') == "CREATED"
        first.mark_terminal(
            operation_id="agyop_canonical",
            response_sha256="d" * 64,
            receipt_sha256=_sha(receipt),
        )

    with guard.acquire(contract) as replay:
        assert replay.disposition == "REUSED"
        assert replay.effect_state == "TERMINAL"
        with pytest.raises(RunEffectConflict, match="RUN_EFFECT_ALREADY_TERMINAL"):
            replay.begin_effect()
        assert launches == ["agyop_canonical"]

    with pytest.raises(ImmutableArtifactConflict, match="IMMUTABLE_ARTIFACT_CONFLICT"):
        write_immutable_artifact(receipt, b'{"operation":"agyop_duplicate"}\n')


def test_immutable_artifact_is_create_once_and_conflicting_bytes_fail_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "receipt.json"

    assert write_immutable_artifact(path, b'{"result":"first"}\n') == "CREATED"
    assert write_immutable_artifact(path, b'{"result":"first"}\n') == "REUSED_SAME_BYTES"

    with pytest.raises(
        ImmutableArtifactConflict,
        match="IMMUTABLE_ARTIFACT_CONFLICT",
    ):
        write_immutable_artifact(path, b'{"result":"different"}\n')


def test_legacy_v1_run_cannot_be_reinterpreted_as_no_effect(tmp_path: Path) -> None:
    state = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(state)
    contract = _contract(workspace, controller)
    payload = contract.payload()
    contract_sha = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    run_key = hashlib.sha256(contract.run_id.encode("utf-8")).hexdigest()
    run_path = state / "runs" / f"{run_key}.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text(
        json.dumps(
            {
                "schema": "nexus.experiment_run_guard.v1",
                "contract": payload,
                "contract_sha256": contract_sha,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert guard.read(contract.run_id)["schema"] == "nexus.experiment_run_guard.v1"
    with pytest.raises(
        RunEffectConflict,
        match="LEGACY_RUN_EFFECT_STATE_UNKNOWN",
    ):
        guard.acquire(contract)


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


def test_mark_no_effect_allows_one_fresh_effect_admission(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(tmp_path / "state")
    contract = _contract(workspace, controller)

    first = guard.acquire(contract)
    first.begin_effect()
    first.mark_no_effect()
    first.release()

    second = guard.acquire(contract)
    assert second.disposition == "REUSED"
    assert second.effect_state == "NOT_STARTED"
    second.begin_effect()
    second.bind_operation("agyop_second")
    second.mark_terminal(
        operation_id="agyop_second",
        response_sha256="d" * 64,
        receipt_sha256="e" * 64,
    )
    second.release()

    with guard.acquire(contract) as replay:
        with pytest.raises(RunEffectConflict, match="RUN_EFFECT_ALREADY_TERMINAL"):
            replay.begin_effect()


def test_context_manager_without_terminal_truth_fails_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("print('stable')\n", encoding="utf-8")
    guard = ExperimentRunGuard(tmp_path / "state")
    contract = _contract(workspace, controller)

    with pytest.raises(
        RunEffectConflict,
        match="RUN_EFFECT_TERMINALIZATION_REQUIRED",
    ):
        with guard.acquire(contract) as lease:
            lease.begin_effect()

    record = guard.read(contract.run_id)
    assert record["effect"]["state"] == "OUTCOME_UNKNOWN"

    with guard.acquire(contract) as replay:
        with pytest.raises(
            RunEffectConflict,
            match="RUN_EFFECT_OUTCOME_UNKNOWN_RECONCILE_SAME_EFFECT",
        ):
            replay.begin_effect()
