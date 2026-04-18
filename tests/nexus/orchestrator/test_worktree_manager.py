import pytest
import subprocess
import shutil
import os
from pathlib import Path
from nexus.orchestrator.worktree_manager import WorktreeManager

@pytest.fixture
def temp_git_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "Initial commit"], cwd=repo_dir, check=True)
    return repo_dir

def test_worktree_create_and_cleanup(temp_git_repo):
    worktree_root = temp_git_repo / ".nexus" / "worktrees"
    manager = WorktreeManager(root_dir=str(worktree_root))
    # We need to change cwd to the repo for git commands to work
    original_cwd = os.getcwd()
    os.chdir(temp_git_repo)
    
    try:
        task_id = "TASK-001"
        path = manager.create(task_id)
        
        assert Path(path).exists()
        assert (Path(path) / ".git").exists()
        
        # Check if branch exists
        branch_name = manager.get_branch_name(task_id)
        result = subprocess.run(["git", "branch"], capture_output=True, text=True)
        assert branch_name in result.stdout
        
        # Cleanup
        manager.cleanup(task_id, force=True)
        assert not Path(path).exists()
        
    finally:
        os.chdir(original_cwd)

def test_worktree_idempotent(temp_git_repo):
    worktree_root = temp_git_repo / ".nexus" / "worktrees"
    manager = WorktreeManager(root_dir=str(worktree_root))
    original_cwd = os.getcwd()
    os.chdir(temp_git_repo)
    
    try:
        task_id = "TASK-002"
        path1 = manager.create(task_id)
        path2 = manager.create(task_id)
        
        assert path1 == path2
        assert Path(path1).exists()
        
    finally:
        os.chdir(original_cwd)
