def compact(batches):
    """Remove empty batches (empty lists) from `batches` in place.

    Returns the number of batches removed. Surviving batches keep their order.
    """
    removed = 0
    for i, batch in enumerate(batches):  # BUG: deleting shifts the later indexes
        if not batch:
            del batches[i]
            removed += 1
    return removed
