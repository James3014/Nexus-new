from stock import drop_stale


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


def make(pairs):
    return [{"id": ident, "age": age} for ident, age in pairs]


items = make([("a", 12), ("b", 12), ("c", 3), ("d", 20), ("e", 11)])
check("removed ids in order", lambda: drop_stale(items, 10), ["a", "b", "d", "e"])
check("survivor stays in the same list", lambda: [i["id"] for i in items], ["c"])

boundary = make([("f", 10), ("g", 10), ("h", 11)])
check("age equal to max_age is kept", lambda: drop_stale(boundary, 10), ["h"])
check("nothing to drop", lambda: drop_stale(make([("k", 1)]), 10), [])
