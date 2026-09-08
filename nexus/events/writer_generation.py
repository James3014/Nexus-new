"""Source-owned opt-in writer generation manifest for the EventStore."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

SCHEMA = "nexus.event_writer_generation.v1"
STORE = "event_log"
MANIFEST_NAME = "event_log.generation.v1.json"
MANIFEST_DIGEST = "manifest_digest"


class GenerationError(RuntimeError):
    """Base class for fail-closed generation manifest errors."""


class GenerationConflict(GenerationError):
    """The requested CAS predecessor is not the current generation."""


@dataclass(frozen=True)
class EventWriterGeneration:
    generation: int
    writer_id: str

    def __post_init__(self) -> None:
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 1:
            raise ValueError("generation must be a positive integer")
        if not isinstance(self.writer_id, str) or not self.writer_id.strip():
            raise ValueError("writer_id is required")


def manifest_path(project_root: Path) -> Path:
    return Path(project_root) / ".nexus" / "events" / MANIFEST_NAME


def _payload(generation: int, writer_id: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "store": STORE,
        "event_log": "event_log.jsonl",
        "lock": "event_log.lock",
        "generation": generation,
        "writer_id": writer_id,
    }


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validated(data: Mapping[str, Any]) -> EventWriterGeneration:
    if not isinstance(data, Mapping):
        raise GenerationError("GENERATION_MANIFEST_MALFORMED")
    required = set(_payload(1, "x")) | {MANIFEST_DIGEST}
    if set(data) != required or data.get("schema") != SCHEMA or data.get("store") != STORE:
        raise GenerationError("GENERATION_MANIFEST_MALFORMED")
    if data.get("event_log") != "event_log.jsonl" or data.get("lock") != "event_log.lock":
        raise GenerationError("GENERATION_MANIFEST_MALFORMED")
    generation = data.get("generation")
    writer_id = data.get("writer_id")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise GenerationError("GENERATION_MANIFEST_MALFORMED")
    if not isinstance(writer_id, str) or not writer_id.strip():
        raise GenerationError("GENERATION_MANIFEST_MALFORMED")
    payload = {k: data[k] for k in required if k != MANIFEST_DIGEST}
    if data.get(MANIFEST_DIGEST) != _digest(payload):
        raise GenerationError("GENERATION_MANIFEST_TAMPERED")
    return EventWriterGeneration(generation, writer_id)


def read_generation(project_root: Path) -> EventWriterGeneration | None:
    path = manifest_path(project_root)
    try:
        path_stat = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(path_stat.st_mode):
        raise GenerationError("GENERATION_MANIFEST_SYMLINK")
    if not stat.S_ISREG(path_stat.st_mode):
        raise GenerationError("GENERATION_MANIFEST_MALFORMED")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise GenerationError("GENERATION_MANIFEST_MALFORMED")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return _validated(data)
    except GenerationError:
        raise
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise GenerationError("GENERATION_MANIFEST_MALFORMED") from exc


@contextmanager
def event_store_lock(project_root: Path, *, timeout: float = 5.0) -> Iterator[None]:
    lock_path = Path(project_root) / ".nexus" / "events" / "event_log.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_stat = os.lstat(lock_path)
        if stat.S_ISLNK(lock_stat.st_mode) or not stat.S_ISREG(lock_stat.st_mode):
            raise GenerationError("GENERATION_LOCK_UNSAFE")
    except FileNotFoundError:
        pass
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags | getattr(os, "O_NONBLOCK", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise GenerationError("GENERATION_LOCK_UNSAFE")
    except Exception:
        os.close(fd)
        raise
    with os.fdopen(fd, "a+", encoding="utf-8") as lock:
        deadline = time.monotonic() + float(timeout)
        while True:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise GenerationError("GENERATION_LOCK_TIMEOUT")
                time.sleep(0.01)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def install_generation(project_root: Path, generation: EventWriterGeneration, *, expected_generation: int | None = None) -> EventWriterGeneration:
    """Atomically install/advance the manifest under the existing EventStore lock."""
    if not isinstance(generation, EventWriterGeneration):
        raise GenerationError("GENERATION_TOKEN_MALFORMED")
    if expected_generation is not None and (
        isinstance(expected_generation, bool)
        or not isinstance(expected_generation, int)
        or expected_generation < 1
    ):
        raise GenerationError("GENERATION_CAS_MALFORMED")
    path = manifest_path(project_root)
    with event_store_lock(project_root):
        current = read_generation(project_root)
        current_number = current.generation if current else None
        if expected_generation != current_number:
            raise GenerationConflict("GENERATION_CAS_CONFLICT")
        if current and generation.generation <= current.generation:
            raise GenerationConflict("GENERATION_MUST_ADVANCE")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _payload(generation.generation, generation.writer_id)
        document = dict(payload)
        document[MANIFEST_DIGEST] = _digest(payload)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    return generation
