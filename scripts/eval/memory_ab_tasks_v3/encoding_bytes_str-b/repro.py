import hashlib

from cache_key import fingerprint


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


def digest(data):
    return hashlib.sha256(data).hexdigest()


check("plain strings", lambda: fingerprint(["user", "42"]), digest(b"user\x1f42"))
check("bytes mixed with str", lambda: fingerprint([b"raw", "text"]), digest(b"raw\x1ftext"))
check(
    "non-ASCII str is UTF-8",
    lambda: fingerprint(["naïve"]),
    digest("naïve".encode("utf-8")),
)
check("binary bytes survive", lambda: fingerprint([b"\xff\x00"]), digest(b"\xff\x00"))
check("no parts", lambda: fingerprint([]), digest(b""))
