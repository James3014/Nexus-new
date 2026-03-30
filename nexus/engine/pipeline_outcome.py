from enum import IntEnum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

class PipelineTerminalState(IntEnum):
    """四態終止語義 + Exit Code 正式映射表"""
    SUCCESS      = 0   # 全部通過
    FAILED       = 1   # 修復失敗，但無需人工
    ESCALATED    = 2   # 需要 Coordinator 重新規劃
    HUMAN_REVIEW = 3   # 需要人工介入，不可自動重試

@dataclass
class HumanReviewHandoff:
    """HUMAN_REVIEW Handoff Bundle Schema"""
    escalation_count: int = 0
    last_root_cause: str = ""
    rejection_history: List[Dict[str, Any]] = field(default_factory=list)
    sandbox_mode: str = "unknown"
    pregate_skip_reason: str = ""
    task_id: str = ""
    trace_id: str = ""
    terminal_state: str = "HUMAN_REVIEW"

@dataclass
class PipelineOutcome:
    """統一 Pipeline 輸出物件，取代散落在 metadata 中的欄位"""
    terminal_state: PipelineTerminalState
    exit_code: int
    task_id: str = ""
    trace_id: str = ""
    handoff: Optional[HumanReviewHandoff] = None
    cycle_root_cause: str = ""
    verification_exit_codes: List[int] = field(default_factory=list)
    sandbox_mode: str = "unknown"
    pregate_skip: bool = False
