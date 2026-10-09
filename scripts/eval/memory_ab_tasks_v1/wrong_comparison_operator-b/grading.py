def has_passing(scores, threshold):
    """True when at least one score is greater than or equal to threshold."""
    return any(s > threshold for s in scores)  # BUG: should be >=
