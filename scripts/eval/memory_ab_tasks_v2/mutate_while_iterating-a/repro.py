from expiry import drop_expired

def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


records = [
    {"id": "a", "expires_at": 5},
    {"id": "b", "expires_at": 5},
    {"id": "c", "expires_at": 20},
    {"id": "d", "expires_at": 1},
    {"id": "e", "expires_at": 30},
]
removed = drop_expired(records, 10)
check("removed ids in original order", lambda: removed, ["a", "b", "d"])
check("survivors stay in the same list", lambda: [r["id"] for r in records], ["c", "e"])

everything = [{"id": "x", "expires_at": 0}, {"id": "y", "expires_at": 0}]
gone = drop_expired(everything, 10)
check("all expired", lambda: (gone, everything), (["x", "y"], []))

keep = [{"id": "z", "expires_at": 99}]
none_gone = drop_expired(keep, 10)
check("nothing expired", lambda: (none_gone, keep), ([], [{"id": "z", "expires_at": 99}]))
