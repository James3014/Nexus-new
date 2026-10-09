def drop_expired(records, now):
    """Remove records whose 'expires_at' is <= now, in place.

    Keeps the same list object and the relative order of the survivors.
    Returns the ids of the removed records in their original order.
    """
    removed = []
    for record in records:  # BUG: removing while iterating skips the next element
        if record["expires_at"] <= now:
            removed.append(record["id"])
            records.remove(record)
    return removed
