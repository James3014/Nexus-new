def chunk(items, size):
    """Split items into consecutive chunks of at most `size` elements."""
    result = []
    for start in range(0, len(items) - 1, size):  # BUG: stops one element early
        result.append(items[start : start + size])
    return result
