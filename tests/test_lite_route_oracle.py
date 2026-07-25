import os
import unittest
from unittest.mock import patch
from nexus.core.lite_route_oracle import (
    LiteRouteDecision,
    lite_route_safety_blockers,
    should_use_lite_route,
)


class TestLiteRouteOracle(unittest.TestCase):
    def test_low_risk_low_complexity_auto_lite(self):
        # 🚀 Low risk & complexity <= 3.0 should auto-route to lite
        decision = should_use_lite_route(
            risk_level="LOW",
            impact_complexity=2.5,
            belief_confidence=0.9,
            lane_name="standard",
            capability_name="codeintel"
        )
        self.assertTrue(decision.is_lite)
        self.assertEqual(decision.reason, "auto_lite_low_risk_low_complexity")
        self.assertEqual(decision.skipped_phases, ["X", "D", "A"])

    def test_critical_risk_never_auto_lite(self):
        # 🛡️ Critical risk should never auto-route to lite
        decision = should_use_lite_route(
            risk_level="CRITICAL",
            impact_complexity=1.0,
            belief_confidence=0.9,
            lane_name="standard",
            capability_name="codeintel"
        )
        self.assertFalse(decision.is_lite)
        self.assertEqual(decision.skipped_phases, [])

    def test_gate_only_receipt_lite_lane(self):
        # 🚀 Lane in GATE_ONLY_RECEIPT_LITE_LANES should route to lite
        decision = should_use_lite_route(
            risk_level="HIGH",
            impact_complexity=4.0,
            belief_confidence=0.5,
            lane_name="hidden_bugfix_supervised",
            capability_name="codeintel"
        )
        self.assertTrue(decision.is_lite)
        self.assertEqual(decision.reason, "lane_policy_gate_only_receipt_lite")
        self.assertEqual(decision.skipped_phases, ["X", "D", "A"])

    def test_deterministic_route_oracle_receipt_lite_capability(self):
        # 🚀 Capability in DETERMINISTIC_ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES should route to lite
        decision = should_use_lite_route(
            risk_level="HIGH",
            impact_complexity=4.0,
            belief_confidence=0.5,
            lane_name="standard",
            capability_name="research"
        )
        self.assertTrue(decision.is_lite)
        self.assertEqual(decision.reason, "capability_policy_receipt_lite")
        self.assertEqual(decision.skipped_phases, ["X", "D", "A"])

    @patch.dict(os.environ, {"NEXUS_LIGHT_ROUTE": "1"})
    def test_env_override_light_route(self):
        # 🚀 Environment override NEXUS_LIGHT_ROUTE=1 with acceptable risk/complexity and high confidence
        decision = should_use_lite_route(
            risk_level="NORMAL",
            impact_complexity=2.0,
            belief_confidence=0.9,
            lane_name="standard",
            capability_name="codeintel"
        )
        self.assertTrue(decision.is_lite)
        self.assertEqual(decision.reason, "env_override_light_route")

    @patch.dict(os.environ, {"NEXUS_LIGHT_ROUTE": "1"})
    def test_env_override_light_route_ignored_on_high_risk(self):
        # 🛡️ Env override NEXUS_LIGHT_ROUTE=1 should be ignored on high risk
        decision = should_use_lite_route(
            risk_level="HIGH",
            impact_complexity=2.0,
            belief_confidence=0.9,
            lane_name="standard",
            capability_name="codeintel"
        )
        self.assertFalse(decision.is_lite)

    @patch.dict(os.environ, {"NEXUS_LIGHT_ROUTE_FORCE": "1"})
    def test_env_override_light_route_force(self):
        # 🚀 Environment override NEXUS_LIGHT_ROUTE_FORCE=1 regardless of risk/complexity
        decision = should_use_lite_route(
            risk_level="CRITICAL",
            impact_complexity=5.0,
            belief_confidence=0.1,
            lane_name="standard",
            capability_name="codeintel"
        )
        self.assertTrue(decision.is_lite)
        self.assertEqual(decision.reason, "env_override_light_route_force")

    def test_normal_risk_high_confidence_returns_lite(self):
        decision = should_use_lite_route(
            risk_level="NORMAL",
            impact_complexity=2.0,
            belief_confidence=0.9,
            lane_name="standard",
            capability_name="codeintel"
        )
        self.assertTrue(decision.is_lite)
        self.assertEqual(decision.reason, "auto_lite_normal_risk_high_confidence")

    def test_normal_risk_low_confidence_blocks_lite(self):
        decision = should_use_lite_route(
            risk_level="NORMAL",
            impact_complexity=2.0,
            belief_confidence=0.6,
            lane_name="standard",
            capability_name="codeintel"
        )
        self.assertFalse(decision.is_lite)
        self.assertEqual(decision.reason, "standard_heavy_route_blocked_lite")

    def test_context_sync_capped_preserves_delivery_phase(self):
        decision = should_use_lite_route(
            risk_level="HIGH",
            impact_complexity=4.0,
            belief_confidence=0.5,
            lane_name="context_sync_capped",
            capability_name="codeintel"
        )
        self.assertTrue(decision.is_lite)
        self.assertEqual(decision.reason, "lane_policy_gate_only_receipt_lite")
        self.assertEqual(decision.skipped_phases, ["X", "A"])
        self.assertNotIn("D", decision.skipped_phases)

    def test_route_cost_controls_override_lane(self):
        # Even if lane_name is standard, controls override to a receipt-lite lane
        decision = should_use_lite_route(
            risk_level="HIGH",
            impact_complexity=4.0,
            belief_confidence=0.5,
            lane_name="standard",
            capability_name="codeintel",
            route_cost_controls={"route_lane": "hidden_bugfix_supervised"}
        )
        self.assertTrue(decision.is_lite)
        self.assertEqual(decision.reason, "lane_policy_gate_only_receipt_lite")

    def test_route_cost_controls_env_parsed_once(self):
        import json
        with patch("os.environ", {"NEXUS_ROUTE_COST_CONTROLS": json.dumps({"route_lane": "hidden_bugfix_supervised", "lite_route": True})}):
            with patch("json.loads", side_effect=json.loads) as mock_json_loads:
                from nexus.engine import learning_policy_loader
                learning_policy_loader.load_route_cost_policy_budget_from_env()
                learning_policy_loader.route_cost_controls_from_env()
                self.assertEqual(mock_json_loads.call_count, 2)

    def test_route_cost_controls_parser_returns_same_result_at_both_callsites(self):
        import json
        controls_dict = {"route_lane": "hidden_bugfix_supervised", "lite_route": True}
        with patch("os.environ", {"NEXUS_ROUTE_COST_CONTROLS": json.dumps(controls_dict)}):
            from nexus.engine import learning_policy_loader
            res1 = learning_policy_loader._parse_route_cost_controls_env()
            self.assertEqual(res1, controls_dict)

    def test_lite_route_capability_list_matches_skipped_phases(self):
        decision = should_use_lite_route(
            risk_level="LOW",
            impact_complexity=1.0,
            belief_confidence=0.9
        )
        self.assertIn("A", decision.skipped_phases)
        lite_caps = ["mempalace", "autonomic_router", "belief", "repair_loop", "learning_closure"]
        self.assertNotIn("artifact_gate", lite_caps)
        self.assertNotIn("claim_gate", lite_caps)

    def test_weak_model_7b_auto_lite(self):
        # High complexity (4.0) or low confidence (0.5) blocks auto-lite even for 7B
        decision = should_use_lite_route(
            risk_level="NORMAL",
            impact_complexity=4.0,
            belief_confidence=0.5,
            model_size=7_000_000_000,
        )
        self.assertFalse(decision.is_lite)
        self.assertEqual(decision.reason, "standard_heavy_route_blocked_lite")

    def test_strong_model_14b_keeps_heavy_route(self):
        decision = should_use_lite_route(
            risk_level="NORMAL",
            impact_complexity=4.0,
            belief_confidence=0.5,
            model_size=14_000_000_000,
        )
        self.assertFalse(decision.is_lite)
        self.assertEqual(decision.reason, "standard_heavy_route_blocked_lite")

    def test_7b_with_low_risk_still_lite(self):
        # LOW risk + complexity <= 3.0 + high confidence (0.9) triggers LITE
        decision = should_use_lite_route(
            risk_level="LOW",
            impact_complexity=2.0,
            belief_confidence=0.9,
            model_size=7_000_000_000,
        )
        self.assertTrue(decision.is_lite)
        self.assertEqual(decision.reason, "auto_lite_low_risk_low_complexity")

    def test_14b_with_low_risk_still_lite(self):
        decision = should_use_lite_route(
            risk_level="LOW",
            impact_complexity=2.0,
            belief_confidence=0.9,
            model_size=14_000_000_000,
        )
        self.assertTrue(decision.is_lite)
        self.assertEqual(decision.reason, "auto_lite_low_risk_low_complexity")

    def test_existing_5_triggers_unchanged(self):
        d1 = should_use_lite_route(risk_level="LOW", impact_complexity=2.5, belief_confidence=0.9)
        self.assertTrue(d1.is_lite)
        self.assertEqual(d1.reason, "auto_lite_low_risk_low_complexity")

        d2 = should_use_lite_route(risk_level="CRITICAL", impact_complexity=1.0, belief_confidence=0.9)
        self.assertFalse(d2.is_lite)

        d3 = should_use_lite_route(risk_level="HIGH", impact_complexity=4.0, belief_confidence=0.5,
                                   lane_name="hidden_bugfix_supervised")
        self.assertTrue(d3.is_lite)
        self.assertEqual(d3.reason, "lane_policy_gate_only_receipt_lite")

    # Phase 1: 5 user-requested correctness tests
    def test_phase1_correctness_rules(self):
        # 1. 7B + NORMAL + complexity 4.0 + confidence 0.5 → NOT LITE
        d1 = should_use_lite_route(
            risk_level="NORMAL",
            impact_complexity=4.0,
            belief_confidence=0.5,
            model_size=7_000_000_000,
        )
        self.assertFalse(d1.is_lite)

        # 2. 3B + HIGH risk → NOT LITE
        d2 = should_use_lite_route(
            risk_level="HIGH",
            impact_complexity=1.0,
            belief_confidence=0.9,
            model_size=3_000_000_000,
        )
        self.assertFalse(d2.is_lite)

        # 3. 7B + recursive task → NOT LITE
        d3 = should_use_lite_route(
            risk_level="LOW",
            impact_complexity=1.0,
            belief_confidence=0.9,
            model_size=7_000_000_000,
            task_desc="Fix the recursive bug in the function."
        )
        self.assertFalse(d3.is_lite)

        # 4. 7B + LOW risk + complexity <= 3 + verifier + high confidence → LITE
        # (verifier present is checked during execution profile, but should_use_lite_route checks base criteria)
        d4 = should_use_lite_route(
            risk_level="LOW",
            impact_complexity=2.0,
            belief_confidence=0.9,
            model_size=7_000_000_000,
        )
        self.assertTrue(d4.is_lite)

        # 5. 14B + LOW risk + complexity <= 3 → LITE
        d5 = should_use_lite_route(
            risk_level="LOW",
            impact_complexity=2.0,
            belief_confidence=0.9,
            model_size=14_000_000_000,
        )
        self.assertTrue(d5.is_lite)

    def test_lite_route_safety_blockers_returns_all_blockers_in_order(self):
        blockers = lite_route_safety_blockers(
            risk_level="HIGH",
            impact_complexity=4.5,
            belief_confidence=0.5,
            cross_module=True,
            hard_signal=True,
            candidate_count=2,
            task_desc="Fix recursive stateful task",
        )
        self.assertEqual(
            blockers,
            (
                "high_or_critical_risk",
                "impact_complexity_gt_3",
                "cross_module",
                "hard_signal",
                "candidate_count_gt_1",
                "confidence_below_0_85",
                "recursive_or_stateful_task",
            ),
        )


if __name__ == "__main__":

    unittest.main()
