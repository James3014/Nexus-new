import subprocess
from typing import List, Tuple
from pathlib import Path
from nexus.orchestrator.task_contract import Task, TaskStatus
from nexus.orchestrator.state_store import StateStore
from nexus.orchestrator.evidence_collector import EvidenceCollector

class IntegrationManager:
    def __init__(
        self,
        state_store: StateStore,
        evidence_collector: EvidenceCollector,
        *,
        repo_root: str | Path = ".",
        require_clean_preflight: bool = False,
    ):
        self.state_store = state_store
        self.evidence_collector = evidence_collector
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.require_clean_preflight = require_clean_preflight

    def _run_git(self, args: List[str]):
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=self.repo_root,
        )
        return result

    def batch_integrate(self, task_ids: List[str], target_branch: str = "main") -> Tuple[List[str], List[str]]:
        """
        Attempts to cherry-pick a list of tasks into target_branch.
        Returns (success_tasks, failed_tasks).
        """
        success_tasks = []
        failed_tasks = []

        if not task_ids:
            return [], ["NO_TASKS_REQUESTED"]
        original_sha = ""
        original_branch_name = ""
        if self.require_clean_preflight:
            status = self._run_git(["status", "--porcelain"])
            if status.returncode != 0 or status.stdout.strip():
                return [], ["WORKTREE_NOT_CLEAN"]
            original_head = self._run_git(["rev-parse", "HEAD"])
            original_branch = self._run_git(["branch", "--show-current"])
            if original_head.returncode != 0:
                return [], ["ORIGINAL_HEAD_UNAVAILABLE"]
            original_sha = original_head.stdout.strip()
            original_branch_name = original_branch.stdout.strip()

        # 1. Ensure we are on target_branch and clean
        checkout = self._run_git(["checkout", target_branch])
        if checkout.returncode != 0:
            return [], ["TARGET_BRANCH_CHECKOUT_FAILED"]
        
        for tid in task_ids:
            task = self.state_store.load_task(tid)
            if not task or task.current_status != TaskStatus.READY_FOR_REVIEW:
                failed_tasks.append(f"{tid} (invalid status)")
                continue

            # Get the last commit of the task branch
            # We assume the task has at least one commit on its branch
            branch = task.branch_name
            commit_res = self._run_git(["rev-parse", branch])
            if commit_res.returncode != 0:
                failed_tasks.append(f"{tid} (branch not found)")
                continue
            
            commit_sha = commit_res.stdout.strip()
            
            # 2. Try to cherry-pick
            cp_res = self._run_git(["cherry-pick", commit_sha])
            if cp_res.returncode == 0:
                task.set_status(TaskStatus.INTEGRATED)
                self.state_store.save_task(task)
                success_tasks.append(tid)
            else:
                # 3. Handle conflict
                self._run_git(["cherry-pick", "--abort"])
                task.set_status(TaskStatus.CONFLICTED)
                self.state_store.save_task(task)
                failed_tasks.append(tid)

        # 4. Final global verification if any tasks were integrated
        if success_tasks:
            # Create a pseudo-task for global verification
            global_task = Task(
                task_id="GLOBAL-INTEGRATION",
                owner="Integrator",
                allowed_files=["*"],
                done_criteria=["Global tests pass"],
                evidence_requirements=["pytest"]
            )
            passed = self.evidence_collector.verify_gate(global_task)
            if not passed:
                # Transactional rollback to the clean pre-integration head.
                if original_sha:
                    self._run_git(["reset", "--merge", original_sha])
                    if original_branch_name and original_branch_name != target_branch:
                        self._run_git(["checkout", original_branch_name])
                for tid in success_tasks:
                    task = self.state_store.load_task(tid)
                    if task:
                        task.set_status(TaskStatus.READY_FOR_REVIEW)
                        self.state_store.save_task(task)
                success_tasks = []
                failed_tasks.append("GLOBAL_VERIFICATION_FAILED")

        return success_tasks, failed_tasks
# integrity-seal: 1776512137
