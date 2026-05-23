from __future__ import annotations

from typing import Any


def apply_per_task_stop_loss(row: dict[str, Any], limit_sec: int) -> bool:
    if limit_sec <= 0:
        return False
    wall_duration = float(row.get("wall_duration_sec", 0.0) or 0.0)
    if wall_duration <= float(limit_sec):
        return False
    row["runtime_classification"] = "task_stop_loss_exceeded"
    row["timeout_scope"] = "benchmark_per_task_stop_loss"
    row["timeout_stage"] = "wall_clock_exceeded"
    row["timeout_sec"] = int(limit_sec)
    row["retryable"] = True
    row["infra_invalid_reason"] = "task_stop_loss_exceeded"
    row["run_eligible"] = False
    row["token_reliable"] = False
    row["token_unreliable_reason"] = "task_stop_loss_exceeded"
    return True


def direct_provider_timeout_row(row: dict[str, Any]) -> bool:
    if str(row.get("mode") or "") != "without_nexus":
        return False
    timeout_markers = {
        str(row.get("gateway_error_category") or ""),
        str(row.get("baseline_gateway_error_category") or ""),
        str(row.get("infra_invalid_reason") or ""),
    }
    return bool(timeout_markers & {"timeout", "timeout_before_model_call", "task_stop_loss_exceeded"})


def direct_provider_infra_row(row: dict[str, Any]) -> bool:
    if str(row.get("mode") or "") != "without_nexus":
        return False
    return not bool(row.get("run_eligible", True)) and bool(str(row.get("infra_invalid_reason") or ""))


def direct_timeout_abort_reason(consecutive_timeouts: int, threshold: int) -> str:
    if int(threshold) <= 0:
        return ""
    if int(consecutive_timeouts) < int(threshold):
        return ""
    return "consecutive_direct_provider_timeouts"


def direct_infra_abort_reason(consecutive_infra: int, threshold: int) -> str:
    if int(threshold) <= 0:
        return ""
    if int(consecutive_infra) < int(threshold):
        return ""
    return "consecutive_direct_provider_infra_invalid"
