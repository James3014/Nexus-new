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

# --- B 階段: Batch Management (v7 Night Factory) ---

class TaskConfig(BaseModel):
    batch_id: Optional[str] = None
    priority: int = 1
    budget_token: int = 5000
    retry_max: int = 3
    allowed_paths: List[str] = ["*"]
    domain: Optional[str] = None  # django, react, infra...
    done_criteria: List[str] = []
    obsidian_ready: bool = False  # 標記是否已同步至 Obsidian

class NexusIssue(BaseModel):
    task_id: str
    batch_id: Optional[str] = None
    goal: str
    domain: Optional[str] = "general"
    priority: int = 1
    config: TaskConfig = Field(default_factory=TaskConfig)
    metadata: Dict[str, Any] = {}

class NexusBatch(BaseModel):
    batch_id: str
    started_at: datetime = Field(default_factory=datetime.now)
    tasks_count: int = 0
    completed_tasks: List[str] = []
    failed_tasks: List[str] = []
    total_token_usage: int = 0
    schedule_cron: Optional[str] = None
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, MELTED
    metadata: Dict[str, Any] = {}

class StepRecord(BaseModel):
    phase: str  # P, D, X, R, A, C
    step_id: str
    status: str # pending, in_progress, completed, failed
    started_at: datetime
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None

from pydantic import model_validator

class NexusState(BaseModel):
    schema_version: str = "1.5.2"
    task_id: str
    batch_id: Optional[str] = None
    config: TaskConfig = Field(default_factory=TaskConfig)
    current_phase: str = "P"
    current_step_id: Optional[str] = None
    steps_history: List[StepRecord] = []
    external_needed: bool = False
    external_used: List[Dict[str, Any]] = []
    skills_used: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}

    @model_validator(mode='after')
    def validate_nexus_protocols(self) -> 'NexusState':
        """
        🚫 Nexus Soul Protocols: Forbidden Transitions & Guardrails
        """
        # 1. Batch Mode 預算守門員
        if self.batch_id and self.current_phase == "P":
            if self.config.budget_token <= 0:
                raise ValueError(f"Soul Protocol Violation: Batch {self.batch_id} at Phase P must have budget_token > 0")
        
        # 2. 狀態轉移禁地 (Forbidden Transitions Matrix)
        if self.steps_history:
            last_phase = self.steps_history[-1].phase
            # 案例：禁止從 P 直接跳到 R (必須經過 D)
            forbidden = {
                "P": ["R", "A", "C"],
                "D": ["A", "C"],
                "X": ["A", "C"]
            }
            if self.current_phase in forbidden.get(last_phase, []):
                raise ValueError(f"Forbidden Transition: Illegal shortcut detected from {last_phase} to {self.current_phase}. Contract v1.5.2 enforces P->D->(X)->R pipeline.")
            
        return self
