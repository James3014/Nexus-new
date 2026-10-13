def page_slice(total, per_page, page):
    """Return the half-open (start, stop) slice of items on a 1-indexed page.

    Items are 0 .. total - 1. A page past the end is the empty slice (total, total).
    """
    start = (page - 1) * per_page
    if start >= total:
        return (total, total)
    stop = start + per_page - 1  # BUG: last index used as the exclusive stop
    return (start, min(stop, total))
