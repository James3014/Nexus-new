from datetime import datetime, timezone

from audit_log import in_window

def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


utc = timezone.utc
start = datetime(2026, 5, 2, 4, 0, tzinfo=utc)
end = datetime(2026, 5, 2, 6, 30, tzinfo=utc)

records = [
    {"id": "a", "at": "2026-05-02T10:00:00+05:00"},  # 05:00Z
    {"id": "b", "at": "2026-05-02T06:00:00"},  # offset-less, read as 06:00Z
    {"id": "c", "at": "2026-05-02T04:30:00Z"},
    {"id": "d", "at": "2026-05-03T00:00:00Z"},
]
check("mixed records ordered by instant", lambda: in_window(records, start, end), ["c", "a", "b"])
check("offset-less only", lambda: in_window([{"id": "n", "at": "2026-05-02T06:00:00"}], start, end), ["n"])
bounds = [{"id": "lo", "at": "2026-05-02T04:00:00Z"}, {"id": "hi", "at": "2026-05-02T06:30:00+00:00"}]
check("bounds are inclusive", lambda: in_window(bounds, start, end), ["lo", "hi"])
# Wall clock 09:00 looks after the window, but the instant 04:00Z is inside it.
shifted = [{"id": "off", "at": "2026-05-02T09:00:00+05:00"}]
check("offset converted before comparing", lambda: in_window(shifted, start, end), ["off"])
