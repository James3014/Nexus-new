from datetime import datetime


def parse_at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def in_window(records, start, end):
    """Return ids of records whose 'at' lies within [start, end], ordered by instant.

    start and end are timezone-aware datetimes. Each record is a dict with an
    ISO 'at' string; a string without an offset is UTC.
    """
    hits = []
    for rec in records:
        at = parse_at(rec["at"])
        if start <= at <= end:
            hits.append((at, rec["id"]))
    hits.sort(key=lambda pair: pair[0])
    return [rid for _, rid in hits]
