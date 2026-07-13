from __future__ import annotations

from nexus.services.cloud_local_quota_policy import apply_quota_policy, run_quota_guarded_chain
from nexus.services.local_heal.quota_state import BudgetClass, QuotaState


def _state(kind: BudgetClass, *, local_available: bool = True) -> QuotaState:
    return QuotaState(
        quota_known=kind != BudgetClass.UNKNOWN,
        budget_class=kind,
        cloud_budget_remaining=20 if kind == BudgetClass.HEALTHY else 5 if kind == BudgetClass.CONSTRAINED else 0 if kind == BudgetClass.EXHAUSTED else None,
        local_available=local_available,
        committee_budget_remaining=10,
        source="test",
        confidence=1.0 if kind != BudgetClass.UNKNOWN else 0.0,
        reason=f"state_{kind.value}",
    )


def test_healthy_allows_normal_cloud_local_chain() -> None:
    policy = apply_quota_policy(_state(BudgetClass.HEALTHY), requested_action="candidate")
    assert policy["mode"] == "cloud_local"
    assert policy["cloud_allowed"] is True
    assert policy["compact_context"] is False
    assert policy["provider_switching"] is False


def test_constrained_compacts_context_and_strengthens_preflight() -> None:
    policy = apply_quota_policy(_state(BudgetClass.CONSTRAINED), requested_action="candidate")
    assert policy["mode"] == "cloud_local_constrained"
    assert policy["compact_context"] is True
    assert policy["stronger_local_preflight"] is True
    assert policy["reason_chain"] == ["state_constrained", "cloud_context_compacted", "local_preflight_strengthened"]


def test_exhausted_uses_local_only_when_available() -> None:
    policy = apply_quota_policy(_state(BudgetClass.EXHAUSTED), requested_action="candidate")
    assert policy["mode"] == "local_only"
    assert policy["cloud_allowed"] is False
    assert policy["local_only"] is True


def test_unknown_is_fail_safe_and_never_silently_switches_provider() -> None:
    policy = apply_quota_policy(_state(BudgetClass.UNKNOWN), requested_action="candidate")
    assert policy["mode"] == "local_only_unknown_quota"
    assert policy["cloud_allowed"] is False
    assert policy["provider_switching"] is False


def test_exhausted_without_local_is_fail_closed() -> None:
    policy = apply_quota_policy(_state(BudgetClass.EXHAUSTED, local_available=False), requested_action="candidate")
    assert policy["mode"] == "FAIL_CLOSED"
    result = run_quota_guarded_chain(
        policy=policy,
        cloud_chain=lambda: {"status": "should_not_run"},
        local_only_fallback=lambda: {"status": "should_not_run"},
    )
    assert result["status"] == "FAILED"
    assert result["cloud_called"] is False
    assert result["local_fallback_called"] is False
