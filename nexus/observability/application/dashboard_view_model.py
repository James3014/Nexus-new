from dataclasses import dataclass, field
from typing import List, Dict, Any
from nexus.observability.domain.heatmap_builder import HeatmapMatrix

@dataclass(frozen=True)
class KPICard:
    title: str
    value: str
    status: str # HEALTHY, WARNING, CRITICAL

@dataclass(frozen=True)
class ReplayAuditRow:
    receipt_id: str
    original_verdict: str
    replay_verdict: str
    matched: bool

@dataclass(frozen=True)
class GovernanceDashboardViewModel:
    """
    🖥️ Task: Dashboard View Model (Application)
    職責: 將底層指標轉化為 UI 可直接消費的薄層模型 (Thin Model)。
    """
    version: str
    kpi_cards: List[KPICard]
    blocker_heatmap: HeatmapMatrix
    replay_audit_log: List[ReplayAuditRow]
    adr_freeze_status: str

class DashboardAssembler:
    @staticmethod
    def assemble(metrics_report: Any, heatmap: HeatmapMatrix, replay_logs: List[ReplayAuditRow]) -> GovernanceDashboardViewModel:
        
        # 建立高管視角 KPI 卡片
        kpi_cards = [
            KPICard("Pass Rate", f"{metrics_report.manifest_pass_rate*100:.1f}%", "HEALTHY" if metrics_report.manifest_pass_rate == 1.0 else "WARNING"),
            KPICard("Drift Incidents", str(metrics_report.drift_incident_count), "CRITICAL" if metrics_report.drift_incident_count > 0 else "HEALTHY")
        ]
        
        return GovernanceDashboardViewModel(
            version="v27.1",
            kpi_cards=kpi_cards,
            blocker_heatmap=heatmap,
            replay_audit_log=replay_logs,
            adr_freeze_status="HARD_FROZEN"
        )
