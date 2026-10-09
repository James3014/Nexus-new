def flatten(value):
    """Flatten nested lists and tuples into a flat list of leaves.

    Strings, dicts and None are leaves. Empty containers contribute nothing.
    """
    if isinstance(value, list):
        if not value:
            return [value]  # BUG: an empty list is emitted as a leaf
        out = []
        for item in value:
            out.extend(flatten(item))
        return out
    return [value]  # BUG: tuples are not recursed into
