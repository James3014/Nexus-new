from scripts.bench.provider_retry import direct_model_retryable_infra_failure


def test_parse_failure_retry_depends_on_measured_token_status():
    retryable, reason = direct_model_retryable_infra_failure(
        {
            "error_category": "parse_failure",
            "tokens_used": 517,
            "token_capture_status": "estimated",
        },
        "stats_outlier_possible_cumulative",
    )
    assert retryable is True
    assert reason == "parse_failure_without_measured_tokens"

    retryable, reason = direct_model_retryable_infra_failure(
        {
            "error_category": "parse_failure",
            "tokens_used": 321,
            "token_capture_status": "measured",
        },
        "not-json",
    )
    assert retryable is False
    assert reason == ""


def test_invalid_session_is_retryable_but_auth_and_quota_are_not():
    retryable, reason = direct_model_retryable_infra_failure(
        {"error_category": "cli_error", "tokens_used": 0},
        'Error resuming session: Invalid session identifier "abc"',
    )
    assert retryable is True
    assert reason == "gemini_invalid_session_identifier"

    retryable, reason = direct_model_retryable_infra_failure(
        {"error_category": "cli_error", "tokens_used": 0},
        "login required",
    )
    assert retryable is False
    assert reason == "auth_or_permission"

    retryable, reason = direct_model_retryable_infra_failure(
        {"error_category": "cli_error", "tokens_used": 0},
        "429 resource exhausted",
    )
    assert retryable is False
    assert reason == "quota_or_rate_limit"
