"""Keyed digests for the unauthenticated Gateway ``/health`` (#2226).

A plain ``sha256(path)`` is guessable (the paths are predictable), so a local
process could confirm a guess.  ``/health`` therefore publishes
``HMAC-SHA256(per-host secret, label || path)``.  The secret lives in a 0600
file under the user's state dir (``NEXUS_GATEWAY_HEALTH_HMAC_KEY_FILE``
overrides the location) and is created atomically.  Only processes that can
read that file (the Gateway and the GB-077 probe on the same host) can compute
or verify the digests.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import stat
from pathlib import Path

KEY_FILE_ENV = "NEXUS_GATEWAY_HEALTH_HMAC_KEY_FILE"
_KEY_BYTES = 32
_MIN_KEY_HEX = _KEY_BYTES * 2


class HealthHmacKeyError(RuntimeError):
    """The per-host key is missing, unreadable, too permissive or malformed."""


def key_file_path(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    override = env.get(KEY_FILE_ENV)
    if override:
        return Path(override)
    return Path.home() / ".local/state/nexus-gateway/health-hmac.key"


def _read_key(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise HealthHmacKeyError("health hmac key file must be a regular file with mode 0600")
        text = os.read(fd, 4096).decode("ascii", "replace").strip()
    finally:
        os.close(fd)
    if len(text) < _MIN_KEY_HEX or any(c not in "0123456789abcdef" for c in text):
        raise HealthHmacKeyError("health hmac key file is malformed")
    return bytes.fromhex(text)


def load_or_create_key(path: Path | None = None) -> bytes:
    """Return the per-host key, creating it atomically (0600, never overwritten)."""
    target = path or key_file_path()
    try:
        return _read_key(target)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise HealthHmacKeyError(f"health hmac key unreadable: {type(exc).__name__}") from exc
    try:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, (secrets.token_hex(_KEY_BYTES) + "\n").encode("ascii"))
        finally:
            os.close(fd)
        try:
            os.link(tmp, target)  # fails if another process created it first
        except FileExistsError:
            pass
        finally:
            tmp.unlink(missing_ok=True)
        return _read_key(target)
    except OSError as exc:
        raise HealthHmacKeyError(f"health hmac key unavailable: {type(exc).__name__}") from exc


def path_hmac(label: str, value: str, key: bytes) -> str:
    """HMAC-SHA256 of ``value`` domain-separated by ``label`` (e.g. ``repo_root``)."""
    message = label.encode("utf-8") + b"\0" + value.encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def path_hmac_or_none(label: str, value: str) -> str | None:
    """Digest for ``/health``; ``None`` (never a path-derived plain hash) if no key."""
    try:
        return path_hmac(label, value, load_or_create_key())
    except HealthHmacKeyError:
        return None
