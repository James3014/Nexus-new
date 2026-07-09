from __future__ import annotations

import pytest

from nexus.services.local_heal.quota_state import QuotaState, BudgetClass
from nexus.services.local_heal.degradation_controller import DegradationController


class TestDegradationControllerDefault:

    def test_degradation_controller_healthy_returns_keep_full(self):
        quota_state = QuotaState(
            quota_known=True,
            budget_class=BudgetClass.HEALTHY,
            cloud_budget_remaining=50,
            local_available=True,
            committee_budget_remaining=10,
            source="env",
            confidence=1.0,
            reason="cloud_budget_healthy",
        )
        controller = DegradationController()
        decision = controller.on_quota_state_change(quota_state)
        assert decision.action == "keep_full_committee"
        assert decision.cloud_allowed is True

    def test_degradation_controller_constrained_returns_reduce_candidate(self):
        quota_state = QuotaState(
            quota_known=True,
            budget_class=BudgetClass.CONSTRAINED,
            cloud_budget_remaining=5,
            local_available=True,
            committee_budget_remaining=10,
            source="env",
            confidence=1.0,
            reason="cloud_budget_constrained",
        )
        controller = DegradationController()
        decision = controller.on_quota_state_change(quota_state)
        assert decision.action == "reduce_candidate_count"
        assert decision.candidate_count_limit is not None and decision.candidate_count_limit <= 2

    def test_degradation_controller_exhausted_local_returns_local_only(self):
        quota_state = QuotaState(
            quota_known=True,
            budget_class=BudgetClass.EXHAUSTED,
            cloud_budget_remaining=0,
            local_available=True,
            committee_budget_remaining=10,
            source="env",
            confidence=1.0,
            reason="cloud_budget_exhausted",
        )
        controller = DegradationController()
        decision = controller.on_quota_state_change(quota_state)
        assert decision.action == "local_only"
        assert decision.cloud_allowed is False
        assert decision.local_allowed is True

    def test_degradation_controller_exhausted_no_local_returns_fail_closed(self):
        quota_state = QuotaState(
            quota_known=True,
            budget_class=BudgetClass.EXHAUSTED,
            cloud_budget_remaining=0,
            local_available=False,
            committee_budget_remaining=0,
            source="env",
            confidence=1.0,
            reason="local_unavailable_cloud_exhausted",
        )
        controller = DegradationController(local_available=False)
        decision = controller.on_quota_state_change(quota_state)
        assert decision.action == "fail_closed"
        assert decision.cloud_allowed is False
        assert decision.local_allowed is False

    def test_degradation_controller_unknown_returns_fail_closed(self):
        quota_state = QuotaState(
            quota_known=False,
            budget_class=BudgetClass.UNKNOWN,
            cloud_budget_remaining=None,
            local_available=True,
            committee_budget_remaining=None,
            source="env",
            confidence=0.0,
            reason="quota_unknown",
        )
        controller = DegradationController()
        decision = controller.on_quota_state_change(quota_state)
        assert decision.action == "fail_closed"


class TestDegradationControllerChain:

    def test_degradation_controller_reason_chain_appends(self):
        controller = DegradationController()
        state_h = QuotaState(True, BudgetClass.HEALTHY, 50, True, 10, "env", 1.0, "healthy")
        state_c = QuotaState(True, BudgetClass.CONSTRAINED, 5, True, 10, "env", 1.0, "constrained")

        controller.on_quota_state_change(state_h)
        controller.on_quota_state_change(state_c)

        chain = controller.get_reason_chain()
        assert len(chain) == 2
        assert "keep_full_committee" in chain[0]
        assert "reduce_candidate_count" in chain[1]

    def test_degradation_controller_reason_chain_bounded_at_100(self):
        controller = DegradationController()
        state = QuotaState(True, BudgetClass.HEALTHY, 50, True, 10, "env", 1.0, "healthy")
        for _ in range(105):
            controller.on_quota_state_change(state)
        assert len(controller.get_reason_chain()) == 100

    def test_degradation_controller_reset_chain(self):
        controller = DegradationController()
        state = QuotaState(True, BudgetClass.HEALTHY, 50, True, 10, "env", 1.0, "healthy")
        controller.on_quota_state_change(state)
        assert len(controller.get_reason_chain()) == 1
        controller.reset_chain()
        assert len(controller.get_reason_chain()) == 0


class TestDegradationControllerBoundary:

    def test_degradation_controller_does_not_mutate_execution_topology(self):
        controller = DegradationController()
        state = QuotaState(True, BudgetClass.HEALTHY, 50, True, 10, "env", 1.0, "healthy")
        decision = controller.on_quota_state_change(state)
        assert not hasattr(decision, "execution_topology")
