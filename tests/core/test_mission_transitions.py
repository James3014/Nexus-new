import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from nexus.core.mission_contracts import (
    MISSION_TRANSITIONS,
    MissionStatus,
    MissionTransitionError,
    NexusMission,
    transition,
)
from nexus.services.metabolism_engine import metabolism
from scripts.engine.nexus_cli import nexus


def _mission(status: MissionStatus) -> NexusMission:
    return NexusMission(mission_id="MSN-T", objective="obj", status=status)


def test_illegal_transition_raises() -> None:
    mission = _mission(MissionStatus.DRAFT)
    with pytest.raises(MissionTransitionError):
        transition(mission, MissionStatus.COMPLETED)
    assert mission.status == MissionStatus.DRAFT


def test_completed_to_active_impossible() -> None:
    mission = _mission(MissionStatus.COMPLETED)
    with pytest.raises(MissionTransitionError):
        transition(mission, MissionStatus.ACTIVE)
    assert mission.status == MissionStatus.COMPLETED


@pytest.mark.parametrize("terminal", [MissionStatus.COMPLETED, MissionStatus.ABORTED])
def test_terminal_states_have_no_exits(terminal: MissionStatus) -> None:
    assert MISSION_TRANSITIONS[terminal] == frozenset()


def test_legal_path_through_verifying() -> None:
    mission = _mission(MissionStatus.DRAFT)
    for step in (MissionStatus.ACTIVE, MissionStatus.VERIFYING, MissionStatus.COMPLETED):
        transition(mission, step)
    assert mission.status == MissionStatus.COMPLETED


def _invoke(tmp_path: Path, *args: str, run_rc: int = 0):
    runner = CliRunner()
    with (
        patch.object(cli_mod, "repo_root", tmp_path),
        patch.object(NexusMission, "run_fingerprint_preflight", return_value=True),
        patch.object(cli_mod.subprocess, "run", return_value=MagicMock(returncode=run_rc)),
    ):
        return runner.invoke(nexus, ["nexus", *args])


def test_cli_start_refuses_completed_to_active(tmp_path: Path) -> None:
    _mission(MissionStatus.COMPLETED).persist(tmp_path)
    result = _invoke(tmp_path, "mission", "start")
    assert result.exit_code == 1
    assert NexusMission.load(tmp_path).status == MissionStatus.COMPLETED


def test_cli_start_goes_through_verifying_to_completed(tmp_path: Path) -> None:
    _mission(MissionStatus.DRAFT).persist(tmp_path)
    report = tmp_path / ".nexus" / "reports" / "acceptance_check.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"status": "PASS", "gate_passed": True}), encoding="utf-8")
    seen = []
    real_persist = NexusMission.persist

    def _spy(self, root):
        seen.append(self.status)
        real_persist(self, root)

    with patch.object(NexusMission, "persist", _spy):
        result = _invoke(tmp_path, "mission", "start")
    assert result.exit_code == 0, result.output
    assert MissionStatus.VERIFYING in seen
    assert NexusMission.load(tmp_path).status == MissionStatus.COMPLETED


def test_cli_start_without_acceptance_returns_to_active(tmp_path: Path) -> None:
    _mission(MissionStatus.DRAFT).persist(tmp_path)
    _invoke(tmp_path, "mission", "start")
    assert NexusMission.load(tmp_path).status == MissionStatus.ACTIVE


def test_cli_abort(tmp_path: Path) -> None:
    _mission(MissionStatus.ACTIVE).persist(tmp_path)
    assert _invoke(tmp_path, "mission", "abort").exit_code == 0
    assert NexusMission.load(tmp_path).status == MissionStatus.ABORTED
    assert _invoke(tmp_path, "mission", "abort").exit_code == 1
    assert _invoke(tmp_path, "mission", "start").exit_code == 1


def test_cli_pause_illegal_from_completed(tmp_path: Path) -> None:
    _mission(MissionStatus.COMPLETED).persist(tmp_path)
    assert _invoke(tmp_path, "mission", "pause").exit_code == 1
    assert NexusMission.load(tmp_path).status == MissionStatus.COMPLETED


def test_resume_without_checkpoint_exits_nonzero(tmp_path: Path) -> None:
    runner = CliRunner()
    with (
        patch.object(cli_mod, "repo_root", tmp_path),
        patch.object(metabolism, "stack_path", tmp_path / ".nexus" / "metabolism" / "task_stack.json"),
    ):
        result = runner.invoke(nexus, ["nexus", "resume"])
    assert result.exit_code != 0
    assert "No checkpoint found" in result.output


def test_resume_restores_checkpoint_into_mission(tmp_path: Path) -> None:
    stack = tmp_path / ".nexus" / "metabolism" / "task_stack.json"
    stack.parent.mkdir(parents=True)
    stack.write_text(
        json.dumps({"task_id": "T-42", "last_active_step": "s2", "pending_steps": ["s3", "s4"]}),
        encoding="utf-8",
    )
    _mission(MissionStatus.PAUSED).persist(tmp_path)
    runner = CliRunner()
    with patch.object(cli_mod, "repo_root", tmp_path), patch.object(metabolism, "stack_path", stack):
        result = runner.invoke(nexus, ["nexus", "resume"])
    assert result.exit_code == 0, result.output
    assert "T-42" in result.output
    loaded = NexusMission.load(tmp_path)
    assert loaded.status == MissionStatus.ACTIVE
    assert loaded.last_snapshot_path == str(Path(".nexus/metabolism/task_stack.json"))


def test_mission_resume_without_checkpoint_fails_and_stays_paused(tmp_path: Path) -> None:
    _mission(MissionStatus.PAUSED).persist(tmp_path)
    result = _invoke(tmp_path, "mission", "resume", run_rc=1)
    assert result.exit_code == 1
    assert NexusMission.load(tmp_path).status == MissionStatus.PAUSED
