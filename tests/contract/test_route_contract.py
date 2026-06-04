import unittest
from nexus.optimize.route_oracle import RouteOracle
from nexus.optimize.contracts import RouteDecision

class TestRouteContract(unittest.TestCase):
    """
    [NEXUS v2.5.1] Contract Test: Route Oracle
    驗證介面穩定性，防止欄位漂移。
    """
    def test_oracle_published_interface(self):
        res = RouteOracle.decide_route({"risk_score": 10})
        # 驗證返回型別為 DTO 而非 dict
        self.assertIsInstance(res, RouteDecision)
        # 驗證必要欄位存在性 (由編譯器或靜態檢查，此處為運行時驗證)
        self.assertTrue(hasattr(res, "version"))
        self.assertEqual(res.version, "1.0")

if __name__ == "__main__":
    unittest.main()
