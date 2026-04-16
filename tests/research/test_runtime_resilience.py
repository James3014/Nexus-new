import pytest
from nexus.research.runtime.runtime_resilience import compute_time_budget, get_retry_delay, classify_infra_block, RetryParams

def test_time_budget():
    assert compute_time_budget(60) == 66
    assert compute_time_budget(100, buffer_ratio=0.2) == 120

def test_retry_delay():
    p = RetryParams(attempt=1, max_retries=3, base_delay=1.0, jitter=False)
    assert get_retry_delay(p) == 1.0
    p.attempt = 2
    assert get_retry_delay(p) == 2.0

def test_classify_infra_block():
    assert classify_infra_block("429 Too Many Requests") == "infra_blocked:quota"
    assert classify_infra_block("Gateway Timeout") == "infra_blocked:timeout"
    assert classify_infra_block("Internal algorithm fail") is None
