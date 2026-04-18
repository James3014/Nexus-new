import subprocess
from typing import List, Tuple
from pathlib import Path
from nexus.orchestrator.task_contract import Task, TaskStatus
from nexus.orchestrator.state_store import StateStore
from nexus.orchestrator.evidence_collector import EvidenceCollector

class IntegrationManager:
    def __init__(self, state_store: StateStore, evidence_collector: EvidenceCollector):
        self.state_store = state_store
        self.evidence_collector = evidence_collector

    def _run_git(self, args: List[str]):
        result = subprocess.run(["git"] + args, capture_output=True, text=True)
        return result

    def batch_integrate(self, task_ids: List[str], target_branch: str = "main") -> Tuple[List[str], List[str]]:
        """
        Attempts to cherry-pick a list of tasks into target_branch.
        Returns (success_tasks, failed_tasks).
        """
        success_tasks = []
        failed_tasks = []

        # 1. Ensure we are on target_branch and clean
        self._run_git(["checkout", target_branch])
        
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
                # In a real system, we might rollback here. 
                # For now, we report the status.
                failed_tasks.append("GLOBAL_VERIFICATION_FAILED")

        return success_tasks, failed_tasks
