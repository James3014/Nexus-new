import hashlib

SEP = "\x1f"


def fingerprint(parts):
    """Return the sha256 hex digest of parts joined by a 0x1f byte.

    Each part is str (UTF-8 encoded) or bytes (used unchanged).
    """
    joined = SEP.join(parts)
    return hashlib.sha256(joined).hexdigest()
