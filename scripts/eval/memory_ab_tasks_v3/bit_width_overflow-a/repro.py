from fnv import fnv1a32


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("empty input", lambda: fnv1a32(b""), 2166136261)
check("single letter", lambda: fnv1a32(b"a"), 3826002220)
check("value above 2**31", lambda: fnv1a32(b"foobar"), 3214735720)
check("high bit byte", lambda: fnv1a32(b"\xff"), 2047574606)
