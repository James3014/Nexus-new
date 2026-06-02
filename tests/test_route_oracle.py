import unittest
from nexus.optimize.route_oracle import RouteOracle

class TestRouteOracle(unittest.TestCase):
    """
    [NEXUS v2.5] TDD Task 1: RouteOracle
    驗證：決策邏輯是否與能力裝配分離，且能精準處理 30-60 分流。
    """
    def test_low_risk_lite_route(self):
        # risk < 30 應走 baseline + lite
        res = RouteOracle.decide_route(risk_score=25, bare_sufficiency="high")
        self.assertEqual(res["flow"], "baseline")
        self.assertTrue(res["lite_preferred"])

    def test_medium_risk_admission_calibration(self):
        # 30 <= risk <= 60 且信心高時，降級至 lite_supervised 而非 full hyper
        res = RouteOracle.decide_route(risk_score=55, bare_sufficiency="high")
        self.assertEqual(res["flow"], "lite_supervised")
        self.assertTrue(res["lite_preferred"])

    def test_high_risk_forced_hyper(self):
        # risk > 60 應強制 hyper
        res = RouteOracle.decide_route(risk_score=75, bare_sufficiency="low")
        self.assertEqual(res["flow"], "hyper_sprint")
        self.assertFalse(res["lite_preferred"])

if __name__ == "__main__":
    unittest.main()
