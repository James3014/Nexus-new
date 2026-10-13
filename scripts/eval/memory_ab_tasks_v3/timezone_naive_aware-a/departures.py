from datetime import datetime


def to_instant(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def next_departure(flights, now):
    """Return the code of the soonest flight departing at or after `now`, or None.

    `now` is a timezone-aware UTC datetime. Each flight is a dict with 'code' and
    an ISO 8601 'departs' string.
    """
    upcoming = [f for f in flights if to_instant(f["departs"]) >= now]
    if not upcoming:
        return None
    soonest = min(upcoming, key=lambda f: to_instant(f["departs"]))
    return soonest["code"]
