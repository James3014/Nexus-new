"""Fail-closed identity and collision guards for bounded research experiments.

This module owns no scheduling, model selection, verification, acceptance, retry,
or completion authority.  It only binds immutable run evidence, holds an
exclusive workspace ownership lock while a run is active, and detects controller
byte drift across an effect boundary.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

_SCHEMA = "nexus.experiment_run_guard.v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ExperimentRunGuardError(RuntimeError):
    """Base error for fail-closed experiment-run guards."""


class InvalidRunContract(ExperimentRunGuardError):
    """The immutable run contract is malformed or cannot be bound."""


class RunContractConflict(ExperimentRunGuardError):
    """A run ID was reused with different immutable contract bytes."""


class WorkspaceOwnershipConflict(ExperimentRunGuardError):
    """Another live process owns the canonical workspace lock."""


class ControllerDigestMismatch(ExperimentRunGuardError):
    """The controller bytes do not match the pre-effect frozen digest."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_id(name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise InvalidRunContract(f"INVALID_{name.upper()}")
    return value


def _validate_optional_sha(name: str, value: str | None) -> str | None:
    if value is not None and _SHA256_RE.fullmatch(value) is None:
        raise InvalidRunContract(f"INVALID_{name.upper()}")
    return value


@dataclass(frozen=True)
class ExperimentRunContract:
    experiment_id: str
    run_id: str
    workspace_realpath: str
    owner_id: str
    subject_id: str
    controller_path: str
    controller_sha256: str
    prompt_sha256: str | None = None
    verifier_sha256: str | None = None
    experiment_contract_sha256: str | None = None

    def normalized(self) -> "ExperimentRunContract":
        _validate_id("experiment_id", self.experiment_id)
        _validate_id("run_id", self.run_id)
        _validate_id("owner_id", self.owner_id)
        if not isinstance(self.subject_id, str) or not self.subject_id.strip():
            raise InvalidRunContract("INVALID_SUBJECT_ID")

        workspace = Path(self.workspace_realpath).expanduser().resolve()
        controller = Path(self.controller_path).expanduser().resolve()
        if not workspace.is_dir():
            raise InvalidRunContract("WORKSPACE_NOT_DIRECTORY")
        if not controller.is_file():
            raise InvalidRunContract("CONTROLLER_NOT_FILE")

        return replace(
            self,
            workspace_realpath=str(workspace),
            controller_path=str(controller),
            controller_sha256=_validate_optional_sha("controller_sha256", self.controller_sha256)
            or "",
            prompt_sha256=_validate_optional_sha("prompt_sha256", self.prompt_sha256),
            verifier_sha256=_validate_optional_sha("verifier_sha256", self.verifier_sha256),
            experiment_contract_sha256=_validate_optional_sha(
                "experiment_contract_sha256", self.experiment_contract_sha256
            ),
        )

    def payload(self) -> dict[str, Any]:
        return asdict(self.normalized())

    def digest(self) -> str:
        return _canonical_json_sha256(self.payload())


@dataclass(frozen=True)
class ControllerFenceResult:
    status: str
    expected_sha256: str
    observed_sha256: str
    same_workspace_continuation_allowed: bool
    required_next_gate: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExperimentRunLease:
    def __init__(
        self,
        *,
        contract: ExperimentRunContract,
        contract_sha256: str,
        disposition: str,
        lock_handle: Any,
    ) -> None:
        self.contract = contract
        self.contract_sha256 = contract_sha256
        self.disposition = disposition
        self._lock_handle = lock_handle
        self._released = False

    def verify_controller(self) -> ControllerFenceResult:
        observed = sha256_file(Path(self.contract.controller_path))
        if observed != self.contract.controller_sha256:
            return ControllerFenceResult(
                status="CONTROLLER_DRIFT_REVERIFY_REQUIRED",
                expected_sha256=self.contract.controller_sha256,
                observed_sha256=observed,
                same_workspace_continuation_allowed=False,
                required_next_gate="FRESH_REVERIFY_IMMUTABLE_RESPONSE",
            )
        return ControllerFenceResult(
            status="CONTROLLER_STABLE",
            expected_sha256=self.contract.controller_sha256,
            observed_sha256=observed,
            same_workspace_continuation_allowed=True,
            required_next_gate=None,
        )

    def release(self) -> None:
        if self._released:
            return
        fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
        self._lock_handle.close()
        self._released = True

    def __enter__(self) -> "ExperimentRunLease":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


