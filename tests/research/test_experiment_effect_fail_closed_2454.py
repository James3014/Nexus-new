"""#2454 regression: the effect controller's terminal check stays fail-closed.

A nonterminal or unrecognised status after reconciliation raises the module's
existing error codes; the check now runs through ``nexus.contracts.fail_closed``.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import pytest

from nexus.research.experiment_effect_controller import (
    EffectArtifacts,
    ExperimentEffectController,
    ExperimentEffectOutcomeUnknown,
)
from nexus.research.experiment_run_guard import (
    ExperimentRunContract,
    ExperimentRunGuard,
    sha256_file,
)


class _StrStatus(str, Enum):
    COMPLETED = "COMPLETED"


class _PlainStatus(Enum):
    COMPLETED = "COMPLETED"


def _contract(tmp_path: Path) -> ExperimentRunContract:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    controller = tmp_path / "controller.py"
    controller.write_text("# issue2454 controller\n", encoding="utf-8")
    return ExperimentRunContract(
        experiment_id="ISSUE2454-REGRESSION",
        run_id="ISSUE2454-REGRESSION/fail-closed",
        workspace_realpath=str(workspace),
        owner_id="test-owner",
        subject_id="issue2454",
        controller_path=str(controller),
        controller_sha256=sha256_file(controller),
    )


def _artifacts(tmp_path: Path, operation: dict[str, object]) -> EffectArtifacts:
    op = str(operation["operation_id"]).encode()
    return EffectArtifacts(
        response_path=tmp_path / "responses" / "r.json",
        response_bytes=b'{"operation":"' + op + b'"}\n',
        receipt_path=tmp_path / "receipts" / "r.json",
        receipt_bytes=b'{"terminal":true}\n',
    )


def _reconcile_to(tmp_path: Path, reconciled_status: object):
    guard = ExperimentRunGuard(tmp_path / "guard-state")
    contract = _contract(tmp_path)
    with guard.acquire(contract) as first:
        first.begin_effect()
        first.bind_operation("agyop_existing")
        first.mark_outcome_unknown(operation_id="agyop_existing")

    def forbidden_launch() -> str:
        raise AssertionError("replacement effect must not launch")

    with guard.acquire(contract) as replay:
        return ExperimentEffectController(replay).run(
            launch_effect=forbidden_launch,
            read_status=lambda op: {"status": "OUTCOME_UNKNOWN", "operation_id": op},
            reconcile_effect=lambda op: {"status": reconciled_status, "operation_id": op},
            build_artifacts=lambda operation: _artifacts(tmp_path, dict(operation)),
            poll_interval_seconds=0,
        )


@pytest.mark.parametrize(
    ("reconciled_status", "expected_code"),
    [
        ("OUTCOME_UNKNOWN", "PROVIDER_EFFECT_OUTCOME_UNKNOWN"),
        ("RUNNING", "PROVIDER_EFFECT_STILL_RUNNING_AFTER_RECONCILE"),
        ("QUEUED", "PROVIDER_EFFECT_STILL_RUNNING_AFTER_RECONCILE"),
        ("PENDING", "PROVIDER_EFFECT_STATUS_UNRECOGNIZED"),
        ("ABSTAIN", "PROVIDER_EFFECT_STATUS_UNRECOGNIZED"),
        ("completed", "PROVIDER_EFFECT_STATUS_UNRECOGNIZED"),
        ("SUCCEEDED", "PROVIDER_EFFECT_STATUS_UNRECOGNIZED"),
        ("", "PROVIDER_EFFECT_STATUS_UNRECOGNIZED"),
        (None, "PROVIDER_EFFECT_STATUS_UNRECOGNIZED"),
        (0, "PROVIDER_EFFECT_STATUS_UNRECOGNIZED"),
        (True, "PROVIDER_EFFECT_STATUS_UNRECOGNIZED"),
        (_PlainStatus.COMPLETED, "PROVIDER_EFFECT_STATUS_UNRECOGNIZED"),
    ],
)
def test_nonterminal_or_unrecognised_status_raises_existing_code(
    tmp_path: Path, reconciled_status: object, expected_code: str
) -> None:
    with pytest.raises(ExperimentEffectOutcomeUnknown) as excinfo:
        _reconcile_to(tmp_path, reconciled_status)
    assert str(excinfo.value) == expected_code


def test_str_enum_terminal_status_is_still_terminal(tmp_path: Path) -> None:
    result = _reconcile_to(tmp_path, _StrStatus.COMPLETED)
    assert result.operation_id == "agyop_existing"


def test_running_status_timeout_keeps_existing_code(tmp_path: Path) -> None:
    """A RUNNING status that times out keeps the existing wait-timeout code."""
    guard = ExperimentRunGuard(tmp_path / "guard-state")
    contract = _contract(tmp_path)
    clock = iter([0.0, 10.0, 20.0])
    with guard.acquire(contract) as lease:
        controller = ExperimentEffectController(
            lease, sleep=lambda _s: None, monotonic=lambda: next(clock)
        )
        with pytest.raises(ExperimentEffectOutcomeUnknown, match="PROVIDER_EFFECT_WAIT_TIMEOUT"):
            controller.run(
                launch_effect=lambda: "agyop_running",
                read_status=lambda op: {"status": "RUNNING", "operation_id": op},
                reconcile_effect=lambda _op: pytest.fail("must not reconcile"),
                build_artifacts=lambda operation: _artifacts(tmp_path, dict(operation)),
                poll_interval_seconds=0,
                wait_timeout_seconds=1,
            )
