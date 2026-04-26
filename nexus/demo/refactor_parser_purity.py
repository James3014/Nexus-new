def parse_pairs(items):
    out = {}
    for it in items:
        it = it.strip()
        if not it:
            continue
        if "=" not in it:
            continue
        k, v = it.split("=", 1)
        out[k.strip()] = v.strip()
    return out
