from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fcntl


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
