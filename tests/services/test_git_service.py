from pathlib import Path
import pytest
import subprocess
from unittest.mock import MagicMock, patch
from nexus.services.git import GitManager

@pytest.fixture
def git_mgr(tmp_path):
    """準備測試用的 GitManager。"""
    project_root = tmp_path / "project"
    project_root.mkdir()
    # 模擬 git rev-parse
    with patch("subprocess.check_output") as mock_rev:
        mock_rev.return_value = str(project_root).encode()
        return GitManager(project_root=str(project_root))

def test_git_manager_init(git_mgr, tmp_path):
    """驗證 GitManager 是否能正確獲取專案根目錄。"""
    assert "project" in git_mgr.project_root

def test_git_get_changes_staged(git_mgr):
    """驗證獲取暫存區變更的邏輯。"""
    with patch("subprocess.check_output") as mock_run:
        # 模擬兩次 git 呼叫：一次獲取檔名，一次獲取 diff 文字
        mock_run.side_effect = [
            b"app.py\nutils.py", # files
            b"--- a/app.py\n+++ b/app.py" # diff
        ]
        
        files, diff = git_mgr.get_changes(scope="staged")
        
        assert len(files) == 2
        assert "app.py" in files
        assert "---" in diff
        assert mock_run.call_count == 2

def test_git_get_changes_error(git_mgr):
    """驗證當 Git 執行錯誤時應回傳空結果。"""
    with patch("subprocess.check_output") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "git diff")
        files, diff = git_mgr.get_changes(scope="staged")
        assert files == []
        assert diff == ""
