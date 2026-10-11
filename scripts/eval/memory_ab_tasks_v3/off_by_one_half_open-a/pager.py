def chunk_ranges(total, size):
    """Return half-open (start, stop) pairs that cover range(total) in steps of size."""
    ranges = []
    for start in range(0, total - size + 1, size):  # BUG: drops the final partial chunk
        ranges.append((start, start + size))
    return ranges
