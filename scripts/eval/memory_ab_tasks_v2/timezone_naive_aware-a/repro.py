from datetime import datetime, timezone

from schedule import earliest_due


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


now = datetime(2026, 3, 1, 7, 0, tzinfo=timezone.utc)

# Offsets are compared by instant: 10:00+02:00 is 08:00Z, before 09:30Z.
mixed = [
    {"id": "wall-clock-later", "due": "2026-03-01T09:30:00Z"},
    {"id": "offset-earlier", "due": "2026-03-01T10:00:00+02:00"},
]
check("offset instant ordering", lambda: earliest_due(mixed, now), "offset-earlier")

# A timestamp without an offset is read as UTC (08:15Z here).
naive = [
    {"id": "aware-later", "due": "2026-03-01T08:30:00+00:00"},
    {"id": "naive", "due": "2026-03-01T08:15:00"},
]
check("naive timestamp accepted", lambda: earliest_due(naive, now), "naive")

# Past-due tasks are ignored even when they would sort first.
past = [
    {"id": "past", "due": "2026-03-01T05:00:00+00:00"},
    {"id": "future", "due": "2026-03-01T12:00:00"},
]
check("past tasks skipped", lambda: earliest_due(past, now), "future")

# A naive timestamp equal to now is still pending.
exact = [{"id": "exact", "due": "2026-03-01T07:00:00"}]
check("equal-to-now is pending", lambda: earliest_due(exact, now), "exact")

check(
    "nothing pending", lambda: earliest_due([{"id": "x", "due": "2026-03-01T01:00:00Z"}], now), None
)
