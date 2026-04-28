from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator
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


class EvidenceKind(str, Enum):
    PYTEST = "pytest"
    ACCEPTANCE_CHECK = "acceptance-check"
    DELIVERY_GATE = "delivery-gate"
    CODE_IMPACT = "code-impact"
    HUMAN_APPROVAL = "human-approval"
    OTHER = "other"


class EvidenceRequirement(str, Enum):
    PYTEST = "pytest"
    ACCEPTANCE_CHECK = "acceptance-check"
    DELIVERY_GATE = "delivery-gate"
    CODE_IMPACT = "code-impact"
    HUMAN_APPROVAL = "human-approval"


class DeliveryProfile(str, Enum):
    MOCK_ONLY = "mock_only"
    LIVE_BROWSER = "live_browser"
    LIVE_API = "live_api"


def normalize_requirement(
    requirement: str | EvidenceRequirement,
) -> str | EvidenceRequirement:
    if isinstance(requirement, EvidenceRequirement):
        return requirement
    text = str(requirement).strip().lower()
    if "pytest" in text:
        return EvidenceRequirement.PYTEST
    if "acceptance-check" in text:
        return EvidenceRequirement.ACCEPTANCE_CHECK
    if "delivery-gate" in text:
        return EvidenceRequirement.DELIVERY_GATE
    if "code-impact" in text or "code:impact" in text:
        return EvidenceRequirement.CODE_IMPACT
    if "human-approval" in text or "human approval" in text:
        return EvidenceRequirement.HUMAN_APPROVAL
    return text


def infer_evidence_kind(command: str) -> EvidenceKind:
    text = (command or "").strip().lower()
    if "delivery-gate" in text:
        return EvidenceKind.DELIVERY_GATE
    if "acceptance-check" in text:
        return EvidenceKind.ACCEPTANCE_CHECK
    if "code-impact" in text or "code:impact" in text:
        return EvidenceKind.CODE_IMPACT
    if "human-approval" in text or "human approval" in text:
        return EvidenceKind.HUMAN_APPROVAL
    if "pytest" in text:
        return EvidenceKind.PYTEST
    return EvidenceKind.OTHER

class Evidence(BaseModel):
    command: str
    exit_code: int
    output_summary: str
    artifact_path: Optional[str] = None
    kind: EvidenceKind = EvidenceKind.OTHER

    @model_validator(mode="after")
    def _infer_kind(self):
        if self.kind == EvidenceKind.OTHER:
            self.kind = infer_evidence_kind(self.command)
        return self

    def satisfies(self, requirement: str | EvidenceRequirement) -> bool:
        normalized = normalize_requirement(requirement)
        if isinstance(normalized, EvidenceRequirement):
            if normalized == EvidenceRequirement.PYTEST:
                return self.kind == EvidenceKind.PYTEST
            if normalized == EvidenceRequirement.ACCEPTANCE_CHECK:
                return self.kind in {EvidenceKind.ACCEPTANCE_CHECK, EvidenceKind.DELIVERY_GATE}
            if normalized == EvidenceRequirement.DELIVERY_GATE:
                return self.kind == EvidenceKind.DELIVERY_GATE
            if normalized == EvidenceRequirement.CODE_IMPACT:
                return self.kind == EvidenceKind.CODE_IMPACT
            if normalized == EvidenceRequirement.HUMAN_APPROVAL:
                return self.kind == EvidenceKind.HUMAN_APPROVAL
        return str(normalized) in self.command.lower()

class Task(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    task_id: str
    owner: str
    allowed_files: List[str]
    base_branch: str = "main"
    current_status: TaskStatus = TaskStatus.CREATED
    done_criteria: List[str]
    evidence_requirements: List[str | EvidenceRequirement]
    evidence_list: List[Evidence] = []
    branch_name: Optional[str] = None
    last_commit: Optional[str] = None
    working_dir: Optional[str] = None
    consulted_agents: List[str] = Field(default_factory=list)
    delivery_profile: DeliveryProfile = DeliveryProfile.MOCK_ONLY
    requires_proposal: bool = False
    proposal_ref: Optional[str] = None

    @field_validator("consulted_agents")
    @classmethod
    def check_consulted_agents_limit(cls, v: List[str]) -> List[str]:
        if len(v) > 2:
            raise ValueError("consulted_agents must contain at most 2 agents")
        return v

    @model_validator(mode="after")
    def check_workos_contract(self):
        if self.owner in self.consulted_agents:
            raise ValueError("owner cannot also be a consulted agent")
        if self.requires_proposal and not (self.proposal_ref or "").strip():
            raise ValueError("proposal_ref is required when requires_proposal is true")
        return self

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

    @property
    def normalized_evidence_requirements(self) -> List[str | EvidenceRequirement]:
        return [normalize_requirement(req) for req in self.evidence_requirements]

    def missing_evidence_requirements(self) -> List[str | EvidenceRequirement]:
        missing: List[str | EvidenceRequirement] = []
        for requirement in self.normalized_evidence_requirements:
            if not any(evidence.satisfies(requirement) for evidence in self.evidence_list):
                missing.append(requirement)
        if (
            self.delivery_profile in {DeliveryProfile.LIVE_API, DeliveryProfile.LIVE_BROWSER}
            and EvidenceRequirement.HUMAN_APPROVAL not in missing
            and not any(evidence.satisfies(EvidenceRequirement.HUMAN_APPROVAL) for evidence in self.evidence_list)
        ):
            missing.append(EvidenceRequirement.HUMAN_APPROVAL)
        return missing

    def is_done_ready(self) -> bool:
        if not self.evidence_list:
            return False
        return not self.missing_evidence_requirements()

    def get_context_report(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "branch": self.branch_name,
            "commit": self.last_commit,
            "cwd": self.working_dir or os.getcwd(),
            "status": self.current_status
        }
# integrity-seal: 1776512137
