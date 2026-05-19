from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from nexus.core import memory_manager
from nexus.core.memory_manager import ProjectMemoryManager


def test_project_memory_manager_write_guard_uses_wal(tmp_path: Path) -> None:
    manager = ProjectMemoryManager(tmp_path)

    payload = manager.build_write_guard_receipt()

    assert payload["status"] == "PASS"
    assert payload["wal_status"] == "PASS"
    assert payload["target_path"].endswith("project_memory.sqlite")


def test_project_memory_manager_write_guard_blocks_unqueued_concurrency(tmp_path: Path) -> None:
    manager = ProjectMemoryManager(tmp_path)

    payload = manager.build_write_guard_receipt(concurrent_writer_count=4)

    assert payload["status"] == "RETURN"
    assert "write_queue_not_pass" in payload["blockers"]
    assert "backoff_not_pass" in payload["blockers"]


def test_project_memory_manager_guarded_write_persists_after_guard_pass(tmp_path: Path) -> None:
    manager = ProjectMemoryManager(tmp_path)

    payload = manager.add_insight_guarded("routing", "adapter receipt passed", "ARCH")

    assert payload["schema"] == "nexus.memory_write_result.v1"
    assert payload["status"] == "PASS"
    assert payload["written"] is True
    assert payload["write_guard_receipt"]["status"] == "PASS"
    rows = manager.search("adapter receipt")
    assert len(rows) == 1
    assert rows[0][:3] == ("routing", "adapter receipt passed", "ARCH")


def test_project_memory_manager_guarded_write_returns_without_persisting_on_guard_failure(tmp_path: Path) -> None:
    manager = ProjectMemoryManager(tmp_path)

    payload = manager.add_insight_guarded(
        "routing",
        "should not persist",
        "ARCH",
        concurrent_writer_count=4,
    )

    assert payload["schema"] == "nexus.memory_write_result.v1"
    assert payload["status"] == "RETURN"
    assert payload["written"] is False
    assert "write_queue_not_pass" in payload["blockers"]
    assert manager.search("should not persist") == []


def test_project_memory_manager_write_retries_sqlite_lock(tmp_path: Path, monkeypatch) -> None:
    manager = ProjectMemoryManager(tmp_path)
    calls = {"count": 0}
    original_connect = manager._connect

    class FlakyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *_args, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise sqlite3.OperationalError("database is locked")
            with original_connect() as conn:
                return conn.execute(*_args, **_kwargs)

    monkeypatch.setattr(manager, "_connect", lambda: FlakyConnection())
    monkeypatch.setattr(memory_manager.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(memory_manager.random, "uniform", lambda _left, _right: 0)

    manager.add_insight("sqlite", "retry succeeded", "ARCH")

    assert calls["count"] == 2
    assert manager.search("retry succeeded")[0][:3] == ("sqlite", "retry succeeded", "ARCH")


def test_project_memory_manager_write_does_not_retry_non_lock_errors(tmp_path: Path, monkeypatch) -> None:
    manager = ProjectMemoryManager(tmp_path)

    class BrokenConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("no such table")

    monkeypatch.setattr(manager, "_connect", lambda: BrokenConnection())

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        manager.add_insight("sqlite", "do not retry", "ARCH")
