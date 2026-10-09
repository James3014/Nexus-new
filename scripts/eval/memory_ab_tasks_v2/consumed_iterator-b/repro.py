from table_reader import read_table


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


t = read_table(iter([["id", "qty"], ["a", "1"], ["b", "2"]]))
check("columns", lambda: t["columns"], ["id", "qty"])
check("records", lambda: t["records"], [{"id": "a", "qty": "1"}, {"id": "b", "qty": "2"}])
check("row_count", lambda: t["row_count"], 2)
check("header only", lambda: read_table(iter([["x"]]))["row_count"], 0)
