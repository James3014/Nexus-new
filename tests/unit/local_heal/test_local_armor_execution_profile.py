import unittest
from nexus.services.local_heal.local_armor_execution_profile import resolve_local_armor_profile, build_profile_controls

class TestLocalArmorExecutionProfile(unittest.TestCase):
    def test_lite_profile_resolution(self):
        # Meets all LITE requirements
        route_ctx = {
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(0)"],
            "signal_snapshot": {
                "routing_tier": "L1_green_lane",
                "risk_score": 10,
                "confidence": 0.9,
                "cross_module": False,
                "hard_signal": False,
                "candidate_count": 1,
                "reasoning_mode": "FAST",
                "task_desc": "Fix syntax typo in greet."
            }
        }
        profile = resolve_local_armor_profile(route_ctx)
        self.assertEqual(profile.profile, "LITE")
        self.assertFalse(profile.planning_llm_allowed)
        self.assertFalse(profile.spec_gen_allowed)
        self.assertEqual(profile.candidate_cap, 1)
        self.assertTrue(profile.escalation_allowed)

    def test_full_profile_resolution_due_to_recursion(self):
        # Meets LITE parameters but task has "recursion" -> FULL
        route_ctx = {
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(0)"],
            "signal_snapshot": {
                "routing_tier": "L1_green_lane",
                "risk_score": 10,
                "confidence": 0.9,
                "cross_module": False,
                "hard_signal": False,
                "candidate_count": 1,
                "reasoning_mode": "FAST",
                "task_desc": "Fix recursion bug in the tree function."
            }
        }
        profile = resolve_local_armor_profile(route_ctx)
        self.assertEqual(profile.profile, "FULL")
        self.assertTrue(profile.planning_llm_allowed)

    def test_full_profile_resolution_due_to_high_risk(self):
        route_ctx = {
            "signal_snapshot": {
                "routing_tier": "L2_hardened",
                "risk_score": 75,  # High risk -> FULL
                "confidence": 0.9,
                "cross_module": False,
                "hard_signal": False,
                "candidate_count": 1,
                "reasoning_mode": "INTUITIVE",
                "task_desc": "Fix simple bug."
            }
        }
        profile = resolve_local_armor_profile(route_ctx)
        self.assertEqual(profile.profile, "FULL")
        self.assertTrue(profile.planning_llm_allowed)
        self.assertTrue(profile.spec_gen_allowed)
        self.assertTrue(profile.ddtree_allowed)

    def test_missing_signals_fail_closed_to_standard(self):
        profile = resolve_local_armor_profile({})
        self.assertEqual(profile.profile, "STANDARD")
        self.assertTrue(profile.planning_llm_allowed)

if __name__ == "__main__":
    unittest.main()
