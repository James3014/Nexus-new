import subprocess
import pytest
from unittest.mock import MagicMock
from pathlib import Path
from scripts.ops import ci_gate

def test_ci_gate_wiki_sync_no_longer_warns_but_blocks_dry_run(monkeypatch):
    """
    驗證 ci_gate --dry-run 時，若 wiki_sync_check 回傳 2，
    ci_gate 應回傳 1 (FAIL) 而非 0。
    """
    def mock_run(cmd, *args, **kwargs):
        class MockRes:
            def __init__(self, returncode, stdout="", stderr=""):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr
        
        if "wiki_sync_check.py" in cmd:
            return MockRes(2, "❌ [WIKI-SYNC-BLOCK] Code changes detected...")
        return MockRes(0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr("scripts.ops.ci_gate.Path.exists", lambda x: True)
    monkeypatch.setattr("scripts.ops.ci_gate.ROOT", Path("/tmp"))
    
    exit_code = ci_gate.run_dry_run()
    # 升級後應為 1 (Block)
    assert exit_code == 1

def test_ci_gate_wiki_sync_status_is_fail(monkeypatch, capsys):
    """
    驗證 ci_gate 呼叫 wiki_sync_check 回傳 2 時，狀態為 FAIL。
    """
    def mock_run(cmd, *args, **kwargs):
        class MockRes:
            def __init__(self, returncode):
                self.returncode = returncode
        if "wiki_sync_check.py" in cmd:
            return MockRes(2)
        return MockRes(0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    
    status = ci_gate.run_wiki_sync_check(dry_run=False)
    assert status == "FAIL"
    
    captured = capsys.readouterr()
    assert "❌ [CI-BLOCK] Wiki Sync Check FAILED" in captured.out
