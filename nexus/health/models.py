from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


HealthStatus = Literal["UNKNOWN", "HEALTHY", "WARNING", "CRITICAL"]
DiagnosisKind = Literal[
    "healthy",
    "insufficient_signals",
    "environment_failure",
    "research_failure",
    "repair_failure",
    "audit_failure",
    "evidence_failure",
]
RepairDisposition = Literal["safe_execute", "inject_only", "noop"]
SelfHealStatus = Literal["healthy", "noop", "repaired", "degraded", "failed"]
TriggerSeverity = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True)
class PhaseScore:
    phase: str
    score: float
    completeness: float
    status: HealthStatus
    signals: Dict[str, float]
    issues: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class HealthSnapshot:
    overall_score: float
    outcome_score: Optional[float]
    phase_average: Optional[float]
    confidence: float
    status: HealthStatus
    phase_scores: Dict[str, PhaseScore]
    reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class HealthDiagnosis:
    kind: DiagnosisKind
    summary: str
    reasons: List[str] = field(default_factory=list)
    target_phase: Optional[str] = None


@dataclass(frozen=True)
class HealthTrigger:
    code: str
    reason: str
    severity: TriggerSeverity
    target_phase: Optional[str] = None


@dataclass(frozen=True)
class RepairAction:
    id: str
    description: str
    run: str
    priority: str
    disposition: RepairDisposition
    reason: str
    verify_commands: List[str] = field(default_factory=list)
    artifact_paths: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RepairPlan:
    diagnosis: HealthDiagnosis
    actions: List[RepairAction]
    phase_route: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RepairExecutionResult:
    disposition: RepairDisposition
    executed_actions: List[str] = field(default_factory=list)
    injected_tasks: List[str] = field(default_factory=list)
    manifest_path: Optional[Path] = None
    task_runner_invoked: bool = False
    success: bool = True
    return_codes: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    telemetry: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FaultSignature:
    hash: str
    error_type: str
    location: str
    traceback_summary: str


@dataclass(frozen=True)
class SelfHealCycleResult:
    status: SelfHealStatus
    before: HealthSnapshot
    diagnosis: HealthDiagnosis
    plan: RepairPlan
    execution: RepairExecutionResult
    after: HealthSnapshot
    after_diagnosis: HealthDiagnosis
    notes: List[str] = field(default_factory=list)
