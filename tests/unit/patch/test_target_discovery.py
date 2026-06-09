import pytest
from nexus.engine.patch.target_discovery import TargetFileDiscovery

def test_extract_target_from_diff_header():
    discovery = TargetFileDiscovery()
    raw = "diff --git a/core.py b/core.py\n--- a/core.py\n+++ b/core.py\n@@ -1 +1 @@"
    res = discovery.resolve(raw)
    assert res.resolved is True
    assert res.target_file == "core.py"

def test_extract_target_from_search_block_metadata():
    # If there is no explicit diff header but we passed context
    discovery = TargetFileDiscovery()
    raw = "<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE"
    res = discovery.resolve(raw, context_files=["utils/helpers.py"])
    assert res.resolved is True
    assert res.target_file == "utils/helpers.py"

def test_reject_when_multiple_candidate_files():
    discovery = TargetFileDiscovery()
    raw = "diff --git a/one.py b/one.py\n--- a/one.py\n+++ b/one.py\ndiff --git a/two.py b/two.py\n--- a/two.py\n+++ b/two.py\n"
    res = discovery.resolve(raw)
    assert res.resolved is False
    assert "AMBIGUOUS_TARGET_FILES" in res.reason

def test_reject_when_no_target_can_be_resolved():
    discovery = TargetFileDiscovery()
    raw = "<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE"
    res = discovery.resolve(raw) # No context files
    assert res.resolved is False
    assert res.reason == "NO_TARGET_FILE_FOUND"

def test_resolve_filters_nonexistent_files(tmp_path):
    discovery = TargetFileDiscovery()
    raw = "diff --git a/exists.py b/exists.py\n--- a/exists.py\n+++ b/exists.py\ndiff --git a/not_exists.py b/not_exists.py\n--- a/not_exists.py\n+++ b/not_exists.py"
    
    # 建立一個測試目錄並真的建立 exists.py
    exists_file = tmp_path / "exists.py"
    exists_file.write_text("print('hello')")
    
    res = discovery.resolve(raw, project_root=str(tmp_path))
    assert res.resolved is True
    assert res.target_file == "exists.py"

def test_resolve_prefers_git_changes():
    from unittest.mock import patch, MagicMock
    discovery = TargetFileDiscovery()
    raw = "diff --git a/one.py b/one.py\n--- a/one.py\n+++ b/one.py\ndiff --git a/two.py b/two.py\n--- a/two.py\n+++ b/two.py"
    
    with patch("subprocess.run") as mock_run, \
         patch("pathlib.Path.exists", return_value=True):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = " M two.py\n"
        mock_run.return_value = mock_res
        
        res = discovery.resolve(raw, project_root="/dummy/root")
        assert res.resolved is True
        assert res.target_file == "two.py"

def test_resolve_from_git_changes_fallback():
    from unittest.mock import patch, MagicMock
    discovery = TargetFileDiscovery()
    raw = "<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE"
    
    with patch("subprocess.run") as mock_run, \
         patch("pathlib.Path.exists", return_value=True):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = " M modified.py\n"
        mock_run.return_value = mock_res
        
        res = discovery.resolve(raw, project_root="/dummy/root")
        assert res.resolved is True
        assert res.target_file == "modified.py"
