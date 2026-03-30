from __future__ import annotations

import fcntl
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple
import logging

logger = logging.getLogger(__name__)


class LockTimeoutError(TimeoutError):
    """Raised when lock wait exceeds timeout budget."""


class LockCycleError(RuntimeError):
    """Raised when in-process lock graph detects a potential cycle."""


class MemoryCoordinator:
    """
    File-level coordination for memory writes.
    - Uses fcntl for atomic process-safe locking.
    - Tracks wait time and timeout.
    - Guards against in-process lock-order cycles.
    """

    _graph_lock = threading.Lock()
    _lock_graph: Set[Tuple[str, str]] = set()
    _thread_local = threading.local()

    def __init__(self, timeout_sec: float = 30.0, poll_interval_sec: float = 0.05):
        self.timeout_sec = max(0.1, float(timeout_sec))
        self.poll_interval_sec = max(0.01, float(poll_interval_sec))
        self.last_wait_ms: float = 0.0
        self._wait_samples_ms: List[float] = []

    @contextmanager
    def lock(self, target_path: Path) -> Iterator[Path]:
        lock_path = self._lock_path(target_path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        start = time.monotonic()

        with os.fdopen(lock_fd, "a+") as handle:
            lock_key = str(lock_path.resolve())
            self._register_lock_order(lock_key)
            try:
                while True:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        elapsed = time.monotonic() - start
                        if elapsed > self.timeout_sec:
                            self.last_wait_ms = elapsed * 1000.0
                            raise LockTimeoutError(
                                f"LockTimeout: waited {elapsed:.2f}s for {lock_path}"
                            )
                        time.sleep(self.poll_interval_sec)

                self.last_wait_ms = (time.monotonic() - start) * 1000.0
                self._record_wait(self.last_wait_ms)
                yield lock_path
            finally:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    self._release_lock_order(lock_key)

    @staticmethod
    def _lock_path(target_path: Path) -> Path:
        return target_path.with_suffix(target_path.suffix + ".lock")

    @classmethod
    def _register_lock_order(cls, lock_key: str) -> None:
        stack: List[str] = getattr(cls._thread_local, "held_locks", [])
        if stack:
            prev = stack[-1]
            edge = (prev, lock_key)
            reverse = (lock_key, prev)
            with cls._graph_lock:
                if reverse in cls._lock_graph:
                    raise LockCycleError(f"graph_cycle_detection: {lock_key} <-> {prev}")
                cls._lock_graph.add(edge)
        stack.append(lock_key)
        cls._thread_local.held_locks = stack

    @classmethod
    def _release_lock_order(cls, lock_key: str) -> None:
        stack: List[str] = getattr(cls._thread_local, "held_locks", [])
        if stack and stack[-1] == lock_key:
            stack.pop()
        else:
            try:
                stack.remove(lock_key)
            except ValueError:
                logger.debug("lock_order_release_missing: %s", lock_key)
        cls._thread_local.held_locks = stack

    def _record_wait(self, wait_ms: float) -> None:
        self._wait_samples_ms.append(float(wait_ms))
        if len(self._wait_samples_ms) > 200:
            self._wait_samples_ms = self._wait_samples_ms[-200:]

    def wait_p95_ms(self) -> float:
        if not self._wait_samples_ms:
            return 0.0
        samples = sorted(self._wait_samples_ms)
        idx = int(round(0.95 * (len(samples) - 1)))
        return float(samples[idx])
