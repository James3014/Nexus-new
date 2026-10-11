from menu_tree import tree_depth


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("no node", lambda: tree_depth(None), 0)
check("missing children key", lambda: tree_depth({"name": "Home"}), 1)
check("empty children list", lambda: tree_depth({"name": "Settings", "children": []}), 1)
tree = {
    "name": "root",
    "children": [
        {"name": "a", "children": [{"name": "deep"}]},
        {"name": "b", "children": []},
    ],
}
check("uneven nested tree", lambda: tree_depth(tree), 3)
