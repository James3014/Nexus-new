from names import initials

assert initials("ada lovelace") == "AL", "initials of a normal name"
try:
    got = initials(None)
except Exception as exc:
    raise AssertionError(f"initials(None) raised {type(exc).__name__}")
assert got == "", f"initials(None) got {got!r} want empty string"
