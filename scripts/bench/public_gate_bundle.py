from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostEfficiencyDecision:
    status: str
    failures: list[str]


def derive_cost_efficiency_decision(
    *,
    delivery_gate_passed: bool,
    delivery_gate_failures: list[str],
    cost_gate_failures: list[str],
    wall_cost_ratio_with_over_without: float,
    token_cost_ratio_with_over_without: float,
    model_call_ratio_with_over_without: float,
    retry_cost_share_wall: float,
    retry_cost_share_tokens: float,
    wall_ledger_invalid: bool,
    warning_ledger_invalid: bool,
    valid_comparison_ready: bool,
) -> CostEfficiencyDecision:
    failures: list[str] = []
    if not delivery_gate_passed:
        failures.extend(delivery_gate_failures)
    if cost_gate_failures:
        failures.extend(cost_gate_failures)
    if wall_cost_ratio_with_over_without > 1.0:
        failures.append("wall_cost_not_improved")
    if token_cost_ratio_with_over_without > 1.0:
        failures.append("token_cost_not_improved")
    if model_call_ratio_with_over_without > 1.0:
        failures.append("model_calls_not_improved")
    if retry_cost_share_wall > 0.0:
        failures.append("hidden_retry_wall_share_present")
    if retry_cost_share_tokens > 0.0:
        failures.append("hidden_retry_token_share_present")
    if retry_cost_share_wall >= 0.25 or retry_cost_share_tokens >= 0.25:
        failures.append("hidden_retry_second_attempt_dominant")
    if wall_ledger_invalid:
        failures.append("wall_ledger_telemetry_invalid")
    if warning_ledger_invalid:
        failures.append("warning_ledger_telemetry_invalid")

    status = "IMPROVED" if not failures else "REGRESSED"
    if wall_ledger_invalid or warning_ledger_invalid:
        status = "RETURN"
    if not valid_comparison_ready:
        status = "INCONCLUSIVE_PROVIDER_VARIANCE"
        failures.append("valid_comparison_not_ready")
    return CostEfficiencyDecision(status=status, failures=failures)
