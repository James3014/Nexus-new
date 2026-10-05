"""Durable execution observation for direct external-worker operations.

The journal records what happened to one already-authorized direct execution.
It is transport observation only: it does not own routing, Workforce admission,
acceptance, merge, release, or production authority.
"""

from __future__ import annotations

import fcntl
import hashlib
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
    "dispatcher_heartbeat_at",
    "provider_pid",
    "provider_pgid",
    "provider_process_state",
    "provider_started_at",
    "provider_stream_last_activity_at",
    "first_stream_activity_at",
    "first_effect_at",
    "time_to_first_effect_ms",
    "last_output_at",
    "finished_at",
    "reconciled_at",
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
    "source_baseline_sha256",
    "source_attribution_state",
    "input_delivery_state",
    "input_delivery_source",
    "input_delivery_truncations",
    "quota_preflight_progress",
    "reconciliation",
    "stdout_path",
    "stderr_path",
    "review_profile_version",
    "review_launch_catalog_version",
    "review_launch_profile_id",
    "review_launch_profile_sha256",
    "review_launch_mode",
    "review_launch_requested_effort",
    "review_packet_mode",
    "review_compaction_schema",
    "review_compact_payload_sha256",
    "review_effect_id",
    "review_role",
    "review_repository",
    "review_repo_root_sha256",
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
    "permission_profile_sha256",
    "permission_profile_kind",
    "effective_permissions",
    "write_paths",
    "scope_validation_state",
    "scope_violations",
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


