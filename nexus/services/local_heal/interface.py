from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple

@dataclass(frozen=True)
class PhaseResult:
    success: bool
    exit_layer: str = ""
    failure_reason: str = ""
    error_details: Optional[Dict[str, Any]] = None
    error_metadata: Optional[Dict[str, Any]] = None

@dataclass(frozen=True)
class ReproductionInput:
    instance_id: str
    repo_dir: Path
    problem_statement: str
    repro_script: str
    python_executable: str

@dataclass(frozen=True)
class ReproductionOutput:
    success: bool
    reproduced: bool
    repro_evidence: str
    error_reason: str = ""
    env_denoise: Dict[str, Any] = field(default_factory=dict)
    model_decision: Dict[str, Any] = field(default_factory=dict)

    @property
    def failure_reason(self) -> str:
        return self.error_reason

@dataclass(frozen=True)
class PlanningInput:
    problem_statement: str
    repro_evidence: str
    repo_dir: Path
    reasoning_mode: str = "INTUITIVE"

@dataclass(frozen=True)
class RepairPlan:
    """🛡️ Structured Repair Plan"""
    search_symbols: List[str]
    repair_strategy: str
    violated_invariants: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class PlanningOutput:
    success: bool
    plan: Optional[RepairPlan]
    model_decision: Dict[str, Any]
    error_reason: str = ""

    @property
    def failure_reason(self) -> str:
        return self.error_reason

@dataclass(frozen=True)
class LocalizationInput:
    problem_statement: str
    repro_evidence: str
    repo_dir: Path
    plan: Optional[RepairPlan]

@dataclass(frozen=True)
class LocalizedFile:
    """🛡️ Structured Localized File Snippet"""
    path: str
    content: str
    relevance_score: float = 1.0

@dataclass(frozen=True)
class LocalizationOutput:
    success: bool
    localized_files: List[LocalizedFile]
    model_decisions: List[Dict[str, Any]]
    error_reason: str = ""

    @property
    def failure_reason(self) -> str:
        return self.error_reason

@dataclass(frozen=True)
class PatchSynthesisInput:
    instance_id: str
    problem_statement: str
    repro_evidence: str
    plan: Optional[RepairPlan]
    localized_files: List[LocalizedFile]
    repo_dir: Path
    reasoning_mode: str
    attempt: int
    max_tries: int
    system_prompt: str = ""
    user_prompt: str = ""
    failure_reason: str = ""
    python_executable: str = ""
    last_search_anchors: List[str] = field(default_factory=list)
    last_replacement_texts: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class PatchSynthesisOutput:
    success: bool
    final_patch: str
    model_decisions: List[Dict[str, Any]]
    error_reason: str = ""
    syntax_gate_passed: bool = True
    refusal_detected: bool = False
    empty_response: bool = False
    preflight_telemetry: Dict[str, Any] = field(default_factory=dict)
    errors: List = field(default_factory=list)  # T1.2: Forward PatchError objects for telemetry
    last_search_anchors: List[str] = field(default_factory=list)
    last_replacement_texts: List[str] = field(default_factory=list)

    @property
    def failure_reason(self) -> str:
        return self.error_reason

@dataclass(frozen=True)
class VerificationInput:
    instance_id: str
    repo_dir: Path
    problem_statement: str
    final_patch: str
    repro_script: str
    python_executable: str

@dataclass(frozen=True)
class VerificationOutput:
    success: bool
    evaluation_report: str
    hidden_verifier_passed: bool
    solve_eligible: bool
    error_reason: str = ""

    @property
    def failure_reason(self) -> str:
        return self.error_reason

class IPhase:
    """Interface for a pipeline phase (Reproduction, Planning, etc.)"""
    def execute(self, ctx: Any) -> PhaseResult:
        raise NotImplementedError
