from sensor_log import describe


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("map input", lambda: describe(map(float, ["3", "9", "4"])), (6.0, 3))
check("single reading iterator", lambda: describe(iter([7])), (0, 1))
check("generator of floats", lambda: describe(r for r in [1.5, -2.5]), (4.0, 2))
check("empty generator", lambda: describe(r for r in ()), (0, 0))
