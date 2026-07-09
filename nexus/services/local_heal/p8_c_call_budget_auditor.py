from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P8CCallBudgetAuditResult:
    audit_version: str = "1.0"
    receipt_present: bool = False
    network_call_count: int = 0
    retry_attempted: bool = False
    streaming_used: bool = False
    tool_call_used: bool = False
    timed_out: bool = False
    timeout_seconds: int = 0
    cost_budget_usd: float = 0.0
    estimated_cost_usd: float = 0.0
    cost_budget_exceeded: bool = False
    call_budget_audit_passed: bool = False
    rollback_required: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def audit_call_budget(receipt: dict[str, Any]) -> P8CCallBudgetAuditResult:
    blocked = []
    rollback = []
    cc = receipt.get("network_call_count", 0)
    retry = receipt.get("retry_attempted", False)
    streaming = receipt.get("streaming_used", False)
    tool = receipt.get("tool_call_used", False)
    timed_out = receipt.get("timed_out", False)
    timeout = receipt.get("timeout_seconds", 0)
    cost_exceeded = receipt.get("cost_budget_exceeded", False)
    est_cost = receipt.get("estimated_cost_usd", 0.0)

    if cc > 1: rollback.append("network_call_count_exceeded")
    if retry: rollback.append("retry_attempted")
    if streaming: rollback.append("streaming_used")
    if tool: rollback.append("tool_call_used")
    if cost_exceeded: rollback.append("cost_budget_exceeded")
    if timeout > 30 or timeout <= 0:
        if receipt.get("network_call_attempted", False):
            blocked.append("timeout_invalid")
    if receipt.get("network_call_completed", False) and est_cost <= 0:
        blocked.append("estimated_cost_missing")

    return P8CCallBudgetAuditResult(
        receipt_present=True, network_call_count=cc,
        retry_attempted=retry, streaming_used=streaming,
        tool_call_used=tool, timed_out=timed_out,
        timeout_seconds=timeout, cost_budget_usd=receipt.get("cost_budget_usd", 0.0),
        estimated_cost_usd=est_cost, cost_budget_exceeded=cost_exceeded,
        call_budget_audit_passed=len(blocked) == 0 and len(rollback) == 0,
        rollback_required=len(rollback) > 0,
        blocked_reasons=blocked + rollback,
    )
