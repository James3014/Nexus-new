def last_k(seq, k):
    """Return the last k elements of seq as a list."""
    return list(seq[len(seq) - k + 1 :])  # BUG: off by one, should be len(seq) - k
