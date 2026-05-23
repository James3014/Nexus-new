from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _int_field(report: Mapping[str, Any], key: str) -> int:
    return int(report.get(key, 0) or 0)


def merge_guard_fallback_accounting(
    baseline_report: Mapping[str, Any],
    *,
    hyper_flow: str,
    hyper_elapsed_sec: float | int | None,
    hyper_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge the attempted Hyper receipt into a successful baseline fallback report."""

    merged = dict(baseline_report)
    merged["guard_fallback_from"] = {
        "flow": hyper_flow,
        "elapsed_sec": hyper_elapsed_sec,
        "model_calls": _int_field(hyper_report, "model_calls"),
        "model_name": hyper_report.get("model_name", ""),
        "model_patch_generated": bool(hyper_report.get("model_patch_generated", False)),
        "fallback_used": bool(hyper_report.get("fallback_used", False)),
        "total_tokens": _int_field(hyper_report, "total_tokens"),
        "token_capture_status": hyper_report.get("token_capture_status", "unknown"),
        "gateway_stats_present": bool(hyper_report.get("gateway_stats_present", False)),
        "gateway_usage_metadata_present": bool(hyper_report.get("gateway_usage_metadata_present", False)),
        "gateway_token_source": hyper_report.get("gateway_token_source", "missing"),
        "gateway_error_category": hyper_report.get("gateway_error_category", ""),
        "gateway_prompt_chars": _int_field(hyper_report, "gateway_prompt_chars"),
        "gateway_payload_chars": _int_field(hyper_report, "gateway_payload_chars"),
        "gateway_total_chars": _int_field(hyper_report, "gateway_total_chars"),
        "gateway_timeout_sec": _int_field(hyper_report, "gateway_timeout_sec"),
        "winner_source": hyper_report.get("winner_source", "unknown"),
        "learning_trace": hyper_report.get("learning_trace", {}),
    }
    merged["model_calls"] = _int_field(merged, "model_calls") + _int_field(hyper_report, "model_calls")
    merged["model_name"] = hyper_report.get("model_name", merged.get("model_name", ""))
    merged["model_patch_generated"] = bool(hyper_report.get("model_patch_generated", False))
    merged["fallback_used"] = bool(hyper_report.get("fallback_used", False))
    merged["total_tokens"] = _int_field(merged, "total_tokens") + _int_field(hyper_report, "total_tokens")
    if hyper_report.get("token_capture_status") == "measured":
        merged["token_capture_status"] = "measured"
    merged["gateway_stats_present"] = bool(
        merged.get("gateway_stats_present", False) or hyper_report.get("gateway_stats_present", False)
    )
    merged["gateway_usage_metadata_present"] = bool(
        merged.get("gateway_usage_metadata_present", False)
        or hyper_report.get("gateway_usage_metadata_present", False)
    )
    merged["gateway_token_source"] = hyper_report.get(
        "gateway_token_source",
        merged.get("gateway_token_source", "missing"),
    )
    merged["gateway_error_category"] = hyper_report.get(
        "gateway_error_category",
        merged.get("gateway_error_category", ""),
    )
    merged["gateway_prompt_chars"] = max(
        _int_field(merged, "gateway_prompt_chars"),
        _int_field(hyper_report, "gateway_prompt_chars"),
    )
    merged["gateway_payload_chars"] = max(
        _int_field(merged, "gateway_payload_chars"),
        _int_field(hyper_report, "gateway_payload_chars"),
    )
    merged["gateway_total_chars"] = max(
        _int_field(merged, "gateway_total_chars"),
        _int_field(hyper_report, "gateway_total_chars"),
    )
    merged["gateway_timeout_sec"] = max(
        _int_field(merged, "gateway_timeout_sec"),
        _int_field(hyper_report, "gateway_timeout_sec"),
    )
    return merged
