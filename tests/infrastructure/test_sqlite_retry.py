from __future__ import annotations

import random
import sqlite3

import pytest

from nexus.infrastructure.sqlite_retry import (
    SQLITE_RETRY_SCHEMA,
    SQLiteRetryHandler,
    is_retryable_sqlite_busy,
)


def test_sqlite_retry_handler_retries_busy_then_succeeds() -> None:
    sleeps: list[float] = []
    calls = {"count": 0}
    handler = SQLiteRetryHandler(
        max_attempts=3,
        base_delay_sec=0.1,
        max_delay_sec=0.2,
        jitter_ratio=0.0,
        sleeper=sleeps.append,
        rng=random.Random(7),
    )

    def operation() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    assert handler.run(operation, target_path=".nexus/state/memory.sqlite") == "ok"

    assert calls["count"] == 2
    assert sleeps == [0.1]
    assert handler.last_receipt == {
        "schema": SQLITE_RETRY_SCHEMA,
        "status": "PASS",
        "target_path": ".nexus/state/memory.sqlite",
        "operation_name": "sqlite_write",
        "attempts": 2,
        "max_attempts": 3,
        "backoff_status": "PASS",
        "write_queue_status": "NOT_APPLICABLE",
        "blockers": [],
        "last_error": "",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "claim_boundary": [
            "SQLite busy retry receipts validate bounded retry behavior only.",
            "They do not approve runtime promotion or public benchmark claims.",
        ],
    }


def test_sqlite_retry_handler_exhausts_busy_errors() -> None:
    sleeps: list[float] = []
    handler = SQLiteRetryHandler(max_attempts=2, jitter_ratio=0.0, sleeper=sleeps.append)

    with pytest.raises(sqlite3.OperationalError, match="database table is locked"):
        handler.run(
            lambda: (_ for _ in ()).throw(sqlite3.OperationalError("database table is locked")),
            target_path=".nexus/state/memory.sqlite",
            operation_name="upsert_memory",
        )

    assert len(sleeps) == 1
    assert handler.last_receipt is not None
    assert handler.last_receipt["status"] == "RETURN"
    assert handler.last_receipt["operation_name"] == "upsert_memory"
    assert handler.last_receipt["attempts"] == 2
    assert handler.last_receipt["blockers"] == ["sqlite_busy_retry_exhausted"]
    assert handler.last_receipt["runtime_update_allowed"] is False
    assert handler.last_receipt["public_benchmark_allowed"] is False


def test_sqlite_retry_handler_fails_fast_on_non_busy_operational_error() -> None:
    sleeps: list[float] = []
    handler = SQLiteRetryHandler(max_attempts=5, sleeper=sleeps.append)

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        handler.run(
            lambda: (_ for _ in ()).throw(sqlite3.OperationalError("no such table: memories")),
            target_path=".nexus/state/memory.sqlite",
        )

    assert sleeps == []
    assert handler.last_receipt is not None
    assert handler.last_receipt["attempts"] == 1
    assert handler.last_receipt["blockers"] == ["sqlite_error_not_retryable"]


def test_retryable_sqlite_busy_detection_uses_stable_sqlite_markers() -> None:
    assert is_retryable_sqlite_busy(sqlite3.OperationalError("database is busy"))
    assert is_retryable_sqlite_busy(sqlite3.OperationalError("SQLITE_BUSY"))
    assert is_retryable_sqlite_busy(sqlite3.OperationalError("SQLITE_LOCKED"))
    assert not is_retryable_sqlite_busy(sqlite3.OperationalError("syntax error"))
