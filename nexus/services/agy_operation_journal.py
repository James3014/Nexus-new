"""Agy compatibility facade over the provider-neutral direct-operation journal."""

from __future__ import annotations

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


def new_operation_id() -> str:
    return _new_operation_id(_OPERATION_PREFIX)


def _process_alive(pid: object) -> bool:
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

    for p in sorted(verified_pids):
        _stop_process(p, grace_seconds=grace_seconds)

    if isinstance(provider_pgid, int) and provider_pgid > 1:
        if _group_has_operation_marker(provider_pgid, marker, operation_id=operation_id):
            _stop_process_group(provider_pgid, grace_seconds=grace_seconds)
    if isinstance(pid, int) and pid > 1 and pid != current_pid and pid != supervisor_pid:
        if _group_has_operation_marker(pid, marker, operation_id=operation_id):
            _stop_process_group(pid, grace_seconds=grace_seconds)

    alive_after = any(_process_alive(p) for p in verified_pids) or bool(unverified_alive_pids)
    has_unverified_conflict = bool(unverified_alive_pids)
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

        op_dir = self.operation_dir(operation_id)
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
