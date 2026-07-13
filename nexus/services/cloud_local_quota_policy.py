"""Quota-aware degradation policy for the provider-neutral cloud/local chain."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from nexus.services.local_heal.quota_state import BudgetClass, QuotaState


def apply_quota_policy(quota_state: QuotaState, *, requested_action: str) -> dict[str, Any]:
    if requested_action not in {"skip", "advisor", "candidate", "verified-subtask"}:
        raise ValueError("invalid_requested_action")
    reason_chain = [quota_state.reason]
    base = {
        "schema": "nexus.cloud_local_assist.quota_policy.v1",
        "requested_action": requested_action,
        "budget_class": quota_state.budget_class.value,
        "cloud_allowed": False,
        "local_only": False,
        "compact_context": False,
        "stronger_local_preflight": False,
        "provider_switching": False,
        "route_truth_source": "CapabilityPlanner",
        "quota_source": quota_state.source,
    }
    if quota_state.budget_class == BudgetClass.HEALTHY:
        base.update({"mode": "cloud_local", "cloud_allowed": True})
    elif quota_state.budget_class == BudgetClass.CONSTRAINED:
        base.update({"mode": "cloud_local_constrained", "cloud_allowed": True, "compact_context": True, "stronger_local_preflight": True})
        reason_chain.extend(["cloud_context_compacted", "local_preflight_strengthened"])
    elif quota_state.budget_class == BudgetClass.EXHAUSTED:
        if quota_state.local_available:
            base.update({"mode": "local_only", "local_only": True})
            reason_chain.append("cloud_disabled_local_fallback")
        else:
            base.update({"mode": "FAIL_CLOSED"})
            reason_chain.append("local_unavailable")
    else:
        if quota_state.local_available:
            base.update({"mode": "local_only_unknown_quota", "local_only": True})
            reason_chain.append("unknown_quota_local_safe_path")
        else:
            base.update({"mode": "FAIL_CLOSED"})
            reason_chain.append("unknown_quota_and_local_unavailable")
    base["reason_chain"] = reason_chain
    return base


def run_quota_guarded_chain(
    *,
    policy: Mapping[str, Any],
    cloud_chain: Callable[[], Mapping[str, Any]],
    local_only_fallback: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    policy = dict(policy)
    if policy.get("mode") == "FAIL_CLOSED":
        return {
            "schema": "nexus.cloud_local_assist.quota_execution.v1",
            "status": "FAILED",
            "failure_reason": "quota_fail_closed",
            "cloud_called": False,
            "local_fallback_called": False,
            "policy": policy,
        }
    if policy.get("local_only"):
        result = dict(local_only_fallback() or {})
        return {
            "schema": "nexus.cloud_local_assist.quota_execution.v1",
            "status": result.get("status", "FAILED"),
            "cloud_called": False,
            "local_fallback_called": True,
            "policy": policy,
            "result": result,
        }
    result = dict(cloud_chain() or {})
    return {
        "schema": "nexus.cloud_local_assist.quota_execution.v1",
        "status": result.get("status", "FAILED"),
        "cloud_called": True,
        "local_fallback_called": False,
        "policy": policy,
        "result": result,
    }
