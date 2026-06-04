import unittest
from nexus.optimize.route_oracle import RouteOracle
from nexus.optimize.cost_policy import CostEvidencePolicy
from nexus.optimize.capability_assembler import CapabilityAssembler
from nexus.optimize.optional_chain_rules import OptionalChainRules

class TestGovernanceV25Boundary(unittest.TestCase):
    """
    [NEXUS v2.5] Boundary & Contract Tests
    驗證模組間的職責不重疊、不洩漏。
    """
    
    def test_oracle_cost_separation(self):
        """[Boundary] 驗證：RouteOracle 不應依賴 CostPolicy 的內部欄位"""
        # 契約：Oracle 只收 risk/sufficiency，不應處理 model_calls 這種執行期細節
        context = {"risk_score": 55, "bare_sufficiency": "high"}
        res = RouteOracle.decide_route(context)
        
        # 只要輸出符合 Flow 指令，Oracle 責任即完成
        self.assertIn("flow", res)
        self.assertNotIn("cost_evidence_class", res, "Oracle leaked into Cost domain!")

    def test_assembler_lazy_contract(self):
        """[Contract] 驗證：裝配器輸出的 Optional 鏈必須可被 Rule 引擎消費"""
        chains = CapabilityAssembler.assemble_chains("hyper_sprint")
        
        # 裝配器必須提供 optional 欄位，不論是否為空
        self.assertIn("optional", chains)
        self.assertTrue(isinstance(chains["optional"], list))

    def test_optional_rules_independence(self):
        """[SoC] 驗證：規則引擎不應知道 admission 分數線"""
        rules = OptionalChainRules()
        # 規則引擎只看密度與標籤，不應看 risk_score (那是 Oracle 的事)
        upgrades = rules.evaluate_upgrades({"evidence_density": 0.1})
        self.assertIn("codeintel", upgrades)

if __name__ == "__main__":
    unittest.main()
