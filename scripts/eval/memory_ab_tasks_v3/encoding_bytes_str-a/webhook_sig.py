import hashlib
import hmac


def sign(body, secret):
    """Return the lowercase hex HMAC-SHA256 of body keyed by secret.

    body and secret may each be str (UTF-8 encoded) or bytes (used unchanged).
    """
    return hmac.new(secret, body, hashlib.sha256).hexdigest()
