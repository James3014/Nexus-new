from leaderboard import rank


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check(
    "unscored entry goes last",
    lambda: rank([
        {"name": "a", "score": 5},
        {"name": "b", "score": None},
        {"name": "c", "score": 9},
    ]),
    ["c", "a", "b"],
)
check(
    "ties keep input order",
    lambda: rank([{"name": "x", "score": 3}, {"name": "y", "score": 7}, {"name": "z", "score": 3}]),
    ["y", "x", "z"],
)
check(
    "all unscored keep input order",
    lambda: rank([{"name": "p", "score": None}, {"name": "q", "score": None}]),
    ["p", "q"],
)
check("no entries", lambda: rank([]), [])
