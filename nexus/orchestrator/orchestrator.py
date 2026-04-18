from typing import List, Optional
from nexus.orchestrator.task_contract import Task, TaskStatus
from nexus.orchestrator.worktree_manager import WorktreeManager
from nexus.orchestrator.file_lock_registry import FileLockRegistry
from nexus.orchestrator.evidence_collector import EvidenceCollector
from nexus.orchestrator.state_store import StateStore

from nexus.orchestrator.event_logger import EventLogger

class NexusOrchestrator:
    def __init__(self):
        self.state_store = StateStore()
        self.worktree_manager = WorktreeManager()
        self.lock_registry = FileLockRegistry()
        self.evidence_collector = EvidenceCollector()
        self.logger = EventLogger()

    def create_task(self, task_id: str, owner: str, allowed_files: List[str], 
                    done_criteria: List[str], evidence_requirements: List[str]) -> Task:
        task = Task(
            task_id=task_id,
            owner=owner,
            allowed_files=allowed_files,
            done_criteria=done_criteria,
            evidence_requirements=evidence_requirements
        )
        self.state_store.save_task(task)
        self.logger.log_event("TASK_CREATE", {"task_id": task_id, "owner": owner})
        return task

    def start_task(self, task_id: str) -> Task:
        task = self.state_store.load_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        # 1. Acquire locks
        conflicts = self.lock_registry.acquire(task_id, task.allowed_files)
        if conflicts:
            task.set_status(TaskStatus.CONFLICTED)
            self.state_store.save_task(task)
            self.logger.log_event("TASK_CONFLICT", {"task_id": task_id, "conflicts": conflicts})
            raise RuntimeError(f"File conflicts detected: {conflicts}")

        # 2. Create worktree
        path = self.worktree_manager.create(task_id, task.base_branch)
        task.working_dir = path
        task.branch_name = self.worktree_manager.get_branch_name(task_id)
        
        # 3. Update status
        task.set_status(TaskStatus.ASSIGNED)
        task.set_status(TaskStatus.IN_PROGRESS)
        self.state_store.save_task(task)
        self.logger.log_event("TASK_START", {"task_id": task_id, "branch": task.branch_name})
        
        return task

    def verify_task(self, task_id: str) -> bool:
        task = self.state_store.load_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        passed = self.evidence_collector.verify_gate(task)
        if passed:
            task.set_status(TaskStatus.READY_FOR_REVIEW)
            self.logger.log_event("GATE_PASS", {"task_id": task_id})
        else:
            task.set_status(TaskStatus.FAILED)
            self.logger.log_event("GATE_FAILURE", {"task_id": task_id})
        
        self.state_store.save_task(task)
        return passed

    def close_task(self, task_id: str, cleanup: bool = True):
        task = self.state_store.load_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        # Release locks
        self.lock_registry.release(task_id)
        
        # Cleanup worktree
        if cleanup:
            self.worktree_manager.cleanup(task_id)
        
        task.set_status(TaskStatus.CLOSED)
        self.state_store.save_task(task)
        self.logger.log_event("TASK_CLOSE", {"task_id": task_id})
# v24.13 final hardening
