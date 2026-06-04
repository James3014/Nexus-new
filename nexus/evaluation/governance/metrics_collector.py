from dataclasses import dataclass, field
from typing import List, Dict, Any
from datetime import datetime

@dataclass(frozen=True)
class GateVerdict:
    """[NEXUS v27] 單一閘門執行結果"""
    gate_id: str
    status: str # PASS, FAIL, WARNING
    reason_code: str
    blockers: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class GovernanceMetricsReport:
    """[NEXUS v27] 治理指標彙總報告"""
    timestamp: str
    manifest_pass_rate: float
    promotion_success_rate: float
    seal_integrity_rate: float
    drift_incident_count: int
    mean_time_to_convergence_ms: float
    gate_verdicts: List[GateVerdict] = field(default_factory=list)

class GovernanceMonitor:
    """
    📊 Task: Governance Metrics Panel
    職責: 追蹤治理閘門健康度，並將結果結構化落盤。
    """
    def __init__(self):
        self.verdicts: List[GateVerdict] = []

    def record_verdict(self, verdict: GateVerdict):
        self.verdicts.append(verdict)

    def generate_report(self) -> GovernanceMetricsReport:
        # 在實際系統中，這會從資料庫或 Receipt 歷史中聚合
        total = len(self.verdicts)
        passed = len([v for v in self.verdicts if v.status == "PASS"])
        
        return GovernanceMetricsReport(
            timestamp=datetime.now().isoformat(),
            manifest_pass_rate=passed / total if total > 0 else 1.0,
            promotion_success_rate=0.92, # Mock
            seal_integrity_rate=1.0,      # Mock
            drift_incident_count=len([v for v in self.verdicts if "DRIFT" in v.reason_code]),
            mean_time_to_convergence_ms=45000.0,
            gate_verdicts=self.verdicts
        )
