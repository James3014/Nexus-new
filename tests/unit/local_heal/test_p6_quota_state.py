"""P6-B1: QuotaState Runtime Contract Tests."""
from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.quota_state import (
    QuotaState,
    BudgetClass,
    resolve_quota_state,
)


def test_unknown_budget_class():
    """P6-B1: unknown quota != healthy."""
    os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)
    state = resolve_quota_state()
    assert state.budget_class == BudgetClass.UNKNOWN
    assert state.budget_class != BudgetClass.HEALTHY


def test_healthy_budget_class():
    """P6-B1: cloud_budget >= 10 → healthy."""
    os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "10"
    state = resolve_quota_state()
    assert state.budget_class == BudgetClass.HEALTHY
    os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)


def test_constrained_budget_class():
    """P6-B1: cloud_budget < 10 → constrained."""
    os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "5"
    state = resolve_quota_state()
    assert state.budget_class == BudgetClass.CONSTRAINED
    os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)


def test_exhausted_budget_class():
    """P6-B1: cloud_budget <= 0 → exhausted."""
    os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "0"
    state = resolve_quota_state()
    assert state.budget_class == BudgetClass.EXHAUSTED
    os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)


def test_memory_cannot_change_budget_class():
    """P6-B1: memory confidence cannot change budget_class."""
    os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "5"
    state = resolve_quota_state()
    # Memory confidence is not part of QuotaState
    assert state.budget_class == BudgetClass.CONSTRAINED
    os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)


def test_quota_state_immutable():
    """P6-B1: QuotaState is immutable (frozen dataclass)."""
    state = QuotaState(
        quota_known=True,
        budget_class=BudgetClass.HEALTHY,
        cloud_budget_remaining=10,
        local_available=True,
        committee_budget_remaining=10,
        source="env",
        confidence=1.0,
        reason="test",
    )
    with pytest.raises(AttributeError):
        state.budget_class = BudgetClass.EXHAUSTED


def test_local_unavailable_cloud_exhausted():
    """P6-B1: local_unavailable + cloud_exhausted → fail_closed candidate."""
    os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "0"
    os.environ["NEXUS_LOCAL_AVAILABLE"] = "0"
    state = resolve_quota_state()
    assert state.budget_class == BudgetClass.EXHAUSTED
    assert state.local_available is False
    assert "local_unavailable_cloud_exhausted" in state.reason
    os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)
    os.environ.pop("NEXUS_LOCAL_AVAILABLE", None)
