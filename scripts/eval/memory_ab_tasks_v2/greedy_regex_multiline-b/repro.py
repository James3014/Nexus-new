from comments import strip_comments


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


def squash(text):
    return " ".join(text.split())


check(
    "two comments on one line",
    lambda: squash(strip_comments("a = 1 /* x */ b = 2 /* y */ c = 3")),
    "a = 1 b = 2 c = 3",
)
check(
    "multi-line comment",
    lambda: squash(strip_comments("x = 1\n/* line one\nline two */\ny = 2")),
    "x = 1 y = 2",
)
check("empty comment", lambda: squash(strip_comments("p /**/ q")), "p q")
check("star inside comment", lambda: squash(strip_comments("u /* a * b */ v")), "u v")
check(
    "division and multiplication untouched",
    lambda: squash(strip_comments("r = a / b * c")),
    "r = a / b * c",
)
