def _total(entries):
    return sum(e["amount"] for e in entries)


def _count(entries):
    return sum(1 for _ in entries)


def summarize(entries):
    """Return count, total and mean of 'amount' (integer cents) over an iterable of entries."""
    total = _total(entries)
    count = _count(entries)  # BUG: a generator is already exhausted by _total
    return {"count": count, "total": total, "mean": total / count if count else 0.0}


def top_category(entries):
    """Return the category with the largest summed amount (ties: first seen), or None if empty."""
    totals = {}
    for e in entries:
        totals[e["category"]] = totals.get(e["category"], 0) + e["amount"]
    if not any(True for _ in entries):  # BUG: entries was consumed by the loop above
        return None
    return max(totals, key=totals.get)
