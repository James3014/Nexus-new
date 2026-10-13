from datetime import datetime


def read_stamp(text):
    return datetime.fromisoformat(text)


def active_leases(leases, now):
    """Return sorted ids of leases with start <= now < end. `now` is aware UTC."""
    found = []
    for lease in leases:
        start = read_stamp(lease["start"])
        end = read_stamp(lease["end"])
        if start <= now < end:
            found.append(lease["id"])
    return sorted(found)
