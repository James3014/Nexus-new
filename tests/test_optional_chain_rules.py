import unittest
from nexus.optimize.optional_chain_rules import OptionalChainRules

class TestOptionalChainRules(unittest.TestCase):
    def test_rule_based_activation(self):
        """Task 4: 未命中 rule 不得啟用 heavy chain"""
        context = {"evidence_density": 0.8} # 證據充足
        rules = OptionalChainRules()
        upgrades = rules.evaluate_upgrades(context)
        self.assertNotIn("codeintel", upgrades)

    def test_rule_trigger_on_low_density(self):
        """Task 4: 證據不足觸發升級"""
        context = {"evidence_density": 0.2}
        rules = OptionalChainRules()
        upgrades = rules.evaluate_upgrades(context)
        self.assertIn("codeintel", upgrades)

if __name__ == "__main__":
    unittest.main()
