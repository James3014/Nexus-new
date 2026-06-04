import unittest
from nexus.problem.taxonomy import ProblemClass
from nexus.policy.policy_profile_engine import PolicyProfileEngine

class TestPolicyProfiles(unittest.TestCase):
    """
    🛡️ [v27.5 M4 TDD] 驗證政策設定檔的匹配邏輯。
    """
    
    def test_production_profile_constraints(self):
        profile = PolicyProfileEngine.get_profile(ProblemClass.PRODUCTION)
        self.assertEqual(profile.profile_name, "PROD_INCIDENT")
        self.assertTrue(profile.requires_two_person_review)
        self.assertFalse(profile.allow_canary)

    def test_debug_profile_is_readonly(self):
        profile = PolicyProfileEngine.get_profile(ProblemClass.DEBUG)
        self.assertTrue(profile.read_only)
        self.assertFalse(profile.requires_sandbox)

if __name__ == "__main__":
    unittest.main()
