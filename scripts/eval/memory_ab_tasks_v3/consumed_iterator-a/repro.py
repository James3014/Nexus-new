from manifest import summarize


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


SOURCE = [{"id": "a", "kg": 1.5}, {"id": "b", "kg": 2.25}, {"id": "c", "kg": 2.25}]

check("list input", lambda: summarize(SOURCE), (3, 6.0, "b"))
check("generator input", lambda: summarize(p for p in SOURCE), (3, 6.0, "b"))
check("tuple input", lambda: summarize(tuple(SOURCE)), (3, 6.0, "b"))
check("empty generator", lambda: summarize(p for p in []), (0, 0.0, None))
check("single item iterator", lambda: summarize(iter([{"id": "z", "kg": 4.0}])), (1, 4.0, "z"))
