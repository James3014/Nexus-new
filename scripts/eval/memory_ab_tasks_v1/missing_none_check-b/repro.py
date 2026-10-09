from directory import find_user_email

users = [{"id": 1, "email": "A@X.com"}]
assert find_user_email(users, 1) == "a@x.com", "found user email"
try:
    got = find_user_email(users, 99)
except Exception as exc:
    raise AssertionError(f"missing user raised {type(exc).__name__}")
assert got is None, f"missing user got {got!r} want None"
