import unittest
import os
from nexus.governance.domain.blocker_taxonomy import BlockerCode
from nexus.observability.domain.heatmap_builder import HeatmapSeriesBuilder
from nexus.observability.application.dashboard_view_model import DashboardAssembler, ReplayAuditRow
from nexus.evaluation.governance.metrics_collector import GovernanceMetricsReport
from nexus.observability.application.canary_view_model import CanaryPanelAssembler
from nexus.rollout.canary_guard import CanaryGuard

class TestSprint5Dashboard(unittest.TestCase):
    """
    🖥️ [v27.1 Sprint 5] Observability Dashboard TDD
    驗證熱圖聚合、View Model 轉換與 Canary 面板一致性。
    """

    def test_heatmap_aggregates_blocker_density(self):
        events = [
            {"time": "2026-06-03", "blocker": BlockerCode.DRIFT_DETECTED},
            {"time": "2026-06-03", "blocker": BlockerCode.DRIFT_DETECTED},
            {"time": "2026-06-03", "blocker": BlockerCode.SCHEMA_MISMATCH},
            {"time": "2026-06-04", "blocker": BlockerCode.DRIFT_DETECTED}
        ]
        matrix = HeatmapSeriesBuilder.build_matrix(events)
        point = next(p for p in matrix.data_points if p["x"] == "2026-06-03" and p["y"] == "DRIFT_DETECTED")
        self.assertEqual(point["value"], 2)
        
    def test_dashboard_view_model_assembly(self):
        metrics = GovernanceMetricsReport(
            timestamp="now", manifest_pass_rate=1.0, promotion_success_rate=1.0,
            seal_integrity_rate=1.0, drift_incident_count=0, mean_time_to_convergence_ms=100
        )
        heatmap = HeatmapSeriesBuilder.build_matrix([])
        replay_logs = [ReplayAuditRow("r1", "APPROVED", "APPROVED", True)]
        vm = DashboardAssembler.assemble(metrics, heatmap, replay_logs)
        pass_rate_card = next(c for c in vm.kpi_cards if c.title == "Pass Rate")
        self.assertEqual(pass_rate_card.status, "HEALTHY")

    def test_canary_panel_shows_mode_and_rollout(self):
        """[Canary P1] 驗證：狀態能正確映射為 OBSERVATION"""
        os.environ["NEXUS_GOVERNANCE_MODE"] = "OBSERVATION"
        guard = CanaryGuard()
        vm = CanaryPanelAssembler.assemble(guard, rollout_fraction=0.0)
        self.assertEqual(vm.mode, "OBSERVATION")
        self.assertEqual(vm.rollout_percent, "0.0%")
        
    def test_canary_panel_shows_latest_blocker(self):
        """[Canary P1] 驗證：重大 Blocker 會讓 Canary 面板亮紅燈"""
        if "NEXUS_GOVERNANCE_MODE" in os.environ:
            del os.environ["NEXUS_GOVERNANCE_MODE"]
            
        guard = CanaryGuard()
        vm = CanaryPanelAssembler.assemble(guard, rollout_fraction=0.1, recent_blocker_code=BlockerCode.BASELINE_REGRESSION)
        self.assertEqual(vm.mode, "CANARY")
        self.assertEqual(vm.latest_blocker, "BASELINE_REGRESSION")
        self.assertEqual(vm.health_status, "CRITICAL")

if __name__ == "__main__":
    unittest.main()
