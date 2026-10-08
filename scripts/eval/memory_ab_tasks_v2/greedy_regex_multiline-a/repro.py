from markers import extract_blocks

def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("multiple blocks", lambda: extract_blocks("x <<begin>>one<<end>> y <<begin>>two<<end>>"), ["one", "two"])
check("multi-line block", lambda: extract_blocks("<<begin>>\n  a = 1\n  b = 2\n<<end>>"), ["a = 1\n  b = 2"])
check("empty block", lambda: extract_blocks("<<begin>><<end>>"), [""])
check("unclosed ignored", lambda: extract_blocks("<<begin>>oops"), [])
check("no markers", lambda: extract_blocks("plain text"), [])
