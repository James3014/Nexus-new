
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum, auto

class ProblemClass(Enum):
    PRODUCTION = auto()
    SAFETY = auto()
    DEBUG = auto()
    REVIEW = auto()
    CHANGE = auto()
    MIGRATION = auto()
    PERFORMANCE = auto()
    GOVERNANCE = auto()

class Severity(Enum):
    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()

@dataclass(frozen=True)
class ProblemTicket:
    task_id: str
    problem_class: ProblemClass
    domain_family: str
    severity: Severity
    change_scope: str
    rollback_required: bool
    evidence_inputs: List[str] = field(default_factory=list)
    acceptance_contract: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    required_gates: List[str]
    max_rollout: float
