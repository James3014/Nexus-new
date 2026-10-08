from leaf_paths import leaf_paths

def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("nested dict and list", lambda: leaf_paths({"a": 1, "b": {"c": [2, 3]}}), [(("a",), 1), (("b", "c", 0), 2), (("b", "c", 1), 3)])
check("empty dict skipped", lambda: leaf_paths({"a": {}, "b": 1}), [(("b",), 1)])
check("None is a leaf", lambda: leaf_paths({"a": None}), [(("a",), None)])
check("empty top-level containers", lambda: leaf_paths([{}, [], {"x": {}}]), [])
check("empty dict inside list", lambda: leaf_paths({"k": [{"n": None}, {}]}), [(("k", 0, "n"), None)])
