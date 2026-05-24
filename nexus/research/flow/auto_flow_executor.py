from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _int_field(report: Mapping[str, Any], key: str) -> int:
    return int(report.get(key, 0) or 0)


def _attr_int(obj: Any, key: str) -> int:
    return int(getattr(obj, key, 0) or 0)


def build_hyper_sprint_report(
    result: Any,
    *,
    effective_stage1_timeout_sec: int,
    r_phase_breakdown_sec: Mapping[str, Any],
    candidate_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    learning_trace = getattr(result, "learning_trace", {}) or {}
    learning_trace = learning_trace if isinstance(learning_trace, dict) else {}
    return {
        "status": result.status,
        "reason": result.reason,
        "winner_source": result.winner_source,
        "error_codes": result.error_codes,
        "rejection_summary": result.rejection_summary,
        "attempt_count": result.attempt_count,
        "model_calls": result.model_calls,
        "model_name": getattr(result, "model_name", ""),
        "model_patch_generated": bool(getattr(result, "model_patch_generated", False)),
        "fallback_used": bool(getattr(result, "fallback_used", False)),
        "total_tokens": result.total_tokens,
        "token_capture_status": result.token_capture_status,
        "gateway_stats_present": bool(getattr(result, "gateway_stats_present", False)),
        "gateway_usage_metadata_present": bool(getattr(result, "gateway_usage_metadata_present", False)),
        "gateway_token_source": str(getattr(result, "gateway_token_source", "missing") or "missing"),
        "gateway_error_category": str(getattr(result, "gateway_error_category", "") or ""),
        "gateway_prompt_chars": _attr_int(result, "gateway_prompt_chars"),
        "gateway_payload_chars": _attr_int(result, "gateway_payload_chars"),
        "gateway_total_chars": _attr_int(result, "gateway_total_chars"),
        "gateway_timeout_sec": _attr_int(result, "gateway_timeout_sec"),
        "effective_stage1_timeout_sec": effective_stage1_timeout_sec,
        "candidate_summaries": candidate_summaries,
        "learning_trace": learning_trace,
        "distant_scout_execution": learning_trace.get("distant_scout_execution", {}),
        "r_phase_breakdown_sec": dict(r_phase_breakdown_sec),
    }


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
