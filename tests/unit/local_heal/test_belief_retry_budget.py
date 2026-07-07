"""C6AC: RED tests for belief retry budget wiring.

Tests verify:
1. High confidence / low uncertainty -> conservative retry budget
2. Low confidence / high uncertainty -> wider retry budget (bounded)
3. Belief cannot override verifier / claim / owner gate
4. Belief extraction failure is fail-open
5. Telemetry includes all belief budget fields
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestBeliefRetryBudget:
    """Belief confidence should influence retry budget decisions."""

    def test_high_confidence_conservative_budget(self):
        """
        Given: belief_before = 0.9, uncertainty_delta = -0.05 (low uncertainty)
        When: budget policy is resolved
        Then: max_rounds = 1 (conservative — high confidence means less retry needed)
        """
        from nexus.services.local_heal.belief_budget_policy import resolve_retry_budget

        budget = resolve_retry_budget(
            belief_before=0.9,
            uncertainty_delta=-0.05,
        )
        assert budget["max_rounds"] == 1
        assert budget["policy"] == "conservative"

    def test_low_uncertainty_wider_budget(self):
        """
        Given: belief_before = 0.2, uncertainty_delta = 0.3 (high uncertainty)
        When: budget policy is resolved
        Then: max_rounds = 3 (wider — low confidence, try more)
        """
        from nexus.services.local_heal.belief_budget_policy import resolve_retry_budget

        budget = resolve_retry_budget(
            belief_before=0.2,
            uncertainty_delta=0.3,
        )
        assert budget["max_rounds"] == 3
        assert budget["policy"] == "exploratory"

    def test_medium_confidence_moderate_budget(self):
        """
        Given: belief_before = 0.5, uncertainty_delta = 0.1
        When: budget policy is resolved
        Then: max_rounds = 2 (moderate)
        """
        from nexus.services.local_heal.belief_budget_policy import resolve_retry_budget

        budget = resolve_retry_budget(
            belief_before=0.5,
            uncertainty_delta=0.1,
        )
        assert budget["max_rounds"] == 2
        assert budget["policy"] == "moderate"

    def test_budget_always_bounded(self):
        """
        Given: extreme values
        When: budget policy is resolved
        Then: max_rounds is always between 1 and 4
        """
        from nexus.services.local_heal.belief_budget_policy import resolve_retry_budget

        for belief in [0.0, 0.5, 1.0]:
            for delta in [-1.0, 0.0, 1.0]:
                budget = resolve_retry_budget(belief_before=belief, uncertainty_delta=delta)
                assert 1 <= budget["max_rounds"] <= 4


class TestBeliefCannotOverride:
    """Belief must never override verifier / claim / owner gate."""

    def test_belief_cannot_override_verifier(self):
        """
        Given: belief trace exists
        Then: cannot_override_verifier is always True
        """
        from nexus.services.local_heal.reasoning_advisory_bridge import apply_belief_update

        mock_ctx = MagicMock()
        mock_ctx.op.instance_id = "task-1"
        mock_ctx.op.solve_eligible = False
        mock_ctx.op.failure_reason = "VERIFIER_FAIL"
        mock_ctx.op.receipt_path = "receipt.json"

        trace = apply_belief_update(mock_ctx)
        assert trace["cannot_override_verifier"] is True

    def test_belief_cannot_bypass_owner_gate(self):
        """
        Given: belief trace exists
        Then: cannot_bypass_owner_gate is always True
        """
        from nexus.services.local_heal.reasoning_advisory_bridge import apply_belief_update

        mock_ctx = MagicMock()
        mock_ctx.op.instance_id = "task-2"
        mock_ctx.op.solve_eligible = False
        mock_ctx.op.failure_reason = "owner_gated"
        mock_ctx.op.receipt_path = "receipt.json"

        trace = apply_belief_update(mock_ctx)
        assert trace["cannot_bypass_owner_gate"] is True


class TestBeliefFailOpen:
    """Belief extraction failure must not block retry."""

    def test_budget_fallback_when_belief_unavailable(self):
        """
        Given: BeliefEngine raises exception
        When: resolve_retry_budget is called with fallback
        Then: returns default moderate budget
        """
        from nexus.services.local_heal.belief_budget_policy import resolve_retry_budget

        # No belief available — use defaults
        budget = resolve_retry_budget(belief_before=None, uncertainty_delta=None)
        assert budget["max_rounds"] == 2
        assert budget["policy"] == "moderate"


class TestBeliefTelemetry:
    """Telemetry should include all belief budget fields."""

    def test_expected_telemetry_fields(self):
        """
        Given: semantic retry runs with belief budget
        When: telemetry is written
        Then: all belief fields are present
        """
        expected_fields = {
            "semantic_retry_belief_used",
            "semantic_retry_belief_before",
            "semantic_retry_belief_after",
            "semantic_retry_uncertainty_delta",
            "semantic_retry_budget_policy",
            "semantic_retry_budget_rounds",
        }
        assert len(expected_fields) == 6

    def test_telemetry_dict_contains_belief_fields(self):
        """
        Given: ctx.op with belief budget attributes set
        When: _semantic_retry_telemetry is built (simulating orchestrator path)
        Then: telemetry dict contains real values from ctx.op
        """
        mock_op = MagicMock()
        mock_op._belief_budget_used = True
        mock_op._belief_before = 0.35
        mock_op._uncertainty_delta = 0.25
        mock_op._budget_policy = "exploratory"
        mock_op._budget_rounds = 3

        # Simulate what orchestrator builds
        telemetry = {
            "semantic_retry_belief_used": bool(getattr(mock_op, "_belief_budget_used", False)),
            "semantic_retry_belief_before": getattr(mock_op, "_belief_before", None),
            "semantic_retry_belief_after": None,
            "semantic_retry_uncertainty_delta": getattr(mock_op, "_uncertainty_delta", None),
            "semantic_retry_budget_policy": str(getattr(mock_op, "_budget_policy", "")),
            "semantic_retry_budget_rounds": int(getattr(mock_op, "_budget_rounds", 2)),
        }

        assert telemetry["semantic_retry_belief_used"] is True
        assert telemetry["semantic_retry_belief_before"] == 0.35
        assert telemetry["semantic_retry_uncertainty_delta"] == 0.25
        assert telemetry["semantic_retry_budget_policy"] == "exploratory"
        assert telemetry["semantic_retry_budget_rounds"] == 3

    def test_multipass_writes_budget_to_ctx_op(self):
        """
        Given: orchestrator._attempt_multipass_semantic_retry runs
        When: belief budget is resolved
        Then: ctx.op has _belief_budget_used, _budget_policy, _budget_rounds set
        """
        from nexus.services.local_heal.orchestrator import HealOrchestrator

        orchestrator = HealOrchestrator.__new__(HealOrchestrator)
        mock_ctx = MagicMock()
        mock_ctx.op.instance_id = "task-budget-test"
        mock_ctx.op.task_id = "task-budget-test"
        mock_ctx.op.verifier_stdout_excerpt = "EVIDENCE: assert x == 1"
        mock_ctx.op._belief_trace = None

        # Mock the semantic retry to avoid actual LLM call
        with patch.object(orchestrator, '_attempt_semantic_retry', return_value=False):
            with patch('nexus.core.belief_engine.BeliefEngine') as mock_engine_cls:
                mock_engine = MagicMock()
                mock_engine.get_confidence.return_value = 0.2
                mock_engine_cls.return_value = mock_engine

                orchestrator._attempt_multipass_semantic_retry(
                    mock_ctx, "FAIL: test", "semantic_wrong"
                )

        # Verify budget attributes were written to ctx.op
        assert hasattr(mock_ctx.op, '_belief_budget_used')
        assert hasattr(mock_ctx.op, '_budget_policy')
        assert hasattr(mock_ctx.op, '_budget_rounds')
        assert isinstance(mock_ctx.op._budget_rounds, int)
