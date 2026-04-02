from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

# Schema Swell Prevention: Only approved top-level fields are allowed.
# If you need to add a field, add it here AND update OUTCOME_SCHEMA_VERSION.
OUTCOME_SCHEMA_VERSION = "v2.1"
_ALLOWED_FIELDS_V2 = {
    "outcome_version", "task_id", "trace_id", "span_id",
    "terminal_state", "exit_code",
    "sandbox_mode", "pregate_skip", "pregate_skip_reason",
    "trust_level", "escalation_count",
    "verification_commands", "verification_exit_codes",
    "cycle_root_cause", "rejection_history", "phantom_patterns",
    "commit_sha", "model_version", "timestamp",
    "benchmark_version", "problem_set_version",
}

class SchemaError(ValueError):
    """Raised when an unauthorized field is injected into NexusOutcomeV2."""

@dataclass
class NexusOutcomeV1:
    """Legacy V1 schema — forwards-only, do not add fields here."""
    task_id: str
    terminal_state: str
    exit_code: int
    commit_sha: str = "unknown"
    model_version: str = "unknown"
    timestamp: str = ""

@dataclass
class NexusOutcomeV2:
    """統一產出 Schema（Single Truth Object）v2.1"""
    # 版本標識
    outcome_version: str = OUTCOME_SCHEMA_VERSION
    
    # 識別
    task_id: str = ""
    trace_id: str = ""
    span_id: str = ""
    
    # 終止語義
    terminal_state: str = "UNKNOWN"  # SUCCESS / FAILED / ESCALATED / HUMAN_REVIEW
    exit_code: int = -1
    
    # 治理指標
    sandbox_mode: str = "unknown"
    pregate_skip: bool = False
    pregate_skip_reason: str = ""
    trust_level: str = "production"
    escalation_count: int = 0
    
    # 驗證證據
    verification_commands: List[str] = field(default_factory=list)
    verification_exit_codes: List[int] = field(default_factory=list)
    
    # 學習元數據
    cycle_root_cause: str = ""
    rejection_history: List[Any] = field(default_factory=list)
    phantom_patterns: List[str] = field(default_factory=list)
    
    # 環境指紋
    commit_sha: str = "unknown"
    model_version: str = "unknown"
    benchmark_version: str = "unknown"
    problem_set_version: str = "unknown"
    timestamp: str = ""

    def __post_init__(self) -> None:
        extra = set(self.__dict__) - _ALLOWED_FIELDS_V2
        if extra:
            raise SchemaError(
                f"NexusOutcomeV2 rejected unauthorized fields: {extra}. "
                f"Add to _ALLOWED_FIELDS_V2 and bump OUTCOME_SCHEMA_VERSION."
            )

    @staticmethod
    def upgrade_from_v1(v1: NexusOutcomeV1) -> "NexusOutcomeV2":
        """Up-convert a legacy V1 outcome to V2 with safe defaults."""
        return NexusOutcomeV2(
            task_id=v1.task_id,
            terminal_state=v1.terminal_state,
            exit_code=v1.exit_code,
            commit_sha=v1.commit_sha,
            model_version=v1.model_version,
            timestamp=v1.timestamp,
        )
