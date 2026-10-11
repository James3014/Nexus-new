from ini_sections import section_names


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check(
    "two headers with keys between",
    lambda: section_names("[core]\nname = x\n[net]\nport = 1\n"),
    ["core", "net"],
)
check("bracketed value is not a header", lambda: section_names("x = [1, 2]\n[core]\n"), ["core"])
check("blank line between headers", lambda: section_names("[a]\n\n[b]"), ["a", "b"])
check("header with trailing text", lambda: section_names("[one] trailing\n[two]"), ["two"])
