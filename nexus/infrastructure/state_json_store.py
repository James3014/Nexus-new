from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        for item in value.values():
            _validate_json_value(item)
        return
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _validate_json_object(payload: dict[str, Any]) -> None:
    _validate_json_value(payload)


def _canonical_json(payload: dict[str, Any]) -> str:
    _validate_json_object(payload)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _strict_snapshot(payload: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    """Freeze a strict JSON object before any filesystem side effect."""
    canonical = _canonical_json(payload).encode("utf-8")
    snapshot = json.loads(canonical.decode("utf-8"))
    if not isinstance(snapshot, dict):  # pragma: no cover - guarded above
        raise ValueError("state JSON must be an object")
    return snapshot, canonical


@dataclass(frozen=True)
class StateJsonStore:
    """Atomic JSON object storage for small Nexus state files."""

    indent: int = 2

    def read_dict(self, path: Path) -> dict[str, Any]:
        try:
            if not path.exists():
                return {}
            with self._locked(path, shared=True):
                payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def write_dict(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._locked(path, shared=False):
            self._atomic_write(path, payload)

    @staticmethod
    def content_digest(payload: dict[str, Any]) -> str:
        """Return the stable SHA-256 digest used by compare-and-swap."""
        canonical = _canonical_json(payload).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def compare_and_swap_dict(
        self,
        path: Path,
        expected_digest: str | None,
        payload: dict[str, Any],
    ) -> bool:
        """Write ``payload`` only when the current object matches exactly.

        The existence check, current read, digest comparison, write, and
        readback all happen while holding one exclusive file lock.
        """
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        snapshot, canonical = _strict_snapshot(payload)
        expected_output_digest = hashlib.sha256(canonical).hexdigest()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._locked(path, shared=False):
            exists = os.path.lexists(path)
            if exists and path.is_symlink():
                raise OSError("final state path must not be a symlink")
            current = self._read_dict_locked(path) if exists else None
            if expected_digest is None:
                if current is not None:
                    return False
            elif current is None or self.content_digest(current) != expected_digest:
                return False
            if os.path.lexists(path) and path.is_symlink():
                raise OSError("final state path must not be a symlink")
            self._atomic_write(path, snapshot)
            readback = self._read_dict_locked(path)
            if readback != snapshot or self.content_digest(readback) != expected_output_digest:
                raise RuntimeError("state JSON readback mismatch")
            return True

    def _read_dict_locked(self, path: Path) -> dict[str, Any]:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                fd = -1
                payload = json.load(handle, parse_constant=_reject_constant)
        finally:
            if fd >= 0:
                os.close(fd)
        if not isinstance(payload, dict):
            raise ValueError("state JSON must be an object")
        _validate_json_object(payload)
        return payload

    def _atomic_write(self, path: Path, payload: dict[str, Any]) -> None:
        temp_name = ""
        with tempfile.NamedTemporaryFile(
            "w",
            dir=path.parent,
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(payload, handle, indent=self.indent)
            handle.flush()
            os.fsync(handle.fileno())
            temp_name = handle.name
        try:
            os.replace(temp_name, path)
            self._fsync_dir(path.parent)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)

    def _fsync_dir(self, path: Path) -> None:
        try:
            dir_fd = os.open(str(path), os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def _locked(self, path: Path, *, shared: bool):
        return _FileLock(path.with_suffix(path.suffix + ".lock"), shared=shared)


class _FileLock:
    def __init__(self, path: Path, *, shared: bool) -> None:
        self.path = path
        self.shared = shared
        self._handle: Any | None = None

    def __enter__(self) -> "_FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.path, "a+", encoding="utf-8")
        flag = fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX
        fcntl.flock(self._handle.fileno(), flag)
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
