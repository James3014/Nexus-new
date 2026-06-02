import unittest
from nexus.optimize.route_oracle import RouteOracle, CapabilityAssembler

class TestRouteOptimization(unittest.TestCase):
    """
    [NEXUS v2.5] TDD: Route & Capability Chain Optimization
    驗證中風險路徑的分流與精簡邏輯。
    """
    
    def test_medium_risk_admission_calibration(self):
        """驗證：Risk 55 且信心高時，不再進入 full hyper"""
        # 舊版此處會回 hyper_sprint
        res = RouteOracle.recommend_flow(risk_score=55, bare_sufficiency="high", task_type="refactor")
        self.assertEqual(res["flow"], "lite_supervised")
        self.assertTrue(res["lite"])

    def test_cost_evidence_classification(self):
        """驗證：成本證據分類語義正確"""
        from nexus.optimize.cost_policy import CostEvidencePolicy
        
        # 案例 1: 確定性救援
        profile = CostEvidencePolicy.classify_evidence(model_calls=0, total_tokens=0, capability_count=3)
        self.assertEqual(profile, "rescue_only_no_model_call")
        
        # 案例 2: 全鏈交付
        profile = CostEvidencePolicy.classify_evidence(model_calls=1, total_tokens=1000, capability_count=8)
        self.assertEqual(profile, "full_chain_delivery")

    def test_lazy_activation_trigger(self):
        """驗證：延後啟用觸發邏輯"""
        from nexus.optimize.cost_policy import CostEvidencePolicy
        
        # 證據充足時不升級
        self.assertFalse(CostEvidencePolicy.should_upgrade_to_optional(0.8, False))
        # 證據不足時觸發升級
        self.assertTrue(CostEvidencePolicy.should_upgrade_to_optional(0.3, False))
