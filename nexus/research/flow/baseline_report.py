from __future__ import annotations

from typing import Any


def baseline_report_from_meta(source: str, meta: dict[str, Any]) -> dict[str, Any]:
    model_calls = int(meta.get("model_calls", 0) or 0)
    total_tokens = int(meta.get("tokens_used", meta.get("total_tokens", 0)) or 0)
    return {
        "source": source,
        "attempt_count": 1,
        "model_calls": model_calls,
        "model_name": str(meta.get("model_name", "") or ""),
        "model_patch_generated": bool(meta.get("model_patch_generated", model_calls > 0)),
        "fallback_used": bool(meta.get("fallback_used", False)),
        "total_tokens": total_tokens,
        "token_capture_status": str(meta.get("token_capture_status", "not_applicable_local_only") or "unknown"),
        "gateway_stats_present": bool(meta.get("gateway_stats_present", False)),
        "gateway_usage_metadata_present": bool(meta.get("gateway_usage_metadata_present", False)),
        "gateway_token_source": str(meta.get("gateway_token_source", "missing") or "missing"),
        "gateway_error_category": str(meta.get("gateway_error_category", "") or ""),
        "gateway_prompt_chars": int(meta.get("gateway_prompt_chars", 0) or 0),
        "gateway_payload_chars": int(meta.get("gateway_payload_chars", 0) or 0),
        "gateway_total_chars": int(meta.get("gateway_total_chars", 0) or 0),
        "gateway_timeout_sec": int(meta.get("gateway_timeout_sec", 0) or 0),
        "baseline_llm_required": bool(meta.get("baseline_llm_required", False)),
        "baseline_source_policy": str(meta.get("baseline_source_policy", "")),
    }


def local_baseline_meta(*, fallback_reason: str | None = None) -> dict[str, Any]:
    meta = {
        "source": "local",
        "model_calls": 0,
        "tokens_used": 0,
        "token_capture_status": "not_applicable_local_only",
        "model_patch_generated": False,
    }
    if fallback_reason:
        meta["fallback_used"] = True
        meta["gateway_error_category"] = fallback_reason
    return meta


def strict_baseline_failure_meta(reason: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    out = dict(meta or {})
    out.setdefault("source", "nexus_llm_baseline")
    out.setdefault("model_calls", 0)
    out.setdefault("tokens_used", out.get("total_tokens", 0) or 0)
    out.setdefault("token_capture_status", "missing_gateway_stats")
    out["model_patch_generated"] = False
    out["fallback_used"] = False
    out["gateway_error_category"] = reason
    out["baseline_llm_required"] = True
    out["baseline_source_policy"] = "strict_llm_no_local_fallback"
    return out
