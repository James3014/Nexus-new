from listing import order_files


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check(
    "dated oldest first, undated last",
    lambda: order_files([
        {"name": "b.txt", "modified": "2026-02-01"},
        {"name": "a.txt", "modified": "2026-01-05"},
        {"name": "c.txt", "modified": None},
    ]),
    ["a.txt", "b.txt", "c.txt"],
)
check(
    "same date sorted by name",
    lambda: order_files([
        {"name": "z.md", "modified": "2026-01-01"},
        {"name": "m.md", "modified": "2026-01-01"},
    ]),
    ["m.md", "z.md"],
)
check(
    "undated sorted by name",
    lambda: order_files([{"name": "q", "modified": None}, {"name": "c", "modified": None}]),
    ["c", "q"],
)
check("no files", lambda: order_files([]), [])
