from datetime import datetime, timezone

from departures import next_departure


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


now = datetime(2026, 3, 1, 7, 0, tzinfo=timezone.utc)

# Offsets are compared by instant: 10:00+02:00 is 08:00Z, before 09:30Z.
mixed = [
    {"code": "WALL", "departs": "2026-03-01T09:30:00Z"},
    {"code": "OFFSET", "departs": "2026-03-01T10:00:00+02:00"},
]
check("offset instant ordering", lambda: next_departure(mixed, now), "OFFSET")

# A timestamp without an offset is read as UTC (08:15Z here).
naive = [
    {"code": "AWARE", "departs": "2026-03-01T08:30:00+00:00"},
    {"code": "NAIVE", "departs": "2026-03-01T08:15:00"},
]
check("naive timestamp read as UTC", lambda: next_departure(naive, now), "NAIVE")

past = [
    {"code": "PAST", "departs": "2026-03-01T05:00:00+00:00"},
    {"code": "LATER", "departs": "2026-03-01T12:00:00"},
]
check("past flights skipped", lambda: next_departure(past, now), "LATER")

exact = [{"code": "EXACT", "departs": "2026-03-01T07:00:00"}]
check("equal to now is upcoming", lambda: next_departure(exact, now), "EXACT")

check(
    "nothing upcoming",
    lambda: next_departure([{"code": "X", "departs": "2026-03-01T01:00:00Z"}], now),
    None,
)
