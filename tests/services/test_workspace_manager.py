from pathlib import Path
import subprocess
import pytest
import os
from unittest.mock import MagicMock, patch
from nexus.services.workspace import WorkspaceManager


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(repo: Path) -> str:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "nexus@example.test")
    _git(repo, "config", "user.name", "Nexus Test")
    _git(repo, "config", "core.hooksPath", "/dev/null")
    (repo / "tracked.txt").write_text("controller\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "branch", "-M", "main")
    return _git(repo, "rev-parse", "HEAD")


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


def test_lease_rejects_placeholder_swarm_and_preserves_controller(tmp_path, monkeypatch):
    controller = tmp_path / "controller"
    head_before = _init_repo(controller)
    placeholder = controller / ".nexus-swarm-001"
    placeholder.mkdir()
    (placeholder / "marker.txt").write_text("ordinary child\n", encoding="utf-8")
    status_before = _git(controller, "status", "--porcelain=v1", "-z")
    branch_before = _git(controller, "branch", "--show-current")
    workspace_base = tmp_path / "workspaces"
    monkeypatch.setenv("NEXUS_WORKSPACE_BASE", str(workspace_base))
    monkeypatch.setattr(WorkspaceManager, "_sync_brain_to_path", lambda self, path: None)

    manager = WorkspaceManager(controller)
    task_id, branch, path = manager.lease(task_id="T123")

    assert task_id == "T123"
    assert branch == "isolated/task-T123"
    assert path.resolve() != placeholder.resolve()
    assert path.resolve() == (workspace_base / "T123").resolve()
    assert _git(path, "rev-parse", "--show-toplevel") == str(path.resolve())
    assert str(path.resolve()) in _git(controller, "worktree", "list", "--porcelain")
    assert _git(controller, "rev-parse", "HEAD") == head_before
    assert _git(controller, "branch", "--show-current") == branch_before
    assert _git(controller, "status", "--porcelain=v1", "-z") == status_before


def test_lease_accepts_registered_swarm_worktree_and_preserves_controller(tmp_path, monkeypatch):
    controller = tmp_path / "controller"
    head_before = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), head_before)
    status_before = _git(controller, "status", "--porcelain=v1", "-z")
    branch_before = _git(controller, "branch", "--show-current")
    monkeypatch.setenv("NEXUS_WORKSPACE_BASE", str(tmp_path / "workspaces"))
    monkeypatch.setattr(WorkspaceManager, "_sync_brain_to_path", lambda self, path: None)

    manager = WorkspaceManager(controller)
    task_id, branch, path = manager.lease(task_id="T456")

    assert task_id == "T456"
    assert branch == "isolated/task-T456"
    assert path.resolve() == swarm.resolve()
    assert _git(path, "rev-parse", "--show-toplevel") == str(swarm.resolve())
    assert _git(path, "branch", "--show-current") == "isolated/task-T456"
    assert (swarm / ".swarm_lease").read_text(encoding="utf-8") == "isolated/task-T456"
    assert _git(controller, "rev-parse", "HEAD") == head_before
    assert _git(controller, "branch", "--show-current") == branch_before
    assert _git(controller, "status", "--porcelain=v1", "-z") == status_before