class ExperimentRunGuard:
    """Persist immutable run identity and hold exclusive workspace ownership."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root).expanduser().resolve()
        self.runs_dir = self.state_root / "runs"
        self.locks_dir = self.state_root / "locks"

    @staticmethod
    def _key(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _run_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{self._key(run_id)}.json"

    def _lock_path(self, workspace_realpath: str) -> Path:
        return self.locks_dir / f"{self._key(workspace_realpath)}.lock"

    def _load_record(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RunContractConflict("RUN_RECORD_INVALID") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != _SCHEMA
            or not isinstance(payload.get("contract"), dict)
            or _SHA256_RE.fullmatch(str(payload.get("contract_sha256") or "")) is None
        ):
            raise RunContractConflict("RUN_RECORD_INVALID")
        if _canonical_json_sha256(payload["contract"]) != payload["contract_sha256"]:
            raise RunContractConflict("RUN_RECORD_TAMPERED")
        return payload

    def read(self, run_id: str) -> dict[str, Any]:
        _validate_id("run_id", run_id)
        return self._load_record(self._run_path(run_id))

    def acquire(self, contract: ExperimentRunContract) -> ExperimentRunLease:
        normalized = contract.normalized()
        observed_controller_sha = sha256_file(Path(normalized.controller_path))
        if observed_controller_sha != normalized.controller_sha256:
            raise ControllerDigestMismatch(
                "CONTROLLER_PRE_EFFECT_SHA256_MISMATCH"
            )

        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.locks_dir.mkdir(parents=True, exist_ok=True)

        lock_path = self._lock_path(normalized.workspace_realpath)
        lock_handle = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            lock_handle.close()
            raise WorkspaceOwnershipConflict("WORKSPACE_OWNERSHIP_CONFLICT") from exc

        contract_payload = normalized.payload()
        contract_sha = _canonical_json_sha256(contract_payload)
        run_path = self._run_path(normalized.run_id)
        disposition = "CREATED"

        try:
            if run_path.exists():
                existing = self._load_record(run_path)
                if (
                    existing.get("contract_sha256") != contract_sha
                    or existing.get("contract") != contract_payload
                ):
                    raise RunContractConflict("RUN_CONTRACT_CONFLICT")
                disposition = "REUSED"
            else:
                record = {
                    "schema": _SCHEMA,
                    "contract": contract_payload,
                    "contract_sha256": contract_sha,
                }
                encoded = (
                    json.dumps(record, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
                ).encode("utf-8")
                try:
                    fd = os.open(
                        str(run_path),
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                    )
                except FileExistsError:
                    existing = self._load_record(run_path)
                    if (
                        existing.get("contract_sha256") != contract_sha
                        or existing.get("contract") != contract_payload
                    ):
                        raise RunContractConflict("RUN_CONTRACT_CONFLICT")
                    disposition = "REUSED"
                else:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(encoded)
                        handle.flush()
                        os.fsync(handle.fileno())

            lock_handle.seek(0)
            lock_handle.truncate()
            json.dump(
                {
                    "schema": "nexus.experiment_workspace_lock.v1",
                    "experiment_id": normalized.experiment_id,
                    "run_id": normalized.run_id,
                    "owner_id": normalized.owner_id,
                    "workspace_realpath": normalized.workspace_realpath,
                    "contract_sha256": contract_sha,
                },
                lock_handle,
                sort_keys=True,
            )
            lock_handle.write("\n")
            lock_handle.flush()
            os.fsync(lock_handle.fileno())
            return ExperimentRunLease(
                contract=normalized,
                contract_sha256=contract_sha,
                disposition=disposition,
                lock_handle=lock_handle,
            )
        except Exception:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()
            raise
