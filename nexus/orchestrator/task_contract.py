from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
import os

class TaskStatus(str, Enum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    INTEGRATED = "INTEGRATED"
    CLOSED = "CLOSED"
    
    # Failure states
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CONFLICTED = "CONFLICTED"

class TaskStateTransition:
    ALLOWED_TRANSITIONS = {
        TaskStatus.CREATED: [TaskStatus.ASSIGNED, TaskStatus.BLOCKED, TaskStatus.CLOSED, TaskStatus.CONFLICTED, TaskStatus.FAILED],
        TaskStatus.ASSIGNED: [TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.CLOSED, TaskStatus.FAILED],
        TaskStatus.IN_PROGRESS: [TaskStatus.READY_FOR_REVIEW, TaskStatus.FAILED, TaskStatus.CONFLICTED, TaskStatus.BLOCKED, TaskStatus.CLOSED],
        TaskStatus.READY_FOR_REVIEW: [TaskStatus.INTEGRATED, TaskStatus.REJECTED, TaskStatus.FAILED, TaskStatus.CLOSED, TaskStatus.CONFLICTED],
        TaskStatus.INTEGRATED: [TaskStatus.CLOSED],
        TaskStatus.REJECTED: [TaskStatus.IN_PROGRESS, TaskStatus.CLOSED, TaskStatus.FAILED],
        TaskStatus.FAILED: [TaskStatus.IN_PROGRESS, TaskStatus.CLOSED],
        TaskStatus.CONFLICTED: [TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.CLOSED, TaskStatus.FAILED],
        TaskStatus.BLOCKED: [TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.CLOSED, TaskStatus.FAILED],
    }

    @classmethod
    def validate_transition(cls, current: TaskStatus, target: TaskStatus):
        if current == target:
            return
        if target not in cls.ALLOWED_TRANSITIONS.get(current, []):
            raise ValueError(f"Illegal state transition from {current} to {target}")

class Evidence(BaseModel):
    command: str
    exit_code: int
    output_summary: str
    artifact_path: Optional[str] = None

class Task(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    task_id: str
    owner: str
    allowed_files: List[str]
    base_branch: str = "main"
    current_status: TaskStatus = TaskStatus.CREATED
    done_criteria: List[str]
    evidence_requirements: List[str]
    evidence_list: List[Evidence] = []
    branch_name: Optional[str] = None
    last_commit: Optional[str] = None
    working_dir: Optional[str] = None

    @field_validator("current_status")
    @classmethod
    def check_transition(cls, v: TaskStatus, info) -> TaskStatus:
        # info.data contains the validated fields so far. 
        # For validation on assignment, we need to compare with the current instance value.
        # But in field_validator, we don't have direct access to the old value easily without a hack.
        # However, for Pydantic V2 validate_assignment, this will be called.
        # We will implement a property setter or use a more robust transition method.
        return v

    def set_status(self, target: TaskStatus):
        TaskStateTransition.validate_transition(self.current_status, target)
        self.current_status = target

    def add_evidence(self, evidence: Evidence):
        self.evidence_list.append(evidence)

    def is_done_ready(self) -> bool:
        # Claim guard: check if all evidence requirements have at least one matching evidence (simple heuristic)
        # In practice, this would be more sophisticated.
        if not self.evidence_list:
            return False
        return len(self.evidence_list) >= len(self.evidence_requirements)

    def get_context_report(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "branch": self.branch_name,
            "commit": self.last_commit,
            "cwd": self.working_dir or os.getcwd(),
            "status": self.current_status
        }
