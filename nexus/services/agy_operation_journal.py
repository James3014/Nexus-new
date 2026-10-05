"""Agy compatibility facade over the provider-neutral direct-operation journal."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from nexus.services.direct_operation_journal import (
    TERMINAL_STATES,
    DirectOperationJournal,
    DirectOperationJournalError,
    process_alive,
)
from nexus.services.direct_operation_journal import (
    new_attempt_id as new_attempt_id,
)
from nexus.services.direct_operation_journal import (
    new_operation_id as _new_operation_id,
)
from nexus.services.direct_operation_journal import (
    public_operation_view as public_operation_view,
)
from nexus.services.direct_operation_journal import (
    utc_now as utc_now,
)

SCHEMA = "nexus.agy_operation.v1"
_OPERATION_PREFIX = "agyop_"
AgyOperationJournalError = DirectOperationJournalError

_EFFECT_RESOLUTION_SCHEMA = "nexus.agy_operation_effect_resolution.v1"
_NO_REPOSITORY_EFFECT = "CONFIRMED_NO_REPOSITORY_EFFECT"
_HEX64 = frozenset("0123456789abcdef")


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in _HEX64 for ch in value)


def new_operation_id() -> str:
    return _new_operation_id(_OPERATION_PREFIX)


_process_alive = process_alive


def _process_command(pid: object) -> str | None:
    if not isinstance(pid, int) or pid <= 0:
        return None
    proc = subprocess.run(
        ["ps", "-ww", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _pid_has_operation_marker(pid: int, marker: str, operation_id: str | None = None) -> bool:
    cmd = _process_command(pid)
    if not cmd:
        return False
    if marker in cmd:
        return True
    if operation_id and f"{operation_id}/agy.log" in cmd:
        return True
    return False


def _find_operation_process(
    marker: str, operation_id: str | None = None
) -> tuple[int | None, int | None]:
    current_pid = os.getpid()
    parent_pid = os.getppid()
    try:
        current_pgrp = os.getpgrp()
    except OSError:
        current_pgrp = None
    proc = subprocess.run(
        ["ps", "axww", "-o", "pid=,pgid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None, None
    for line in proc.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        try:
            row_pid = int(parts[0])
            row_pgid = int(parts[1])
        except ValueError:
            continue
        if row_pid in (current_pid, parent_pid) or row_pid <= 1:
            continue
        command = parts[2]
        if marker in command or (operation_id and f"{operation_id}/agy.log" in command):
            if _process_alive(row_pid):
                effective_pgid = row_pgid if row_pgid != current_pgrp and row_pgid > 1 else None
                return row_pid, effective_pgid
    return None, None


def _child_pids_of(parent_pid: int) -> list[int]:
    if not isinstance(parent_pid, int) or parent_pid <= 0:
        return []
    proc = subprocess.run(
        ["ps", "axww", "-o", "pid=,ppid="],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    children: list[int] = []
    for line in proc.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            try:
                p_pid = int(parts[0])
                p_ppid = int(parts[1])
                if p_ppid == parent_pid:
                    children.append(p_pid)
            except ValueError:
                continue
    return children


def _process_group_process_rows(pgid: object) -> list[tuple[int, str, str]]:
    if not isinstance(pgid, int) or pgid <= 0:
        return []
    proc = subprocess.run(
        ["ps", "axww", "-o", "pgid=,pid=,stat=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    rows: list[tuple[int, str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) != 4:
            continue
        try:
            row_pgid = int(parts[0])
            row_pid = int(parts[1])
        except ValueError:
            continue
        if row_pgid == pgid:
            rows.append((row_pid, parts[2], parts[3]))
    return rows


def _process_group_rows(pgid: object) -> list[tuple[str, str]]:
    return [(stat, command) for _pid, stat, command in _process_group_process_rows(pgid)]


def _process_group_alive(pgid: object) -> bool:
    rows = _process_group_rows(pgid)
    if rows:
        return any(not stat.startswith("Z") for stat, _command in rows)
    if not isinstance(pgid, int) or pgid <= 0:
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _group_has_operation_marker(pgid: int, marker: str, operation_id: str | None = None) -> bool:
    for _stat, command in _process_group_rows(pgid):
        if marker in command:
            return True
        if operation_id and f"{operation_id}/agy.log" in command:
            return True
    return False


def _stop_process(pid: int, *, grace_seconds: float = 2.0) -> bool:
    try:
        r_pid, _ = os.waitpid(pid, os.WNOHANG)
        if r_pid == pid:
            return True
    except (ChildProcessError, OSError):
        pass
    if not _process_alive(pid):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False

    deadline = time.monotonic() + max(0.1, grace_seconds)
    while time.monotonic() < deadline:
        try:
            r_pid, _ = os.waitpid(pid, os.WNOHANG)
            if r_pid == pid:
                return True
        except (ChildProcessError, OSError):
            pass
        if not _process_alive(pid):
            return True
        time.sleep(0.05)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False

    deadline = time.monotonic() + max(0.1, grace_seconds)
    while time.monotonic() < deadline:
        try:
            r_pid, _ = os.waitpid(pid, os.WNOHANG)
            if r_pid == pid:
                return True
        except (ChildProcessError, OSError):
            pass
        if not _process_alive(pid):
            return True
        time.sleep(0.05)
    return not _process_alive(pid)


def _stop_process_group(pgid: int, *, grace_seconds: float = 2.0) -> bool:
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False

    deadline = time.monotonic() + max(0.1, grace_seconds)
    while time.monotonic() < deadline:
        if not _process_group_alive(pgid):
            return True
        time.sleep(0.05)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False

    deadline = time.monotonic() + max(0.1, grace_seconds)
    while time.monotonic() < deadline:
        if not _process_group_alive(pgid):
            return True
        time.sleep(0.05)
    return not _process_group_alive(pgid)


def _stop_operation_processes(
    operation_id: str,
    op_dir: Path,
    *,
    pid: int | None = None,
    provider_pid: int | None = None,
    provider_pgid: int | None = None,
    supervisor_pid: int | None = None,
    grace_seconds: float = 2.0,
) -> tuple[bool, bool, bool]:
    current_pid = os.getpid()
    marker = str(op_dir / "agy.log")
    candidate_pids: set[int] = set()
    group_or_recorded_pids: set[int] = set()
    if isinstance(provider_pid, int) and provider_pid > 1:
        candidate_pids.add(provider_pid)
        group_or_recorded_pids.add(provider_pid)
    if isinstance(provider_pgid, int) and provider_pgid > 1:
        for row_pid, _stat, _cmd in _process_group_process_rows(provider_pgid):
            if row_pid > 1:
                candidate_pids.add(row_pid)
                group_or_recorded_pids.add(row_pid)
    if isinstance(pid, int) and pid > 1 and pid != current_pid and pid != supervisor_pid:
        for row_pid, _stat, _cmd in _process_group_process_rows(pid):
            if row_pid > 1:
                candidate_pids.add(row_pid)
                group_or_recorded_pids.add(row_pid)
    if isinstance(supervisor_pid, int) and supervisor_pid > 1:
        for child_pid in _child_pids_of(supervisor_pid):
            if child_pid > 1:
                candidate_pids.add(child_pid)

    if not candidate_pids:
        disc_pid, disc_pgid = _find_operation_process(marker, operation_id=operation_id)
        if disc_pid is not None:
            candidate_pids.add(disc_pid)
            group_or_recorded_pids.add(disc_pid)
            if disc_pgid is not None:
                provider_pgid = disc_pgid
                for row_pid, _stat, _cmd in _process_group_process_rows(disc_pgid):
                    if row_pid > 1:
                        candidate_pids.add(row_pid)
                        group_or_recorded_pids.add(row_pid)

    candidate_pids.discard(current_pid)
    group_or_recorded_pids.discard(current_pid)
    if supervisor_pid is not None:
        candidate_pids.discard(supervisor_pid)
        group_or_recorded_pids.discard(supervisor_pid)

    verified_pids: set[int] = set()
    unverified_alive_pids: set[int] = set()

    for c_pid in candidate_pids:
        if not _process_alive(c_pid):
            continue
        if _pid_has_operation_marker(c_pid, marker, operation_id=operation_id):
            verified_pids.add(c_pid)
        elif c_pid in group_or_recorded_pids:
            unverified_alive_pids.add(c_pid)

    had_alive_before = bool(verified_pids) or bool(unverified_alive_pids)

    provider_group_verified = (
        isinstance(provider_pgid, int)
        and provider_pgid > 1
        and _group_has_operation_marker(provider_pgid, marker, operation_id=operation_id)
    )
    wrapper_group_verified = (
        isinstance(pid, int)
        and pid > 1
        and pid != current_pid
        and pid != supervisor_pid
        and _group_has_operation_marker(pid, marker, operation_id=operation_id)
    )

    # Preserve the ownership witness while the marked leader is still present.
    # Killing the leader first can erase the only marker and strand owned
    # grandchildren as an unverifiable group.
    if provider_group_verified and isinstance(provider_pgid, int):
        _stop_process_group(provider_pgid, grace_seconds=grace_seconds)
    if wrapper_group_verified and isinstance(pid, int):
        _stop_process_group(pid, grace_seconds=grace_seconds)

    for p in sorted(verified_pids):
        if _process_alive(p):
            _stop_process(p, grace_seconds=grace_seconds)

    residual_unverified = {p for p in unverified_alive_pids if _process_alive(p)}
    residual_verified = {p for p in verified_pids if _process_alive(p)}
    provider_group_alive = (
        isinstance(provider_pgid, int) and provider_pgid > 1 and _process_group_alive(provider_pgid)
    )
    wrapper_group_alive = (
        isinstance(pid, int)
        and pid > 1
        and pid != current_pid
        and pid != supervisor_pid
        and _process_group_alive(pid)
    )

    alive_after = bool(
        residual_verified or residual_unverified or provider_group_alive or wrapper_group_alive
    )
    has_unverified_conflict = bool(residual_unverified)
    if provider_group_alive and not provider_group_verified:
        has_unverified_conflict = True
    if wrapper_group_alive and not wrapper_group_verified:
        has_unverified_conflict = True
    return had_alive_before, alive_after, has_unverified_conflict


class AgyOperationJournal(DirectOperationJournal):
    """Preserve the existing Agy journal contract while sharing the core."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            root,
            schema=SCHEMA,
            operation_prefix=_OPERATION_PREFIX,
        )

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
        return super().create(
            operation_id=operation_id,
            attempt_id=attempt_id,
            cwd=cwd,
            provider=provider,
            model=model,
            effort=effort,
            prompt_sha256=prompt_sha256,
            runtime_revision=runtime_revision,
            initial_fields=initial_fields,
        )

    def effect_resolution_path(self, operation_id: str) -> Path:
        return self.operation_dir(operation_id) / "effect-resolution.json"

    @staticmethod
    def _operation_identity(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "operation_id": record.get("operation_id"),
            "attempt_id": record.get("attempt_id"),
            "provider": record.get("provider"),
            "provider_session_id": record.get("provider_session_id"),
            "runtime_revision": record.get("runtime_revision"),
            "base_head": record.get("base_head"),
            "prompt_sha256": record.get("prompt_sha256"),
            "created_at": record.get("created_at"),
            "finished_at": record.get("finished_at"),
        }

    def _validate_effect_resolution(
        self,
        operation_id: str,
        payload: object,
        *,
        record: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise AgyOperationJournalError("EFFECT_RESOLUTION_INVALID")
        expected_keys = {
            "schema",
            "operation_id",
            "attempt_id",
            "disposition",
            "evidence_ref",
            "evidence_sha256",
            "operation_identity_sha256",
            "provider_process_state",
            "resolved_at",
            "resolution_sha256",
        }
        if set(payload) != expected_keys:
            raise AgyOperationJournalError("EFFECT_RESOLUTION_INVALID")
        current = record or self.read(operation_id)
        if current.get("status") != "OUTCOME_UNKNOWN":
            raise AgyOperationJournalError("EFFECT_RESOLUTION_REQUIRES_OUTCOME_UNKNOWN")
        reconciliation = current.get("reconciliation")
        if (
            not isinstance(reconciliation, dict)
            or reconciliation.get("retry_permitted") is not False
        ):
            raise AgyOperationJournalError("EFFECT_RESOLUTION_RETRY_STATE_INVALID")
        if reconciliation.get("provider_alive_after") is not False:
            raise AgyOperationJournalError("EFFECT_RESOLUTION_PROVIDER_STATE_UNPROVEN")
        if payload.get("schema") != _EFFECT_RESOLUTION_SCHEMA:
            raise AgyOperationJournalError("EFFECT_RESOLUTION_SCHEMA_MISMATCH")
        if payload.get("operation_id") != operation_id:
            raise AgyOperationJournalError("EFFECT_RESOLUTION_OPERATION_MISMATCH")
        if payload.get("attempt_id") != current.get("attempt_id"):
            raise AgyOperationJournalError("EFFECT_RESOLUTION_ATTEMPT_MISMATCH")
        if payload.get("disposition") != _NO_REPOSITORY_EFFECT:
            raise AgyOperationJournalError("EFFECT_RESOLUTION_DISPOSITION_INVALID")
        evidence_ref = payload.get("evidence_ref")
        if (
            not isinstance(evidence_ref, str)
            or not evidence_ref.strip()
            or len(evidence_ref) > 512
            or "\n" in evidence_ref
            or "\r" in evidence_ref
        ):
            raise AgyOperationJournalError("EFFECT_RESOLUTION_EVIDENCE_REF_INVALID")
        if not _valid_sha256(payload.get("evidence_sha256")):
            raise AgyOperationJournalError("EFFECT_RESOLUTION_EVIDENCE_HASH_INVALID")
        identity_hash = _canonical_sha256(self._operation_identity(current))
        if payload.get("operation_identity_sha256") != identity_hash:
            raise AgyOperationJournalError("EFFECT_RESOLUTION_IDENTITY_MISMATCH")
        if payload.get("provider_process_state") != "ABSENT_AT_RESOLUTION":
            raise AgyOperationJournalError("EFFECT_RESOLUTION_PROCESS_STATE_INVALID")
        if not isinstance(payload.get("resolved_at"), str) or not payload["resolved_at"]:
            raise AgyOperationJournalError("EFFECT_RESOLUTION_TIMESTAMP_INVALID")
        expected_hash = _canonical_sha256({
            key: value for key, value in payload.items() if key != "resolution_sha256"
        })
        if payload.get("resolution_sha256") != expected_hash:
            raise AgyOperationJournalError("EFFECT_RESOLUTION_HASH_MISMATCH")
        return dict(payload)

    def read_effect_resolution(
        self,
        operation_id: str,
        *,
        record: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        path = self.effect_resolution_path(operation_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise AgyOperationJournalError("EFFECT_RESOLUTION_INVALID") from exc
        return self._validate_effect_resolution(operation_id, payload, record=record)

    def resolve_no_repository_effect(
        self,
        operation_id: str,
        *,
        evidence_ref: str,
        evidence_sha256: str,
    ) -> dict[str, Any]:
        record = self.read(operation_id)
        if record.get("status") != "OUTCOME_UNKNOWN":
            raise AgyOperationJournalError("EFFECT_RESOLUTION_REQUIRES_OUTCOME_UNKNOWN")
        reconciliation = record.get("reconciliation")
        if (
            not isinstance(reconciliation, dict)
            or reconciliation.get("retry_permitted") is not False
        ):
            raise AgyOperationJournalError("EFFECT_RESOLUTION_RETRY_STATE_INVALID")
        if reconciliation.get("provider_alive_after") is not False:
            raise AgyOperationJournalError("EFFECT_RESOLUTION_PROVIDER_STATE_UNPROVEN")
        if (
            not isinstance(evidence_ref, str)
            or not evidence_ref.strip()
            or len(evidence_ref) > 512
            or "\n" in evidence_ref
            or "\r" in evidence_ref
        ):
            raise AgyOperationJournalError("EFFECT_RESOLUTION_EVIDENCE_REF_INVALID")
        if not _valid_sha256(evidence_sha256):
            raise AgyOperationJournalError("EFFECT_RESOLUTION_EVIDENCE_HASH_INVALID")

        existing = self.read_effect_resolution(operation_id, record=record)
        if existing is not None:
            if (
                existing["evidence_ref"] == evidence_ref
                and existing["evidence_sha256"] == evidence_sha256
            ):
                return existing
            raise AgyOperationJournalError("EFFECT_RESOLUTION_ALREADY_EXISTS")

        payload: dict[str, Any] = {
            "schema": _EFFECT_RESOLUTION_SCHEMA,
            "operation_id": operation_id,
            "attempt_id": record.get("attempt_id"),
            "disposition": _NO_REPOSITORY_EFFECT,
            "evidence_ref": evidence_ref,
            "evidence_sha256": evidence_sha256,
            "operation_identity_sha256": _canonical_sha256(self._operation_identity(record)),
            "provider_process_state": "ABSENT_AT_RESOLUTION",
            "resolved_at": utc_now(),
        }
        payload["resolution_sha256"] = _canonical_sha256(payload)
        path = self.effect_resolution_path(operation_id)
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = self.read_effect_resolution(operation_id, record=record)
            if (
                existing is not None
                and existing["evidence_ref"] == evidence_ref
                and existing["evidence_sha256"] == evidence_sha256
            ):
                return existing
            raise AgyOperationJournalError("EFFECT_RESOLUTION_ALREADY_EXISTS")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(encoded)
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:
            try:
                path.unlink()
            except OSError:
                pass
            raise
        return self._validate_effect_resolution(operation_id, payload, record=record)

    def reconcile(
        self,
        operation_id: str,
        *,
        heartbeat_stale_seconds: float = 120.0,
    ) -> dict[str, Any]:
        record = self.read(operation_id)
        status = record["status"]
        if status in TERMINAL_STATES and status != "OUTCOME_UNKNOWN":
            return record

        wrapper_pid = record.get("pid")
        wrapper_alive = _process_alive(wrapper_pid)
        provider_pid = record.get("provider_pid")
        provider_pgid = record.get("provider_pgid")
        provider_alive = _process_alive(provider_pid)

        if wrapper_alive:
            if status == "OUTCOME_UNKNOWN":
                return self.update(
                    operation_id,
                    phase="RECONCILE_REQUIRED",
                    reconciliation={
                        "at": utc_now(),
                        "result": "PROVIDER_OR_WRAPPER_STILL_RUNNING",
                        "pid_alive": True,
                        "provider_alive_before": True,
                        "provider_alive_after": True,
                        "retry_permitted": False,
                    },
                )
            return super().reconcile(
                operation_id,
                heartbeat_stale_seconds=heartbeat_stale_seconds,
            )

        op_dir = self.operation_dir(operation_id)
        marker = str(op_dir / "agy.log")
        if not provider_alive:
            disc_pid, disc_pgid = _find_operation_process(marker, operation_id=operation_id)
            if disc_pid is not None:
                provider_pid = disc_pid
                provider_pgid = disc_pgid
                provider_alive = True
                record = self.update(
                    operation_id,
                    provider_pid=provider_pid,
                    provider_pgid=provider_pgid,
                    provider_process_state="RUNNING",
                )

        group_alive = _process_group_alive(provider_pgid) if provider_pgid else False
        if not group_alive and wrapper_pid:
            group_alive = _process_group_alive(wrapper_pid)

        if not provider_alive and not group_alive:
            if status == "OUTCOME_UNKNOWN":
                reconciliation = dict(record.get("reconciliation") or {})
                reconciliation.update({
                    "at": utc_now(),
                    "result": reconciliation.get("result") or "OUTCOME_UNKNOWN",
                    "pid_alive": False,
                    "provider_alive_before": False,
                    "provider_alive_after": False,
                    "retry_permitted": False,
                })
                return self.update(
                    operation_id,
                    phase="TERMINAL",
                    reconciliation=reconciliation,
                )
            result = super().reconcile(
                operation_id,
                heartbeat_stale_seconds=heartbeat_stale_seconds,
            )
            reconciliation = dict(result.get("reconciliation") or {})
            reconciliation.update({
                "provider_alive_before": False,
                "provider_alive_after": False,
            })
            return self.update(operation_id, reconciliation=reconciliation)

        had_before, alive_after, unverified = _stop_operation_processes(
            operation_id,
            op_dir,
            pid=wrapper_pid,
            provider_pid=provider_pid,
            provider_pgid=provider_pgid,
            grace_seconds=2.0,
        )

        if unverified:
            return self.update(
                operation_id,
                phase="RECONCILE_REQUIRED",
                reconciliation={
                    "at": utc_now(),
                    "result": "ORPHAN_PROCESS_GROUP_UNVERIFIED",
                    "pid_alive": False,
                    "provider_alive_before": True,
                    "provider_alive_after": True,
                    "retry_permitted": False,
                },
            )

        if alive_after:
            return self.update(
                operation_id,
                phase="RECONCILE_REQUIRED",
                reconciliation={
                    "at": utc_now(),
                    "result": "ORPHAN_PROVIDER_STILL_RUNNING",
                    "pid_alive": False,
                    "provider_alive_before": True,
                    "provider_alive_after": True,
                    "retry_permitted": False,
                },
            )

        return self.mark_terminal(
            operation_id,
            status="OUTCOME_UNKNOWN",
            exit_code=None,
            failure_kind=(
                record.get("failure_kind") or "PROCESS_NOT_RUNNING_WITHOUT_TERMINAL_RECEIPT"
            ),
            cwd=record.get("cwd"),
            reconciliation={
                "at": utc_now(),
                "result": "ORPHAN_PROVIDER_TERMINATED",
                "pid_alive": False,
                "provider_alive_before": True,
                "provider_alive_after": False,
                "retry_permitted": False,
            },
        )
