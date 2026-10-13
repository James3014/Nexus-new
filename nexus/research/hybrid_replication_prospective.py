from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess  # nosec B404
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from nexus.research.hybrid_replication_pipeline import (
    ADMISSION_MARKER,
    PRIMARY_ADMISSION_DISPOSITION,
    READINESS_CONTROL_DISPOSITION,
    TaskSnapshot,
    parse_admission_comment,
)

EXECUTION_START_SCHEMA = "nexus.hybrid_replication.execution_start.v1"
PROVIDER_OPERATION_SCHEMA = "nexus.hybrid_replication.provider_operation.v1"
PROVIDER_START_SCHEMA = "nexus.hybrid_replication.provider_start.v1"
SYNCHRONOUS_EFFECT_START_SCHEMA = "nexus.hybrid_replication.synchronous_effect_start.v1"
PROTOCOL_LOSS_SCHEMA = "nexus.hybrid_replication.prospective_protocol_loss.v1"


class ProspectiveProtocolLoss(RuntimeError):
    """The frozen execution can no longer start prospectively for this task."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp_missing_timezone")
    return parsed.astimezone(timezone.utc)


def _task_dir_name(task_key: str) -> str:
    return task_key.replace("/", "__").replace("#", "--")


def _gh_json(*args: str) -> Any:
    completed = subprocess.run(  # nosec B603 B607
        ["gh", "api", *args],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"gh_api_failed:{completed.returncode}:{completed.stderr.strip()}")
    return json.loads(completed.stdout)


def _gh_list(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, 11):
        sep = "&" if "?" in path else "?"
        payload = _gh_json("-X", "GET", f"{path}{sep}per_page=100&page={page}")
        if not isinstance(payload, list):
            raise RuntimeError("github_paged_response_not_list")
        rows.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return rows
    raise RuntimeError("github_pagination_exceeds_bound")


def _write_create_only_json(path: Path, payload: Mapping[str, Any]) -> str:
    data = _canonical_bytes(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"immutable_prospective_receipt_conflict:{path}")
        return _sha256(data)

    temp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError(f"immutable_prospective_receipt_conflict:{path}") from None
        return _sha256(data)
    finally:
        temp.unlink(missing_ok=True)


@dataclass(frozen=True)
class ProspectiveExecutionGuard:
    store_root: Path
    snapshot: TaskSnapshot

    @property
    def task_dir(self) -> Path:
        return self.store_root / "tasks" / _task_dir_name(self.snapshot.task_key)

    @property
    def protocol_loss_path(self) -> Path:
        return self.task_dir / "prospective_protocol_loss.json"

    @contextmanager
    def task_lock(self) -> Iterator[None]:
        self.task_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.task_dir / "execution.lock"
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def has_protocol_loss(self) -> bool:
        return self.protocol_loss_path.is_file()

    def _load_state(self) -> dict[str, Any]:
        path = self.task_dir / "state.json"
        if not path.is_file():
            raise ValueError("prospective_task_state_missing")
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("task_key") != self.snapshot.task_key:
            raise ValueError("prospective_task_key_mismatch")
        if state.get("capture_sha256") != self.snapshot.capture_sha256:
            raise ValueError("prospective_capture_identity_mismatch")
        if state.get("admission_disposition") not in {
            PRIMARY_ADMISSION_DISPOSITION,
            READINESS_CONTROL_DISPOSITION,
        }:
            raise ValueError("prospective_task_not_executable")
        if not state.get("admission_receipt_sha256"):
            raise ValueError("prospective_admission_receipt_missing")
        return state

    def _read_admission_receipt(self, state: Mapping[str, Any]) -> None:
        comments = _gh_list(
            f"repos/{self.snapshot.repository}/issues/{self.snapshot.issue_number}/comments"
        )
        bodies = [
            str(item.get("body") or "")
            for item in comments
            if ADMISSION_MARKER in str(item.get("body") or "")
        ]
        if len(bodies) != 1:
            raise ValueError("prospective_admission_marker_ambiguous")
        receipt = parse_admission_comment(bodies[0])
        if receipt.task_key != self.snapshot.task_key:
            raise ValueError("prospective_admission_task_mismatch")
        if receipt.capture_sha256 != self.snapshot.capture_sha256:
            raise ValueError("prospective_admission_capture_mismatch")
        if receipt.receipt_sha256 != state.get("admission_receipt_sha256"):
            raise ValueError("prospective_admission_identity_mismatch")

    def _issue(self) -> dict[str, Any]:
        payload = _gh_json(
            "-X",
            "GET",
            f"repos/{self.snapshot.repository}/issues/{self.snapshot.issue_number}",
        )
        if not isinstance(payload, dict):
            raise RuntimeError("github_issue_response_not_object")
        return payload

    def _closed_events(self) -> list[dict[str, Any]]:
        return [
            event
            for event in _gh_list(
                f"repos/{self.snapshot.repository}/issues/{self.snapshot.issue_number}/events"
            )
            if str(event.get("event") or "") == "closed" and event.get("created_at")
        ]

    def _record_protocol_loss(self, *, reason: str, details: Mapping[str, Any]) -> dict[str, Any]:
        if self.protocol_loss_path.exists():
            return json.loads(self.protocol_loss_path.read_text(encoding="utf-8"))
        payload = {
            "schema": PROTOCOL_LOSS_SCHEMA,
            "task_key": self.snapshot.task_key,
            "capture_sha256": self.snapshot.capture_sha256,
            "reason": reason,
            "observed_at": _utc_now(),
            "details": dict(details),
            "claim_ceiling": "PROTOCOL_EVIDENCE_ONLY_DO_NOT_COUNT",
        }
        _write_create_only_json(self.protocol_loss_path, payload)
        return payload

    def _ensure_no_prior_terminal(self, *, reason: str) -> None:
        closed = self._closed_events()
        if not closed:
            return
        first = min(closed, key=lambda item: str(item.get("created_at") or ""))
        payload = self._record_protocol_loss(
            reason=reason,
            details={
                "terminal_event_id": int(first.get("id") or 0),
                "terminal_at": str(first.get("created_at") or ""),
            },
        )
        raise ProspectiveProtocolLoss(f"{reason}:{payload['details'].get('terminal_at')}")

    def ensure_execution_start(self) -> dict[str, Any]:
        state = self._load_state()
        self._read_admission_receipt(state)
        if self.has_protocol_loss():
            raise ProspectiveProtocolLoss("existing_prospective_protocol_loss")
        path = self.task_dir / "execution_start.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("capture_sha256") != self.snapshot.capture_sha256:
                raise ValueError("execution_start_capture_mismatch")
            if payload.get("admission_receipt_sha256") != state.get("admission_receipt_sha256"):
                raise ValueError("execution_start_admission_mismatch")
            return payload

        self._ensure_no_prior_terminal(reason="TERMINAL_BEFORE_EXECUTION_START")
        issue = self._issue()
        if str(issue.get("state") or "") != "open":
            payload = self._record_protocol_loss(
                reason="TERMINAL_BEFORE_EXECUTION_START",
                details={"terminal_at": str(issue.get("closed_at") or "")},
            )
            raise ProspectiveProtocolLoss(
                f"TERMINAL_BEFORE_EXECUTION_START:{payload['details'].get('terminal_at')}"
            )
        payload = {
            "schema": EXECUTION_START_SCHEMA,
            "task_key": self.snapshot.task_key,
            "capture_sha256": self.snapshot.capture_sha256,
            "admission_receipt_sha256": str(state["admission_receipt_sha256"]),
            "pre_implementation_revision": self.snapshot.pre_implementation_revision,
            "source_event_id": self.snapshot.source_event_id,
            "issue_state": "open",
            "issue_updated_at": str(issue.get("updated_at") or ""),
            "observed_at": _utc_now(),
        }
        _write_create_only_json(path, payload)
        return payload

    def ensure_synchronous_effect_start(
        self,
        *,
        slot: str,
        effect_identity_sha256: str,
        provider: str,
        model: str,
    ) -> dict[str, Any]:
        """Fence a non-reconcilable synchronous provider request before I/O.

        If the process dies after this receipt but before raw sealing, a later worker
        must fail closed instead of replaying a provider request whose effect cannot
        be reconciled by operation ID.
        """

        if self.has_protocol_loss():
            raise ProspectiveProtocolLoss("existing_prospective_protocol_loss")
        path = self.effect_root(slot) / "synchronous_effect_start.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("effect_identity_sha256") != effect_identity_sha256:
                raise ValueError("synchronous_effect_identity_mismatch")
            self._record_protocol_loss(
                reason="UNRECONCILABLE_SYNCHRONOUS_EFFECT_RESTART",
                details={
                    "slot": slot,
                    "effect_identity_sha256": effect_identity_sha256,
                    "provider": provider,
                    "model": model,
                    "started_at": str(payload.get("started_at") or ""),
                },
            )
            raise ProspectiveProtocolLoss("UNRECONCILABLE_SYNCHRONOUS_EFFECT_RESTART")

        self._ensure_no_prior_terminal(reason="TERMINAL_BEFORE_PROVIDER_START")
        issue = self._issue()
        if str(issue.get("state") or "") != "open":
            self._record_protocol_loss(
                reason="TERMINAL_BEFORE_PROVIDER_START",
                details={"terminal_at": str(issue.get("closed_at") or "")},
            )
            raise ProspectiveProtocolLoss("TERMINAL_BEFORE_PROVIDER_START")
        payload = {
            "schema": SYNCHRONOUS_EFFECT_START_SCHEMA,
            "task_key": self.snapshot.task_key,
            "capture_sha256": self.snapshot.capture_sha256,
            "slot": slot,
            "effect_identity_sha256": effect_identity_sha256,
            "provider": provider,
            "model": model,
            "started_at": _utc_now(),
        }
        _write_create_only_json(path, payload)
        return payload

    def effect_root(self, slot: str) -> Path:
        return self.task_dir / "effects" / slot

    def shadow_source(self, slot: str) -> Path:
        return self.effect_root(slot) / "source"

    def provider_operation_path(self, slot: str) -> Path:
        return self.effect_root(slot) / "provider_operation.json"

    def provider_start_path(self, slot: str) -> Path:
        return self.effect_root(slot) / "provider_start.json"

    def before_provider_start(self) -> None:
        if self.has_protocol_loss():
            raise ProspectiveProtocolLoss("existing_prospective_protocol_loss")
        self._ensure_no_prior_terminal(reason="TERMINAL_BEFORE_PROVIDER_START")
        issue = self._issue()
        if str(issue.get("state") or "") != "open":
            payload = self._record_protocol_loss(
                reason="TERMINAL_BEFORE_PROVIDER_START",
                details={"terminal_at": str(issue.get("closed_at") or "")},
            )
            raise ProspectiveProtocolLoss(
                f"TERMINAL_BEFORE_PROVIDER_START:{payload['details'].get('terminal_at')}"
            )

    def bind_provider_operation(
        self,
        *,
        slot: str,
        operation_root: Path,
        record: Mapping[str, Any],
        prompt_sha256: str,
        cwd: Path,
        mode: str,
        recovered_from_journal: bool,
    ) -> dict[str, Any]:
        del recovered_from_journal  # recovery provenance is observational, not receipt identity.
        operation_id = str(record.get("operation_id") or "")
        if not operation_id:
            raise ValueError("provider_operation_id_missing")
        payload = {
            "schema": PROVIDER_OPERATION_SCHEMA,
            "task_key": self.snapshot.task_key,
            "capture_sha256": self.snapshot.capture_sha256,
            "slot": slot,
            "operation_id": operation_id,
            "operation_root": str(operation_root),
            "prompt_sha256": prompt_sha256,
            "cwd": str(cwd.resolve()),
            "mode": mode,
            "provider": "agy",
            "model": str(record.get("model") or ""),
            "created_at": str(record.get("created_at") or ""),
        }
        _write_create_only_json(self.provider_operation_path(slot), payload)
        return payload

    def recover_provider_operation(
        self,
        *,
        slot: str,
        operation_root: Path,
        prompt_sha256: str,
        cwd: Path,
        model: str,
        mode: str,
    ) -> dict[str, Any] | None:
        receipt_path = self.provider_operation_path(slot)
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("prompt_sha256") != prompt_sha256:
                raise ValueError("provider_operation_prompt_mismatch")
            if receipt.get("cwd") != str(cwd.resolve()):
                raise ValueError("provider_operation_cwd_mismatch")
            if receipt.get("mode") != mode:
                raise ValueError("provider_operation_mode_mismatch")
            if receipt.get("operation_root") != str(operation_root):
                raise ValueError("provider_operation_root_mismatch")
            if receipt.get("model") != model:
                raise ValueError("provider_operation_model_mismatch")
            op_path = (
                operation_root
                / "operations"
                / str(receipt.get("operation_id") or "")
                / "operation.json"
            )
            if not op_path.is_file():
                raise ValueError("provider_operation_journal_missing")
            return json.loads(op_path.read_text(encoding="utf-8"))

        matches: list[dict[str, Any]] = []
        for op_path in sorted((operation_root / "operations").glob("*/operation.json")):
            try:
                record = json.loads(op_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if str(record.get("prompt_sha256") or "") != prompt_sha256:
                continue
            if str(record.get("cwd") or "") != str(cwd.resolve()):
                continue
            if str(record.get("provider") or "") != "agy":
                continue
            if str(record.get("model") or "") != model:
                continue
            matches.append(record)
        if len(matches) > 1:
            raise ValueError("ambiguous_provider_operation_recovery")
        if not matches:
            return None
        record = matches[0]
        self.bind_provider_operation(
            slot=slot,
            operation_root=operation_root,
            record=record,
            prompt_sha256=prompt_sha256,
            cwd=cwd,
            mode=mode,
            recovered_from_journal=True,
        )
        return record

    def observe_provider_start(self, *, slot: str, record: Mapping[str, Any]) -> None:
        provider_started_at = str(record.get("provider_started_at") or "")
        if not provider_started_at:
            return
        payload = {
            "schema": PROVIDER_START_SCHEMA,
            "task_key": self.snapshot.task_key,
            "capture_sha256": self.snapshot.capture_sha256,
            "slot": slot,
            "operation_id": str(record.get("operation_id") or ""),
            "provider_started_at": provider_started_at,
        }
        _write_create_only_json(self.provider_start_path(slot), payload)
        start_time = _parse_timestamp(provider_started_at)
        prior_closes = [
            event
            for event in self._closed_events()
            if _parse_timestamp(str(event.get("created_at") or "")) <= start_time
        ]
        if prior_closes:
            first = min(prior_closes, key=lambda item: str(item.get("created_at") or ""))
            loss = self._record_protocol_loss(
                reason="PROVIDER_STARTED_AFTER_TERMINAL",
                details={
                    "operation_id": str(record.get("operation_id") or ""),
                    "provider_started_at": provider_started_at,
                    "terminal_event_id": int(first.get("id") or 0),
                    "terminal_at": str(first.get("created_at") or ""),
                },
            )
            raise ProspectiveProtocolLoss(
                f"PROVIDER_STARTED_AFTER_TERMINAL:{loss['details'].get('terminal_at')}"
            )
