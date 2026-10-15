import contextlib
import fcntl
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from pydantic import BaseModel

def canonical_lock_key(workspace_root: str | Path, path: str | Path) -> str:
    """One registry key per physical file: resolved against ``workspace_root``; inside it the
    workspace-relative POSIX path, outside it the resolved absolute path. So ``target.py``,
    ``./target.py`` and ``/abs/ws/target.py`` all lock the same entry."""
    root = Path(workspace_root).expanduser().resolve()
    candidate = Path(str(path)).expanduser()
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return str(resolved)


class LockEntry(BaseModel):
    task_id: str
    files: List[str]

class FileLockRegistry:
    """One registry file shared by every task: ``locks`` maps file path -> holder task id.

    acquire/release re-read the file under an exclusive ``flock`` so two processes (two
    tasks) see each other's locks.  A lock older than ``ttl_sec`` (when set) is stale and
    may be taken over; the takeover is reported by ``acquire_detailed``.
    """

    def __init__(
        self,
        lock_file: str = ".nexus/multi_agent/locks/file_locks.json",
        *,
        ttl_sec: Optional[float] = None,
    ):
        self.lock_file = Path(lock_file)
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_sec = ttl_sec
        self.locks: Dict[str, str] = {}  # file_path -> task_id (holder)
        self.acquired_at: Dict[str, float] = {}  # file_path -> epoch seconds
        self._load()

    @contextlib.contextmanager
    def _exclusive(self) -> Iterator[None]:
        guard = self.lock_file.with_name(self.lock_file.name + ".flock")
        with open(guard, "a") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                self._load()
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def _load(self):
        self.locks, self.acquired_at = {}, {}
        if self.lock_file.exists():
            try:
                with open(self.lock_file, "r") as f:
                    data = json.load(f)
                self.locks = dict(data.get("locks", {}))
                self.acquired_at = {
                    k: float(v) for k, v in dict(data.get("acquired_at", {})).items()
                }
            except Exception:
                self.locks, self.acquired_at = {}, {}

    def _save(self):
        tmp = self.lock_file.with_name(self.lock_file.name + ".tmp")
        with open(tmp, "w") as f:
            json.dump({"locks": self.locks, "acquired_at": self.acquired_at}, f, indent=2)
        os.replace(tmp, self.lock_file)

    def _stale(self, path: str, now: float) -> bool:
        if self.ttl_sec is None:
            return False
        return now - self.acquired_at.get(path, 0.0) > float(self.ttl_sec)

    def acquire_detailed(self, task_id: str, files: List[str]) -> Dict[str, Any]:
        """All-or-nothing acquire.  Returns conflicts with their holders and stale takeovers."""
        paths = [os.path.normpath(f) for f in files]
        now = time.time()
        with self._exclusive():
            holders = {
                p: self.locks[p]
                for p in paths
                if p in self.locks and self.locks[p] != task_id and not self._stale(p, now)
            }
            taken_over = {
                p: self.locks[p]
                for p in paths
                if p in self.locks and self.locks[p] != task_id and p not in holders
            }
            newly_acquired: List[str] = []
            if not holders:
                for p in paths:
                    if self.locks.get(p) != task_id:
                        self.acquired_at[p] = now
                        newly_acquired.append(p)
                    self.locks[p] = task_id
                self._save()
        # ``newly_acquired`` is decided under the same flock as the acquire (no stale read).
        return {
            "conflicts": list(holders),
            "holders": holders,
            "stale_taken_over": taken_over,
            "newly_acquired": newly_acquired,
        }

    def acquire(self, task_id: str, files: List[str]) -> List[str]:
        """
        Attempts to acquire locks for a list of files.
        Returns a list of conflicting files (files already locked by others).
        If no conflicts, saves the locks and returns an empty list.
        Re-locking files a task already holds is idempotent.
        """
        return list(self.acquire_detailed(task_id, files)["conflicts"])

    def release(self, task_id: str):
        """Releases all locks held by a task."""
        with self._exclusive():
            to_remove = [f for f, t in self.locks.items() if t == task_id]
            for f in to_remove:
                del self.locks[f]
                self.acquired_at.pop(f, None)
            if to_remove:
                self._save()

    def release_files(self, task_id: str, files: List[str]) -> List[str]:
        """Release only ``files`` (normalized) that ``task_id`` holds; other locks it holds
        stay. Returns the released paths."""
        paths = {os.path.normpath(f) for f in files}
        with self._exclusive():
            to_remove = [f for f, t in self.locks.items() if t == task_id and f in paths]
            for f in to_remove:
                del self.locks[f]
                self.acquired_at.pop(f, None)
            if to_remove:
                self._save()
        return to_remove

    def holder(self, file_path: str) -> Optional[str]:
        return self.locks.get(os.path.normpath(file_path))

    def check_access(self, task_id: str, file_path: str) -> bool:
        """Checks if a task has access to a specific file."""
        normalized_path = os.path.normpath(file_path)
        return self.locks.get(normalized_path) == task_id

    def get_task_files(self, task_id: str) -> List[str]:
        """Returns all files currently locked by a task."""
        return [f for f, t in self.locks.items() if t == task_id]
# integrity-seal: 1776512137


# --- Task-completion release ---------------------------------------------------------------
#
# The ``file_lock`` capability acquires locks for the running task inside a registry file under
# the task's workspace.  The registry files a task touched are remembered (in-process) so the
# mainchain entry can release them when the task completes instead of waiting for the TTL.

_TASK_LOCK_FILES: Dict[str, set[str]] = {}
_TASK_LOCK_FILES_GUARD = threading.Lock()


def register_task_lock_file(task_id: str, lock_file: str) -> None:
    """Remember that ``task_id`` holds locks in ``lock_file`` (released on completion)."""
    if not str(task_id or "").strip() or not str(lock_file or "").strip():
        return
    with _TASK_LOCK_FILES_GUARD:
        _TASK_LOCK_FILES.setdefault(str(task_id), set()).add(str(lock_file))


def release_task_locks(task_id: str) -> Dict[str, List[str]]:
    """Release every lock ``task_id`` holds in the registries it touched; returns lock_file -> files."""
    with _TASK_LOCK_FILES_GUARD:
        lock_files = sorted(_TASK_LOCK_FILES.pop(str(task_id or ""), set()))
    released: Dict[str, List[str]] = {}
    for lock_file in lock_files:
        if not Path(lock_file).is_file():
            continue
        registry = FileLockRegistry(lock_file=lock_file)
        held = sorted(f for f, holder in registry.locks.items() if holder == task_id)
        registry.release(task_id)
        released[lock_file] = held
    return released
