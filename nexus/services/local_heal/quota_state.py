from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class BudgetClass(str, Enum):
    HEALTHY = "healthy"
    CONSTRAINED = "constrained"
    EXHAUSTED = "exhausted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class QuotaState:
    """P6-B1: QuotaState runtime contract.

    Immutable dataclass representing the current quota state.
    """
    quota_known: bool
    budget_class: BudgetClass
    cloud_budget_remaining: int | None
    local_available: bool
    committee_budget_remaining: int | None
    source: str  # env | receipt | provider_error | manual | unknown
    confidence: float
    reason: str


def resolve_quota_state() -> QuotaState:
    """Resolve current quota state from environment.

    Rules:
    - unknown quota != healthy (conservative)
    - provider_error quota -> unknown or exhausted, never healthy
    - memory confidence cannot change budget_class
    """
    # Read from environment
    cloud_budget_str = os.environ.get("NEXUS_CLOUD_BUDGET_REMAINING", "")
    local_available_str = os.environ.get("NEXUS_LOCAL_AVAILABLE", "1")
    committee_budget_str = os.environ.get("NEXUS_COMMITTEE_BUDGET_REMAINING", "")

    cloud_budget_remaining = int(cloud_budget_str) if cloud_budget_str.isdigit() else None
    local_available = local_available_str == "1"
    committee_budget_remaining = int(committee_budget_str) if committee_budget_str.isdigit() else None

    # Determine budget class
    if cloud_budget_remaining is not None and cloud_budget_remaining <= 0:
        budget_class = BudgetClass.EXHAUSTED
        reason = "cloud_budget_exhausted"
    elif cloud_budget_remaining is not None and cloud_budget_remaining < 10:
        budget_class = BudgetClass.CONSTRAINED
        reason = "cloud_budget_constrained"
    elif cloud_budget_remaining is not None and cloud_budget_remaining >= 10:
        budget_class = BudgetClass.HEALTHY
        reason = "cloud_budget_healthy"
    else:
        budget_class = BudgetClass.UNKNOWN
        reason = "quota_unknown"

    # Override: if local not available and cloud exhausted -> fail_closed candidate
    if not local_available and budget_class == BudgetClass.EXHAUSTED:
        reason = "local_unavailable_cloud_exhausted"

    quota_known = cloud_budget_remaining is not None

    return QuotaState(
        quota_known=quota_known,
        budget_class=budget_class,
        cloud_budget_remaining=cloud_budget_remaining,
        local_available=local_available,
        committee_budget_remaining=committee_budget_remaining,
        source="env",
        confidence=1.0 if quota_known else 0.0,
        reason=reason,
    )
