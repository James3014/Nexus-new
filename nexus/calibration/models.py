from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class CalibrationInput:
    """[NEXUS v26.6] 校準系統輸入"""
    raw_confidence: float
    verifier_scores: Dict[str, float]
    gap: float
    task_difficulty: str = "medium"

@dataclass(frozen=True)
class ReliabilitySlice:
    """[NEXUS v26.6] 可信度分桶"""
    bin_index: int
    mean_confidence: float
    observed_accuracy: float
    sample_count: int
