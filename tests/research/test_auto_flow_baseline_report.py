from nexus.research.flow.baseline_report import (
    baseline_report_from_meta,
    local_baseline_meta,
    strict_baseline_failure_meta,
)


def test_baseline_report_from_meta_preserves_gateway_and_model_fields():
    report = baseline_report_from_meta(
        "nexus_llm_baseline",
        {
            "model_calls": 1,
            "model_name": "gemini-3-flash",
            "tokens_used": 123,
            "token_capture_status": "measured",
            "gateway_stats_present": True,
            "gateway_usage_metadata_present": True,
            "gateway_token_source": "usage_metadata",
            "gateway_error_category": "",
            "gateway_prompt_chars": 10,
            "gateway_payload_chars": 20,
            "gateway_total_chars": 30,
            "gateway_timeout_sec": 40,
            "baseline_llm_required": True,
            "baseline_source_policy": "strict_llm_no_local_fallback",
        },
    )

    assert report == {
        "source": "nexus_llm_baseline",
        "attempt_count": 1,
        "model_calls": 1,
        "model_name": "gemini-3-flash",
        "model_patch_generated": True,
        "fallback_used": False,
        "total_tokens": 123,
        "token_capture_status": "measured",
        "gateway_stats_present": True,
        "gateway_usage_metadata_present": True,
        "gateway_token_source": "usage_metadata",
        "gateway_error_category": "",
        "gateway_prompt_chars": 10,
        "gateway_payload_chars": 20,
        "gateway_total_chars": 30,
        "gateway_timeout_sec": 40,
        "baseline_llm_required": True,
        "baseline_source_policy": "strict_llm_no_local_fallback",
    }


def test_local_baseline_meta_marks_fallback_reason_without_model_cost():
    assert local_baseline_meta(fallback_reason="timeout") == {
        "source": "local",
        "model_calls": 0,
        "tokens_used": 0,
        "token_capture_status": "not_applicable_local_only",
        "model_patch_generated": False,
        "fallback_used": True,
        "gateway_error_category": "timeout",
    }


def test_strict_baseline_failure_meta_is_fail_closed_and_no_local_fallback():
    meta = strict_baseline_failure_meta("llm_no_patch", {"total_tokens": 7})

    assert meta["source"] == "nexus_llm_baseline"
    assert meta["model_calls"] == 0
    assert meta["tokens_used"] == 7
    assert meta["token_capture_status"] == "missing_gateway_stats"
    assert meta["model_patch_generated"] is False
    assert meta["fallback_used"] is False
    assert meta["gateway_error_category"] == "llm_no_patch"
    assert meta["baseline_llm_required"] is True
    assert meta["baseline_source_policy"] == "strict_llm_no_local_fallback"
