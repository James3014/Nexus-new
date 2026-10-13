from flatten import flatten


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("nested lists and tuples", lambda: flatten([1, (2, 3), [4, (5, [6])]]), [1, 2, 3, 4, 5, 6])
check("None kept, empties dropped", lambda: flatten([None, [], (), [[]], 0]), [None, 0])
check("strings are leaves", lambda: flatten(["ab", ("c",)]), ["ab", "c"])
check("dicts are leaves", lambda: flatten([{"k": [1]}]), [{"k": [1]}])
check("top-level empties", lambda: (flatten([]), flatten(())), ([], []))
