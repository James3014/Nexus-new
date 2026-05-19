from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SQLITE_WRITE_GUARD_SCHEMA = "nexus.sqlite_write_guard.v1"
PASS_LIKE = {"PASS", "NOT_APPLICABLE"}


@dataclass(frozen=True)
class SQLiteWriteGuardReceipt:
    target_path: str
    wal_status: str = "NOT_APPLICABLE"
    write_queue_status: str = "NOT_APPLICABLE"
    backoff_status: str = "NOT_APPLICABLE"
    concurrent_writer_count: int = 0
    memory_sanitizer_status: str = "NOT_APPLICABLE"
    private_leak_detected: bool = False
    dedup_precision_status: str = "NOT_APPLICABLE"
    low_entropy_merge_detected: bool = False
    schema: str = SQLITE_WRITE_GUARD_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "target_path": self.target_path,
            "wal_status": _status(self.wal_status),
            "write_queue_status": _status(self.write_queue_status),
            "backoff_status": _status(self.backoff_status),
            "concurrent_writer_count": int(self.concurrent_writer_count),
            "memory_sanitizer_status": _status(self.memory_sanitizer_status),
            "private_leak_detected": bool(self.private_leak_detected),
            "dedup_precision_status": _status(self.dedup_precision_status),
            "low_entropy_merge_detected": bool(self.low_entropy_merge_detected),
            "claim_boundary": [
                "SQLite write guards validate persistence hygiene only.",
                "They do not approve retrieval quality, runtime promotion, or public benchmark claims.",
            ],
        }
        payload["blockers"] = validate_sqlite_write_guard(payload)
        payload["status"] = "PASS" if not payload["blockers"] else "RETURN"
        return payload


def build_sqlite_write_guard_receipt(
    *,
    target_path: str,
    wal_status: str = "NOT_APPLICABLE",
    write_queue_status: str = "NOT_APPLICABLE",
    backoff_status: str = "NOT_APPLICABLE",
    concurrent_writer_count: int = 0,
    memory_sanitizer_status: str = "NOT_APPLICABLE",
    private_leak_detected: bool = False,
    dedup_precision_status: str = "NOT_APPLICABLE",
    low_entropy_merge_detected: bool = False,
) -> dict[str, Any]:
    return SQLiteWriteGuardReceipt(
        target_path=target_path,
        wal_status=wal_status,
        write_queue_status=write_queue_status,
        backoff_status=backoff_status,
        concurrent_writer_count=concurrent_writer_count,
        memory_sanitizer_status=memory_sanitizer_status,
        private_leak_detected=private_leak_detected,
        dedup_precision_status=dedup_precision_status,
        low_entropy_merge_detected=low_entropy_merge_detected,
    ).to_dict()


def validate_sqlite_write_guard(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != SQLITE_WRITE_GUARD_SCHEMA:
        blockers.append("invalid_sqlite_write_guard_schema")
    if not str(payload.get("target_path") or "").strip():
        blockers.append("missing_target_path")
    if _status(payload.get("wal_status")) not in PASS_LIKE:
        blockers.append("wal_not_pass")
    if int(payload.get("concurrent_writer_count") or 0) > 1:
        if _status(payload.get("write_queue_status")) != "PASS":
            blockers.append("write_queue_not_pass")
        if _status(payload.get("backoff_status")) != "PASS":
            blockers.append("backoff_not_pass")
    if _status(payload.get("memory_sanitizer_status")) not in PASS_LIKE:
        blockers.append("memory_sanitizer_not_pass")
    if bool(payload.get("private_leak_detected", False)):
        blockers.append("private_leak_detected")
    if _status(payload.get("dedup_precision_status")) not in PASS_LIKE:
        blockers.append("dedup_precision_not_pass")
    if bool(payload.get("low_entropy_merge_detected", False)):
        blockers.append("low_entropy_merge_detected")
    if bool(payload.get("runtime_update_allowed", False)):
        blockers.append("sqlite_write_guard_must_not_update_runtime")
    if bool(payload.get("public_benchmark_allowed", False)):
        blockers.append("sqlite_write_guard_must_not_unlock_public_benchmark")
    return sorted(set(blockers))


def _status(value: Any) -> str:
    return str(value or "NOT_APPLICABLE").strip().upper()
