import pytest
import json
from pathlib import Path
from nexus.app.learn_refresh_service import LearnRefreshService

def test_refresh_service_init(tmp_path: Path):
    svc = LearnRefreshService(repo_root=tmp_path)
    assert svc.repo_root == tmp_path
    assert svc.status_file == tmp_path / ".nexus" / "learn_refresh_daemon_status.json"

def test_execute_refresh_cycle_writes_status(tmp_path, monkeypatch):
    svc = LearnRefreshService(repo_root=tmp_path)
    import subprocess
    class MockRes:
        def __init__(self, rc): self.returncode = rc; self.stdout = "{}"; self.stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: MockRes(0))
    
    # Mock venv_python to sys.executable for test
    import sys
    svc.venv_python = sys.executable
    
    svc._execute_refresh_cycle(topic="", due_within_days=0, pass_threshold=0.8, question_count=5, benchmark_manifest=None)
    assert svc.status_file.exists()
    data = json.loads(svc.status_file.read_text())
    assert "last_run" in data
