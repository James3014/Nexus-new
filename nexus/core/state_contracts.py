from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator
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


class NexusState(BaseModel):
    schema_version: str = "2.0.0"
    task_id: str
    batch_id: Optional[str] = None
    config: TaskConfig = Field(default_factory=TaskConfig)
    
    # Execution
    current_phase: str = "P"
    current_step_id: Optional[str] = None
    steps_history: List[StepRecord] = Field(default_factory=list)
    external_needed: bool = False
    external_used: List[Dict[str, Any]] = Field(default_factory=list)
    skills_used: List[Dict[str, Any]] = Field(default_factory=list)
    execution_mode: str = "one-shot"
    trigger_reason: str = "user"

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
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # === Backward Compatibility Properties ===

    # TokenAccounting
    @property
    def total_token_usage(self) -> int:
        return self.tokens.total_usage

    @total_token_usage.setter
    def total_token_usage(self, v: int):
        self.tokens.total_usage = v

    @property
    def token_raw_model(self) -> int:
        return self.tokens.raw_model

    @token_raw_model.setter
    def token_raw_model(self, v: int):
        self.tokens.raw_model = v

    @property
    def token_fallback_est(self) -> int:
        return self.tokens.fallback_est

    @token_fallback_est.setter
    def token_fallback_est(self, v: int):
        self.tokens.fallback_est = v

    @property
    def token_system_overhead(self) -> int:
        return self.tokens.system_overhead

    @token_system_overhead.setter
    def token_system_overhead(self, v: int):
        self.tokens.system_overhead = v

    @property
    def token_capture_status(self) -> str:
        return self.tokens.capture_status

    @token_capture_status.setter
    def token_capture_status(self, v: str):
        self.tokens.capture_status = v

    @property
    def phase_tokens(self) -> Dict[str, int]:
        return self.tokens.phase_tokens

    @phase_tokens.setter
    def phase_tokens(self, v: Dict[str, int]):
        self.tokens.phase_tokens = v

    # ObservabilityContext
    @property
    def trace_id(self) -> str:
        return self.observability.trace_id

    @trace_id.setter
    def trace_id(self, v: str):
        self.observability.trace_id = v

    @property
    def span_id(self) -> str:
        return self.observability.span_id

    @span_id.setter
    def span_id(self, v: str):
        self.observability.span_id = v

    @property
    def auto_actions(self) -> List[Dict[str, Any]]:
        return self.observability.auto_actions

    @auto_actions.setter
    def auto_actions(self, v: List[Dict[str, Any]]):
        self.observability.auto_actions = v

    # AuditCounters
    @property
    def audit_pass_count(self) -> int:
        return self.audit.audit_pass_count

    @audit_pass_count.setter
    def audit_pass_count(self, v: int):
        self.audit.audit_pass_count = v

    @property
    def retry_count(self) -> int:
        return self.audit.retry_count

    @retry_count.setter
    def retry_count(self, v: int):
        self.audit.retry_count = v

    @property
    def turn_count(self) -> int:
        return self.audit.turn_count

    @turn_count.setter
    def turn_count(self, v: int):
        self.audit.turn_count = v

    @property
    def clarification_count(self) -> int:
        return self.audit.clarification_count

    @clarification_count.setter
    def clarification_count(self, v: int):
        self.audit.clarification_count = v

    @property
    def correction_count(self) -> int:
        return self.audit.correction_count

    @correction_count.setter
    def correction_count(self, v: int):
        self.audit.correction_count = v

    @property
    def unresolved_count(self) -> int:
        return self.audit.unresolved_count

    @unresolved_count.setter
    def unresolved_count(self, v: int):
        self.audit.unresolved_count = v

    # PhaseHealthSnapshot
    @property
    def health_score(self) -> float:
        return self.phase_health.health_score

    @health_score.setter
    def health_score(self, v: float):
        self.phase_health.health_score = v

    @property
    def health_metrics(self) -> HealthMetrics:
        return self.phase_health.health_metrics

    @health_metrics.setter
    def health_metrics(self, v: HealthMetrics):
        self.phase_health.health_metrics = v

    @property
    def pipeline_health(self) -> float:
        return self.phase_health.pipeline_health

    @pipeline_health.setter
    def pipeline_health(self, v: float):
        self.phase_health.pipeline_health = v

    @property
    def learning_velocity(self) -> float:
        return self.phase_health.learning_velocity

    @learning_velocity.setter
    def learning_velocity(self, v: float):
        self.phase_health.learning_velocity = v

    @property
    def phase_metrics(self) -> Dict[str, PhaseMetric]:
        return self.phase_health.phase_metrics

    @phase_metrics.setter
    def phase_metrics(self, v: Dict[str, PhaseMetric]):
        self.phase_health.phase_metrics = v

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
        if not isinstance(data, dict):
            return data
            
        # mapping token fields
        tokens = data.get('tokens', {})
        if not isinstance(tokens, dict):
            tokens = tokens.model_dump() if hasattr(tokens, 'model_dump') else {}
        for legacy_key, new_key in [
            ('total_token_usage', 'total_usage'),
            ('token_raw_model', 'raw_model'),
            ('token_fallback_est', 'fallback_est'),
            ('token_system_overhead', 'system_overhead'),
            ('token_capture_status', 'capture_status'),
            ('phase_tokens', 'phase_tokens'),
        ]:
            if legacy_key in data:
                tokens[new_key] = data.pop(legacy_key)
        if tokens:
            data['tokens'] = tokens

        # mapping observability
        observability = data.get('observability', {})
        if not isinstance(observability, dict):
            observability = observability.model_dump() if hasattr(observability, 'model_dump') else {}
        for legacy_key, new_key in [
            ('trace_id', 'trace_id'),
            ('span_id', 'span_id'),
            ('auto_actions', 'auto_actions'),
        ]:
            if legacy_key in data:
                observability[new_key] = data.pop(legacy_key)
        if observability:
            data['observability'] = observability

        # mapping audit
        audit = data.get('audit', {})
        if not isinstance(audit, dict):
            audit = audit.model_dump() if hasattr(audit, 'model_dump') else {}
        for legacy_key, new_key in [
            ('audit_pass_count', 'audit_pass_count'),
            ('retry_count', 'retry_count'),
            ('turn_count', 'turn_count'),
            ('clarification_count', 'clarification_count'),
            ('correction_count', 'correction_count'),
            ('unresolved_count', 'unresolved_count'),
        ]:
            if legacy_key in data:
                audit[new_key] = data.pop(legacy_key)
        if audit:
            data['audit'] = audit

        # mapping phase_health
        phase_health = data.get('phase_health', {})
        if not isinstance(phase_health, dict):
            phase_health = phase_health.model_dump() if hasattr(phase_health, 'model_dump') else {}
        for legacy_key, new_key in [
            ('health_score', 'health_score'),
            ('health_metrics', 'health_metrics'),
            ('pipeline_health', 'pipeline_health'),
            ('learning_velocity', 'learning_velocity'),
            ('phase_metrics', 'phase_metrics'),
        ]:
            if legacy_key in data:
                phase_health[new_key] = data.pop(legacy_key)
        if phase_health:
            data['phase_health'] = phase_health

        return data

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
