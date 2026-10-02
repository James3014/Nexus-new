"""Durable execution observation for direct external-worker operations.

The journal records what happened to one already-authorized direct execution.
It is transport observation only: it does not own routing, Workforce admission,
acceptance, merge, release, or production authority.
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

TERMINAL_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED", "OUTCOME_UNKNOWN"})
ACTIVE_STATES = frozenset({"QUEUED", "RUNNING", "WAITING_INPUT"})
_ALLOWED_STATES = TERMINAL_STATES | ACTIVE_STATES

PUBLIC_OPERATION_KEYS = (
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
    "mode",
    "auto_approve",
    "require_free",
    "cli_version",
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
    "observed_provider",
    "observed_model",
    "finish_reason",
    "total_cost",
    "provider_session_id",
    "tool_event_count",
    "command_sha256",
    "failure_kind",
    "exit_code",
    "observed_changed_paths",
    "reconciliation",
    "stdout_path",
    "stderr_path",
    "review_profile_version",
    "review_effect_id",
    "review_role",
    "review_repository",
    "review_base_revision",
    "review_candidate_head",
    "candidate_digest",
    "acceptance_contract_sha256",
    "review_packet_sha256",
    "review_changed_path_count",
    "review_state",
    "review_verdict",
    "review_applicable",
    "subject_stable",
    "current_candidate_digest",
    "review_receipt_path",
    "review_receipt_sha256",
    "review_failure_kind",
)


class DirectOperationJournalError(RuntimeError):
    """Operation journal contract or persistence failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_operation_id(prefix: str) -> str:
    _validate_prefix(prefix)
    return prefix + uuid.uuid4().hex


def new_attempt_id() -> str:
    return "attempt_" + uuid.uuid4().hex


def _validate_prefix(prefix: str) -> str:
    value = str(prefix)
    if not value or len(value) > 32:
        raise DirectOperationJournalError("INVALID_OPERATION_PREFIX")
    if any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for ch in value):
        raise DirectOperationJournalError("INVALID_OPERATION_PREFIX")
    return value


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


class DirectOperationJournal:
    """Filesystem-backed journal for one direct external-worker provider."""

    def __init__(
        self,
        root: Path,
        *,
        schema: str,
        operation_prefix: str,
    ) -> None:
        if not schema or not isinstance(schema, str):
            raise DirectOperationJournalError("INVALID_OPERATION_SCHEMA")
        self.root = Path(root).expanduser()
        self.schema = schema
        self.operation_prefix = _validate_prefix(operation_prefix)
        self.operations_dir = self.root / "operations"

    def _validate_operation_id(self, operation_id: str) -> str:
        value = str(operation_id).strip()
        if not value.startswith(self.operation_prefix):
            raise DirectOperationJournalError("INVALID_OPERATION_ID")
        suffix = value[len(self.operation_prefix) :]
        if len(suffix) != 32 or any(ch not in "0123456789abcdef" for ch in suffix):
            raise DirectOperationJournalError("INVALID_OPERATION_ID")
        return value

    def new_operation_id(self) -> str:
        return new_operation_id(self.operation_prefix)

    def operation_dir(self, operation_id: str) -> Path:
        return self.operations_dir / self._validate_operation_id(operation_id)

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
        initial_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        operation_id = self._validate_operation_id(operation_id)
        op_dir = self.operation_dir(operation_id)
        try:
            op_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        except FileExistsError as exc:
            raise DirectOperationJournalError("OPERATION_ALREADY_EXISTS") from exc
        repo_root, base_head = _git_identity(cwd)
        now = utc_now()
        record: dict[str, Any] = {
            "schema": self.schema,
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
            "observed_provider": None,
            "observed_model": None,
            "finish_reason": None,
            "total_cost": None,
            "provider_session_id": None,
            "tool_event_count": 0,
            "command_sha256": None,
            "failure_kind": None,
            "exit_code": None,
            "observed_changed_paths": [],
            "reconciliation": None,
            "stdout_path": str(self.stdout_path(operation_id)),
            "stderr_path": str(self.stderr_path(operation_id)),
        }
        if initial_fields:
            reserved = {
                "schema",
                "operation_id",
                "attempt_id",
                "prompt_sha256",
                "stdout_path",
                "stderr_path",
            }
            if reserved.intersection(initial_fields):
                raise DirectOperationJournalError("INITIAL_FIELD_RESERVED")
            record.update(initial_fields)
        _atomic_json_write(self.record_path(operation_id), record)
        return record

    def read(self, operation_id: str) -> dict[str, Any]:
        path = self.record_path(operation_id)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DirectOperationJournalError("OPERATION_NOT_FOUND") from exc
        except json.JSONDecodeError as exc:
            raise DirectOperationJournalError("OPERATION_RECORD_INVALID") from exc
        if record.get("schema") != self.schema:
            raise DirectOperationJournalError("OPERATION_SCHEMA_MISMATCH")
        if record.get("operation_id") != self._validate_operation_id(operation_id):
            raise DirectOperationJournalError("OPERATION_ID_MISMATCH")
        if record.get("status") not in _ALLOWED_STATES:
            raise DirectOperationJournalError("OPERATION_STATUS_INVALID")
        return record

    def update(self, operation_id: str, **changes: Any) -> dict[str, Any]:
        operation_id = self._validate_operation_id(operation_id)
        lock_path = self.operation_dir(operation_id) / ".lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as lock_fh:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
            try:
                record = self.read(operation_id)
                if "status" in changes and changes["status"] not in _ALLOWED_STATES:
                    raise DirectOperationJournalError("OPERATION_STATUS_INVALID")
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
        self,
        operation_id: str,
        *,
        phase: str | None = None,
        output_observed: bool = False,
        **changes: Any,
    ) -> dict[str, Any]:
        now = utc_now()
        payload: dict[str, Any] = {"last_heartbeat_at": now}
        if output_observed:
            payload["last_output_at"] = now
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
            raise DirectOperationJournalError("TERMINAL_STATUS_REQUIRED")
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
    return {key: record.get(key) for key in PUBLIC_OPERATION_KEYS}
