import unittest
from nexus.optimize.capability_assembler import CapabilityAssembler

class TestCapabilityAssembler(unittest.TestCase):
    """
    [NEXUS v2.5] TDD Task 2: CapabilityAssembler
    驗證：裝配器是否能將能力鏈切分為 Core 與 Optional。
    """
    def test_baseline_assembly(self):
        # Baseline 應僅包含核心鏈
        res = CapabilityAssembler.assemble_chain(flow="baseline")
        self.assertIn("delivery_gate", res["core"])
        self.assertEqual(len(res["optional"]), 0)

    def test_hyper_assembly_pruning(self):
        # Hyper 候選狀態下，重型工具不應出現在 Core 鏈
        res = CapabilityAssembler.assemble_chain(flow="hyper_sprint")
        self.assertNotIn("codeintel", res["core"])
        self.assertNotIn("mempalace_gate", res["core"])

if __name__ == "__main__":
    unittest.main()
