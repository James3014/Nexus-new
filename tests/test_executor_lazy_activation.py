import unittest
import time
from nexus.optimize.capability_assembler import CapabilityAssembler
from nexus.optimize.optional_chain_rules import OptionalChainRules

class LazyExecutor:
    """
    ⚡ Task 5: ExecutorLazyActivation
    職責: 實施二段式執行邏輯。
    """
    def __init__(self, flow):
        self.chains = CapabilityAssembler.assemble_chains(flow)
        self.rules = OptionalChainRules()
        self.executed = []

    def run_core(self):
        # 模擬核心鏈執行
        for cap in self.chains["core"]:
            self.executed.append(cap)
        return True

    def run_optional_if_needed(self, context):
        upgrades = self.rules.evaluate_upgrades(context)
        for cap in upgrades:
            if cap in self.chains["optional"]:
                self.executed.append(cap)
        return len(upgrades) > 0

class TestLazyActivation(unittest.TestCase):
    def test_lazy_skip_on_high_density(self):
        """驗證：高密度時自動跳過重型能力"""
        executor = LazyExecutor("hyper_sprint")
        executor.run_core()
        # 模擬證據充足
        triggered = executor.run_optional_if_needed({"evidence_density": 0.9})
        self.assertFalse(triggered)
        self.assertNotIn("codeintel", executor.executed)

    def test_lazy_trigger_on_low_density(self):
        """驗證：低密度時動態追加能力"""
        executor = LazyExecutor("hyper_sprint")
        executor.run_core()
        # 模擬證據不足
        triggered = executor.run_optional_if_needed({"evidence_density": 0.2})
        self.assertTrue(triggered)
        self.assertIn("codeintel", executor.executed)

if __name__ == "__main__":
    unittest.main()
