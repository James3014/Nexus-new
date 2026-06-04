from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal

@dataclass(frozen=True)
class EvaluationReport:
    """[NEXUS v26.7] 評測車道報告契約"""
    lane_id: str # baseline_lane / challenge_lane
    success_rate: float
    abstain_rate: float
    ece: float
    oracle_gap_recovery: float
    task_count: int

@dataclass(frozen=True)
class PromotionEvidence:
    """[NEXUS v27] 策略晉升證據包"""
    task_id: str
    challenge_recovery_gain: float   # 攻堅組的淨增益
    baseline_regression_loss: float # 穩定組的淨損失 (應為 0)
    receipt_id: str
    failure_family_reduction: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class PromotionReceipt:
    """[NEXUS v27] 晉升准許收據"""
    receipt_id: str
    status: Literal["APPROVED", "REJECTED"]
    total_gain: float
    total_loss: float
    evidence_hash: str
    verdict: str
    blockers: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: "2026-06-03T00:00:00Z")

@dataclass(frozen=True)
class SealedEvidence:
    """[NEXUS v27] 統一封印證據"""
    artifact_id: str
    manifest_hash: str
    test_results_summary: Dict[str, Any]
    promotion_receipt_id: Optional[str]
    regression_summary: Dict[str, float]
    telemetry_complete: bool
    is_claimable: bool # 是否符合公共發佈標準
