from nexus.research.hybrid_replication_live import _complete_token_usage_metrics


def test_complete_token_usage_metrics_preserves_unavailable_as_unknown() -> None:
    assert _complete_token_usage_metrics({}) == (None, None, None)
    assert _complete_token_usage_metrics({"input_tokens": 50, "output_tokens": 10}, {}) == (
        None,
        None,
        None,
    )


def test_complete_token_usage_metrics_preserves_observed_totals() -> None:
    assert _complete_token_usage_metrics(
        {"input_tokens": 50, "output_tokens": 10},
        {"input_tokens": 80, "cached_input_tokens": 20, "output_tokens": 20},
    ) == (130, 110, 30)
