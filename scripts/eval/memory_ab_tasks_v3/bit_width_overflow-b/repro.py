from ids import pack_id, unpack_id


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


check("large sequence round-trips", lambda: unpack_id(pack_id(3, 2**45)), (3, 2**45))
check("shard lands in high bits", lambda: pack_id(1, 0), 1 << 48)
check("max fields round-trip", lambda: unpack_id(pack_id(65535, 2**48 - 1)), (65535, 2**48 - 1))
expect_error("sequence too wide", lambda: pack_id(1, 2**48), ValueError)
