import time
from nexus.demo.feature_rate_limiter import RateLimiter

def test_rate_limiter_window_reset():
    rl = RateLimiter(limit=2, window_sec=0.05)
    assert rl.allow() is True
    assert rl.allow() is True
    assert rl.allow() is False
    time.sleep(0.06)
    # After window, one new request should be allowed.
    assert rl.allow() is True
