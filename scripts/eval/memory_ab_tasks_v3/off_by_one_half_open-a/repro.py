from pager import chunk_ranges


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("short final chunk", lambda: chunk_ranges(10, 4), [(0, 4), (4, 8), (8, 10)])
check("exact multiple", lambda: chunk_ranges(8, 4), [(0, 4), (4, 8)])
check("total smaller than size", lambda: chunk_ranges(3, 5), [(0, 3)])
check("empty total", lambda: chunk_ranges(0, 4), [])
check("chunks cover every item", lambda: sum(b - a for a, b in chunk_ranges(23, 7)), 23)
