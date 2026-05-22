from __future__ import annotations

import random
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar


SQLITE_RETRY_SCHEMA = "nexus.sqlite_retry.v1"
RETRYABLE_SQLITE_BUSY_MARKERS = (
    "database is locked",
    "database table is locked",
    "database is busy",
    "sqlite_busy",
    "sqlite_locked",
)

T = TypeVar("T")


def is_retryable_sqlite_busy(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).strip().lower()
    return any(marker in message for marker in RETRYABLE_SQLITE_BUSY_MARKERS)


@dataclass
class SQLiteRetryHandler:
    max_attempts: int = 4
    base_delay_sec: float = 0.05
    max_delay_sec: float = 0.5
    jitter_ratio: float = 0.25
    sleeper: Callable[[float], None] = time.sleep
    rng: random.Random = field(default_factory=random.Random)
    last_receipt: dict[str, Any] | None = None

    def run(
        self,
        operation: Callable[[], T],
        *,
        target_path: str,
        operation_name: str = "sqlite_write",
    ) -> T:
        attempts = 0
        last_error: sqlite3.OperationalError | None = None
        for attempt_index in range(self._safe_max_attempts()):
            attempts = attempt_index + 1
            try:
                result = operation()
            except sqlite3.OperationalError as exc:
                last_error = exc
                if not is_retryable_sqlite_busy(exc):
                    self.last_receipt = self._receipt(
                        target_path=target_path,
                        operation_name=operation_name,
                        status="RETURN",
                        attempts=attempts,
                        blockers=["sqlite_error_not_retryable"],
                        last_error=str(exc),
                    )
                    raise
                if attempts >= self._safe_max_attempts():
                    self.last_receipt = self._receipt(
                        target_path=target_path,
                        operation_name=operation_name,
                        status="RETURN",
                        attempts=attempts,
                        blockers=["sqlite_busy_retry_exhausted"],
                        last_error=str(exc),
                    )
                    raise
                self.sleeper(self._delay_for(attempt_index))
                continue
            self.last_receipt = self._receipt(
                target_path=target_path,
                operation_name=operation_name,
                status="PASS",
                attempts=attempts,
                blockers=[],
                last_error="",
            )
            return result

        if last_error is not None:
            raise last_error
        raise RuntimeError("sqlite retry operation did not execute")

    def _safe_max_attempts(self) -> int:
        return max(1, int(self.max_attempts))

    def _delay_for(self, attempt_index: int) -> float:
        base = min(float(self.max_delay_sec), float(self.base_delay_sec) * (2**attempt_index))
        jitter = base * max(0.0, float(self.jitter_ratio)) * self.rng.random()
        return min(float(self.max_delay_sec), base + jitter)

    def _receipt(
        self,
        *,
        target_path: str,
        operation_name: str,
        status: str,
        attempts: int,
        blockers: list[str],
        last_error: str,
    ) -> dict[str, Any]:
        backoff_status = "PASS" if status == "PASS" and attempts > 1 else "NOT_APPLICABLE"
        if status != "PASS" and "sqlite_busy_retry_exhausted" in blockers:
            backoff_status = "RETURN"
        return {
            "schema": SQLITE_RETRY_SCHEMA,
            "status": status,
            "target_path": target_path,
            "operation_name": operation_name,
            "attempts": attempts,
            "max_attempts": self._safe_max_attempts(),
            "backoff_status": backoff_status,
            "write_queue_status": "NOT_APPLICABLE",
            "blockers": blockers,
            "last_error": last_error,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "claim_boundary": [
                "SQLite busy retry receipts validate bounded retry behavior only.",
                "They do not approve runtime promotion or public benchmark claims.",
            ],
        }
