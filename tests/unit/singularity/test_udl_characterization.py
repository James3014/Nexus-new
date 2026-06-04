import unittest
from nexus.governance.udl_engine import UDLEngine

class TestUDLCharacterization(unittest.TestCase):
    """
    ✨ Task 1.1: UDL Characterization Tests
    驗證歷史趨勢與閾值的邊界行為，確保非正式報告字眼誤導治理。
    """

    def test_history_trend_boundaries(self):
        # IMPROVING
        h = UDLEngine.calculate_health(1.0, 1.0, True, True, history=[0.8, 0.9])
        self.assertEqual(h.trend, 'IMPROVING')
        
        # STABLE
        h = UDLEngine.calculate_health(0.9, 0.9, True, True, history=[0.88, 0.91])
        self.assertEqual(h.trend, 'STABLE')
        
        # DECLINING
        h = UDLEngine.calculate_health(0.7, 0.7, True, True, history=[0.8, 0.85])
        self.assertEqual(h.trend, 'DECLINING')

    def test_threshold_boundaries(self):
        # CRITICAL boundary: 0.5
        h = UDLEngine.calculate_health(0.0, 0.0, True, True) # 0.2 + 0.1 = 0.3
        self.assertEqual(h.status, 'CRITICAL')
        
        # 剛好通過 0.5 的測試：(0.5*0.4)+(0.5*0.3)+0.2+0.1 = 0.2+0.15+0.2+0.1 = 0.65 (DEGRADED)
        h = UDLEngine.calculate_health(0.5, 0.5, True, True)
        self.assertEqual(h.status, 'DEGRADED')

        # STABLE boundary: 0.8
        h = UDLEngine.calculate_health(0.8, 0.8, True, True) # 0.32 + 0.24 + 0.2 + 0.1 = 0.86
        self.assertEqual(h.status, 'STABLE')

    def test_malformed_metrics_clamping(self):
        """Green: 驗證指標 Clamping (Fail-Safe)"""
        # 1.5 會被 clamp 回 1.0, -0.5 會被 clamp 回 0.0
        # (1.0*0.4) + (0.0*0.3) + 0.2 + 0.1 = 0.7
        h = UDLEngine.calculate_health(1.5, -0.5, True, True)
        self.assertEqual(h.score, 0.7)
        self.assertEqual(h.status, 'DEGRADED')

if __name__ == "__main__":
    unittest.main()
