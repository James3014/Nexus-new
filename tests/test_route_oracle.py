import unittest
from nexus.optimize.route_oracle import RouteOracle

class TestRouteOracle(unittest.TestCase):
    def test_low_risk_admission(self):
        """Task 1: risk=low 必走 lite"""
        res = RouteOracle.decide_route({"risk_score": 20, "bare_sufficiency": "high"})
        self.assertEqual(res["flow"], "baseline")
        self.assertTrue(res["lite_preferred"])

    def test_medium_risk_calibration(self):
        """Task 1: risk 30-60 不得直接 full hypersprint"""
        res = RouteOracle.decide_route({"risk_score": 45, "bare_sufficiency": "high"})
        self.assertEqual(res["flow"], "lite_supervised")

if __name__ == "__main__":
    unittest.main()
