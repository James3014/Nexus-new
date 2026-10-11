def drop_stale(items, max_age):
    """Remove items whose 'age' exceeds max_age, in place. Return their ids in order.

    Items with age equal to max_age are kept.
    """
    removed = []
    for item in items:
        if item["age"] > max_age:
            removed.append(item["id"])
            items.remove(item)
    return removed