def process_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    proc = subprocess.run(
        ["ps", "-p", str(pid), "-o", "stat="],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        stat = proc.stdout.strip()
        if stat.startswith("Z"):
            return False
    return True


_process_alive = process_alive


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


SOURCE_BASELINE_SCHEMA = "nexus.source_baseline.v1"


def _safe_repo_relative_path(value: str) -> str | None:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        return None
    return value


def _path_fingerprint(root: Path, relative: str) -> dict[str, str] | None:
    safe = _safe_repo_relative_path(relative)
    if safe is None:
        return None
    target = root / safe
    try:
        if target.is_symlink():
            payload = os.fsencode(os.readlink(target))
            return {"kind": "symlink", "sha256": hashlib.sha256(payload).hexdigest()}
        if not target.exists():
            return {"kind": "missing", "sha256": hashlib.sha256(b"missing").hexdigest()}
        if target.is_file():
            digest = hashlib.sha256()
            with target.open("rb") as fh:
                while True:
                    chunk = fh.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
            return {"kind": "file", "sha256": digest.hexdigest()}
        if target.is_dir():
            return {"kind": "directory", "sha256": hashlib.sha256(b"directory").hexdigest()}
    except OSError:
        return None
    return None


def _status_entries(cwd: str) -> dict[str, dict[str, str]] | None:
    root_text, _head = _git_identity(cwd)
    if not root_text:
        return None
    root = Path(root_text)
    proc = subprocess.run(
        [
            "git",
            "-C",
            cwd,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None

    records = proc.stdout.split(b"\0")
    entries: dict[str, dict[str, str]] = {}
    index = 0
    while index < len(records):
        raw = records[index]
        index += 1
        if not raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
        if len(text) < 4 or text[2] != " ":
            return None
        status = text[:2]
        path = _safe_repo_relative_path(text[3:])
        if path is None:
            return None
        fingerprint = _path_fingerprint(root, path)
        if fingerprint is None:
            return None
        entries[path] = {"status": status, **fingerprint}

        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            if index >= len(records) or not records[index]:
                return None
            try:
                source_path = records[index].decode("utf-8")
            except UnicodeDecodeError:
                return None
            index += 1
            source_path = _safe_repo_relative_path(source_path)
            if source_path is None:
                return None
            source_fingerprint = _path_fingerprint(root, source_path)
            if source_fingerprint is None:
                return None
            entries[source_path] = {"status": "OR", **source_fingerprint}
    return dict(sorted(entries.items()))


def capture_source_baseline(cwd: str) -> dict[str, Any] | None:
    entries = _status_entries(cwd)
    if entries is None:
        return None
    return {"schema": SOURCE_BASELINE_SCHEMA, "entries": entries}


def _valid_source_baseline(baseline: object) -> bool:
    if not isinstance(baseline, dict):
        return False
    if set(baseline) != {"schema", "entries"}:
        return False
    if baseline.get("schema") != SOURCE_BASELINE_SCHEMA:
        return False
    entries = baseline.get("entries")
    if not isinstance(entries, dict):
        return False
    for path, entry in entries.items():
        if not isinstance(path, str) or _safe_repo_relative_path(path) != path:
            return False
        if not isinstance(entry, dict) or set(entry) != {"status", "kind", "sha256"}:
            return False
        status = entry.get("status")
        kind = entry.get("kind")
        digest = entry.get("sha256")
        if not isinstance(status, str) or len(status) != 2:
            return False
        if kind not in {"file", "symlink", "missing", "directory"}:
            return False
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            return False
    return True


def source_baseline_sha256(baseline: object) -> str | None:
    if not _valid_source_baseline(baseline):
        return None
    assert isinstance(baseline, dict)
    encoded = json.dumps(
        baseline,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def observed_changed_paths_since(cwd: str, baseline: object) -> list[str] | None:
    if source_baseline_sha256(baseline) is None:
        return None
    assert isinstance(baseline, dict)
    baseline_entries = baseline.get("entries")
    if not isinstance(baseline_entries, dict):
        return None
    current = capture_source_baseline(cwd)
    if current is None:
        return None
    current_entries = current["entries"]
    return sorted(
        path
        for path in set(baseline_entries) | set(current_entries)
        if baseline_entries.get(path) != current_entries.get(path)
    )


def observed_changed_paths(cwd: str) -> list[str]:
    snapshot = capture_source_baseline(cwd)
    if snapshot is None:
        return []
    return sorted(snapshot["entries"])


def normalize_write_paths(
    repo_root: str | Path,
    write_paths: Any,
) -> list[str]:
    """Normalize declared write paths to canonical repo-relative paths."""
    if not write_paths or not isinstance(write_paths, (list, tuple, set)):
        return []
    root = Path(repo_root).resolve()
    normalized: set[str] = set()
    for raw in write_paths:
        if not isinstance(raw, str) or not raw.strip():
            continue
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            rel = candidate.resolve().relative_to(root)
            normalized.add(str(rel))
        except ValueError:
            normalized.add(str(raw).strip())
    return sorted(normalized)


def _is_path_in_scope(path: str, allowed_paths: set[str]) -> bool:
    for allowed in allowed_paths:
        if path == allowed or path.startswith(allowed.rstrip("/") + "/"):
            return True
    return False


def validate_write_scope(
    repo_root: str | Path,
    write_paths: Any,
    observed_changed_paths: list[str] | None,
) -> tuple[str, list[str]]:
    """Validate observed changed paths against declared write paths.

    Returns:
        (scope_validation_state, scope_violations)
        Where scope_validation_state is one of:
        - "UNCONSTRAINED": write_paths is None or empty.
        - "VERIFIED_IN_SCOPE": all observed paths are within write_paths.
        - "VIOLATION_OUT_OF_SCOPE": one or more paths are outside write_paths.
    """
    if not write_paths:
        return "UNCONSTRAINED", []
    if observed_changed_paths is None:
        return "UNCONSTRAINED", []
    allowed = set(normalize_write_paths(repo_root, write_paths))
    violations = [p for p in observed_changed_paths if not _is_path_in_scope(p, allowed)]
    if violations:
        return "VIOLATION_OUT_OF_SCOPE", sorted(violations)
    return "VERIFIED_IN_SCOPE", []


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
        write_paths: list[str] | None = None,
        initial_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        operation_id = self._validate_operation_id(operation_id)
        op_dir = self.operation_dir(operation_id)
        if op_dir.exists():
            raise DirectOperationJournalError("OPERATION_ALREADY_EXISTS")
        repo_root, base_head = _git_identity(cwd)
        source_baseline = capture_source_baseline(cwd) if repo_root else None
        source_baseline_hash = source_baseline_sha256(source_baseline)
        source_attribution_state = (
            "BASELINE_CAPTURED" if source_baseline_hash is not None else "UNAVAILABLE"
        )
        try:
            op_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        except FileExistsError as exc:
            raise DirectOperationJournalError("OPERATION_ALREADY_EXISTS") from exc
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
            "dispatcher_heartbeat_at": None,
            "provider_pid": None,
            "provider_pgid": None,
            "provider_process_state": "IDLE",
            "provider_started_at": None,
            "provider_stream_last_activity_at": None,
            "first_stream_activity_at": None,
            "first_effect_at": None,
            "time_to_first_effect_ms": None,
            "last_output_at": None,
            "finished_at": None,
            "reconciled_at": None,
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
            "source_baseline": source_baseline,
            "source_baseline_sha256": source_baseline_hash,
            "source_attribution_state": source_attribution_state,
            "input_delivery_state": "UNKNOWN",
            "input_delivery_source": None,
            "input_delivery_truncations": [],
            "quota_preflight_progress": None,
            "reconciliation": None,
            "permission_profile_sha256": None,
            "permission_profile_kind": None,
            "effective_permissions": None,
            "write_paths": list(write_paths) if write_paths else [],
            "scope_validation_state": "UNCONSTRAINED",
            "scope_violations": [],
            "stdout_path": str(self.stdout_path(operation_id)),
            "stderr_path": str(self.stderr_path(operation_id)),
        }
        if initial_fields:
            reserved = {
                "schema",
                "operation_id",
                "attempt_id",
                "prompt_sha256",
                "source_baseline",
                "source_baseline_sha256",
                "source_attribution_state",
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
                if "write_paths" in changes and changes["write_paths"] is not None:
                    record_root = record.get("repo_root") or record.get("cwd") or "."
                    changes["write_paths"] = normalize_write_paths(
                        record_root, changes["write_paths"]
                    )
                    if changes["write_paths"]:
                        changes.setdefault("scope_validation_state", "PENDING")
                    else:
                        changes.setdefault("scope_validation_state", "UNCONSTRAINED")
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
            "dispatcher_heartbeat_at": now,
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
        payload: dict[str, Any] = {
            "last_heartbeat_at": now,
            "dispatcher_heartbeat_at": now,
        }
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
        now = utc_now()
        payload: dict[str, Any] = {
            "status": status,
            "phase": "TERMINAL",
            "finished_at": now,
            "last_heartbeat_at": now,
            "dispatcher_heartbeat_at": now,
            "exit_code": exit_code,
            "failure_kind": failure_kind,
        }
        payload.update(changes)
        if cwd:
            record = self.read(operation_id)
            baseline = record.get("source_baseline")
            baseline_hash = record.get("source_baseline_sha256")
            valid_baseline_hash = source_baseline_sha256(baseline)
            record_root = record.get("repo_root")
            current_root, _current_head = _git_identity(cwd)
            try:
                same_root = bool(
                    isinstance(record_root, str)
                    and isinstance(current_root, str)
                    and os.path.samefile(record_root, current_root)
                )
            except OSError:
                same_root = False
            if (
                same_root
                and isinstance(baseline_hash, str)
                and valid_baseline_hash == baseline_hash
            ):
                delta = observed_changed_paths_since(cwd, baseline)
            else:
                delta = None
            if delta is None:
                payload["observed_changed_paths"] = []
                payload["source_attribution_state"] = "UNAVAILABLE"
            else:
                payload["observed_changed_paths"] = delta
                payload["source_attribution_state"] = "ATTRIBUTED"

            effective_write_paths = payload.get("write_paths", record.get("write_paths"))
            scope_state, violations = validate_write_scope(
                repo_root=record_root or cwd,
                write_paths=effective_write_paths,
                observed_changed_paths=delta,
            )
            payload["scope_validation_state"] = scope_state
            payload["scope_violations"] = violations
            if violations and payload.get("status") == "COMPLETED":
                payload["status"] = "FAILED"
                payload["failure_kind"] = "SCOPE_VIOLATION_UNAUTHORIZED_MUTATION"
        return self.update(operation_id, **payload)

    def prove_source_state_unchanged(self, operation_id: str) -> dict[str, Any]:
        """Prove only that the repository source state still equals the captured baseline.

        This is intentionally narrower than proving the provider had no external
        effects. It is suitable only for releasing a source-mutation retry fence.
        """
        record = self.read(operation_id)
        if record.get("status") != "OUTCOME_UNKNOWN":
            raise DirectOperationJournalError("SOURCE_PROOF_REQUIRES_OUTCOME_UNKNOWN")
        if record.get("source_attribution_state") != "ATTRIBUTED":
            raise DirectOperationJournalError("SOURCE_ATTRIBUTION_UNAVAILABLE")
        if record.get("effect_observation_error"):
            raise DirectOperationJournalError("SOURCE_EFFECT_OBSERVATION_UNRELIABLE")
        if record.get("first_effect_at") is not None:
            raise DirectOperationJournalError("SOURCE_EFFECT_PREVIOUSLY_OBSERVED")
        observed = record.get("observed_changed_paths")
        if observed != []:
            raise DirectOperationJournalError("SOURCE_STATE_CHANGED")

        baseline = record.get("source_baseline")
        baseline_hash = record.get("source_baseline_sha256")
        valid_baseline_hash = source_baseline_sha256(baseline)
        if (
            not isinstance(baseline_hash, str)
            or valid_baseline_hash is None
            or valid_baseline_hash != baseline_hash
        ):
            raise DirectOperationJournalError("SOURCE_BASELINE_UNAVAILABLE")

        cwd = record.get("cwd")
        record_root = record.get("repo_root")
        base_head = record.get("base_head")
        if (
            not isinstance(cwd, str)
            or not cwd
            or not isinstance(record_root, str)
            or not record_root
            or not isinstance(base_head, str)
            or not base_head
        ):
            raise DirectOperationJournalError("SOURCE_IDENTITY_UNAVAILABLE")

        current_root, current_head = _git_identity(cwd)
        try:
            same_root = bool(
                isinstance(current_root, str) and os.path.samefile(record_root, current_root)
            )
        except OSError:
            same_root = False
        if not same_root or current_head != base_head:
            raise DirectOperationJournalError("SOURCE_IDENTITY_CHANGED")

        delta = observed_changed_paths_since(cwd, baseline)
        if delta is None:
            raise DirectOperationJournalError("SOURCE_STATE_UNAVAILABLE")
        if delta:
            raise DirectOperationJournalError("SOURCE_STATE_CHANGED")

        return {
            "proof_scope": "SOURCE_STATE_ONLY",
            "repo_root": record_root,
            "base_head": base_head,
            "source_baseline_sha256": baseline_hash,
            "observed_changed_paths": [],
            "first_effect_at": None,
        }

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

        reconciled_now = utc_now()
        extra_changes: dict[str, Any] = {
            "reconciled_at": reconciled_now,
        }
        provider_pid = record.get("provider_pid")
        provider_alive = (
            _process_alive(provider_pid)
            if isinstance(provider_pid, int) and provider_pid > 0
            else False
        )
        if isinstance(provider_pid, int) and provider_pid > 0:
            extra_changes["provider_process_state"] = "RUNNING" if provider_alive else "EXITED"

        if not pid_alive:
            if provider_alive:
                return self.update(
                    operation_id,
                    status="RUNNING",
                    phase="RECONCILE_REQUIRED",
                    reconciliation={
                        "at": reconciled_now,
                        "result": "PROVIDER_PROCESS_STILL_RUNNING",
                        "pid_alive": False,
                        "provider_alive_before": True,
                        "provider_alive_after": True,
                        "heartbeat_age_seconds": heartbeat_age,
                        "retry_permitted": False,
                    },
                    **extra_changes,
                )
            return self.mark_terminal(
                operation_id,
                status="OUTCOME_UNKNOWN",
                exit_code=None,
                failure_kind="PROCESS_NOT_RUNNING_WITHOUT_TERMINAL_RECEIPT",
                cwd=record.get("cwd"),
                reconciliation={
                    "at": reconciled_now,
                    "result": "OUTCOME_UNKNOWN",
                    "pid_alive": False,
                    "heartbeat_age_seconds": heartbeat_age,
                    "retry_permitted": False,
                },
                **extra_changes,
            )

        result = (
            "ACTIVE_STALE_HEARTBEAT"
            if heartbeat_age is None or heartbeat_age > heartbeat_stale_seconds
            else "ACTIVE"
        )
        return self.update(
            operation_id,
            reconciliation={
                "at": reconciled_now,
                "result": result,
                "pid_alive": True,
                "heartbeat_age_seconds": heartbeat_age,
                "retry_permitted": False,
            },
            **extra_changes,
        )


def public_operation_view(record: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, secret-free status payload."""
    return {key: record.get(key) for key in PUBLIC_OPERATION_KEYS}
