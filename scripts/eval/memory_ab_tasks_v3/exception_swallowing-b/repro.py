from profiles_store import load_profile


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


def expect_error(label, fn, exc_type):
    try:
        fn()
    except exc_type:
        return
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    raise AssertionError(f"{label}: no {exc_type.__name__} raised")


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def fetch(self, user_id):
        return self.rows[user_id]  # KeyError for an unknown user


class BrokenDB:
    def fetch(self, user_id):
        raise TimeoutError("db timed out")


db = FakeDB({"u1": {"name": "Ada"}})
check("existing user", lambda: load_profile(db, "u1"), {"name": "Ada"})
check("unknown user is None", lambda: load_profile(db, "nobody"), None)
expect_error("outage propagates", lambda: load_profile(BrokenDB(), "u1"), TimeoutError)
