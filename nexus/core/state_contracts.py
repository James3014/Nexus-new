from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class TddStatus(str, Enum):
    RED = "red"
    GREEN = "green"
    REFACTOR = "refactor"
    NONE = "none"

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
    metadata: Dict[str, Any] = Field(default_factory=dict) # 支援自省等靈活擴展
    summary: Optional[str] = None

# --- H 階段: Health & Self-Check (CHK-001) ---

class HealthMetrics(BaseModel):
    test_pass_rate: float = 0.0 # 0.0 - 1.0
    drift_index: float = 0.0    # 偏離指數 (越小越健康)
    error_rate: float = 0.0     # 錯誤率
    token_efficiency: float = 1.0 # 1.0 為標準
    last_check_at: Optional[datetime] = None
    status: str = "UNKNOWN"     # HEALTHY, WARNING, CRITICAL

class PhaseMetric(BaseModel):
    health: float = 0.0
    signals: Dict[str, Any] = Field(default_factory=dict)
     # HEALTHY, WARNING, CRITICAL

# --- T 階段: Trinity & Learning ---

class TraumaRecord(BaseModel):
    failure_signature: str
    penalty: float = -0.5
    expiry: Optional[datetime] = None

class NexusWeights(BaseModel):
    skill_weights: Dict[str, float] = Field(default_factory=lambda: {"generalist": 1.0})
    trauma_records: List[TraumaRecord] = Field(default_factory=list)

from pydantic import model_validator

class NexusState(BaseModel):
    schema_version: str = "1.9.0"
    task_id: str
    batch_id: Optional[str] = None
    config: TaskConfig = Field(default_factory=TaskConfig)
    current_phase: str = "P"
    current_step_id: Optional[str] = None
    steps_history: List[StepRecord] = []
    external_needed: bool = False
    external_used: List[Dict[str, Any]] = []
    skills_used: List[Dict[str, Any]] = []
    
    # --- Superpowers v5.0.2 Extensions ---
    superpowers_plan: Dict[str, Any] = Field(default_factory=dict)
    tdd_status: TddStatus = TddStatus.NONE
    subagents_active: bool = False
    
    # --- Trinity v9.0 Extensions ---
    autonomic_weights: NexusWeights = Field(default_factory=NexusWeights)
    policy_hit_ids: List[str] = Field(default_factory=list)
    policy_applied: bool = False
    execution_mode: str = "one-shot"
    trigger_reason: str = "user"
    
    # --- Observability & Metrics ---
    total_token_usage: int = 0
    token_raw_model: int = 0
    token_fallback_est: int = 0
    token_system_overhead: int = 0
    token_capture_status: str = "unknown"
    phase_tokens: Dict[str, int] = Field(default_factory=dict)
    audit_pass_count: int = 0
    retry_count: int = 0
    
    # --- Conversation Specific Metrics (CONV-001) ---
    turn_count: int = 0
    clarification_count: int = 0
    correction_count: int = 0
    unresolved_count: int = 0
    
    # --- Health & Self-Check (CHK-001) ---
    health_score: float = 100.0
    health_metrics: HealthMetrics = Field(default_factory=HealthMetrics)
    
    # --- Phase Health Autonomy (PHA-001) ---
    pipeline_health: float = 100.0
    learning_velocity: float = 0.0
    phase_metrics: Dict[str, PhaseMetric] = Field(
        default_factory=lambda: {
            "P": PhaseMetric(),
            "X": PhaseMetric(),
            "D": PhaseMetric(),
            "R": PhaseMetric(),
            "A": PhaseMetric(),
            "C": PhaseMetric()
        }
    )
    auto_actions: List[Dict[str, Any]] = []

    metadata: Dict[str, Any] = {}
    
    def calculate_health(self):
        """Compatibility wrapper for the unified health scoring pipeline."""
        from nexus.health.scoring import HealthScorer

        snapshot = HealthScorer.apply_snapshot(self)
        return snapshot.overall_score
    
    def get_conversation_metadata(self) -> Dict[str, Any]:
        """安全獲取對話元數據容器"""
        return self.metadata.get("conversation", {})

    def init_conversation(self, conversation_id: str, user_goal: str):
        """初始化對話治理容器 (v0.7 Spec)"""
        self.metadata["task_type"] = "conversation"
        self.metadata["conversation"] = {
            "conversation_id": conversation_id,
            "user_goal": user_goal,
            "current_question": None,
            "confirmed_constraints": [],
            "key_context_facts": {},
            "user_corrections": [],
            "unresolved_points": [],
            "needs_research": False,
            "answer_draft_status": "draft",
            "audit_flags": [],
            "return_target_phase": "D",
            "response_mode": "conversation"
        }

    def update_conversation_metadata(self, updates: Dict[str, Any]):
        """更新對話元數據並維持結構一致性 (v2)"""
        if "conversation" not in self.metadata:
            self.init_conversation("pending", "Unknown Goal")
        
        self.metadata["conversation"].update(updates)

    def response_mode(self) -> str:
        """獲取當前響應模式"""
        return self.metadata.get("response_mode", "standard")

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
