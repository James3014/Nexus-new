def normalize_hosts(hosts):
    out = set()
    for h in hosts:
        normalized = h.strip().lower()
        if normalized:
            out.add(normalized)
    return sorted(out)
