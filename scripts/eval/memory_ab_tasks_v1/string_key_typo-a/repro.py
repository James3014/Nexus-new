from settings import effective_timeout

try:
    got = effective_timeout({})
except KeyError as exc:
    raise AssertionError(f"KeyError {exc} for default config")
assert got == 30, f"effective_timeout({{}}) got {got!r} want 30"
