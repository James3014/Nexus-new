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
