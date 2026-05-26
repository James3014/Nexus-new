from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from pathlib import Path

from nexus.core.capability_registry import CapabilityRegistry
from nexus.core.capability_signal_set import CapabilitySignalSet
from nexus.core.capability_constraints import CapabilityConstraints
from nexus.core.capability_selector import CapabilitySelector
from nexus.core.executor_controls import ExecutorControls
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

    def test_selector_dynamic_skill_slots_allocation(self) -> None:
        """Verify HEEP Mode C Swarm multi-skill assembly and Mode A/B solo allocation."""
        # 1. Swarm Mode C critical allocation
        signal_set = CapabilitySignalSet(
            task_id="swarm_test",
            task_desc="Swarm test case",
            risk_level="CRITICAL",
            impact_complexity=4.0,
            belief_confidence=0.9,
            skills_triggered=[],
            tenant_id="tenant_s",
        )
        mock_palace = MagicMock()
        mock_palace.verify_context.return_value = {"status": "ALLOWED"}
        mock_palace.get_skill_constraints.return_value = {"forbid": [], "require": [], "prefer": []}
        constraints = CapabilityConstraints(self.project_root, mem_palace=mock_palace)
        
        plan = self.selector.select_capabilities(signal_set, constraints)
        self.assertIsInstance(plan, CapabilityExecutionPlan)
        
        # Verify Swarm Multi-Agent (Mode C) has 3 roles
        swarm_slots = plan.skill_slots.get("swarm_multi_agent")
        self.assertIsNotNone(swarm_slots)
        self.assertEqual(len(swarm_slots), 3)
        roles = [s.role for s in swarm_slots]
        self.assertIn("SCOUT", roles)
        self.assertIn("LOGIC", roles)
        self.assertIn("AUDIT", roles)
        
        # 2. Regular Mode B allocation (only LOGIC role)
        signal_set_regular = CapabilitySignalSet(
            task_id="regular_test",
            task_desc="Simple test case",
            risk_level="NORMAL",
            impact_complexity=1.0,
            belief_confidence=0.9,
            skills_triggered=[],
            tenant_id="tenant_s",
        )
        plan_regular = self.selector.select_capabilities(signal_set_regular, constraints)
        repair_slots = plan_regular.skill_slots.get("repair_loop")
        self.assertIsNotNone(repair_slots)
        self.assertEqual(len(repair_slots), 1)
        self.assertEqual(repair_slots[0].role, "LOGIC")

    def test_executor_controls_compiles_receipts(self) -> None:
        """Verify that ExecutorControls drives the execution plan and compiles all Receipts."""
        signal_set = CapabilitySignalSet(
            task_id="receipt_test",
            task_desc="Verify capability receipts in execution DAG",
            risk_level="NORMAL",
            impact_complexity=1.5,
            belief_confidence=0.8,
            skills_triggered=[],
            tenant_id="tenant_r",
        )
        mock_palace = MagicMock()
        mock_palace.verify_context.return_value = {"status": "ALLOWED"}
        mock_palace.get_skill_constraints.return_value = {"forbid": [], "require": [], "prefer": []}
        constraints = CapabilityConstraints(self.project_root, mem_palace=mock_palace)
        
        plan = self.selector.select_capabilities(signal_set, constraints)
        self.assertIsInstance(plan, CapabilityExecutionPlan)
        
        controller = ExecutorControls(self.project_root)
        receipts = controller.execute_plan(plan)
        
        # Verify receipts count matches required capabilities
        self.assertEqual(len(receipts), len(plan.required_capabilities))
        
        for cap_receipt in receipts:
            self.assertTrue(cap_receipt.selected)
            self.assertTrue(cap_receipt.invoked)
            self.assertTrue(cap_receipt.gate_passed)
            self.assertTrue(cap_receipt.evidence_id.startswith("ev_cap_"))
            
            # Verify internal skill receipts
            self.assertTrue(len(cap_receipt.skill_receipts) >= 1)
            for skill_receipt in cap_receipt.skill_receipts:
                self.assertTrue(skill_receipt.selected)
                self.assertTrue(skill_receipt.used)
                self.assertTrue(skill_receipt.evidence_id.startswith("ev_slot_"))
                self.assertEqual(skill_receipt.outcome.get("execution_state"), "SUCCESS")


if __name__ == "__main__":
    unittest.main()


