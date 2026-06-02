import unittest
from nexus.optimize.capability_assembler import CapabilityAssembler

class TestCapabilityAssembler(unittest.TestCase):
    def test_core_vs_optional_separation(self):
        """Task 3: core/optional 分離，baseline 不含 heavy chain"""
        res = CapabilityAssembler.assemble_chains("baseline")
        self.assertIn("delivery_gate", res["core"])
        self.assertEqual(len(res["optional"]), 0)

    def test_hyper_assembly_pruning(self):
        """Task 3: capability list 單一出口"""
        res = CapabilityAssembler.assemble_chains("hyper_sprint")
        # 重型工具應被分配到 optional
        self.assertIn("codeintel", res["optional"])
        self.assertNotIn("codeintel", res["core"])

if __name__ == "__main__":
    unittest.main()
