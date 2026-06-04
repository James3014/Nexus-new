from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from nexus.ci.verification_bundle import VerificationBundle
from nexus.evaluation.governance.metrics_collector import GovernanceMetricsReport

@dataclass(frozen=True)
class OperationalSealReport:
    """[NEXUS v27.1] 運營封板報告"""
    version: str = "v27.1"
    bundle: VerificationBundle = field(default=None)
    metrics: GovernanceMetricsReport = field(default=None)
    drift_diffs: List[Dict[str, Any]] = field(default_factory=list)
    replay_audit_status: str = "VERIFIED"
    sealed_at: str = field(default_factory=lambda: "2026-06-03T00:00:00Z")

class FinalizationReportBuilder:
    """
    📜 Task: Operation Sealing (Application)
    職責: 聚合所有治理收據與觀測指標，產出單一結案報告。
    """
    @staticmethod
    def build_seal_report(bundle: VerificationBundle, 
                         metrics: GovernanceMetricsReport) -> OperationalSealReport:
        return OperationalSealReport(
            bundle=bundle,
            metrics=metrics,
            replay_audit_status="VERIFIED" if metrics.seal_integrity_rate == 1.0 else "FAILED"
        )
