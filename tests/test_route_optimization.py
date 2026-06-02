import unittest
from nexus.optimize.route_oracle import RouteOracle
from nexus.optimize.capability_assembler import CapabilityAssembler
from nexus.optimize.cost_policy import CostEvidencePolicy
from nexus.engine.capability_contracts import FlowState

class TestRouteOptimization(unittest.TestCase):
    """
    [NEXUS v2.5] TDD: Route & Capability Chain Optimization
    驗證中風險路徑的分流與精簡邏輯。
    """
    
    def test_medium_risk_admission_calibration(self):
        """驗證：Risk 55 且信心高時，不再進入 full hyper"""
        res = RouteOracle.recommend_flow(risk_score=55, bare_sufficiency="high", task_type="refactor")
        self.assertEqual(res["flow"], "lite_supervised")
        self.assertTrue(res["lite"])

    def test_capability_pruning_logic(self):
        """驗證：能力鏈的兩段式拆分"""
        chain = CapabilityAssembler.assemble(flow="hyper_sprint", risk_score=55)
        self.assertIn("delivery_gate", chain["core"])
        self.assertNotIn("codeintel", chain["core"])
        self.assertNotIn("mempalace_gate", chain["core"])

    def test_cost_evidence_classification(self):
        """驗證：成本證據分類語義正確"""
        # 案例 1: 確定性救援
        profile = CostEvidencePolicy.classify_evidence(model_calls=0, total_tokens=0, capability_count=3)
        self.assertEqual(profile, "rescue_only_no_model_call")
        
        # 案例 2: 全鏈交付
        profile = CostEvidencePolicy.classify_evidence(model_calls=1, total_tokens=1000, capability_count=8)
        self.assertEqual(profile, "full_chain_delivery")

    def test_rule_driven_lazy_activation(self):
        """驗證：裝配器能根據 Rule 引擎正確追加能力"""
        # 模擬證據不足的場景
        context = {"evidence_density": 0.2, "risk_flag": False}
        chain = CapabilityAssembler.assemble(flow="hyper_sprint", risk_score=55, current_context=context)
        
        # 應追加 codeintel 但不應有 mempalace
        self.assertIn("codeintel", chain["optional"])
        self.assertNotIn("mempalace_gate", chain["optional"])

    def test_risk_driven_lazy_activation(self):
        """驗證：風險標籤觸發的升級"""
        context = {"evidence_density": 0.8, "risk_flag": True}
        chain = CapabilityAssembler.assemble(flow="hyper_sprint", risk_score=55, current_context=context)
        
        self.assertIn("mempalace_gate", chain["optional"])
