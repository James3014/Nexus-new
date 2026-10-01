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
    return True


def _process_group_rows(pgid: object) -> list[tuple[str, str]]:
    if not isinstance(pgid, int) or pgid <= 0:
        return []
    proc = subprocess.run(
        ["ps", "axww", "-o", "pgid=,stat=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    rows: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        try:
            row_pgid = int(parts[0])
        except ValueError:
            continue
        if row_pgid == pgid:
            rows.append((parts[1], parts[2]))
    return rows


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


def _group_has_operation_marker(pgid: int, marker: str) -> bool:
    return any(marker in command for _stat, command in _process_group_rows(pgid))


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
        group_alive = _process_group_alive(wrapper_pid)

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

        if not group_alive:
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

        assert isinstance(wrapper_pid, int)
        marker = str(self.operation_dir(operation_id) / "agy.log")
        if not _group_has_operation_marker(wrapper_pid, marker):
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

        stopped = _stop_process_group(wrapper_pid)
        if not stopped:
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
