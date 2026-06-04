import unittest
from nexus.optimize.route_oracle import RouteOracle
from nexus.optimize.capability_assembler import CapabilityAssembler
from nexus.optimize.optional_chain_rules import OptionalChainRules
from scripts.ops.lazy_executor_demo import LazyExecutor

class TestGovernanceScenarios(unittest.TestCase):
    """
    [NEXUS v2.5.1] Scenario Hardening Tests
    驗證全鏈路契約握手：Decision -> Assembly -> Lazy Execution
    """
    
    def test_scenario_baseline_0_model_call(self):
        """情境 1: 低風險路徑 (隱藏 Bug)"""
        # 1. 決策
        decision = RouteOracle.decide_route({"risk_score": 10})
        self.assertEqual(decision.flow, "baseline")
        
        # 2. 裝配
        chains = CapabilityAssembler.assemble_chains(decision.flow)
        self.assertEqual(len(chains.optional), 0)
        
        # 3. 執行 (模擬)
        executor = LazyExecutor(decision.flow, risk_score=10)
        executor.run_core_chain()
        self.assertIn("delivery_gate", executor.executed)

    def test_scenario_optional_escalation(self):
        """情境 2: 中風險路徑且證據不足 (Escalation)"""
        # 1. 決策
        decision = RouteOracle.decide_route({"risk_score": 55, "bare_sufficiency": "high"})
        self.assertEqual(decision.flow, "lite_supervised")
        
        # 2. 裝配
        chains = CapabilityAssembler.assemble_chains(decision.flow)
        
        # 3. 執行 (偵測到證據不足，追加 Optional)
        executor = LazyExecutor(decision.flow, risk_score=55)
        executor.run_core_chain()
        # 模擬證據密度不足
        triggered = executor.run_optional_if_needed({"evidence_density": 0.2})
        
        self.assertTrue(triggered)
        self.assertIn("codeintel", executor.executed)

if __name__ == "__main__":
    unittest.main()
