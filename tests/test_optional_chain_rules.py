import unittest
from nexus.optimize.optional_chain_rules import OptionalChainRules

class TestOptionalChainRules(unittest.TestCase):
    """
    [NEXUS v2.5] TDD Task 3: OptionalChainRules
    驗證：重型工具是否僅在 Rule 命中時才啟用。
    """
    def test_codeintel_rule_trigger(self):
        # 證據密度不足 (0.2) 時應觸發 codeintel
        context = {"evidence_density": 0.2, "risk_flag": False}
        upgrades = OptionalChainRules.evaluate_upgrades(context)
        self.assertIn("codeintel", upgrades)

    def test_no_upgrade_on_high_density(self):
        # 證據充足 (0.8) 時不應追加重工具
        context = {"evidence_density": 0.8, "risk_flag": False}
        upgrades = OptionalChainRules.evaluate_upgrades(context)
        self.assertNotIn("codeintel", upgrades)

if __name__ == "__main__":
    unittest.main()
