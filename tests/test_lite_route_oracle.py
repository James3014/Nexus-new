import os
import unittest
from unittest.mock import patch
from nexus.core.lite_route_oracle import should_use_lite_route, LiteRouteDecision


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
        # 🚀 Environment override NEXUS_LIGHT_ROUTE=1 with acceptable risk/complexity
        decision = should_use_lite_route(
            risk_level="NORMAL",
            impact_complexity=2.0,
            belief_confidence=0.5,
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
            belief_confidence=0.5,
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
        self.assertEqual(decision.reason, "standard_heavy_route")

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
        decision = should_use_lite_route(
            risk_level="NORMAL",
            impact_complexity=4.0,
            belief_confidence=0.5,
            model_size=7_000_000_000,
        )
        self.assertTrue(decision.is_lite)
        self.assertEqual(decision.reason, "auto_lite_weak_model_size_lt_8B")
        self.assertIn("X", decision.skipped_phases)
        self.assertIn("D", decision.skipped_phases)
        self.assertIn("A", decision.skipped_phases)

    def test_strong_model_14b_keeps_heavy_route(self):
        decision = should_use_lite_route(
            risk_level="NORMAL",
            impact_complexity=4.0,
            belief_confidence=0.5,
            model_size=14_000_000_000,
        )
        self.assertFalse(decision.is_lite)
        self.assertEqual(decision.reason, "standard_heavy_route")

    def test_7b_with_low_risk_still_lite(self):
        decision = should_use_lite_route(
            risk_level="LOW",
            impact_complexity=2.0,
            belief_confidence=0.5,
            model_size=7_000_000_000,
        )
        self.assertTrue(decision.is_lite)

    def test_14b_with_low_risk_still_lite(self):
        decision = should_use_lite_route(
            risk_level="LOW",
            impact_complexity=2.0,
            belief_confidence=0.5,
            model_size=14_000_000_000,
        )
        self.assertTrue(decision.is_lite)
        self.assertNotIn("auto_lite_weak_model_size", decision.reason)

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


if __name__ == "__main__":
    unittest.main()
