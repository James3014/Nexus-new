from scripts.bench.benchmark_row_tokens import build_row_token_fields, normalize_token_status


def test_normalize_token_status_preserves_existing_measured_aliases():
    assert normalize_token_status("ok", 12) == "measured"
    assert normalize_token_status("captured", 12) == "measured"
    assert normalize_token_status("ok", 0) == "ok"


def test_build_row_token_fields_marks_no_model_local_fast_path_measured():
    fields = build_row_token_fields(
        {
            "model_calls": 0,
            "total_tokens": 0,
            "token_capture_status": "not_applicable_local_only",
        }
    )

    assert fields["token_measured"] is True
    assert fields["model_total_tokens"] == 0
    assert fields["gateway_token_source"] == ""


def test_build_row_token_fields_preserves_provider_and_ledger_evidence():
    fields = build_row_token_fields(
        {
            "model_calls": 1,
            "model_name": "gemini-3-flash",
            "total_tokens": 42,
            "token_capture_status": "captured",
            "model_total_tokens": 40,
            "model_token_capture_status": "measured",
            "gateway_stats_present": True,
            "gateway_usage_metadata_present": True,
            "gateway_token_source": "usage_metadata",
            "gateway_token_outlier_reason": "none",
            "raw_provider_total_tokens": 45,
            "raw_provider_token_source": "stats",
            "provider_stats_cumulative_suspected": True,
            "token_accounting_failure_class": "provider_stats_outlier",
            "token_ledger_status": "normalized_from_cumulative_stats",
            "token_ledger_source": "prompt_output_char_estimate",
            "token_ledger_normalized_tokens": 41,
            "token_ledger_raw_provider_total_tokens": 45,
        }
    )

    assert fields == {
        "model_calls": 1,
        "model_name": "gemini-3-flash",
        "total_tokens": 42,
        "token_capture_status": "measured",
        "token_measured": True,
        "model_total_tokens": 40,
        "model_token_capture_status": "measured",
        "gateway_stats_present": True,
        "gateway_usage_metadata_present": True,
        "gateway_token_source": "usage_metadata",
        "gateway_token_outlier_reason": "none",
        "raw_provider_total_tokens": 45,
        "raw_provider_token_source": "stats",
        "provider_stats_cumulative_suspected": True,
        "token_accounting_failure_class": "provider_stats_outlier",
        "token_ledger_status": "normalized_from_cumulative_stats",
        "token_ledger_source": "prompt_output_char_estimate",
        "token_ledger_normalized_tokens": 41,
        "token_ledger_raw_provider_total_tokens": 45,
    }
