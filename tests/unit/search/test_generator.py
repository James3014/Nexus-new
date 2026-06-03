import unittest
from nexus.search.generator import ProposalGenerator

class TestProposalGenerator(unittest.TestCase):
    def test_generate_k_candidates(self):
        """[T1.1] 驗證：能產生指定數量的候選者"""
        gen = ProposalGenerator()
        candidates = gen.generate_candidates("task-1", k=3, model="7B")
        self.assertEqual(len(candidates), 3)
        self.assertTrue(all("candidate_id" in c for c in candidates))

if __name__ == "__main__":
    unittest.main()
