import unittest
from nexus.problem.taxonomy import ProblemClass
from nexus.classification.problem_class_classifier import ProblemClassClassifier
from nexus.classification.domain_family_router import DomainFamilyRouter

class TestClassifierV275(unittest.TestCase):
    """
    🧭 [v27.5 M3 TDD] 驗證兩段式分類與路由的一致性。
    """
    
    def test_level1_classification(self):
        # 測試 Production
        self.assertEqual(
            ProblemClassClassifier.classify("Critical production outage"), 
            ProblemClass.PRODUCTION
        )
        # 測試 Debug
        self.assertEqual(
            ProblemClassClassifier.classify("Investigate root cause of memory leak"), 
            ProblemClass.DEBUG
        )

    def test_level2_routing(self):
        # 測試 Django Domain
        self.assertEqual(
            DomainFamilyRouter.route("Fix migrations for user model"),
            "django"
        )
        # 測試 Astropy Domain
        self.assertEqual(
            DomainFamilyRouter.route("Update FITS reader logic"),
            "astropy"
        )

if __name__ == "__main__":
    unittest.main()
