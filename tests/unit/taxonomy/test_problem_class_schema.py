import unittest
from nexus.problem.taxonomy import ProblemClass, Severity

class TestProblemTaxonomy(unittest.TestCase):
    """
    🧬 [v27.5 M1 TDD] 驗證核心治理維度的正確性。
    """
    def test_problem_classes_exist(self):
        classes = [c.name for c in ProblemClass]
        expected = ["PRODUCTION", "DEBUG", "REVIEW", "CHANGE", "PERFORMANCE", "GOVERNANCE"]
        for e in expected:
            self.assertIn(e, classes)

    def test_severity_levels(self):
        levels = [s.name for s in Severity]
        self.assertEqual(len(levels), 4)
        self.assertIn("CRITICAL", levels)

if __name__ == "__main__":
    unittest.main()
