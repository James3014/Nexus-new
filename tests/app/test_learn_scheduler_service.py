import pytest
from pathlib import Path
from nexus.app.learn_scheduler_service import LearnSchedulerService

def test_learn_scheduler_service_init(tmp_path: Path):
    svc = LearnSchedulerService(repo_root=tmp_path)
    assert svc.repo_root == tmp_path
