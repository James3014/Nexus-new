from pathlib import Path
import pytest
import os
from unittest.mock import MagicMock, patch
from nexus.services.workspace import WorkspaceManager

@pytest.fixture
def workspace_mgr(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    return WorkspaceManager(project_root)

def test_workspace_lease_success(workspace_mgr):
    """驗證 Workspace 租借流程（Mock Git）。"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        
        task_id, branch, path = workspace_mgr.lease(task_id="T123")
        
        assert task_id == "T123"
        assert "isolated/task-T123" in branch
        assert path.name == "T123"
        assert mock_run.called
        # 檢查 git worktree add 是否被呼叫
        args = mock_run.call_args_list[0][0][0]
        assert "worktree" in args
        assert "add" in args

def test_workspace_cleanup(workspace_mgr, tmp_path):
    """驗證 Workspace 清理流程。"""
    task_id = "T123"
    branch = "isolated/task-T123"
    work_path = workspace_mgr.workspace_base / task_id
    work_path.mkdir(parents=True, exist_ok=True)
    
    with patch("subprocess.run") as mock_run:
        workspace_mgr.cleanup(task_id, branch)
        
        # 檢查 git worktree remove 與 branch -D 是否被呼叫
        assert mock_run.call_count == 2
        args1 = mock_run.call_args_list[0][0][0]
        assert "remove" in args1
        args2 = mock_run.call_args_list[1][0][0]
        assert "-D" in args2

def test_sync_staged_to_sandbox(workspace_mgr, tmp_path):
    """驗證暫存區同步至沙盒的邏輯。"""
    sandbox_path = tmp_path / "sandbox"
    sandbox_path.mkdir()
    
    with patch("subprocess.run") as mock_run, \
         patch("pathlib.Path.stat") as mock_stat:
        
        mock_run.return_value = MagicMock(returncode=0)
        mock_stat.return_value = MagicMock(st_size=100) # 模擬 patch 大小 > 0
        
        success = workspace_mgr.sync_staged_to_sandbox(sandbox_path)
        assert success is True
        # 應包含 git diff --staged, git apply, git add .
        assert mock_run.call_count >= 3
