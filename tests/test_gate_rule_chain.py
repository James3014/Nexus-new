import unittest
from unittest.mock import MagicMock

from nexus.core.gate_evaluator import (
    GateEvaluator,
    GateRuleResult,
    GateChainResult,
    AbstractGateRule,
)
from nexus.core.gate_rules_builtin import (
    CostRatioRule,
    DenominatorRule,
    BlockerCleanRule,
)


class DummyRule(AbstractGateRule):
    def __init__(self, name: str, passed: bool, reason: str = ""):
        self.name = name
        self.passed = passed
        self.reason = reason
        self.evaluated = False

    def evaluate(self, context: dict) -> GateRuleResult:
        self.evaluated = True
        return GateRuleResult(
            passed=self.passed,
            reason_code=self.name,
            reason=self.reason,
            evidence_refs=[f"ref_{self.name}"]
        )


class TestGateRuleChain(unittest.TestCase):
    def test_gate_chain_all_pass(self):
        evaluator = GateEvaluator()
        rule1 = DummyRule("rule1", passed=True)
        rule2 = DummyRule("rule2", passed=True)
        
        rules = [rule1, rule2]
        result = evaluator.evaluate_rule_chain(rules, {})
        
        self.assertEqual(result.verdict, "GREEN")
        self.assertTrue(rule1.evaluated)
        self.assertTrue(rule2.evaluated)
        self.assertIn("ref_rule1", result.evidence_refs)
        self.assertIn("ref_rule2", result.evidence_refs)

    def test_gate_chain_short_circuit_on_failure(self):
        evaluator = GateEvaluator()
        rule1 = DummyRule("rule1", passed=True)
        rule2 = DummyRule("rule2", passed=False, reason="Rule 2 failed")
        rule3 = DummyRule("rule3", passed=True)
        
        rules = [rule1, rule2, rule3]
        result = evaluator.evaluate_rule_chain(rules, {})
        
        self.assertEqual(result.verdict, "RED")
        self.assertEqual(result.failed_rule, "rule2")
        self.assertEqual(result.reason, "Rule 2 failed")
        self.assertTrue(rule1.evaluated)
        self.assertTrue(rule2.evaluated)
        self.assertFalse(rule3.evaluated)  # Should short-circuit and not run rule3

    def test_cost_ratio_rule(self):
        rule = CostRatioRule(max_ratio=1.2)
        
        # Passes when cost ratio is within bounds
        res_pass = rule.evaluate({"token_cost_ratio": 1.0})
        self.assertTrue(res_pass.passed)
        
        # Fails when cost ratio exceeds bounds
        res_fail = rule.evaluate({"token_cost_ratio": 1.5})
        self.assertFalse(res_fail.passed)
        self.assertEqual(res_fail.reason_code, "COST_RATIO_EXCEEDED")

    def test_denominator_rule(self):
        rule = DenominatorRule(min_chunks=100)
        
        # Passes when chunks count >= 100
        res_pass = rule.evaluate({"chunks_count": 150})
        self.assertTrue(res_pass.passed)
        
        # Fails when chunks count < 100
        res_fail = rule.evaluate({"chunks_count": 50})
        self.assertFalse(res_fail.passed)
        self.assertEqual(res_fail.reason_code, "DENOMINATOR_CONSERVATION_VIOLATION")

    def test_blocker_clean_rule(self):
        rule = BlockerCleanRule()
        
        # Passes when blockers list is empty/clean
        res_pass = rule.evaluate({"blockers": []})
        self.assertTrue(res_pass.passed)
        
        # Fails when active blockers exist
        res_fail = rule.evaluate({"blockers": ["CRITICAL_SEVERITY_BUG"]})
        self.assertFalse(res_fail.passed)
        self.assertEqual(res_fail.reason_code, "ACTIVE_BLOCKERS_PRESENT")


if __name__ == "__main__":
    unittest.main()
