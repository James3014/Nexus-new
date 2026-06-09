from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional

class ExecutionPhase(str, Enum):
    PROMPT_BUILD = "PROMPT_BUILD"
    MODEL_CALL = "MODEL_CALL"
    PATCH_PARSE = "PATCH_PARSE"
    TARGET_LOCATE = "TARGET_LOCATE"
    APPLY_EXECUTE = "APPLY_EXECUTE"
    VERIFY_LIGHT = "VERIFY_LIGHT"
    VERIFY_HEAVY = "VERIFY_HEAVY"
    RECEIPT_WRITE = "RECEIPT_WRITE"

@dataclass
class PhaseTiming:
    phase: ExecutionPhase
    wall_time_sec: float = 0.0
    cpu_time_sec: float = 0.0
    input_size_bytes: int = 0
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, TIMEOUT, FAILED

@dataclass
class ExecutionBudgetProfile:
    profile_name: str
    phase_budgets: Dict[ExecutionPhase, float]  # Phase -> Max Seconds
    total_budget_sec: float

@dataclass
class DeferredCheckSpec:
    check_id: str
    verifier_type: str
    payload_hash: str
    enqueued_at: float
