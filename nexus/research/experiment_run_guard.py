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

_SCHEMA = "nexus.experiment_run_guard.v2"
_LEGACY_SCHEMA = "nexus.experiment_run_guard.v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EFFECT_STATES = {"NOT_STARTED", "STARTED", "TERMINAL", "OUTCOME_UNKNOWN"}


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


class RunEffectConflict(ExperimentRunGuardError):
    """The exact run has already consumed or may have consumed its effect slot."""


class ImmutableArtifactConflict(ExperimentRunGuardError):
    """A canonical immutable artifact path already contains different bytes."""


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


def write_immutable_artifact(path: Path, content: bytes) -> str:
    """Atomically publish one canonical artifact; conflicting bytes fail closed."""

    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.{os.getpid()}.{id(content)}.tmp")

    try:
        fd = os.open(
            str(temp),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        try:
            os.link(temp, target)
        except FileExistsError:
            try:
                existing = target.read_bytes()
            except OSError as exc:
                raise ImmutableArtifactConflict("IMMUTABLE_ARTIFACT_UNREADABLE") from exc
            if existing != content:
                raise ImmutableArtifactConflict("IMMUTABLE_ARTIFACT_CONFLICT")
            return "REUSED_SAME_BYTES"

        dir_fd = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return "CREATED"
    finally:
        temp.unlink(missing_ok=True)


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
        guard: "ExperimentRunGuard",
        run_path: Path,
        contract: ExperimentRunContract,
        contract_sha256: str,
        disposition: str,
        lock_handle: Any,
    ) -> None:
        self.contract = contract
        self.contract_sha256 = contract_sha256
        self.disposition = disposition
        self._guard = guard
        self._run_path = run_path
        self._lock_handle = lock_handle
        self._released = False

    def _ensure_active(self) -> None:
        if self._released:
            raise RunEffectConflict("RUN_LEASE_ALREADY_RELEASED")

    @property
    def effect_state(self) -> str:
        """Return durable effect state without granting new-effect authority."""

        self._ensure_active()
        record = self._guard._load_record(self._run_path)
        if record.get("schema") != _SCHEMA:
            raise RunEffectConflict("LEGACY_RUN_EFFECT_STATE_UNKNOWN")
        return str(record["effect"]["state"])

    def begin_effect(self) -> dict[str, Any]:
        """Consume this exact run's one provider-effect slot."""

        self._ensure_active()

        def update(effect: dict[str, Any]) -> dict[str, Any]:
            state = effect["state"]
            if state == "TERMINAL":
                raise RunEffectConflict("RUN_EFFECT_ALREADY_TERMINAL")
            if state == "OUTCOME_UNKNOWN":
                raise RunEffectConflict("RUN_EFFECT_OUTCOME_UNKNOWN_RECONCILE_SAME_EFFECT")
            if state == "STARTED":
                raise RunEffectConflict("RUN_EFFECT_ALREADY_STARTED")
            if state != "NOT_STARTED":
                raise RunEffectConflict("RUN_EFFECT_STATE_INVALID")
            effect["state"] = "STARTED"
            return effect

        return self._guard._update_effect(
            self._run_path,
            expected_contract_sha256=self.contract_sha256,
            update=update,
        )

    def bind_operation(self, operation_id: str) -> dict[str, Any]:
        """Bind the provider/runtime operation identity to this exact run."""

        self._ensure_active()
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise InvalidRunContract("INVALID_OPERATION_ID")

        def update(effect: dict[str, Any]) -> dict[str, Any]:
            if effect["state"] not in {"STARTED", "OUTCOME_UNKNOWN"}:
                raise RunEffectConflict("RUN_EFFECT_NOT_BINDABLE")
            existing = effect.get("operation_id")
            if existing is not None and existing != operation_id:
                raise RunEffectConflict("RUN_EFFECT_OPERATION_CONFLICT")
            effect["operation_id"] = operation_id
            return effect

        return self._guard._update_effect(
            self._run_path,
            expected_contract_sha256=self.contract_sha256,
            update=update,
        )

    def mark_no_effect(self) -> dict[str, Any]:
        """Release a reserved run only when no external operation was ever bound."""

        self._ensure_active()

        def update(effect: dict[str, Any]) -> dict[str, Any]:
            if effect["state"] != "STARTED":
                raise RunEffectConflict("RUN_EFFECT_NO_EFFECT_NOT_PROVABLE")
            if (
                effect.get("operation_id") is not None
                or effect.get("response_sha256") is not None
                or effect.get("receipt_sha256") is not None
            ):
                raise RunEffectConflict("RUN_EFFECT_NO_EFFECT_NOT_PROVABLE")
            effect["state"] = "NOT_STARTED"
            return effect

        return self._guard._update_effect(
            self._run_path,
            expected_contract_sha256=self.contract_sha256,
            update=update,
        )

    def mark_outcome_unknown(self, *, operation_id: str | None = None) -> dict[str, Any]:
        """Fail closed after lost acknowledgement until the same effect is reconciled."""

        self._ensure_active()

        def update(effect: dict[str, Any]) -> dict[str, Any]:
            if effect["state"] not in {"STARTED", "OUTCOME_UNKNOWN"}:
                raise RunEffectConflict("RUN_EFFECT_NOT_RECONCILABLE")
            existing = effect.get("operation_id")
            if operation_id is not None:
                if existing is not None and existing != operation_id:
                    raise RunEffectConflict("RUN_EFFECT_OPERATION_CONFLICT")
                effect["operation_id"] = operation_id
            effect["state"] = "OUTCOME_UNKNOWN"
            return effect

        return self._guard._update_effect(
            self._run_path,
            expected_contract_sha256=self.contract_sha256,
            update=update,
        )

    def mark_terminal(
        self,
        *,
        operation_id: str,
        response_sha256: str,
        receipt_sha256: str,
    ) -> dict[str, Any]:
        """Persist terminal effect/result identity without granting acceptance authority."""

        self._ensure_active()
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise InvalidRunContract("INVALID_OPERATION_ID")
        _validate_optional_sha("response_sha256", response_sha256)
        _validate_optional_sha("receipt_sha256", receipt_sha256)

        def update(effect: dict[str, Any]) -> dict[str, Any]:
            if effect["state"] not in {"STARTED", "OUTCOME_UNKNOWN"}:
                raise RunEffectConflict("RUN_EFFECT_NOT_TERMINABLE")
            existing = effect.get("operation_id")
            if existing is not None and existing != operation_id:
                raise RunEffectConflict("RUN_EFFECT_OPERATION_CONFLICT")
            effect.update({
                "state": "TERMINAL",
                "operation_id": operation_id,
                "response_sha256": response_sha256,
                "receipt_sha256": receipt_sha256,
            })
            return effect

        return self._guard._update_effect(
            self._run_path,
            expected_contract_sha256=self.contract_sha256,
            update=update,
        )

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
        terminalization_error: RunEffectConflict | None = None
        try:
            record = self._guard._load_record(self._run_path)
            if (
                record.get("schema") == _SCHEMA
                and record.get("contract_sha256") == self.contract_sha256
                and record["effect"]["state"] == "STARTED"
            ):
                self.mark_outcome_unknown(operation_id=record["effect"].get("operation_id"))
                terminalization_error = RunEffectConflict("RUN_EFFECT_TERMINALIZATION_REQUIRED")
        finally:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
            self._lock_handle.close()
            self._released = True
        if terminalization_error is not None:
            raise terminalization_error

    def __enter__(self) -> "ExperimentRunLease":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: object,
    ) -> None:
        try:
            self.release()
        except RunEffectConflict:
            if exc_type is None:
                raise


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

    def _validate_effect(
        self,
        *,
        contract: dict[str, Any],
        effect: dict[str, Any],
    ) -> None:
        if not isinstance(effect, dict) or effect.get("state") not in _EFFECT_STATES:
            raise RunContractConflict("RUN_EFFECT_RECORD_INVALID")
        if effect.get("effect_handle") != contract.get("run_id"):
            raise RunContractConflict("RUN_EFFECT_HANDLE_MISMATCH")
        operation_id = effect.get("operation_id")
        if operation_id is not None and (
            not isinstance(operation_id, str) or not operation_id.strip()
        ):
            raise RunContractConflict("RUN_EFFECT_OPERATION_INVALID")
        for name in ("response_sha256", "receipt_sha256"):
            value = effect.get(name)
            if value is not None and _SHA256_RE.fullmatch(str(value)) is None:
                raise RunContractConflict(f"RUN_EFFECT_{name.upper()}_INVALID")

    def _load_record(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RunContractConflict("RUN_RECORD_INVALID") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema") not in {_SCHEMA, _LEGACY_SCHEMA}
            or not isinstance(payload.get("contract"), dict)
            or _SHA256_RE.fullmatch(str(payload.get("contract_sha256") or "")) is None
        ):
            raise RunContractConflict("RUN_RECORD_INVALID")
        if _canonical_json_sha256(payload["contract"]) != payload["contract_sha256"]:
            raise RunContractConflict("RUN_RECORD_TAMPERED")
        if payload["schema"] == _SCHEMA:
            self._validate_effect(
                contract=payload["contract"],
                effect=payload.get("effect"),
            )
        return payload

    def _write_record(self, path: Path, payload: dict[str, Any]) -> None:
        encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode(
            "utf-8"
        )
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            fd = os.open(
                str(temp_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            temp_path.unlink(missing_ok=True)
            fd = os.open(
                str(temp_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            temp_path.unlink(missing_ok=True)

    def _update_effect(
        self,
        run_path: Path,
        *,
        expected_contract_sha256: str,
        update: Any,
    ) -> dict[str, Any]:
        record = self._load_record(run_path)
        if record.get("schema") != _SCHEMA:
            raise RunEffectConflict("LEGACY_RUN_EFFECT_STATE_UNKNOWN")
        if record.get("contract_sha256") != expected_contract_sha256:
            raise RunContractConflict("RUN_CONTRACT_CONFLICT")
        effect = dict(record["effect"])
        updated = update(effect)
        self._validate_effect(contract=record["contract"], effect=updated)
        record["effect"] = updated
        self._write_record(run_path, record)
        return dict(updated)

    def read(self, run_id: str) -> dict[str, Any]:
        _validate_id("run_id", run_id)
        return self._load_record(self._run_path(run_id))

    def acquire(self, contract: ExperimentRunContract) -> ExperimentRunLease:
        normalized = contract.normalized()
        observed_controller_sha = sha256_file(Path(normalized.controller_path))
        if observed_controller_sha != normalized.controller_sha256:
            raise ControllerDigestMismatch("CONTROLLER_PRE_EFFECT_SHA256_MISMATCH")

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
                if existing.get("schema") != _SCHEMA:
                    raise RunEffectConflict("LEGACY_RUN_EFFECT_STATE_UNKNOWN")
                disposition = "REUSED"
            else:
                record = {
                    "schema": _SCHEMA,
                    "contract": contract_payload,
                    "contract_sha256": contract_sha,
                    "effect": {
                        "state": "NOT_STARTED",
                        "effect_handle": normalized.run_id,
                        "operation_id": None,
                        "response_sha256": None,
                        "receipt_sha256": None,
                    },
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
                    if existing.get("schema") != _SCHEMA:
                        raise RunEffectConflict("LEGACY_RUN_EFFECT_STATE_UNKNOWN")
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
                guard=self,
                run_path=run_path,
                contract=normalized,
                contract_sha256=contract_sha,
                disposition=disposition,
                lock_handle=lock_handle,
            )
        except Exception:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()
            raise
