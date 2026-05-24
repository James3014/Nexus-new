from types import SimpleNamespace

from nexus.research.flow.auto_flow_executor import build_hyper_sprint_report, merge_guard_fallback_accounting


def test_build_hyper_sprint_report_preserves_provider_and_gateway_receipts():
    result = SimpleNamespace(
        status="SUCCESS",
        reason="stage1_pass",
        winner_source="llm",
        error_codes=[],
        rejection_summary={},
        attempt_count=1,
        model_calls=1,
        model_name="gemini-3-flash-preview",
        model_patch_generated=True,
        fallback_used=False,
        total_tokens=111,
        token_capture_status="measured",
        gateway_stats_present=True,
        gateway_usage_metadata_present=True,
        gateway_token_source="usage_metadata",
        gateway_error_category="",
        gateway_prompt_chars=12,
        gateway_payload_chars=34,
        gateway_total_chars=46,
        gateway_timeout_sec=20,
        learning_trace={"distant_scout_execution": {"status": "skipped"}},
        candidates=[],
    )

    report = build_hyper_sprint_report(
        result,
        effective_stage1_timeout_sec=20,
        r_phase_breakdown_sec={"setup_sec": 0.1, "hyper_sprint_sec": 0.2},
        candidate_summaries=[],
    )

    assert report == {
        "status": "SUCCESS",
        "reason": "stage1_pass",
        "winner_source": "llm",
        "error_codes": [],
        "rejection_summary": {},
        "attempt_count": 1,
        "model_calls": 1,
        "model_name": "gemini-3-flash-preview",
        "model_patch_generated": True,
        "fallback_used": False,
        "total_tokens": 111,
        "token_capture_status": "measured",
        "gateway_stats_present": True,
        "gateway_usage_metadata_present": True,
        "gateway_token_source": "usage_metadata",
        "gateway_error_category": "",
        "gateway_prompt_chars": 12,
        "gateway_payload_chars": 34,
        "gateway_total_chars": 46,
        "gateway_timeout_sec": 20,
        "effective_stage1_timeout_sec": 20,
        "candidate_summaries": [],
        "learning_trace": {"distant_scout_execution": {"status": "skipped"}},
        "distant_scout_execution": {"status": "skipped"},
        "r_phase_breakdown_sec": {"setup_sec": 0.1, "hyper_sprint_sec": 0.2},
    }


def test_merge_guard_fallback_accounting_preserves_hyper_provider_receipt():
    baseline_report = {
        "model_calls": 0,
        "model_name": "",
        "model_patch_generated": False,
        "fallback_used": False,
        "total_tokens": 0,
        "token_capture_status": "not_applicable_local_only",
        "gateway_stats_present": False,
        "gateway_usage_metadata_present": False,
        "gateway_token_source": "missing",
        "gateway_error_category": "",
        "gateway_prompt_chars": 0,
        "gateway_payload_chars": 0,
        "gateway_total_chars": 0,
        "gateway_timeout_sec": 0,
    }
    hyper_report = {
        "model_calls": 1,
        "model_name": "gemini-3-flash-preview",
        "model_patch_generated": True,
        "fallback_used": False,
        "total_tokens": 333,
        "token_capture_status": "measured",
        "gateway_stats_present": True,
        "gateway_usage_metadata_present": False,
        "gateway_token_source": "stats",
        "gateway_error_category": "",
        "gateway_prompt_chars": 10,
        "gateway_payload_chars": 20,
        "gateway_total_chars": 30,
        "gateway_timeout_sec": 60,
        "winner_source": "llm",
        "learning_trace": {"mempalace_verified": True},
    }

    merged = merge_guard_fallback_accounting(
        baseline_report,
        hyper_flow="hyper_sprint",
        hyper_elapsed_sec=0.12,
        hyper_report=hyper_report,
    )

    assert merged["model_calls"] == 1
    assert merged["model_name"] == "gemini-3-flash-preview"
    assert merged["model_patch_generated"] is True
    assert merged["total_tokens"] == 333
    assert merged["token_capture_status"] == "measured"
    assert merged["gateway_stats_present"] is True
    assert merged["gateway_token_source"] == "stats"
    assert merged["gateway_total_chars"] == 30
    assert merged["gateway_timeout_sec"] == 60
    assert merged["guard_fallback_from"] == {
        "flow": "hyper_sprint",
        "elapsed_sec": 0.12,
        "model_calls": 1,
        "model_name": "gemini-3-flash-preview",
        "model_patch_generated": True,
        "fallback_used": False,
        "total_tokens": 333,
        "token_capture_status": "measured",
        "gateway_stats_present": True,
        "gateway_usage_metadata_present": False,
        "gateway_token_source": "stats",
        "gateway_error_category": "",
        "gateway_prompt_chars": 10,
        "gateway_payload_chars": 20,
        "gateway_total_chars": 30,
        "gateway_timeout_sec": 60,
        "winner_source": "llm",
        "learning_trace": {"mempalace_verified": True},
    }


def test_merge_guard_fallback_accounting_does_not_mutate_input_report():
    baseline_report = {"model_calls": 0, "gateway_total_chars": 3}

    merged = merge_guard_fallback_accounting(
        baseline_report,
        hyper_flow="hyper_sprint",
        hyper_elapsed_sec=0.01,
        hyper_report={"model_calls": 2, "gateway_total_chars": 8},
    )

    assert baseline_report == {"model_calls": 0, "gateway_total_chars": 3}
    assert merged["model_calls"] == 2
    assert merged["gateway_total_chars"] == 8
