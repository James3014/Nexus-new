def parse_pairs(items):
    # BUG: mutates caller list and mishandles whitespace-only entries.
    items[:] = [x for x in items if x]
    out = {}
    for it in items:
        if "=" not in it:
            continue
        k, v = it.split("=", 1)
        out[k] = v
    return out
