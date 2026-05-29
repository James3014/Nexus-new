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


if __name__ == "__main__":
    unittest.main()
