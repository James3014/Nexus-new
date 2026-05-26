from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from pathlib import Path

from nexus.core.capability_registry import CapabilityRegistry
from nexus.core.capability_signal_set import CapabilitySignalSet
from nexus.core.capability_constraints import CapabilityConstraints
from nexus.core.capability_selector import CapabilitySelector
from nexus.core.belief_contracts import CapabilityExecutionPlan


class TestCapabilitySelector(unittest.TestCase):
    """🛡️ High-fidelity Unit Tests covering the newly decoupled Autonomic Selector Core (P1-P5)."""

    def setUp(self) -> None:
        self.project_root = str(Path(__file__).resolve().parents[2])
        self.registry = CapabilityRegistry()
        self.selector = CapabilitySelector(self.registry)

    def test_registry_looks_up_canonical_capabilities(self) -> None:
        """Verify that all canonical capabilities are correctly registered and accessible."""
        caps = self.registry.list_all_capabilities()
        self.assertEqual(len(caps), 34)

        # Check autonomic_router
        info = self.registry.get_capability("autonomic_router")
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "autonomic_router")
        self.assertIn("P", info.phases)
        self.assertEqual(info.maturity, "ACTIVE")

        # Check a experimental/beta capability
        ui_val = self.registry.get_capability("ui_validator")
        self.assertIsNotNone(ui_val)
        self.assertEqual(ui_val.maturity, "BETA")

    def test_signal_set_from_context_parsing(self) -> None:
        """Verify unified input signals are parsed deterministically."""
        context = {
            "task_id": "task_abc_123",
            "task_desc": "Perform research on citation chain",
            "risk_level": "critical",
            "complexity": "4.2",
        }

        # Mock BeliefEngine
        mock_belief = MagicMock()
        mock_belief.get_confidence.return_value = 0.85

        signal_set = CapabilitySignalSet.from_context(
            context, self.project_root, belief_engine=mock_belief
        )

        self.assertEqual(signal_set.task_id, "task_abc_123")
        self.assertEqual(signal_set.risk_level, "CRITICAL")
        self.assertEqual(signal_set.impact_complexity, 4.2)
        self.assertEqual(signal_set.belief_confidence, 0.85)
        self.assertIn("citation", signal_set.task_desc.lower())

    def test_constraints_ethical_blocking(self) -> None:
        """Verify that MemPalace ethical blacklists block execution plans from generating."""
        signal_set = CapabilitySignalSet(
            task_id="ethical_fail",
            task_desc="attack server or leak data",
            risk_level="NORMAL",
            impact_complexity=1.0,
            belief_confidence=0.9,
            skills_triggered=[],
            tenant_id="tenant_x",
        )

        # Mock Palace showing ethical blockage
        mock_palace = MagicMock()
        mock_palace.verify_context.return_value = {"status": "BLOCKED", "reason": "ethical_leak"}
        mock_palace.get_skill_constraints.return_value = {"forbid": [], "require": [], "prefer": []}

        constraints = CapabilityConstraints(self.project_root, mem_palace=mock_palace)
        verdict = self.selector.select_capabilities(signal_set, constraints)

        self.assertIsInstance(verdict, dict)
        self.assertEqual(verdict.get("status"), "BLOCKED")
        self.assertIn("ETHICAL_BLOCK", verdict.get("reason", ""))

    def test_selector_adaptive_autoreason_on_low_confidence(self) -> None:
        """Verify selector dynamically schedules autoreason when belief confidence is low."""
        signal_set = CapabilitySignalSet(
            task_id="low_conf_task",
            task_desc="Regular coding task",
            risk_level="NORMAL",
            impact_complexity=1.5,
            belief_confidence=0.4,  # Under threshold 0.65!
            skills_triggered=[],
            tenant_id="tenant_y",
        )

        mock_palace = MagicMock()
        mock_palace.verify_context.return_value = {"status": "ALLOWED"}
        mock_palace.get_skill_constraints.return_value = {"forbid": [], "require": [], "prefer": []}

        constraints = CapabilityConstraints(self.project_root, mem_palace=mock_palace)
        plan = self.selector.select_capabilities(signal_set, constraints)

        self.assertIsInstance(plan, CapabilityExecutionPlan)
        self.assertIn("autoreason", plan.required_capabilities)
        self.assertIn("belief", plan.required_capabilities)

    def test_selector_schedules_hyper_and_swarm_on_critical_complexity(self) -> None:
        """Verify selector schedules Mode C Swarm & Hyper on CRITICAL risk/complexity."""
        signal_set = CapabilitySignalSet(
            task_id="complex_refactor",
            task_desc="Massive rewrite",
            risk_level="CRITICAL",
            impact_complexity=4.5,
            belief_confidence=0.9,
            skills_triggered=[],
            tenant_id="tenant_z",
        )

        mock_palace = MagicMock()
        mock_palace.verify_context.return_value = {"status": "ALLOWED"}
        mock_palace.get_skill_constraints.return_value = {"forbid": [], "require": [], "prefer": []}

        constraints = CapabilityConstraints(self.project_root, mem_palace=mock_palace)
        plan = self.selector.select_capabilities(signal_set, constraints)

        self.assertIsInstance(plan, CapabilityExecutionPlan)
        self.assertIn("hyper_sprint", plan.required_capabilities)
        self.assertIn("swarm_multi_agent", plan.required_capabilities)
        self.assertIn("ultra_review", plan.required_capabilities)
        self.assertNotIn("repair_loop", plan.required_capabilities)  # Decoupled / Replaced!


if __name__ == "__main__":
    unittest.main()
