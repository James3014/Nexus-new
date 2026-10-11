from sessions import expire_sessions


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


store = {
    "t1": {"until": 5},
    "t2": {"until": 20},
    "t3": {"until": 9},
    "t4": {"until": 10},
}
check("expired tokens returned sorted", lambda: expire_sessions(store, 10), ["t1", "t3"])
check("live sessions kept", lambda: sorted(store), ["t2", "t4"])
check("nothing left to expire", lambda: expire_sessions(store, 10), [])
check("empty store", lambda: expire_sessions({}, 10), [])
