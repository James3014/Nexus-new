from records import build_record

build_record("x")
rec = build_record("y")
assert rec.get("name") == "y", f"second call name={rec.get('name')!r}"
