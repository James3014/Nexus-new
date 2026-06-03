from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass(frozen=True)
class ReliabilityBin:
    """[NEXUS v26.6] 可信度分桶數據"""
    bin_min: float
    bin_max: float
    avg_confidence: float
    accuracy: float
    sample_count: int

@dataclass(frozen=True)
class TemperatureFitResult:
    """[NEXUS v26.6] 溫度校準結果"""
    optimal_temperature: float
    ece_before: float
    ece_after: float
    nll_before: float
    nll_after: float
    bin_data: List[ReliabilityBin]
