from templates import placeholders


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check(
    "spaced and tight names", lambda: placeholders("Hi {{ first }}, {{last}}!"), ["first", "last"]
)
check("unclosed brace on a line", lambda: placeholders("Dear {{ oops\nHi {{ name }}"), ["name"])
check("adjacent placeholders", lambda: placeholders("{{a}}{{b}}"), ["a", "b"])
check("one per line", lambda: placeholders("{{ x }}\n{{ y }}\nno tags"), ["x", "y"])
