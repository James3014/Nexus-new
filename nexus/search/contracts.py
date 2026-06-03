from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal

@dataclass(frozen=True)
class CandidateBatch:
    """[T2] 一次採樣批次的輸出契約"""
    task_id: str
    candidates: List[Any]
    diversity_score: float
    search_diagnostics: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class RetryDirective:
    """[T2] 重採樣指令契約"""
    should_retry: bool
    mode: Literal["EXPLORE", "EXPLOIT", "WAIT"]
    modified_params: Dict[str, Any]
