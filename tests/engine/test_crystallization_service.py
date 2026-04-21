import json
from pathlib import Path
from unittest.mock import MagicMock

from nexus.engine.crystallization_service import CrystallizationService


def test_crystallization_service_persists_log_and_reports(tmp_path: Path):
    reporter = MagicMock()
    svc = CrystallizationService(project_root=tmp_path, reporter=reporter)
    payload = {
        "task_id": "t-1",
        "skill_id": "nexus:bug",
        "passed": True,
        "decision_id": "d-1",
    }

    log_path = svc.persist_outcome(payload)

    assert log_path.exists()
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    row = json.loads(lines[-1])
    assert row["task_id"] == "t-1"
    reporter.report_outcome.assert_called_once_with(payload)
