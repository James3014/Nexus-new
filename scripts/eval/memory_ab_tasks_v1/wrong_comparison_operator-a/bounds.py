def is_in_range(x, lo, hi):
    """Return True when lo <= x <= hi."""
    return lo < x <= hi  # BUG: lower bound must be inclusive
