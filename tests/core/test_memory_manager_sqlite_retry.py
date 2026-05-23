from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from nexus.core.memory_manager import ProjectMemoryManager


def test_execute_with_retry_uses_sqlite_retry_handler_for_busy_then_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ProjectMemoryManager(tmp_path)
    original_connect = manager._connect
    execute_calls = {"count": 0}
    retry_calls: list[dict[str, str]] = []

    class FlakyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            execute_calls["count"] += 1
            if execute_calls["count"] == 1:
                raise sqlite3.OperationalError("database is locked")
            with original_connect() as conn:
                return conn.execute(*args, **kwargs)

    class RecordingRetryHandler:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.last_receipt = None

        def run(self, operation, *, target_path: str, operation_name: str):
            retry_calls.append({"target_path": target_path, "operation_name": operation_name})
            try:
                operation()
            except sqlite3.OperationalError as exc:
                assert "locked" in str(exc)
                operation()
                self.last_receipt = {
                    "status": "PASS",
                    "attempts": 2,
                    "target_path": target_path,
                    "operation_name": operation_name,
                }
                return None
            raise AssertionError("expected first operation attempt to hit sqlite lock")

    monkeypatch.setattr(manager, "_connect", lambda: FlakyConnection())
    monkeypatch.setattr(
        "nexus.core.memory_manager.SQLiteRetryHandler",
        RecordingRetryHandler,
    )

    manager.add_insight("sqlite", "retry handler used", "ARCH")

    assert execute_calls["count"] == 2
    assert retry_calls == [
        {
            "target_path": str(manager.db_path),
            "operation_name": "project_memory_write",
        }
    ]
    assert manager.last_sqlite_retry_receipt == {
        "status": "PASS",
        "attempts": 2,
        "target_path": str(manager.db_path),
        "operation_name": "project_memory_write",
    }
    assert manager.search("retry handler used")[0][:3] == (
        "sqlite",
        "retry handler used",
        "ARCH",
    )


def test_execute_with_retry_keeps_non_busy_errors_fail_fast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ProjectMemoryManager(tmp_path)

    class BrokenConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("database disk image is malformed")

    monkeypatch.setattr(manager, "_connect", lambda: BrokenConnection())

    with pytest.raises(sqlite3.OperationalError, match="malformed"):
        manager.add_insight("sqlite", "do not retry corrupt db", "ARCH")

    assert manager.last_sqlite_retry_receipt is not None
    assert manager.last_sqlite_retry_receipt["status"] == "RETURN"
    assert manager.last_sqlite_retry_receipt["blockers"] == ["sqlite_error_not_retryable"]
