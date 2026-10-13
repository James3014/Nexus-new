DEFAULTS = {"retries": 3, "timeout_seconds": 30}


def effective_timeout(overrides):
    """Timeout after applying overrides on top of DEFAULTS."""
    merged = dict(DEFAULTS)
    merged.update(overrides)
    return merged["timeout_secs"]  # BUG: key typo, should be "timeout_seconds"
