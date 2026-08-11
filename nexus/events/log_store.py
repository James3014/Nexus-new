from __future__ import annotations

import fcntl
import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from nexus.feedback.contracts import (
    DECISION_SCHEMA,
    DeveloperFeedbackDecisionRequest,
    request_digest,
    with_chain,
)


class DeveloperFeedbackStoreError(RuntimeError):
    """Fail-closed storage or integrity error."""


class DeveloperFeedbackConflict(DeveloperFeedbackStoreError):
    pass


class DeveloperFeedbackStale(DeveloperFeedbackStoreError):
    pass


class DeveloperFeedbackReplay:
    status = "IDEMPOTENT_REPLAY"


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DeveloperFeedbackStoreError("duplicate_json_key")
        result[key] = value
    return result


class DeveloperFeedbackDecisionStore:
    """One strict, append-only per-task chain in a local POSIX JSONL stream."""

    _lock = threading.RLock()
    MAX_RECORD_BYTES = 32 * 1024
    MAX_STREAM_BYTES = 8 * 1024 * 1024

    def __init__(self, project_root: Path, *, lock_timeout: float = 5.0):
        self.directory = Path(project_root) / ".nexus" / "events"
        self.path = self.directory / "developer_feedback_decision.v1.jsonl"
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.lock_timeout = lock_timeout

    @contextmanager
    def _flock(self, exclusive: bool) -> Iterator[None]:
        if not all(hasattr(fcntl, name) for name in ("flock", "LOCK_NB")):
            raise DeveloperFeedbackStoreError("unsupported_posix_flock")
        self.directory.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+", encoding="ascii")
        try:
            flags = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            deadline = time.monotonic() + self.lock_timeout
            while True:
                try:
                    fcntl.flock(handle.fileno(), flags | fcntl.LOCK_NB)
                    break
                except (BlockingIOError, OSError) as exc:
                    if getattr(exc, "errno", None) not in {11, 35}:
                        raise DeveloperFeedbackStoreError(
                            f"flock_failed:{type(exc).__name__}"
                        ) from exc
                    if time.monotonic() >= deadline:
                        raise DeveloperFeedbackStoreError("flock_timeout") from exc
                    time.sleep(0.005)
            yield
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def _scan_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        raw = self.path.read_bytes()
        if len(raw) > self.MAX_STREAM_BYTES or (raw and not raw.endswith(b"\n")):
            raise DeveloperFeedbackStoreError("partial_or_oversized_stream")
        rows: list[dict[str, Any]] = []
        tails: dict[str, tuple[int, str | None]] = {}
        for number, line in enumerate(raw.splitlines(), 1):
            if not line:
                raise DeveloperFeedbackStoreError(f"blank_line:{number}")
            try:
                row = json.loads(line.decode("utf-8"), object_pairs_hook=_strict_object_pairs)
            except (UnicodeError, json.JSONDecodeError, DeveloperFeedbackStoreError) as exc:
                raise DeveloperFeedbackStoreError(f"corrupt_record:{number}") from exc
            if not isinstance(row, dict) or row.get("schema") != DECISION_SCHEMA:
                raise DeveloperFeedbackStoreError(f"invalid_record_schema:{number}")
            if set(row) - {
                "schema",
                "decision_id",
                "task_id",
                "attempt_id",
                "action",
                "candidate_ref",
                "candidate_digest",
                "evidence_refs",
                "source_revision",
                "source_tree",
                "evidence_hash",
                "decision",
                "rationale_codes",
                "delta_type",
                "delta_codes",
                "acceptance_surface",
                "approver_ref",
                "repository_ref",
                "approved_at",
                "idempotency_key",
                "expected_task_seq",
                "expected_parent_digest",
                "next_gate",
                "follow_up_destination_ref",
                "task_seq",
                "parent_digest",
                "request_digest",
                "record_digest",
            }:
                raise DeveloperFeedbackStoreError("unknown_record_field")
            task = row.get("task_id")
            seq = row.get("task_seq")
            if (
                not isinstance(task, str)
                or not isinstance(seq, int)
                or seq < 1
                or seq != tails.get(task, (0, None))[0] + 1
            ):
                raise DeveloperFeedbackStoreError("sequence_tamper")
            parent = row.get("parent_digest")
            if parent != tails.get(task, (0, None))[1]:
                raise DeveloperFeedbackStoreError("parent_tamper")
            digest = row.get("record_digest")
            check = dict(row)
            check.pop("record_digest", None)
            from nexus.feedback.contracts import _digest

            if digest != _digest(check):
                raise DeveloperFeedbackStoreError("digest_tamper")
            tails[task] = (seq, digest)
            rows.append(row)
        return rows

    @contextmanager
    def _transaction(self, exclusive: bool) -> Iterator[list[dict[str, Any]]]:
        with self._lock:
            with self._flock(exclusive):
                yield self._scan_unlocked()

    def append(self, request: DeveloperFeedbackDecisionRequest) -> dict[str, Any]:
        digest = request_digest(request)
        with self._transaction(True) as rows:
            same = [row for row in rows if row.get("decision_id") == request.decision_id]
            if same:
                if same[-1].get("request_digest") == digest:
                    return {"status": "IDEMPOTENT_REPLAY", "record": same[-1]}
                raise DeveloperFeedbackConflict("decision_id_conflict")
            task_rows = [row for row in rows if row.get("task_id") == request.task_id]
            tail_seq = task_rows[-1]["task_seq"] if task_rows else 0
            tail_digest = task_rows[-1].get("record_digest") if task_rows else None
            if request.expected_task_seq is not None and request.expected_task_seq != tail_seq:
                raise DeveloperFeedbackStale("expected_task_seq_stale")
            if (
                request.expected_parent_digest is not None
                and request.expected_parent_digest != tail_digest
            ):
                raise DeveloperFeedbackStale("expected_parent_digest_stale")
            row = with_chain(request, task_seq=tail_seq + 1, parent_digest=tail_digest)
            encoded = (
                json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
            ).encode()
            if len(encoded) > self.MAX_RECORD_BYTES:
                raise DeveloperFeedbackStoreError("record_ceiling")
            self.directory.mkdir(parents=True, exist_ok=True)
            existed = self.path.exists()
            with open(self.path, "ab") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            if not existed:
                directory_fd = os.open(self.directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            return {"status": "RECORDED", "record": row}

    def read(self, *, task_id: str | None = None) -> list[dict[str, Any]]:
        with self._transaction(False) as rows:
            return [row for row in rows if task_id is None or row.get("task_id") == task_id]


class JsonlEventLogStore:
    """Legacy EventBus JSONL store; deliberately separate from the v1 stream."""

    def __init__(self):
        self.event_log_path: Path | None = None

    def configure(self, project_root: Path) -> tuple[Path, Path]:
        log_dir = project_root / ".nexus" / "events"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.event_log_path = log_dir / "event_log.jsonl"
        return log_dir, self.event_log_path

    def append_record(self, record: dict[str, Any]) -> None:
        if self.event_log_path:
            with open(self.event_log_path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, default=str) + "\n")

    def read_recent(self, event_type: str = "", limit: int = 50) -> list[dict[str, Any]]:
        if not self.event_log_path or not self.event_log_path.exists():
            return []
        rows = [
            json.loads(line)
            for line in self.event_log_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        if event_type:
            rows = [row for row in rows if row.get("event_type") == event_type]
        return rows[-limit:]
