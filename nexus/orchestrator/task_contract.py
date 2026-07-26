from enum import Enum
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import List, Optional, Dict, Any, Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
import os


_EXACT_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class MutationMode(str, Enum):
    WORKING_TREE_ONLY = "WORKING_TREE_ONLY"


def _normalize_repository_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("path must be a non-empty repository-relative POSIX path")
    if "\\" in value:
        raise ValueError("path must be a repository-relative POSIX path")
    if value.startswith("/") or PurePosixPath(value).is_absolute():
        raise ValueError("path must be a repository-relative POSIX path")
    parts = value.split("/")
    if ".." in parts:
        raise ValueError("path traversal is not allowed")
    directory_prefix = value.endswith("/")
    raw_path = value[:-1] if directory_prefix else value
    if not raw_path or "." in raw_path.split("/") or "//" in value:
        raise ValueError("path must be normalized")
    normalized = PurePosixPath(raw_path).as_posix()
    if normalized != raw_path:
        raise ValueError("path must be normalized")
    return f"{normalized}/" if directory_prefix else normalized


class SelfHostedTaskContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_: Literal["nexus.self_hosted_task_contract.v1"] = Field(
        default="nexus.self_hosted_task_contract.v1",
        alias="schema",
        serialization_alias="schema",
    )

    @property
    def schema(self) -> str:
        return self.schema_

    def model_dump(self, *args, **kwargs):
        kwargs.setdefault("by_alias", True)
        return super().model_dump(*args, **kwargs)

    def model_dump_json(self, *args, **kwargs):
        kwargs.setdefault("by_alias", True)
        return super().model_dump_json(*args, **kwargs)

    task_id: str
    objective: str
    controller_revision: str
    target_base_revision: str
    controller_repo_root: str
    target_repo_root: str
    target_worktree_root: str
    allowed_files: List[str]
    forbidden_files: List[str] = Field(default_factory=list)
    verifier_commands: List[str] = Field(default_factory=list)
    protected_contracts: List[str] = Field(default_factory=list)
    preferred_provider: Optional[str] = None
    fallback_provider: Optional[str] = None
    maximum_provider_calls: int = Field(default=0, ge=0)
    maximum_replans: int = Field(default=0, ge=0)
    mutation_mode: MutationMode = MutationMode.WORKING_TREE_ONLY
    human_approval_required: bool = True

    @field_validator("task_id")
    @classmethod
    def _validate_task_id(cls, value: str) -> str:
        if not _SAFE_TASK_ID_RE.fullmatch(value):
            raise ValueError("task_id must be a safe slug")
        return value

    @field_validator("objective")
    @classmethod
    def _validate_objective(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("objective must be non-empty")
        return value

    @field_validator("controller_revision", "target_base_revision")
    @classmethod
    def _validate_exact_revision(cls, value: str, info) -> str:
        if not _EXACT_GIT_SHA_RE.fullmatch(value):
            raise ValueError(f"{info.field_name} must be an exact 40-char lowercase Git SHA")
        return value

    @field_validator("allowed_files", "forbidden_files")
    @classmethod
    def _validate_repository_paths(cls, values: List[str]) -> List[str]:
        return [_normalize_repository_path(value) for value in values]

    @model_validator(mode="after")
    def _validate_self_hosted_boundaries(self):
        if not self.allowed_files:
            raise ValueError("allowed_files must be non-empty")
        if self.mutation_mode != MutationMode.WORKING_TREE_ONLY:
            raise ValueError("mutation_mode must be WORKING_TREE_ONLY")
        if not self.human_approval_required:
            raise ValueError("human approval is required")
        controller_root = Path(self.controller_repo_root).expanduser().resolve(strict=False)
        target_root = Path(self.target_repo_root).expanduser().resolve(strict=False)
        if controller_root == target_root:
            raise ValueError("controller and target roots must be physically separate")
        return self

    @computed_field(return_type=str)
    @property
    def contract_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"contract_hash"})
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return sha256(canonical).hexdigest()


def _non_empty_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value.strip()


