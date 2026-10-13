from batches import compact


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


b = [[], [], [1], [], [], [2, 3]]
same = b
removed = compact(b)
check("removed count", lambda: removed, 4)
check("survivors in order", lambda: b, [[1], [2, 3]])
check("same list object", lambda: b is same, True)

all_empty = [[], []]
gone = compact(all_empty)
check("all empty", lambda: (gone, all_empty), (2, []))

keep = [[1], [2]]
none_gone = compact(keep)
check("nothing empty", lambda: (none_gone, keep), (0, [[1], [2]]))
