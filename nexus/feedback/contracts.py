from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal

@dataclass(frozen=True)
class VerifierSignal:
    """[NEXUS v26.7] 原始驗證器訊號"""
    verifier_name: str
    passed: bool
    score: float
    failure_tags: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class FailurePattern:
    """[NEXUS v26.7] 識別出的失敗模式"""
    pattern_code: str
    description: str
    severity: float # 0.0 to 1.0

@dataclass(frozen=True)
class FeedbackDirective:
    """[NEXUS v26.7] 回饋路由產出的指令"""
    identified_patterns: List[FailurePattern]
    retry_hints: List[str]
    is_actionable: bool
