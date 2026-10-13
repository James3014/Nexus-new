"""Failure outcomes of CLI commands must surface as a non-zero exit code."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from nexus.core.mission_contracts import MissionStatus, NexusMission
from scripts.engine.commands.multi_agent_actions import (
    TaskAuditView,
    TaskStatusView,
    TaskSubmissionView,
    TaskVerificationView,
)
from scripts.engine.commands.sandbox_actions import SandboxRunResult


def _invoke(*args: str):
    return CliRunner().invoke(cli_mod.nexus, ["nexus", *args])


def _sandbox_result(success: bool):
    return lambda root, task, **kwargs: SandboxRunResult(
        task=task, success=success, raw_result={"success": success}
    )


def test_sandbox_run_failure_exits_nonzero(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_sandbox_task", _sandbox_result(False))

    result = _invoke("sandbox", "run", "--task", "smoke", "--command", "false")

    assert result.exit_code == 1
    assert "Success: False" in result.output


def test_sandbox_run_success_exits_zero(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_sandbox_task", _sandbox_result(True))

    result = _invoke("sandbox", "run", "--task", "smoke", "--command", "true")

    assert result.exit_code == 0
    assert "Success: True" in result.output


@pytest.mark.parametrize(("passed", "expected_exit"), [(False, 1), (True, 0)])
def test_multi_agent_verify_exit_code(monkeypatch, passed: bool, expected_exit: int) -> None:
    monkeypatch.setattr(
        cli_mod,
        "verify_multi_agent_task",
        lambda task_id: TaskVerificationView(
            task_id=task_id, passed=passed, text_lines=["verify output"]
        ),
    )

    result = _invoke("multi-agent", "verify", "--task-id", "SMK-1")

    assert result.exit_code == expected_exit
    assert "verify output" in result.output


@pytest.mark.parametrize(("submitted", "expected_exit"), [(False, 1), (True, 0)])
def test_multi_agent_submit_exit_code(monkeypatch, submitted: bool, expected_exit: int) -> None:
    monkeypatch.setattr(
        cli_mod,
        "submit_multi_agent_task",
        lambda task_id, *, repo_root: TaskSubmissionView(
            task_id=task_id,
            submitted=submitted,
            delivery_payload=None,
            text_lines=["submit output"],
        ),
    )

    result = _invoke("multi-agent", "submit", "--task-id", "SMK-1")

    assert result.exit_code == expected_exit
    assert "submit output" in result.output


@pytest.mark.parametrize(("found", "expected_exit"), [(False, 1), (True, 0)])
def test_multi_agent_status_exit_code(monkeypatch, found: bool, expected_exit: int) -> None:
    monkeypatch.setattr(
        cli_mod,
        "get_multi_agent_task_status",
        lambda task_id: TaskStatusView(text_lines=["status output"], found=found),
    )

    result = _invoke("multi-agent", "status", "--task-id", "NOPE")

    assert result.exit_code == expected_exit
    assert "status output" in result.output


@pytest.mark.parametrize(("found", "expected_exit"), [(False, 1), (True, 0)])
def test_multi_agent_audit_exit_code(monkeypatch, found: bool, expected_exit: int) -> None:
    monkeypatch.setattr(
        cli_mod,
        "get_multi_agent_task_audit",
        lambda task_id: TaskAuditView(text_lines=["audit output"], found=found),
    )

    result = _invoke("multi-agent", "audit", "--task-id", "NOPE")

    assert result.exit_code == expected_exit
    assert "audit output" in result.output


def test_multi_agent_real_status_and_audit_missing_task_exit_nonzero(monkeypatch) -> None:
    store = SimpleNamespace(load_task=lambda task_id: None, list_tasks=lambda: {})
    orchestrator = SimpleNamespace(state_store=store)
    monkeypatch.setattr(
        "scripts.engine.commands.multi_agent_actions._default_orchestrator_factory",
        lambda: orchestrator,
    )

    status = _invoke("multi-agent", "status", "--task-id", "NOPE")
    audit = _invoke("multi-agent", "audit", "--task-id", "NOPE")

    assert status.exit_code == 1
    assert "Task NOPE not found." in status.output
    assert audit.exit_code == 1
    assert "Task NOPE not found." in audit.output


def test_multi_agent_integrate_keeps_exit_one_for_retired_route() -> None:
    # Historical node id retained: `multi-agent integrate` is removed by the 2026-10-13
    # archive batch (#1906); ControlledIntegrationManager / `self-hosted integrate` is the path.
    result = _invoke("multi-agent", "integrate", "--task-ids", "SMK-1")

    assert result.exit_code == 2
    assert "No such command" in result.output


def _start_mission(tmp_path: Path, run_rc: int):
    NexusMission(mission_id="MSN-EXIT", objective="Fix it").persist(tmp_path)
    with (
        patch.object(cli_mod, "repo_root", tmp_path),
        patch.object(NexusMission, "run_fingerprint_preflight", return_value=True),
        patch.object(cli_mod.subprocess, "run", return_value=MagicMock(returncode=run_rc)),
    ):
        return _invoke("mission", "start")


def test_mission_start_exits_nonzero_when_campaign_run_fails(tmp_path: Path) -> None:
    result = _start_mission(tmp_path, run_rc=1)

    assert result.exit_code == 1
    assert "Campaign execution terminated" in result.output
    mission = NexusMission.load(tmp_path)
    assert mission is not None
    assert mission.accumulated_usage["retries"] == 1


def test_mission_start_exits_zero_when_campaign_run_succeeds(tmp_path: Path) -> None:
    result = _start_mission(tmp_path, run_rc=0)

    assert result.exit_code == 0, result.output
    mission = NexusMission.load(tmp_path)
    assert mission is not None
    assert mission.status in (MissionStatus.ACTIVE, MissionStatus.COMPLETED)


@pytest.mark.parametrize("subcommand", ["status", "pause", "resume"])
def test_mission_commands_without_mission_exit_nonzero(tmp_path: Path, subcommand: str) -> None:
    with patch.object(cli_mod, "repo_root", tmp_path):
        result = _invoke("mission", subcommand)

    assert result.exit_code == 1
    assert "No " in result.output
