from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Any, Optional

class ProblemClass(Enum):
    """[v27.5] 問題本質分類 (SoC)"""
    CORRECTNESS = auto()    # 正確性/Bug
    SAFETY = auto()         # 安全性/注入
    COMPATIBILITY = auto() # 相容性/版本
    PERFORMANCE = auto()   # 性能
    MIGRATION = auto()     # 遷移/ORM
    OBSERVABILITY = auto() # 觀測性
    REFACTOR = auto()      # 重構/技術債

@dataclass(frozen=True)
class ProblemTicket:
    """
    🎟️ Task M1: Unified Problem Ticket (Problem Ingress)
    職責: 將所有外部 code problem 標準化為系統內部的唯一入口合約。
    消滅分散於各處的特例處理。
    """
    source: str
    task_id: str
    problem_class: ProblemClass
    domain_family: str
    risk_level: str
    repro_steps: List[str]
    acceptance_checks: List[str]
    rollbackability: bool
    evidence_refs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
