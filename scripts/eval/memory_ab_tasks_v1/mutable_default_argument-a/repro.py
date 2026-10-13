from tags import collect_tags

first = collect_tags("a")
second = collect_tags("b")
assert first == ["a"] and second == ["b"], f"leaked state: first={first!r} second={second!r}"
