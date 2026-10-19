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
        res = RouteOracle.decide_route({"risk_score": 55, "bare_sufficiency": "high", "task_type": "refactor"})
        self.assertEqual(res["flow"], "lite_supervised")
        self.assertTrue(res["lite_preferred"])

    def test_capability_pruning_logic(self):
        """驗證：能力鏈的兩段式拆分"""
        chain = CapabilityAssembler.assemble_chains(flow="hyper_sprint")
        self.assertIn("delivery_gate", chain["core"])
        self.assertNotIn("codeintel", chain["core"])
        self.assertNotIn("mempalace_gate", chain["core"])

    def test_cost_evidence_classification(self):
        """驗證：成本證據分類語義正確"""
        # 案例 1: 確定性救援
        profile = CostEvidencePolicy.classify_cost_evidence(
            {"model_calls": 0, "total_tokens": 0, "capability_count": 3}
        )
        self.assertEqual(profile.profile, "rescue_only_no_model_call")
        
        # 案例 2: 全鏈交付
        profile = CostEvidencePolicy.classify_cost_evidence(
            {"model_calls": 1, "total_tokens": 1000, "capability_count": 8}
        )
        self.assertEqual(profile.profile, "full_chain_delivery")

    def test_rule_driven_lazy_activation(self):
        """Retired behaviour (#1929): rule-driven lazy activation was removed.

        The id is kept for the impact gate; only assemble_chains(flow) remains.
        """
        self.assertFalse(hasattr(CapabilityAssembler, "assemble"))
        chain = CapabilityAssembler.assemble_chains("hyper_sprint")
        self.assertIn("codeintel", chain.optional)

    def test_risk_driven_lazy_activation(self):
        """Retired behaviour (#1929): risk-driven activation was removed.

        The id is kept for the impact gate; the optional chain depends on flow only.
        """
        self.assertFalse(hasattr(CapabilityAssembler, "assemble"))
        chain = CapabilityAssembler.assemble_chains("hyper_sprint")
        self.assertIn("mempalace_gate", chain.optional)
