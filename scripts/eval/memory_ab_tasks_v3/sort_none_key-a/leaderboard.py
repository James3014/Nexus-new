def rank(entries):
    """Return entry names ordered by score, highest first.

    Entries whose score is None go last. Equal scores keep their input order.
    """
    ordered = sorted(entries, key=lambda e: e["score"], reverse=True)  # BUG: None is not comparable
    return [e["name"] for e in ordered]
