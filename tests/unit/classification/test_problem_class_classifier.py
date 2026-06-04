import unittest
from nexus.problem.taxonomy import ProblemClass
from nexus.classification.problem_class_classifier import ProblemClassClassifier

class TestProblemClassClassifier(unittest.TestCase):
    """
    🧭 [v27.5 M3 TDD]
    驗證 Classifier 能否基於特徵精準判定問題類別。
    """

    def test_detect_safety_problem(self):
        content = "Fix possible SQL injection in user search"
        p_class = ProblemClassClassifier.classify(content)
        # 修正: 檢查名稱而不是物件，避免 enum 實例不匹配
        self.assertEqual(p_class.name, "SAFETY")

    def test_detect_migration_problem(self):
        content = "Add db_table metadata to UserProfile migration"
        p_class = ProblemClassClassifier.classify(content)
        self.assertEqual(p_class.name, "MIGRATION")

if __name__ == "__main__":
    unittest.main()