class DevelopmentGoal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    what: str
    why: str

    @field_validator("what", "why")
    @classmethod
    def _validate_text(cls, value: str, info) -> str:
        return _non_empty_text(value, info.field_name)


class ArchitectureDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    selected_option: str
    rationale: str
    rejected_alternatives: List[str] = Field(default_factory=list)

    @field_validator("decision_id")
    @classmethod
    def _validate_decision_id(cls, value: str) -> str:
        if not _SAFE_TASK_ID_RE.fullmatch(value):
            raise ValueError("decision_id must be a safe slug")
        return value

    @field_validator("selected_option", "rationale")
    @classmethod
    def _validate_text(cls, value: str, info) -> str:
        return _non_empty_text(value, info.field_name)

    @field_validator("rejected_alternatives")
    @classmethod
    def _validate_alternatives(cls, values: List[str]) -> List[str]:
        return [_non_empty_text(value, "rejected_alternatives") for value in values]


class AcceptanceProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verifier_commands: List[str] = Field(default_factory=list)
    protected_contracts: List[str] = Field(default_factory=list)
    required_evidence: List[str] = Field(default_factory=list)

    @field_validator("verifier_commands", "protected_contracts", "required_evidence")
    @classmethod
    def _validate_entries(cls, values: List[str], info) -> List[str]:
        return [_non_empty_text(value, info.field_name) for value in values]


class HumanApprovalPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_approval_required: bool = True
    promotion_approval_required: bool = True
    approver_roles: List[str] = Field(default_factory=list)

    @field_validator("approver_roles")
    @classmethod
    def _validate_roles(cls, values: List[str]) -> List[str]:
        return [_non_empty_text(value, "approver_roles") for value in values]

    @model_validator(mode="after")
    def _require_approvals(self):
        if not self.decision_approval_required:
            raise ValueError("decision approval is required")
        if not self.promotion_approval_required:
            raise ValueError("promotion approval is required")
        if not self.approver_roles:
            raise ValueError("approver_roles must be non-empty")
        return self


class ArchitectTaskContract(SelfHostedTaskContract):
    """Versioned WHAT/WHY contract used to govern the self-hosted worker."""

    schema_: Literal["nexus.self_hosted_task_contract.v2"] = Field(
        default="nexus.self_hosted_task_contract.v2",
        alias="schema",
        serialization_alias="schema",
    )
    goal: DevelopmentGoal
    architecture_decisions: List[ArchitectureDecision]
    acceptance_profile: AcceptanceProfile
    human_approval_policy: HumanApprovalPolicy

    @model_validator(mode="after")
    def _validate_architect_boundaries(self):
        if not self.architecture_decisions:
            raise ValueError("architecture_decisions must be non-empty")
        if self.objective != self.goal.what:
            raise ValueError("objective must match goal.what")
        if self.acceptance_profile.verifier_commands != self.verifier_commands:
            raise ValueError("acceptance_profile.verifier_commands must match verifier_commands")
        if self.acceptance_profile.protected_contracts != self.protected_contracts:
            raise ValueError("acceptance_profile.protected_contracts must match protected_contracts")
        if not self.human_approval_required:
            raise ValueError("human approval is required")
        return self


SelfHostedTaskContractV2 = ArchitectTaskContract

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
    CODE_SCAN = "code-scan"
    CODE_IMPACT = "code-impact"
    HUMAN_APPROVAL = "human-approval"
    OTHER = "other"


class EvidenceRequirement(str, Enum):
    PYTEST = "pytest"
    ACCEPTANCE_CHECK = "acceptance-check"
    DELIVERY_GATE = "delivery-gate"
    CODE_SCAN = "code-scan"
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
    if "code-scan" in text or "code:scan" in text or "code scan" in text:
        return EvidenceRequirement.CODE_SCAN
    if "code-impact" in text or "code:impact" in text or "code impact" in text:
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
    if "code-scan" in text or "code:scan" in text or "code scan" in text:
        return EvidenceKind.CODE_SCAN
    if "code-impact" in text or "code:impact" in text or "code impact" in text:
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
            if normalized == EvidenceRequirement.CODE_SCAN:
                return self.kind == EvidenceKind.CODE_SCAN
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
