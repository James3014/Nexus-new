import hashlib
import hmac

from webhook_sig import sign


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


def oracle(body, key):
    return hmac.new(key, body, hashlib.sha256).hexdigest()


check("str body and secret", lambda: sign("payload", "s3cret"), oracle(b"payload", b"s3cret"))
check("bytes body and secret", lambda: sign(b"payload", b"s3cret"), oracle(b"payload", b"s3cret"))
check(
    "non-ASCII str is UTF-8",
    lambda: sign("café", "ключ"),
    oracle("café".encode("utf-8"), "ключ".encode("utf-8")),
)
check("empty body", lambda: sign("", "k"), oracle(b"", b"k"))
