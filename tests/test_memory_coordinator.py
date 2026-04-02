from pathlib import Path
import fcntl
import threading
import time

import pytest

from nexus.core.memory_coordinator import LockCycleError, LockTimeoutError, MemoryCoordinator


def test_memory_coordinator_timeout(tmp_path):
    target = tmp_path / "episodic_memory.jsonl"
    lock_path = MemoryCoordinator._lock_path(target)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    hold_started = threading.Event()
    release = threading.Event()

    def _holder():
        with lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            hold_started.set()
            release.wait(timeout=5)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    t = threading.Thread(target=_holder, daemon=True)
    t.start()
    hold_started.wait(timeout=1)

    coordinator = MemoryCoordinator(timeout_sec=0.2, poll_interval_sec=0.05)
    with pytest.raises(LockTimeoutError):
        with coordinator.lock(target):
            pass

    release.set()
    t.join(timeout=1)


def test_memory_coordinator_cycle_detection(tmp_path):
    c = MemoryCoordinator()
    a = str((tmp_path / "a.lock").resolve())
    b = str((tmp_path / "b.lock").resolve())
    # Build existing lock ordering A -> B
    with MemoryCoordinator._graph_lock:
        MemoryCoordinator._lock_graph.add((a, b))

    try:
        MemoryCoordinator._thread_local.held_locks = [b]
        with pytest.raises(LockCycleError):
            c._register_lock_order(a)
    finally:
        MemoryCoordinator._thread_local.held_locks = []
        with MemoryCoordinator._graph_lock:
            MemoryCoordinator._lock_graph.discard((a, b))
