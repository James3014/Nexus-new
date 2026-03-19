#!/usr/bin/env python3
import subprocess
import shutil
from pathlib import Path

class GitWorktreeManager:
    def __init__(self, root: Path):
        self.root = root
        self.wt_dir = root / "isolated_swarm"

    def create_worktree(self, task_id: str, branch: str = "main") -> Path:
        target = self.wt_dir / task_id
        if target.exists():
            self.remove_worktree(task_id)
        
        target.parent.mkdir(parents=True, exist_ok=True)
        
        cmd = ["git", "worktree", "add", "-b", f"swarm-{task_id}", str(target), branch]
        subprocess.run(cmd, cwd=self.root, check=True, capture_output=True)
        
        # Copy .env or other necessary config if needed
        # (For now, assume pure git is enough)
        return target

    def remove_worktree(self, task_id: str):
        target = self.wt_dir / task_id
        if not target.exists():
            return
            
        subprocess.run(["git", "worktree", "remove", "--force", str(target)], cwd=self.root, capture_output=True)
        subprocess.run(["git", "branch", "-D", f"swarm-{task_id}"], cwd=self.root, capture_output=True)
        
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

if __name__ == "__main__":
    # Smoke test
    manager = GitWorktreeManager(Path(__file__).resolve().parents[2])
    try:
        path = manager.create_worktree("test-wt")
        print(f"Created wt at: {path}")
        manager.remove_worktree("test-wt")
        print("Removed wt.")
    except Exception as e:
        print(f"Error: {e}")
