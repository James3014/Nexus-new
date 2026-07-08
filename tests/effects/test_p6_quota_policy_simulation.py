"""EA-R8: P6 Quota Policy Simulator Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.quota_policy_simulator import (
    QuotaState,
    P6SimulationResult,
    simulate_p6_quota_policy,
)


def test_quota_healthy_keep_committee():
    """EA-R8: Healthy quota → keep_full_committee."""
    result = simulate_p6_quota_policy(quota_state=QuotaState(budget_class="healthy"))
    assert result.degradation_action == "keep_full_committee"
    assert result.quota_budget_class == "healthy"


def test_quota_constrained_reduce_candidates():
    """EA-R8: Constrained quota → reduce_candidate_count."""
    result = simulate_p6_quota_policy(quota_state=QuotaState(budget_class="constrained"))
    assert result.degradation_action == "reduce_candidate_count"
    assert result.quota_budget_class == "constrained"


def test_quota_exhausted_local_only():
    """EA-R8: Exhausted quota → local_only."""
    result = simulate_p6_quota_policy(quota_state=QuotaState(budget_class="exhausted"))
    assert result.degradation_action == "local_only"
    assert result.quota_budget_class == "exhausted"


def test_quota_unknown_fail_closed():
    """EA-R8: Unknown quota → fail_closed (conservative)."""
    result = simulate_p6_quota_policy(quota_state=QuotaState(budget_class="unknown"))
    assert result.degradation_action == "fail_closed"
    assert result.quota_budget_class == "unknown"


def test_memory_does_not_override_quota():
    """EA-R8: Memory confidence cannot override quota_exhausted."""
    result = simulate_p6_quota_policy(
        quota_state=QuotaState(budget_class="exhausted"),
        memory_confidence_signal=0.9,
        memory_decision_mode="decision_eligible",
    )
    # Memory cannot override quota_exhausted → must fail_closed
    assert result.quota_budget_class == "exhausted"
    assert result.degradation_action == "local_only"
    # Memory only affects diagnostic_confidence
    assert result.diagnostic_confidence > 0.5


def test_memory_influences_diagnostic_confidence():
    """EA-R8: Memory only affects diagnostic_confidence."""
    result_with = simulate_p6_quota_policy(
        quota_state=QuotaState(budget_class="healthy"),
        memory_confidence_signal=0.8,
        memory_decision_mode="decision_eligible",
    )
    result_without = simulate_p6_quota_policy(
        quota_state=QuotaState(budget_class="healthy"),
        memory_confidence_signal=0.0,
        memory_decision_mode="audit_only",
    )
    assert result_with.diagnostic_confidence > result_without.diagnostic_confidence
    assert result_with.degradation_action == result_without.degradation_action


def test_degradation_actions_have_reasons():
    """EA-R8: All degradation actions have receipt-compatible reason."""
    for budget_class in ["healthy", "constrained", "exhausted", "unknown"]:
        result = simulate_p6_quota_policy(quota_state=QuotaState(budget_class=budget_class))
        assert result.degradation_reason != ""
        assert result.degradation_action != ""
