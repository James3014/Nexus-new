from datetime import datetime


def parse_due(text):
    """Parse an ISO-8601 due timestamp. Naive timestamps are UTC by convention."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def earliest_due(tasks, now):
    """Return the id of the pending task with the earliest due instant, or None.

    `now` is a timezone-aware UTC datetime. A task is pending when its due
    instant is not before `now`. Each task is a dict with an ISO 'due' string.
    """
    best = None
    best_due = None
    for task in tasks:
        due = parse_due(task["due"])
        if due < now:
            continue
        if best_due is None or due < best_due:
            best, best_due = task, due
    return best["id"] if best else None
