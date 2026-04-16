import pytest
import json
from pathlib import Path
from nexus.app.learn_scheduler_service import LearnSchedulerService

def test_scheduler_creates_report(tmp_path, monkeypatch):
    svc = LearnSchedulerService(repo_root=tmp_path)
    import subprocess
    class MockRes:
        def __init__(self, rc, out="{}"):
            self.returncode = rc
            self.stdout = out
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: MockRes(0, '{"slo_readiness": 0.9}'))
    
    svc.run_scheduler()
    report_file = tmp_path / ".nexus/reports/learn/scheduler_last_run.json"
    assert report_file.exists()
