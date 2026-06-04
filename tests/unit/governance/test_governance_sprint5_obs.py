import unittest
from nexus.governance.application.observability_aggregator import ObservabilityAggregator, ADRDiffGate
from nexus.governance.domain.blocker_taxonomy import BlockerCode

class TestSprint5Observability(unittest.TestCase):
    """[v27.1 Sprint 5] Observability & Freeze TDD"""

    def test_heatmap_aggregates_blocker_density(self):
        """[P1] 驗證：熱圖是否正確統計 Blocker 密度"""
        raw = [BlockerCode.DRIFT_DETECTED, BlockerCode.DRIFT_DETECTED, BlockerCode.EVIDENCE_MISSING]
        cells = ObservabilityAggregator.generate_heatmap(raw)
        
        drift_cell = [c for c in cells if c.blocker_code == BlockerCode.DRIFT_DETECTED][0]
        self.assertEqual(drift_cell.occurrence_count, 2)

    def test_adr_diff_gate_blocks_unapproved_change(self):
        """[P1] 驗證：ADR 雜湊不匹配時應阻斷"""
        self.assertFalse(ADRDiffGate.verify_no_unauthorized_changes("new-schema", "old-adr"))
        self.assertTrue(ADRDiffGate.verify_no_unauthorized_changes("matched", "matched"))

    def test_trend_line_mapping(self):
        """[P1] 驗證：趨勢點映射邏輯"""
        history = [{"t": "2026-06-03", "v": 0.94}]
        trends = ObservabilityAggregator.aggregate_trends(history)
        self.assertEqual(trends[0].value, 0.94)

if __name__ == "__main__":
    unittest.main()
