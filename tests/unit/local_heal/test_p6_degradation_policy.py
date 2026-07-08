"""P6-B2: DegradationPolicy Runtime Contract Tests."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.quota_state import QuotaState, BudgetClass
from nexus.services.local_heal.degradation_policy import evaluate_degradation_policy


def test_healthy_keep_committee():
    """P6-B2: healthy → keep_full_committee."""
    decision = evaluate_degradation_policy(
        quota_state=QuotaState(
            quota_known=True, budget_class=BudgetClass.HEALTHY,
            cloud_budget_remaining=10, local_available=True,
            committee_budget_remaining=10, source="env",
            confidence=1.0, reason="healthy",
        ),
    )
    assert decision.action == "keep_full_committee"
    assert decision.cloud_allowed is True
    assert decision.committee_allowed is True


def test_constrained_reduce_candidates():
    """P6-B2: constrained → reduce_candidate_count."""
    decision = evaluate_degradation_policy(
        quota_state=QuotaState(
            quota_known=True, budget_class=BudgetClass.CONSTRAINED,
            cloud_budget_remaining=5, local_available=True,
            committee_budget_remaining=5, source="env",
            confidence=1.0, reason="constrained",
        ),
        requested_candidate_count=5,
    )
    assert decision.action == "reduce_candidate_count"
    assert decision.candidate_count_limit is not None
    assert decision.candidate_count_limit >= 2
    assert decision.candidate_count_limit < 5


def test_exhausted_local_only():
    """P6-B2: exhausted + local → local_only."""
    decision = evaluate_degradation_policy(
        quota_state=QuotaState(
            quota_known=True, budget_class=BudgetClass.EXHAUSTED,
            cloud_budget_remaining=0, local_available=True,
            committee_budget_remaining=0, source="env",
            confidence=1.0, reason="exhausted",
        ),
        local_available=True,
    )
    assert decision.action == "local_only"
    assert decision.cloud_allowed is False
    assert decision.local_allowed is True


def test_exhausted_no_local_fail_closed():
    """P6-B2: exhausted + no local → fail_closed."""
    decision = evaluate_degradation_policy(
        quota_state=QuotaState(
            quota_known=True, budget_class=BudgetClass.EXHAUSTED,
            cloud_budget_remaining=0, local_available=False,
            committee_budget_remaining=0, source="env",
            confidence=1.0, reason="exhausted",
        ),
        local_available=False,
    )
    assert decision.action == "fail_closed"
    assert decision.cloud_allowed is False
    assert decision.local_allowed is False


def test_unknown_fail_closed():
    """P6-B2: unknown → fail_closed (conservative)."""
    decision = evaluate_degradation_policy(
        quota_state=QuotaState(
            quota_known=False, budget_class=BudgetClass.UNKNOWN,
            cloud_budget_remaining=None, local_available=True,
            committee_budget_remaining=None, source="env",
            confidence=0.0, reason="unknown",
        ),
    )
    assert decision.action == "fail_closed"
    assert decision.cloud_allowed is False


def test_memory_cannot_change_action():
    """P6-B2: memory_signal_used_for_quota is always false."""
    decision = evaluate_degradation_policy(
        quota_state=QuotaState(
            quota_known=True, budget_class=BudgetClass.HEALTHY,
            cloud_budget_remaining=10, local_available=True,
            committee_budget_remaining=10, source="env",
            confidence=1.0, reason="healthy",
        ),
    )
    assert decision.memory_signal_used_for_quota is False


def test_verifier_and_claim_required():
    """P6-B2: verifier_required and claim_gate_required are always true."""
    decision = evaluate_degradation_policy(
        quota_state=QuotaState(
            quota_known=True, budget_class=BudgetClass.HEALTHY,
            cloud_budget_remaining=10, local_available=True,
            committee_budget_remaining=10, source="env",
            confidence=1.0, reason="healthy",
        ),
    )
    assert decision.verifier_required is True
    assert decision.claim_gate_required is True


def test_receipt_fields_complete():
    """P6-B2: receipt_fields contains all required keys."""
    decision = evaluate_degradation_policy(
        quota_state=QuotaState(
            quota_known=True, budget_class=BudgetClass.HEALTHY,
            cloud_budget_remaining=10, local_available=True,
            committee_budget_remaining=10, source="env",
            confidence=1.0, reason="healthy",
        ),
    )
    required_keys = [
        "p6_quota_state_known", "p6_budget_class", "p6_degradation_action",
        "p6_degradation_reason", "p6_candidate_count_limit", "p6_cloud_allowed",
        "p6_local_allowed", "p6_committee_allowed", "p6_p5_allowed",
        "p6_memory_signal_used_for_quota", "p6_runtime_route_mutation_allowed",
        "p6_env_guard_required",
    ]
    for key in required_keys:
        assert key in decision.receipt_fields, f"Missing key: {key}"


def test_runtime_route_mutation_not_allowed():
    """P6-B2: runtime_route_mutation_allowed is always false."""
    decision = evaluate_degradation_policy(
        quota_state=QuotaState(
            quota_known=True, budget_class=BudgetClass.HEALTHY,
            cloud_budget_remaining=10, local_available=True,
            committee_budget_remaining=10, source="env",
            confidence=1.0, reason="healthy",
        ),
    )
    assert decision.runtime_route_mutation_allowed is False
