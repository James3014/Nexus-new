from __future__ import annotations

from nexus.contracts.sqlite_write_guard import (
    SQLITE_WRITE_GUARD_SCHEMA,
    build_sqlite_write_guard_receipt,
    validate_sqlite_write_guard,
)


def test_sqlite_write_guard_passes_single_writer_wal_receipt() -> None:
    payload = build_sqlite_write_guard_receipt(
        target_path=".nexus/state/memory.sqlite",
        wal_status="PASS",
        concurrent_writer_count=1,
        memory_sanitizer_status="PASS",
        dedup_precision_status="PASS",
    )

    assert payload["schema"] == SQLITE_WRITE_GUARD_SCHEMA
    assert payload["status"] == "PASS"
    assert payload["blockers"] == []


def test_sqlite_write_guard_requires_queue_and_backoff_for_concurrent_writes() -> None:
    payload = build_sqlite_write_guard_receipt(
        target_path=".nexus/state/memory.sqlite",
        wal_status="RETURN",
        concurrent_writer_count=3,
        write_queue_status="RETURN",
        backoff_status="RETURN",
        memory_sanitizer_status="RETURN",
        private_leak_detected=True,
        dedup_precision_status="RETURN",
        low_entropy_merge_detected=True,
    )

    assert payload["status"] == "RETURN"
    assert payload["blockers"] == [
        "backoff_not_pass",
        "dedup_precision_not_pass",
        "low_entropy_merge_detected",
        "memory_sanitizer_not_pass",
        "private_leak_detected",
        "wal_not_pass",
        "write_queue_not_pass",
    ]


def test_sqlite_write_guard_rejects_unlock_attempts() -> None:
    blockers = validate_sqlite_write_guard(
        {
            "schema": SQLITE_WRITE_GUARD_SCHEMA,
            "target_path": ".nexus/state/memory.sqlite",
            "runtime_update_allowed": True,
            "public_benchmark_allowed": True,
        }
    )

    assert blockers == [
        "sqlite_write_guard_must_not_unlock_public_benchmark",
        "sqlite_write_guard_must_not_update_runtime",
    ]
