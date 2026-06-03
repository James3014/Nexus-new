from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class EvaluationReport:
    """[NEXUS v26.7] 評測車道報告契約"""
    lane_id: str # baseline_lane / challenge_lane
    success_rate: float
    abstain_rate: float
    ece: float
    oracle_gap_recovery: float
    task_count: int
