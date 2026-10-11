def describe(readings):
    """Return (spread, count) for an iterable of numeric readings.

    spread is max minus min. An empty input gives (0, 0).
    """
    count = sum(1 for _ in readings)
    if count == 0:
        return 0, 0
    return max(readings) - min(readings), count
