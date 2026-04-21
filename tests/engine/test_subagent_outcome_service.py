import json
from pathlib import Path
from unittest.mock import MagicMock

from nexus.engine.subagent_outcome_service import SubagentOutcomeService


def test_subagent_outcome_service_rejects_failed_audit(tmp_path: Path):
    subprocess_run = MagicMock()
    crystal_cls = MagicMock()
    svc = SubagentOutcomeService(
        project_root=tmp_path,
        subprocess_run=subprocess_run,
        crystal_cls=crystal_cls,
    )
    payload = {"taskid": "s-1", "audit_passed": False, "worktree": "wt/a"}

    ok = svc.handle(payload, _state=MagicMock())

    assert ok is False
    subprocess_run.assert_not_called()
    crystal_cls.assert_not_called()


def test_subagent_outcome_service_merges_and_saves_lesson(tmp_path: Path):
    subprocess_run = MagicMock(return_value=MagicMock())
    crystal = MagicMock()
    crystal_cls = MagicMock(return_value=crystal)
    svc = SubagentOutcomeService(
        project_root=tmp_path,
        subprocess_run=subprocess_run,
        crystal_cls=crystal_cls,
    )
    payload = {"taskid": "s-2", "audit_passed": True, "worktree": "wt/b"}

    ok = svc.handle(payload, _state=MagicMock())

    assert ok is True
    subprocess_run.assert_called_once()
    crystal_cls.assert_called_once()
    crystal.save_lesson.assert_called_once()
    log_path = tmp_path / ".nexus" / "metrics" / "skill_outcome_events.jsonl"
    assert log_path.exists()
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    row = json.loads(lines[-1])
    assert row["taskid"] == "s-2"
