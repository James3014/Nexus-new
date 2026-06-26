import uuid

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, model_validator
from .state_legacy import NexusStateLegacyMixin
from datetime import datetime
from enum import Enum
from nexus.core.pipeline_metadata import PipelineMetadata
from .state_models import (
    HealthMetrics, PhaseMetric, TokenAccounting, 
    ObservabilityContext, AuditCounters, PhaseHealthSnapshot
)

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

# --- D 階段: Diagnosis ---

class DiagnosisViolation(BaseModel):
    file: str
    line: int
    severity: str  # CRITICAL, ADVICE
    reason: str
    suggestion: Optional[str] = None

class NexusDiagnosis(BaseModel):
    reasoning_mode: str = "INTUITIVE"
    violated_invariants: List[str] = []
    failed_proof_obligations: List[str] = []
    counterexamples: List[str] = []
    derivation_ref: Optional[str] = None
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

# --- E 階段: Evidence & Derivation (v26 Algebraic Reasoning) ---

class DerivationStep(BaseModel):
    step_index: int
    operation: str # e.g., Rewrite, Compose, Fold
    rationale: str
    law_id: Optional[str] = None
    input_state: Optional[str] = None
    output_state: Optional[str] = None

class NexusDerivation(BaseModel):
    task_id: str
    goal: str
    reasoning_mode: str = "FORMAL"
    invariants: List[str] = []
    proof_obligations: List[str] = []
    steps: List[DerivationStep] = []
    final_equivalence_proven: bool = False
    metadata: Dict[str, Any] = {}

# --- A 階段: Audit ---

class NexusRepair(BaseModel):
    task_id: str
    reasoning_mode: str = "INTUITIVE"
    rewrite_trace: List[str] = []
    resolved_invariants: List[str] = []
    resolved_proof_obligations: List[str] = []
    equivalence_claim: Optional[str] = None
    risk_delta: float = 0.0
    derivation_ref: Optional[str] = None
    patch_hash: str

class AuditResult(BaseModel):
    reasoning_mode: str = "INTUITIVE"
    formal_gate_passed: bool = False
    obligation_coverage_pct: float = 0.0
    audit_notes_formal: List[str] = []
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
    metadata: Dict[str, Any] = Field(default_factory=dict) # 支援自省等靈活擴展
    summary: Optional[str] = None

class NexusManifest(BaseModel):
    task_id: str
    formal_reasoning: Dict[str, Any] = Field(default_factory=dict) # gate_passed, coverage
    seal_status: str = "OPEN" # OPEN, SEALED, FAILED
    artifact_hashes: Dict[str, str] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

# --- H 階段: Health & Self-Check (CHK-001) ---

# --- T 階段: Trinity & Learning ---

class TraumaRecord(BaseModel):
    failure_signature: str
    penalty: float = -0.5
    expiry: Optional[datetime] = None

class NexusWeights(BaseModel):
    skill_weights: Dict[str, float] = Field(default_factory=lambda: {"generalist": 1.0})
    trauma_records: List[TraumaRecord] = Field(default_factory=list)

class NexusState(BaseModel, NexusStateLegacyMixin):
    # Legacy Root Fields (Consolidated)
    version: str = "v26.1"
    aos_score: float = 131.5
    active_shards: Dict[str, str] = Field(default_factory=dict)
    last_audit: Optional[Dict[str, Any]] = None
    soul_alignment: bool = True

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
    derivation: Optional[NexusDerivation] = None

    # Legacy (保持)
    superpowers_plan: Dict[str, Any] = Field(default_factory=dict)
    tdd_status: TddStatus = TddStatus.NONE
    subagents_active: bool = False
    autonomic_weights: NexusWeights = Field(default_factory=NexusWeights)
    policy_hit_ids: List[str] = Field(default_factory=list)
    policy_applied: bool = False
    metadata: PipelineMetadata = Field(default_factory=PipelineMetadata)
    
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
        
        conversation = self.metadata.get("conversation")
        if conversation:
            conversation.update(updates)

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
