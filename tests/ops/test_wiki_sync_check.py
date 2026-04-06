import pytest
import subprocess
from scripts.ops.wiki_sync_check import check_sync

def test_wiki_sync_no_changes(monkeypatch):
    """測試無變更的情況"""
    def mock_run(*args, **kwargs):
        class MockRes:
            stdout = ""
            returncode = 0
        return MockRes()
    
    monkeypatch.setattr(subprocess, "run", mock_run)
    assert check_sync() == 0

def test_wiki_sync_code_changed_no_wiki(monkeypatch):
    """測試程式碼變更但無 Wiki 變更的情況 (應回傳 2)"""
    def mock_run(*args, **kwargs):
        class MockRes:
            stdout = "scripts/ops/ci_gate.py\n"
            returncode = 0
        return MockRes()
    
    monkeypatch.setattr(subprocess, "run", mock_run)
    assert check_sync() == 2

def test_wiki_sync_code_changed_with_wiki(monkeypatch):
    """測試程式碼與 Wiki 同步變更的情況 (應回傳 0)"""
    def mock_run(*args, **kwargs):
        class MockRes:
            stdout = "scripts/ops/ci_gate.py\nnexus_wiki_vault/test.md\n"
            returncode = 0
        return MockRes()
    
    monkeypatch.setattr(subprocess, "run", mock_run)
    assert check_sync() == 0

def test_wiki_sync_with_changelog(monkeypatch):
    """測試程式碼與 Changelog 同步變更的情況 (應回傳 0)"""
    def mock_run(*args, **kwargs):
        class MockRes:
            stdout = "nexus/core/main.py\nnexus_wiki_vault/06_Ops/Ops - Governance Changelog.md\n"
            returncode = 0
        return MockRes()
    
    monkeypatch.setattr(subprocess, "run", mock_run)
    assert check_sync() == 0

def test_wiki_sync_unprotected_code(monkeypatch):
    """測試非保護路徑變更的情況 (應回傳 0)"""
    def mock_run(*args, **kwargs):
        class MockRes:
            stdout = "README.md\ntests/test_app.py\n"
            returncode = 0
        return MockRes()
    
    monkeypatch.setattr(subprocess, "run", mock_run)
    assert check_sync() == 0
