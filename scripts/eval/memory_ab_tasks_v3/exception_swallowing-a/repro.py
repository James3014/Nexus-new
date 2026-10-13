from settings import load_port


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


def expect_error(label, fn, exc_type):
    try:
        fn()
    except exc_type:
        return
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    raise AssertionError(f"{label}: no {exc_type.__name__} raised")


check("plain number", lambda: load_port("8443"), 8443)
check("padded number", lambda: load_port(" 9000 "), 9000)
check("blank and missing use default", lambda: [load_port(None), load_port("  ")], [8080, 8080])
expect_error("trailing letters", lambda: load_port("80a"), ValueError)
expect_error("out of range", lambda: load_port("70000"), ValueError)
