from tally import deep_sum


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("nested lists and tuples", lambda: deep_sum([1, [2, 3], (4, [5])]), 15)
check("empty list", lambda: deep_sum([]), 0)
check("empty tuple", lambda: deep_sum(()), 0)
check("None and empty nesting", lambda: deep_sum([None, 2.5, [None], [[]], ()]), 2.5)
check("bare number", lambda: deep_sum(7), 7)
