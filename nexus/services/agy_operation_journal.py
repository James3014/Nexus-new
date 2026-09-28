"""Durable execution observation for direct Agy operations.

This module records what happened to one already-authorized direct execution.
It is not a route, workforce, acceptance, merge, release, or production
authority.
"""

from __future__ import annotations

import fcntl
import json
import os
import socket
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "nexus.agy_operation.v1"
TERMINAL_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED", "OUTCOME_UNKNOWN"})
ACTIVE_STATES = frozenset({"QUEUED", "RUNNING", "WAITING_INPUT"})
_ALLOWED_STATES = TERMINAL_STATES | ACTIVE_STATES


class AgyOperationJournalError(RuntimeError):
    """Operation journal contract or persistence failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_operation_id() -> str:
    return "agyop_" + uuid.uuid4().hex


def new_attempt_id() -> str:
    return "attempt_" + uuid.uuid4().hex


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _validate_operation_id(operation_id: str) -> str:
    value = str(operation_id).strip()
    if not value.startswith("agyop_") or len(value) != 38:
        raise AgyOperationJournalError("INVALID_OPERATION_ID")
    suffix = value[6:]
    if any(ch not in "0123456789abcdef" for ch in suffix):
        raise AgyOperationJournalError("INVALID_OPERATION_ID")
    return value


def _process_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _git_identity(cwd: str) -> tuple[str | None, str | None]:
    root = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if root.returncode != 0:
        return None, None
    repo_root = root.stdout.strip() or None
    head = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return repo_root, head.stdout.strip() if head.returncode == 0 else None


def observed_changed_paths(cwd: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", cwd, "status", "--porcelain=v1", "-z"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    paths: set[str] = set()
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        if len(text) >= 4:
            path = text[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if path:
                paths.add(path)
    return sorted(paths)


class AgyOperationJournal:
    """Filesystem-backed journal for one host's direct Agy operations."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        self.operations_dir = self.root / "operations"

    def operation_dir(self, operation_id: str) -> Path:
        return self.operations_dir / _validate_operation_id(operation_id)

    def record_path(self, operation_id: str) -> Path:
        return self.operation_dir(operation_id) / "operation.json"

    def stdout_path(self, operation_id: str) -> Path:
        return self.operation_dir(operation_id) / "stdout.log"

    def stderr_path(self, operation_id: str) -> Path:
        return self.operation_dir(operation_id) / "stderr.log"

    def prompt_path(self, operation_id: str) -> Path:
        return self.operation_dir(operation_id) / ".prompt"

    def create(
        self,
        *,
        operation_id: str,
        attempt_id: str,
        cwd: str,
        provider: str,
        model: str | None,
        effort: str | None,
        prompt_sha256: str,
        runtime_revision: str | None,
    ) -> dict[str, Any]:
        operation_id = _validate_operation_id(operation_id)
        op_dir = self.operation_dir(operation_id)
        try:
            op_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        except FileExistsError as exc:
            raise AgyOperationJournalError("OPERATION_ALREADY_EXISTS") from exc
        repo_root, base_head = _git_identity(cwd)
        now = utc_now()
        record: dict[str, Any] = {
            "schema": SCHEMA,
            "operation_id": operation_id,
            "attempt_id": attempt_id,
            "host_id": socket.gethostname(),
            "pid": None,
            "status": "QUEUED",
            "phase": "QUEUED",
            "provider": provider,
            "model": model,
            "effort": effort,
            "cwd": cwd,
            "repo_root": repo_root,
            "base_head": base_head,
            "runtime_revision": runtime_revision,
            "prompt_sha256": prompt_sha256,
            "created_at": now,
            "started_at": None,
            "last_heartbeat_at": None,
            "last_output_at": None,
            "finished_at": None,
            "attempts": 0,
            "rotations": 0,
            "account_alias_hash": None,
            "lease_id_hash": None,
            "failure_kind": None,
            "exit_code": None,
            "observed_changed_paths": [],
            "reconciliation": None,
            "stdout_path": str(self.stdout_path(operation_id)),
            "stderr_path": str(self.stderr_path(operation_id)),
        }
        _atomic_json_write(self.record_path(operation_id), record)
        return record

    def read(self, operation_id: str) -> dict[str, Any]:
        path = self.record_path(operation_id)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise AgyOperationJournalError("OPERATION_NOT_FOUND") from exc
        except json.JSONDecodeError as exc:
            raise AgyOperationJournalError("OPERATION_RECORD_INVALID") from exc
        if record.get("schema") != SCHEMA:
            raise AgyOperationJournalError("OPERATION_SCHEMA_MISMATCH")
        if record.get("operation_id") != _validate_operation_id(operation_id):
            raise AgyOperationJournalError("OPERATION_ID_MISMATCH")
        if record.get("status") not in _ALLOWED_STATES:
            raise AgyOperationJournalError("OPERATION_STATUS_INVALID")
        return record

    def update(self, operation_id: str, **changes: Any) -> dict[str, Any]:
        operation_id = _validate_operation_id(operation_id)
        lock_path = self.operation_dir(operation_id) / ".lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as lock_fh:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
            try:
                record = self.read(operation_id)
                if "status" in changes and changes["status"] not in _ALLOWED_STATES:
                    raise AgyOperationJournalError("OPERATION_STATUS_INVALID")
                record.update(changes)
                _atomic_json_write(self.record_path(operation_id), record)
                return record
            finally:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)

    def bind_pid(self, operation_id: str, pid: int) -> dict[str, Any]:
        return self.update(operation_id, pid=int(pid))

    def mark_started(self, operation_id: str, *, pid: int | None = None) -> dict[str, Any]:
        now = utc_now()
        changes: dict[str, Any] = {
            "status": "RUNNING",
            "phase": "STARTING",
            "started_at": now,
            "last_heartbeat_at": now,
        }
        if pid is not None:
            changes["pid"] = int(pid)
        return self.update(operation_id, **changes)

    def heartbeat(
        self, operation_id: str, *, phase: str | None = None, **changes: Any
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"last_heartbeat_at": utc_now()}
        if phase is not None:
            payload["phase"] = phase
        payload.update(changes)
        return self.update(operation_id, **payload)

    def mark_terminal(
        self,
        operation_id: str,
        *,
        status: str,
        exit_code: int | None,
        failure_kind: str | None = None,
        cwd: str | None = None,
        **changes: Any,
    ) -> dict[str, Any]:
        if status not in TERMINAL_STATES:
            raise AgyOperationJournalError("TERMINAL_STATUS_REQUIRED")
        payload: dict[str, Any] = {
            "status": status,
            "phase": "TERMINAL",
            "finished_at": utc_now(),
            "last_heartbeat_at": utc_now(),
            "exit_code": exit_code,
            "failure_kind": failure_kind,
        }
        if cwd:
            payload["observed_changed_paths"] = observed_changed_paths(cwd)
        payload.update(changes)
        return self.update(operation_id, **payload)

    def reconcile(
        self,
        operation_id: str,
        *,
        heartbeat_stale_seconds: float = 120.0,
    ) -> dict[str, Any]:
        record = self.read(operation_id)
        status = record["status"]
        if status in TERMINAL_STATES:
            return record

        pid_alive = _process_alive(record.get("pid"))
        now_ts = time.time()
        heartbeat_age: float | None = None
        heartbeat = record.get("last_heartbeat_at")
        if isinstance(heartbeat, str):
            try:
                heartbeat_ts = datetime.fromisoformat(heartbeat.replace("Z", "+00:00")).timestamp()
                heartbeat_age = max(0.0, now_ts - heartbeat_ts)
            except ValueError:
                heartbeat_age = None

        if not pid_alive:
            return self.mark_terminal(
                operation_id,
                status="OUTCOME_UNKNOWN",
                exit_code=None,
                failure_kind="PROCESS_NOT_RUNNING_WITHOUT_TERMINAL_RECEIPT",
                cwd=record.get("cwd"),
                reconciliation={
                    "at": utc_now(),
                    "result": "OUTCOME_UNKNOWN",
                    "pid_alive": False,
                    "heartbeat_age_seconds": heartbeat_age,
                    "retry_permitted": False,
                },
            )

        result = (
            "ACTIVE_STALE_HEARTBEAT"
            if heartbeat_age is None or heartbeat_age > heartbeat_stale_seconds
            else "ACTIVE"
        )
        return self.update(
            operation_id,
            reconciliation={
                "at": utc_now(),
                "result": result,
                "pid_alive": True,
                "heartbeat_age_seconds": heartbeat_age,
                "retry_permitted": False,
            },
        )


def public_operation_view(record: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, secret-free status payload."""
    keys = (
        "schema",
        "operation_id",
        "attempt_id",
        "host_id",
        "pid",
        "status",
        "phase",
        "provider",
        "model",
        "effort",
        "cwd",
        "repo_root",
        "base_head",
        "runtime_revision",
        "created_at",
        "started_at",
        "last_heartbeat_at",
        "last_output_at",
        "finished_at",
        "attempts",
        "rotations",
        "account_alias_hash",
        "lease_id_hash",
        "failure_kind",
        "exit_code",
        "observed_changed_paths",
        "reconciliation",
        "stdout_path",
        "stderr_path",
    )
    return {key: record.get(key) for key in keys}
