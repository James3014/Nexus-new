import unittest
from unittest.mock import patch
from nexus.services.local_heal.local_armor_execution_profile import resolve_local_armor_profile, build_profile_controls

PROFILE_ORDER = {"LITE": 1, "STANDARD": 2, "FULL": 3}

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

    def test_force_full_is_resolved_by_production_profile_resolver(self):
        with patch.dict("os.environ", {"NEXUS_FORCE_FULL_ARMOR": "1"}, clear=False):
            profile = resolve_local_armor_profile({"signal_snapshot": {"routing_tier": "L1_green_lane"}})
        self.assertEqual(profile.profile, "FULL")
        self.assertEqual(profile.reason, "env_force_full_armor")
        self.assertFalse(profile.escalation_allowed)

    # Issue #579 regression tests
    def test_low_risk_fast_mode_resolves_to_lite(self):
        # A: Low risk + FAST_MODE -> LITE
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
                "reasoning_mode": "INTUITIVE",
                "task_desc": "Fix syntax typo in greet."
            }
        }
        with patch.dict("os.environ", {"NEXUS_FAST_MODE": "1"}, clear=False):
            profile = resolve_local_armor_profile(route_ctx)
        self.assertEqual(profile.profile, "LITE")
        self.assertEqual(profile.candidate_cap, 1)

    def test_medium_risk_fast_mode_cannot_drop_below_standard(self):
        # B: Medium risk + FAST_MODE -> STANDARD
        route_ctx = {
            "signal_snapshot": {
                "routing_tier": "L2_standard",
                "risk_score": 50,
                "confidence": 0.8,
                "cross_module": False,
                "hard_signal": False,
                "candidate_count": 1,
                "reasoning_mode": "INTUITIVE",
                "task_desc": "Fix medium calculation logic."
            }
        }
        with patch.dict("os.environ", {"NEXUS_FAST_MODE": "1"}, clear=False):
            profile = resolve_local_armor_profile(route_ctx)
        self.assertEqual(profile.profile, "STANDARD")
        self.assertTrue(profile.planning_llm_allowed)
        self.assertEqual(profile.semantic_retry_cap, 1)

    def test_high_risk_fast_mode_cannot_drop_below_full(self):
        # C: High risk (risk_score >= 85, hard_signal=True, stateful) + FAST_MODE -> FULL
        route_ctx = {
            "signal_snapshot": {
                "routing_tier": "L2_hardened",
                "risk_score": 85,
                "confidence": 0.6,
                "cross_module": True,
                "hard_signal": True,
                "candidate_count": 2,
                "reasoning_mode": "INTUITIVE",
                "task_desc": "Stateful database migration and recursive cache invalidation."
            }
        }
        with patch.dict("os.environ", {"NEXUS_FAST_MODE": "1"}, clear=False):
            profile = resolve_local_armor_profile(route_ctx)
        self.assertEqual(profile.profile, "FULL")
        self.assertTrue(profile.planning_llm_allowed)
        self.assertTrue(profile.spec_gen_allowed)
        self.assertEqual(profile.candidate_cap, 3)
        self.assertEqual(profile.semantic_retry_cap, 2)
        self.assertTrue(profile.ddtree_allowed)

    def test_missing_signals_fast_mode_fail_closed_to_standard(self):
        # D: Missing signals + FAST_MODE -> STANDARD fail-closed
        with patch.dict("os.environ", {"NEXUS_FAST_MODE": "1"}, clear=False):
            profile = resolve_local_armor_profile({})
        self.assertEqual(profile.profile, "STANDARD")
        self.assertEqual(profile.reason, "missing_planner_signals_fail_closed_to_standard")
        self.assertTrue(profile.planning_llm_allowed)

    def test_force_full_armor_precedence_over_fast_mode(self):
        # E: FORCE_FULL + FAST_MODE -> FULL (Force Full must not be lowered)
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
        with patch.dict("os.environ", {"NEXUS_FORCE_FULL_ARMOR": "1", "NEXUS_FAST_MODE": "1"}, clear=False):
            profile = resolve_local_armor_profile(route_ctx)
        self.assertEqual(profile.profile, "FULL")
        self.assertEqual(profile.reason, "env_force_full_armor")

    def test_profile_monotonicity_under_fast_mode(self):
        # Invariant: As risk level increases (low -> medium -> high),
        # profile rank LITE (1) <= STANDARD (2) <= FULL (3) must never decrease,
        # both with and without NEXUS_FAST_MODE.
        for fast_mode in ["0", "1"]:
            with patch.dict("os.environ", {"NEXUS_FAST_MODE": fast_mode}, clear=False):
                ranks = []
                # 1. Low risk fixture
                low_ctx = {
                    "locked_search": "def f(): pass",
                    "verifier_command": ["true"],
                    "signal_snapshot": {
                        "routing_tier": "L1_green_lane",
                        "risk_score": 10,
                        "confidence": 0.95,
                        "cross_module": False,
                        "hard_signal": False,
                        "candidate_count": 1,
                        "reasoning_mode": "FAST",
                        "task_desc": "simple fix"
                    }
                }
                ranks.append(PROFILE_ORDER[resolve_local_armor_profile(low_ctx).profile])

                # 2. Medium risk fixture
                med_ctx = {
                    "signal_snapshot": {
                        "routing_tier": "L2_standard",
                        "risk_score": 50,
                        "confidence": 0.85,
                        "cross_module": False,
                        "hard_signal": False,
                        "candidate_count": 1,
                        "reasoning_mode": "INTUITIVE",
                        "task_desc": "medium logic fix"
                    }
                }
                ranks.append(PROFILE_ORDER[resolve_local_armor_profile(med_ctx).profile])

                # 3. High risk fixture
                high_ctx = {
                    "signal_snapshot": {
                        "routing_tier": "L2_hardened",
                        "risk_score": 85,
                        "confidence": 0.60,
                        "cross_module": True,
                        "hard_signal": True,
                        "candidate_count": 2,
                        "reasoning_mode": "INTUITIVE",
                        "task_desc": "stateful migration"
                    }
                }
                ranks.append(PROFILE_ORDER[resolve_local_armor_profile(high_ctx).profile])

                # Verify monotonicity: ranks[0] <= ranks[1] <= ranks[2]
                self.assertLessEqual(ranks[0], ranks[1], f"Monotonicity violated low->med under fast_mode={fast_mode}: {ranks}")
                self.assertLessEqual(ranks[1], ranks[2], f"Monotonicity violated med->high under fast_mode={fast_mode}: {ranks}")

    def test_build_profile_controls_direct_invocation_not_overridden(self):
        # Direct calls to build_profile_controls must retain requested profile
        with patch.dict("os.environ", {"NEXUS_FAST_MODE": "1"}, clear=False):
            std_ctrl = build_profile_controls("STANDARD", "escalated_from_lite", "L1_green_lane")
            self.assertEqual(std_ctrl.profile, "STANDARD")
            self.assertEqual(std_ctrl.semantic_retry_cap, 1)

            full_ctrl = build_profile_controls("FULL", "escalated_to_full", "L2_hardened")
            self.assertEqual(full_ctrl.profile, "FULL")
            self.assertEqual(full_ctrl.candidate_cap, 3)

if __name__ == "__main__":
    unittest.main()
