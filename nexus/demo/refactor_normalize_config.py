def normalize_hosts(hosts):
    out = []
    for h in hosts:
        if h:
            out.append(h.strip().lower())
    # BUG: duplicate entries are not removed and order is unstable for consumers.
    return out
