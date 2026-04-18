import subprocess
import os
import shutil
from pathlib import Path
from typing import Optional

class WorktreeManager:
    def __init__(self, root_dir: str = ".nexus/worktrees"):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _run_git(self, args: list[str], cwd: Optional[str] = None):
        result = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=cwd)
        if result.returncode != 0:
            raise RuntimeError(f"Git command failed: git {' '.join(args)}\nError: {result.stderr}")
        return result.stdout.strip()

    def get_worktree_path(self, task_id: str) -> Path:
        return self.root_dir / task_id

    def get_branch_name(self, task_id: str) -> str:
        return f"codex/task/{task_id}"

    def create(self, task_id: str, base_branch: str = "main") -> str:
        worktree_path = self.get_worktree_path(task_id)
        branch_name = self.get_branch_name(task_id)

        # Check if worktree already exists
        if worktree_path.exists():
            # Verify if it's a valid worktree
            try:
                self._run_git(["worktree", "list"])
                if str(worktree_path.absolute()) in self._run_git(["worktree", "list"]):
                    return str(worktree_path.absolute())
            except Exception:
                # If path exists but not a worktree, remove it
                shutil.rmtree(worktree_path)

        # Create branch if it doesn't exist
        try:
            self._run_git(["rev-parse", "--verify", branch_name])
        except Exception:
            self._run_git(["branch", branch_name, base_branch])

        # Add worktree
        self._run_git(["worktree", "add", str(worktree_path), branch_name])
        
        return str(worktree_path.absolute())

    def cleanup(self, task_id: str, force: bool = False):
        worktree_path = self.get_worktree_path(task_id)
        if not worktree_path.exists():
            return

        args = ["worktree", "remove", str(worktree_path)]
        if force:
            args.append("--force")
        
        self._run_git(args)

    def prune(self):
        self._run_git(["worktree", "prune"])
