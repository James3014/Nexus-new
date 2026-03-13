from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

# --- P 階段: Plan ---

class PlanStep(BaseModel):
    step_id: int
    action: str
    target: str
    description: str
    depends_on: List[int] = []

class NexusPlan(BaseModel):
    plan_id: str
    goal: str
    steps: List[PlanStep]
    metadata: Dict[str, Any] = {}

# --- D 階段: Diagnosis ---

class DiagnosisViolation(BaseModel):
    file: str
    line: int
    severity: str  # CRITICAL, ADVICE
    reason: str
    suggestion: Optional[str] = None

class NexusDiagnosis(BaseModel):
    task_id: str
    status: str  # PASS, FAIL
    summary: str
    failure_signature: Optional[str] = None
    hotspots: List[str] = []
    pseudo_flows: List[str] = []
    violations: List[DiagnosisViolation] = []
    needs_external: bool = False
    metadata: Dict[str, Any] = {}

# --- X 階段: External Research ---

class ResearchSource(BaseModel):
    title: str
    url: str
    snippet: str

class NexusResearch(BaseModel):
    task_id: str
    query: str
    sources: List[ResearchSource]
    key_findings: List[str]
    metadata: Dict[str, Any] = {}

# --- A 階段: Audit ---

class AuditResult(BaseModel):
    audit_id: str
    repair_status: str  # PASSED, FAILED
    smoke_status: str  # PASSED, FAILED
    prior_audit_failures: List[str] = []
    code_quality_score: Optional[float] = None
    summary: str
    metadata: Dict[str, Any] = {}

# --- Global State (.musestate / JSONL) ---

class StepRecord(BaseModel):
    phase: str  # P, D, X, R, A, C
    step_id: str
    status: str # pending, in_progress, completed, failed
    started_at: datetime
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None

class NexusState(BaseModel):
    schema_version: str = "1.5.2"
    task_id: str
    current_phase: str = "P"
    current_step_id: Optional[str] = None
    steps_history: List[StepRecord] = []
    external_needed: bool = False
    external_used: List[Dict[str, Any]] = []
    skills_used: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}
