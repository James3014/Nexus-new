from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple

@dataclass
class PhaseResult:
    success: bool
    exit_layer: str = ""
    error_reason: str = ""
    error_metadata: dict = field(default_factory=dict)

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

@dataclass(frozen=True)
class PlanningInput:
    problem_statement: str
    repro_evidence: str
    repo_dir: Path
    reasoning_mode: str = "INTUITIVE"

@dataclass(frozen=True)
class PlanningOutput:
    success: bool
    plan: Dict[str, Any]
    model_decision: Dict[str, Any]
    error_reason: str = ""

@dataclass(frozen=True)
class LocalizationInput:
    problem_statement: str
    repro_evidence: str
    repo_dir: Path
    plan: Dict[str, Any]

@dataclass(frozen=True)
class LocalizationOutput:
    success: bool
    localized_files: List[Tuple[str, str]]
    model_decisions: List[Dict[str, Any]]
    error_reason: str = ""

@dataclass(frozen=True)
class PatchSynthesisInput:
    instance_id: str
    problem_statement: str
    repro_evidence: str
    plan: Dict[str, Any]
    localized_files: List[Tuple[str, str]]
    repo_dir: Path
    reasoning_mode: str
    attempt: int
    max_tries: int
    system_prompt: str = ""
    user_prompt: str = ""
    failure_reason: str = ""

@dataclass(frozen=True)
class PatchSynthesisOutput:
    success: bool
    final_patch: str
    model_decisions: List[Dict[str, Any]]
    error_reason: str = ""
    syntax_gate_passed: bool = True
    refusal_detected: bool = False
    empty_response: bool = False

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

class IPhase:
    """Interface for a pipeline phase (Reproduction, Planning, etc.)"""
    def execute(self, ctx: Any) -> PhaseResult:
        raise NotImplementedError
