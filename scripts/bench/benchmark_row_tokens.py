from __future__ import annotations

from typing import Any


def normalize_token_status(status: str, total_tokens: int) -> str:
    normalized = str(status or "unknown").strip().lower() or "unknown"
    if normalized in {"ok", "captured"} and total_tokens > 0:
        return "measured"
    return normalized


def build_row_token_fields(report: dict[str, Any]) -> dict[str, Any]:
    model_calls = int(report.get("model_calls", 0) or 0)
    total_tokens = int(report.get("total_tokens", 0) or 0)
    token_capture_status = normalize_token_status(
        str(report.get("token_capture_status", "unknown") or "unknown"),
        total_tokens,
    )
    token_measured = token_capture_status == "measured" or (
        model_calls <= 0 and token_capture_status in {"not_applicable_local_only", "not_applicable_no_model"}
    )
    return {
        "model_calls": model_calls,
        "model_name": str(report.get("model_name", "") or ""),
        "total_tokens": total_tokens,
        "token_capture_status": token_capture_status,
        "token_measured": token_measured,
        "model_total_tokens": int(report.get("model_total_tokens", total_tokens if model_calls > 0 else 0) or 0),
        "model_token_capture_status": str(report.get("model_token_capture_status") or ""),
        "gateway_stats_present": bool(report.get("gateway_stats_present", False)),
        "gateway_usage_metadata_present": bool(report.get("gateway_usage_metadata_present", False)),
        "gateway_token_source": str(report.get("gateway_token_source") or ""),
        "gateway_token_outlier_reason": str(report.get("gateway_token_outlier_reason") or ""),
        "raw_provider_total_tokens": int(report.get("raw_provider_total_tokens", 0) or 0),
        "raw_provider_token_source": str(report.get("raw_provider_token_source") or ""),
        "provider_stats_cumulative_suspected": bool(report.get("provider_stats_cumulative_suspected", False)),
        "token_accounting_failure_class": str(report.get("token_accounting_failure_class") or ""),
        "token_ledger_status": str(report.get("token_ledger_status") or ""),
        "token_ledger_source": str(report.get("token_ledger_source") or ""),
        "token_ledger_normalized_tokens": int(report.get("token_ledger_normalized_tokens", 0) or 0),
        "token_ledger_raw_provider_total_tokens": int(report.get("token_ledger_raw_provider_total_tokens", 0) or 0),
    }
