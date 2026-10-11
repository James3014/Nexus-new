from datetime import datetime, timezone

from leases import active_leases


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


now = datetime(2026, 3, 1, 7, 0, tzinfo=timezone.utc)

leases = [
    {"id": "L1", "start": "2026-03-01T06:00:00", "end": "2026-03-01T09:00:00"},
    # 07:30+01:00 is 06:30Z: active, although its wall-clock text is after now.
    {"id": "L2", "start": "2026-03-01T07:30:00+01:00", "end": "2026-03-01T08:00:00Z"},
    # End is exclusive: ending exactly at now means not active.
    {"id": "L3", "start": "2026-03-01T05:00:00", "end": "2026-03-01T07:00:00"},
    {"id": "L4", "start": "2026-03-01T07:00:00+00:00", "end": "2026-03-01T10:00:00"},
    {"id": "L5", "start": "2026-03-01T08:00:00", "end": "2026-03-01T09:00:00"},
]
check("mixed naive and offset windows", lambda: active_leases(leases, now), ["L1", "L2", "L4"])
check("no active lease", lambda: active_leases(leases[4:], now), [])
check(
    "start equal to now is active",
    lambda: active_leases(
        [{"id": "S", "start": "2026-03-01T07:00:00", "end": "2026-03-01T08:00:00"}], now
    ),
    ["S"],
)
