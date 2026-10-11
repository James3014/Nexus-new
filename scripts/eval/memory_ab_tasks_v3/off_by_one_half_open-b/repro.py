from paging import page_slice


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("first page", lambda: page_slice(10, 4, 1), (0, 4))
check("middle page", lambda: page_slice(10, 4, 2), (4, 8))
check("short last page", lambda: page_slice(10, 4, 3), (8, 10))
check("exact multiple last page", lambda: page_slice(8, 4, 2), (4, 8))
check("page past the end", lambda: page_slice(10, 4, 9), (10, 10))
