from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator
from .state_legacy import NexusStateLegacyMixin
from datetime import datetime
from enum import Enum
from nexus.core.pipeline_metadata import PipelineMetadata

class TddStatus(str, Enum):
    RED = "red"
    GREEN = "green"
    REFACTOR = "refactor"
    NONE = "none"

class AestheticViolation(Exception):
    """當產出代碼未達美學門檻 (Critique Score < 90) 時觸發"""
    pass

# --- P 階段: Plan ---

class Plan(BaseModel):
    task_id: str
    goal: str
    actions: List[str]
    parent_task_id: Optional[str] = None
    aesthetic_gate: List[str] = Field(default_factory=list) # [Polish, Normalize, Distill]
    expected_critique_score: int = 90
    traceid: str = Field(default_factory=lambda: str(uuid.uuid4()))

class NexusState(BaseModel):
    version: str = "v26.1"
    aos_score: float = 135.2
    active_shards: Dict[str, str] = {} # shard_id -> worktree_path
    last_audit: Optional[Dict[str, Any]] = None
    soul_alignment: bool = True

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
    metadata: PipelineMetadata = {}

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
    metadata: PipelineMetadata = {}

class NexusBatch(BaseModel):
    batch_id: str
    started_at: datetime = Field(default_factory=datetime.now)
    tasks_count: int = 0
    completed_tasks: List[str] = []
    failed_tasks: List[str] = []
    total_token_usage: int = 0
    schedule_cron: Optional[str] = None
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, MELTED
    metadata: PipelineMetadata = {}

class StepRecord(BaseModel):
    phase: str  # P, D, X, R, A, C
    step_id: str
    status: str # pending, in_progress, completed, failed
    started_at: datetime
    ended_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict) # 支援自省等靈活擴展 # 支援自省等靈活擴展
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

# --- R02 Decomposed Sub-objects ---

class TokenAccounting(BaseModel):
    """Token 使用量追蹤"""
    total_usage: int = 0
    raw_model: int = 0
    fallback_est: int = 0
    system_overhead: int = 0
    capture_status: str = "unknown"
    phase_tokens: Dict[str, int] = Field(default_factory=dict)

class ObservabilityContext(BaseModel):
    """追蹤與可觀測性"""
    trace_id: str = ""
    span_id: str = ""
    auto_actions: List[Dict[str, Any]] = Field(default_factory=list)

class AuditCounters(BaseModel):
    """審計與重試計數器"""
    audit_pass_count: int = 0
    retry_count: int = 0
    turn_count: int = 0
    clarification_count: int = 0
    correction_count: int = 0
    unresolved_count: int = 0

class PhaseHealthSnapshot(BaseModel):
    """階段健康快照"""
    health_score: float = 100.0
    health_metrics: HealthMetrics = Field(default_factory=HealthMetrics)
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

# --- T 階段: Trinity & Learning ---

class TraumaRecord(BaseModel):
    failure_signature: str
    penalty: float = -0.5
    expiry: Optional[datetime] = None

class NexusWeights(BaseModel):
    skill_weights: Dict[str, float] = Field(default_factory=lambda: {"generalist": 1.0})
    trauma_records: List[TraumaRecord] = Field(default_factory=list)


class NexusState(BaseModel, NexusStateLegacyMixin):
    schema_version: str = "2.0.0"
    task_id: str
    batch_id: Optional[str] = None
    config: TaskConfig = Field(default_factory=TaskConfig)
    
    # Execution
    current_phase: Optional[str] = None
    current_step_id: Optional[str] = None
    steps_history: List[StepRecord] = Field(default_factory=list)
    external_needed: bool = False
    external_used: List[Dict[str, Any]] = Field(default_factory=list)
    skills_used: List[Dict[str, Any]] = Field(default_factory=list)
    execution_mode: str = "one-shot"
    trigger_reason: str = "user"
    trust_level: str = "standard"

    # Sub-objects (Composition)
    tokens: TokenAccounting = Field(default_factory=TokenAccounting)
    observability: ObservabilityContext = Field(default_factory=ObservabilityContext)
    audit: AuditCounters = Field(default_factory=AuditCounters)
    phase_health: PhaseHealthSnapshot = Field(default_factory=PhaseHealthSnapshot)

    # Legacy (保持)
    superpowers_plan: Dict[str, Any] = Field(default_factory=dict)
    tdd_status: TddStatus = TddStatus.NONE
    subagents_active: bool = False
    autonomic_weights: NexusWeights = Field(default_factory=NexusWeights)
    policy_hit_ids: List[str] = Field(default_factory=list)
    policy_applied: bool = False
    metadata: PipelineMetadata = Field(default_factory=dict)
    
    # ----------------------------------------------------

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

    @model_validator(mode='before')
    @classmethod
    def map_legacy_fields(cls, data: Any) -> Any:
        from nexus.core.state_migrator import StateMigrator
        return StateMigrator.migrate(data)

    @model_validator(mode='after')
    def validate_nexus_protocols(self) -> 'NexusState':
        from nexus.core.state_validator import StateValidator
        StateValidator.validate_protocols(self)
        return self
