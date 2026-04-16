import pytest
from pathlib import Path
from nexus.app.nightshift_runner_service import AutoResearchNightShift

def test_nightshift_service_init(tmp_path: Path):
    runner = AutoResearchNightShift(project_root=tmp_path, task="test-task")
    assert runner.task == "test-task"
    assert runner.project_root == tmp_path.resolve()
