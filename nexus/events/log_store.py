from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from nexus.feedback.contracts import (
    _CODE_RE,
    _REF_RE,
    AUTHORITY_FLAG_KEYS,
    DeveloperFeedbackDecision,
    _tokens,
)


class JsonlEventLogStore:
    """Append/read access for event JSONL persistence."""

    def __init__(self):
        self.event_log_path: Optional[Path] = None

    def configure(self, project_root: Path) -> Tuple[Path, Path]:
        log_dir = project_root / ".nexus" / "events"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.event_log_path = log_dir / "event_log.jsonl"
        return log_dir, self.event_log_path

    def append_record(self, record: Dict[str, Any]) -> None:
        if not self.event_log_path:
            return
        with open(self.event_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def read_recent(self, event_type: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        if not self.event_log_path or not self.event_log_path.exists():
            return []
        lines = self.event_log_path.read_text(encoding="utf-8").strip().split("\n")
        events = [json.loads(line) for line in lines[-limit:] if line.strip()]
        if event_type:
            events = [e for e in events if e.get("event_type") == event_type]
        return events


class DeveloperFeedbackDecisionStore:
    """Fail-closed append-only POSIX JSONL store for typed feedback decisions."""

    MAX_RECORDS = 10_000
    MAX_BYTES = 8 * 1024 * 1024

    def __init__(self, project_root: Optional[Path] = None):
        self.path: Optional[Path] = None
        self.lock_path: Optional[Path] = None
        self._lock = threading.RLock()
        if project_root is not None:
            self.configure(project_root)

    def configure(self, project_root: Path) -> Tuple[Path, Path]:
        directory = project_root / ".nexus" / "events"
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "developer_feedback_decision.v1.jsonl"
        self.lock_path = directory / "developer_feedback_decision.v1.lock"
        return directory, self.path

    @staticmethod
    def _canonical(value: Dict[str, Any]) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

    @staticmethod
    def _parse(line: str) -> Dict[str, Any]:
        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise ValueError("duplicate JSON key")
                out[key] = value
            return out

        obj = json.loads(line, object_pairs_hook=pairs)
        if not isinstance(obj, dict) or obj.get("schema") != "nexus.developer_feedback_decision.v1":
            raise ValueError("invalid decision record")
        allowed = {
            "schema",
            "task_id",
            "decision_id",
            "decision",
            "reason_codes",
            "evidence_refs",
            "request_digest",
            "authority_flags",
            "sequence",
            "parent_digest",
            "record_digest",
        }
        if set(obj) != allowed or obj.get("decision") not in {
            "KEEP",
            "REVISE",
            "REJECT",
            "INVESTIGATE",
        }:
            raise ValueError("invalid decision fields")
        flags = obj.get("authority_flags")
        if (
            not isinstance(flags, dict)
            or set(flags) != AUTHORITY_FLAG_KEYS
            or any(type(value) is not bool for value in flags.values())
            or any(flags.values())
        ):
            raise ValueError("invalid authority flags")
        if (
            not isinstance(obj.get("task_id"), str)
            or not isinstance(obj.get("decision_id"), str)
            or not isinstance(obj.get("reason_codes"), list)
            or not all(isinstance(value, str) for value in obj["reason_codes"])
            or not isinstance(obj.get("evidence_refs"), list)
            or not all(isinstance(value, str) for value in obj["evidence_refs"])
            or not isinstance(obj.get("request_digest"), str)
            or not isinstance(obj.get("sequence"), int)
            or isinstance(obj.get("sequence"), bool)
            or not isinstance(obj.get("parent_digest"), str)
            or not isinstance(obj.get("record_digest"), str)
            or (obj["request_digest"] and not re.fullmatch(r"[0-9a-f]{64}", obj["request_digest"]))
            or not re.fullmatch(r"[0-9a-f]{64}", obj["parent_digest"])
            or not re.fullmatch(r"[0-9a-f]{64}", obj["record_digest"])
        ):
            raise ValueError("invalid decision field types")
        try:
            _tokens((obj["task_id"],), _REF_RE, "task_id")
            _tokens((obj["decision_id"],), _REF_RE, "decision_id")
            _tokens(obj["reason_codes"], _CODE_RE, "reason_codes")
            _tokens(obj["evidence_refs"], _REF_RE, "evidence_refs")
        except ValueError as exc:
            raise ValueError("invalid decision token grammar") from exc
        return obj

    def _scan(self) -> Tuple[list[Dict[str, Any]], str, int]:
        if not self.path or not self.path.exists() or self.path.stat().st_size == 0:
            return [], "0" * 64, 0
        raw = self.path.read_bytes()
        if len(raw) > self.MAX_BYTES or not raw.endswith(b"\n"):
            raise ValueError("corrupt decision stream")
        records = []
        task_tails: Dict[str, Tuple[int, str]] = {}
        for line in raw.splitlines():
            record = self._parse(line.decode("utf-8"))
            task_id = record.get("task_id")
            sequence, parent = task_tails.get(task_id, (0, "0" * 64))
            if record.get("parent_digest") != parent or record.get("sequence") != sequence + 1:
                raise ValueError("broken decision chain")
            expected = record.get("record_digest")
            unsigned = dict(record)
            unsigned.pop("record_digest", None)
            digest = hashlib.sha256(self._canonical(unsigned)).hexdigest()
            if expected != digest:
                raise ValueError("tampered decision record")
            task_tails[task_id] = (sequence + 1, digest)
            records.append(record)
        if len(records) > self.MAX_RECORDS:
            raise ValueError("decision stream ceiling exceeded")
        return records, (records[-1].get("record_digest") if records else "0" * 64), len(raw)

    def append(
        self,
        decision: DeveloperFeedbackDecision,
        *,
        expected_tail: Optional[str] = None,
        lock_timeout: float = 5.0,
    ) -> Dict[str, Any]:
        if not self.path or not self.lock_path:
            raise RuntimeError("store is not configured")
        with self._lock, open(self.lock_path, "a+", encoding="utf-8") as lock:
            deadline = time.monotonic() + lock_timeout
            while True:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("decision stream lock timeout")
                    time.sleep(0.01)
            try:
                records, _, size = self._scan()
                task_records = [row for row in records if row.get("task_id") == decision.task_id]
                sequence = len(task_records) + 1
                tail = task_records[-1]["record_digest"] if task_records else "0" * 64
                if expected_tail is not None and expected_tail != tail:
                    raise ValueError("stale expected tail")
                for old in records:
                    if old.get("decision_id") == decision.decision_id:
                        candidate = decision.to_record(
                            sequence=old["sequence"], parent_digest=old["parent_digest"]
                        )
                        old_unsigned = dict(old)
                        old_unsigned.pop("record_digest", None)
                        if self._canonical(candidate) == self._canonical(old_unsigned):
                            return old
                        raise ValueError("idempotency conflict")
                record = decision.to_record(sequence=sequence, parent_digest=tail)
                record["record_digest"] = hashlib.sha256(self._canonical(record)).hexdigest()
                encoded = self._canonical(record) + b"\n"
                if size + len(encoded) > self.MAX_BYTES or len(records) >= self.MAX_RECORDS:
                    raise ValueError("decision stream ceiling exceeded")
                existed = self.path.exists()
                with open(self.path, "ab") as out:
                    out.write(encoded)
                    out.flush()
                    os.fsync(out.fileno())
                if not existed:
                    directory_fd = os.open(str(self.path.parent), os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                return record
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    append_decision = append

    def read_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return self._scan()[0][-limit:]
