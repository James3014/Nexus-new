from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from nexus.services.external_intelligence import (
    ENVELOPE_SCHEMA,
    ExternalIntelligenceError,
    parse_external_execution_envelope,
)

FANOUT_DECISION_SCHEMA = "external_intelligence_fanout_decision.v1"
DISPATCH_ATTEMPT_SCHEMA = "external_intelligence_dispatch_attempt.v1"
WORKER_RESULT_SCHEMA = "external_intelligence_worker_result.v1"
WORKER_RECEIPT_SCHEMA = "external_intelligence_worker_receipt.v1"
FANOUT_RUN_SCHEMA = "external_intelligence_fanout_run.v1"
PROVIDER = "opencode"
MODEL = "opencode-go/deepseek-v4-flash"
PROVIDER_ID = "opencode-go"
MODEL_ID = "deepseek-v4-flash"
CLAIM_CEILING = "CANDIDATE_READY_FOR_VERIFICATION"
_SESSION_RE = re.compile(r"^ses_[A-Za-z0-9_-]{8,}$")
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")


class FanoutError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(dict(value), sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _run_git(root: Path, *args: str, timeout: float = 30.0) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:1000]
        raise FanoutError(f"GIT_COMMAND_FAILED:{args[0]}:{detail}")
    return result.stdout.strip()


def _safe_slug(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not _SLUG_RE.fullmatch(text):
        raise FanoutError(f"INVALID_{field.upper()}")
    return text


def _safe_relative_path(value: Any) -> str:
    text = str(value or "").strip()
    try:
        path = PurePosixPath(text)
    except (TypeError, ValueError) as exc:
        raise FanoutError("INVALID_MUTATION_PATH") from exc
    if not text or path.is_absolute() or ".." in path.parts or "\\" in text or "\x00" in text:
        raise FanoutError("INVALID_MUTATION_PATH")
    return path.as_posix()


def _path_matches(path: str, boundary: str) -> bool:
    p = path.rstrip("/")
    b = boundary.rstrip("/")
    return p == b or p.startswith(b + "/")


def _paths_overlap(left: str, right: str) -> bool:
    return _path_matches(left, right) or _path_matches(right, left)


def _sets_overlap(left: Sequence[str], right: Sequence[str]) -> bool:
    return any(_paths_overlap(a, b) for a in left for b in right)


@dataclass(frozen=True)
class ExecutionUnit:
    task_id: str
    unit_id: str
    envelope_ref: str
    envelope_sha256: str
    expected_base_sha: str
    mutation_paths: tuple[str, ...]
    dependencies_ready: bool = True
    priority: int = 0
    allow_deletions: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExecutionUnit":
        task_id = _safe_slug(value.get("task_id"), "task_id")
        unit_id = _safe_slug(value.get("unit_id"), "unit_id")
        envelope_ref = str(value.get("envelope_ref") or "").strip()
        envelope_sha256 = str(value.get("envelope_sha256") or "").strip().lower()
        expected_base_sha = str(value.get("expected_base_sha") or "").strip().lower()
        raw_paths = value.get("mutation_paths")
        if not isinstance(raw_paths, (list, tuple)) or not raw_paths:
            raise FanoutError("MUTATION_PATHS_REQUIRED")
        mutation_paths = tuple(dict.fromkeys(_safe_relative_path(path) for path in raw_paths))
        if not envelope_ref:
            raise FanoutError("ENVELOPE_REF_REQUIRED")
        if not _SHA256_RE.fullmatch(envelope_sha256):
            raise FanoutError("INVALID_ENVELOPE_SHA256")
        if not _SHA1_RE.fullmatch(expected_base_sha):
            raise FanoutError("INVALID_EXPECTED_BASE_SHA")
        priority = value.get("priority", 0)
        if not isinstance(priority, int):
            raise FanoutError("INVALID_PRIORITY")
        return cls(
            task_id=task_id,
            unit_id=unit_id,
            envelope_ref=envelope_ref,
            envelope_sha256=envelope_sha256,
            expected_base_sha=expected_base_sha,
            mutation_paths=mutation_paths,
            dependencies_ready=bool(value.get("dependencies_ready", True)),
            priority=priority,
            allow_deletions=bool(value.get("allow_deletions", False)),
        )

    def identity(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "unit_id": self.unit_id,
            "envelope_ref": self.envelope_ref,
            "envelope_sha256": self.envelope_sha256,
            "expected_base_sha": self.expected_base_sha,
            "mutation_paths": list(self.mutation_paths),
            "dependencies_ready": self.dependencies_ready,
            "priority": self.priority,
            "allow_deletions": self.allow_deletions,
        }

    @property
    def identity_sha256(self) -> str:
        return _sha256(_canonical_json(self.identity()))


@dataclass(frozen=True)
class CapacityLease:
    requested_concurrency: int
    provider_available: int
    workspace_available: int
    controller_attention_limit: int
    active_workers: int = 0
    pending_verifications: int = 0
    pending_repairs: int = 0
    pending_candidates: int = 0

    def effective_capacity(self) -> tuple[int, dict[str, int]]:
        values = (
            self.requested_concurrency,
            self.provider_available,
            self.workspace_available,
            self.controller_attention_limit,
            self.active_workers,
            self.pending_verifications,
            self.pending_repairs,
            self.pending_candidates,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise FanoutError("INVALID_CAPACITY_LEASE")
        pressure = (
            self.active_workers
            + self.pending_verifications
            + self.pending_repairs
            + self.pending_candidates
        )
        controller_available = max(0, self.controller_attention_limit - pressure)
        provider_free = max(0, self.provider_available - self.active_workers)
        capacity = min(
            self.requested_concurrency,
            provider_free,
            self.workspace_available,
            controller_available,
        )
        return capacity, {
            "control_pressure": pressure,
            "controller_available": controller_available,
            "provider_free": provider_free,
            "workspace_available": self.workspace_available,
        }


@dataclass(frozen=True)
class WorkspaceLease:
    workspace_id: str
    path: str
    expected_base_sha: str


@dataclass(frozen=True)
class OpenCodeRunResult:
    status: str
    session_id: str = ""
    response_text: str = ""
    provider_id: str = ""
    model_id: str = ""
    directory: str = ""
    version: str = ""
    stdout_sha256: str = ""
    stderr_sha256: str = ""
    export_sha256: str = ""
    argv_sha256: str = ""
    process_started: bool = False
    outcome_unknown: bool = False
    retry_safe: bool = False
    error: str = ""


def plan_fanout(
    units: Iterable[Mapping[str, Any] | ExecutionUnit],
    lease: CapacityLease,
    *,
    completed_unit_ids: Iterable[str] = (),
) -> dict[str, Any]:
    parsed = [
        unit if isinstance(unit, ExecutionUnit) else ExecutionUnit.from_mapping(unit)
        for unit in units
    ]
    if not parsed:
        raise FanoutError("EXECUTION_UNITS_REQUIRED")
    task_ids = {unit.task_id for unit in parsed}
    if len(task_ids) != 1:
        raise FanoutError("MIXED_TASK_FANOUT_FORBIDDEN")
    unit_ids = [unit.unit_id for unit in parsed]
    if len(set(unit_ids)) != len(unit_ids):
        raise FanoutError("DUPLICATE_UNIT_ID")

    capacity, pressure = lease.effective_capacity()
    completed_ids = set(completed_unit_ids)
    if not completed_ids.issubset(unit_ids):
        raise FanoutError("COMPLETED_UNIT_UNKNOWN")
    ordered = sorted(parsed, key=lambda unit: (-unit.priority, unit.unit_id))
    admitted: list[ExecutionUnit] = []
    blocked_dependencies: list[str] = []
    deferred_overlap: list[str] = []
    deferred_capacity: list[str] = []

    completed_paths = [unit.mutation_paths for unit in ordered if unit.unit_id in completed_ids]
    for unit in ordered:
        if unit.unit_id in completed_ids:
            continue
        if not unit.dependencies_ready:
            blocked_dependencies.append(unit.unit_id)
            continue
        if any(_sets_overlap(unit.mutation_paths, paths) for paths in completed_paths):
            deferred_overlap.append(unit.unit_id)
            continue
        if any(
            _sets_overlap(unit.mutation_paths, selected.mutation_paths) for selected in admitted
        ):
            deferred_overlap.append(unit.unit_id)
            continue
        if len(admitted) >= capacity:
            deferred_capacity.append(unit.unit_id)
            continue
        admitted.append(unit)

    material = {
        "schema": FANOUT_DECISION_SCHEMA,
        "task_id": next(iter(task_ids)),
        "requested_concurrency": lease.requested_concurrency,
        "effective_capacity": capacity,
        "control_pressure": pressure,
        "admitted_units": [unit.unit_id for unit in admitted],
        "completed_units": sorted(completed_ids),
        "blocked_dependencies": blocked_dependencies,
        "deferred_mutation_overlap": deferred_overlap,
        "deferred_capacity": deferred_capacity,
        "fixed_worker_pool": False,
        "provider": PROVIDER,
        "model": MODEL,
    }
    material["decision_sha256"] = _sha256(_canonical_json(material))
    return material


class GitWorktreeAllocator:
    """Allocate fresh detached worktrees; lifecycle cleanup is intentionally out of scope."""

    def __init__(
        self, repository_root: str | os.PathLike[str], workspace_root: str | os.PathLike[str]
    ):
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.workspace_root = Path(workspace_root).expanduser().resolve()

    def allocate(self, unit: ExecutionUnit) -> WorkspaceLease:
        live_base = _run_git(self.repository_root, "cat-file", "-t", unit.expected_base_sha)
        if live_base != "commit":
            raise FanoutError("EXPECTED_BASE_NOT_COMMIT")
        workspace_id = f"ei-{unit.task_id}-{unit.unit_id}-{uuid.uuid4().hex[:12]}"
        path = self.workspace_root / workspace_id
        if path.exists():
            raise FanoutError("WORKSPACE_COLLISION")
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(path), unit.expected_base_sha],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise FanoutError(
                f"WORKSPACE_ALLOCATION_FAILED:{(result.stderr or result.stdout).strip()[:1000]}"
            )
        observed = _run_git(path, "rev-parse", "HEAD")
        dirty = _run_git(path, "status", "--porcelain=v1")
        if observed != unit.expected_base_sha or dirty:
            raise FanoutError("WORKSPACE_FRESHNESS_FAILED")
        return WorkspaceLease(workspace_id=workspace_id, path=str(path), expected_base_sha=observed)


class FanoutStore:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser().resolve()
        self.attempts = self.root / "attempts"
        self.receipts = self.root / "receipts"
        self.sessions = self.root / "sessions"

    @staticmethod
    def _unit_key(task_id: str, unit_id: str) -> str:
        return f"{task_id}--{unit_id}"

    def _attempt_path(self, task_id: str, unit_id: str, suffix: str = "initial") -> Path:
        return self.attempts / f"{self._unit_key(task_id, unit_id)}--{suffix}.json"

    def _receipt_path(self, task_id: str, unit_id: str, suffix: str = "initial") -> Path:
        return self.receipts / f"{self._unit_key(task_id, unit_id)}--{suffix}.json"

    def _session_path(self, session_id: str) -> Path:
        return self.sessions / f"{_sha256(session_id)}.json"

    def existing_initial_attempt(self, unit: ExecutionUnit) -> dict[str, Any] | None:
        path = self._attempt_path(unit.task_id, unit.unit_id)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            value.get("schema") != DISPATCH_ATTEMPT_SCHEMA
            or value.get("unit_identity_sha256") != unit.identity_sha256
        ):
            raise FanoutError("FANOUT_ATTEMPT_IDENTITY_MISMATCH")
        return value

    def existing_initial_receipt(self, unit: ExecutionUnit) -> dict[str, Any] | None:
        path = self._receipt_path(unit.task_id, unit.unit_id)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            value.get("schema") != WORKER_RECEIPT_SCHEMA
            or value.get("task_id") != unit.task_id
            or value.get("unit_id") != unit.unit_id
            or value.get("envelope_sha256") != unit.envelope_sha256
            or value.get("base_sha") != unit.expected_base_sha
            or value.get("mutation_paths") != list(unit.mutation_paths)
        ):
            raise FanoutError("FANOUT_RECEIPT_IDENTITY_MISMATCH")
        return value

    def prepare_initial(self, unit: ExecutionUnit, workspace: WorkspaceLease) -> dict[str, Any]:
        path = self._attempt_path(unit.task_id, unit.unit_id)
        previous: dict[str, Any] | None = None
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("state") == "RETRY_SAFE" and value.get("retry_safe") is True:
                previous = value
            elif value.get("state") in {"PREPARED", "DISPATCHING", "OUTCOME_UNKNOWN"}:
                raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
            else:
                raise FanoutError("FANOUT_REPLAY_FORBIDDEN")
        attempt = {
            "schema": DISPATCH_ATTEMPT_SCHEMA,
            "task_id": unit.task_id,
            "unit_id": unit.unit_id,
            "unit_identity_sha256": unit.identity_sha256,
            "attempt_id": str(uuid.uuid4()),
            "mode": "INITIAL",
            "state": "PREPARED",
            "retry_safe": True,
            "workspace_id": workspace.workspace_id,
            "workspace_path": workspace.path,
            "expected_base_sha": workspace.expected_base_sha,
            "envelope_ref": unit.envelope_ref,
            "envelope_sha256": unit.envelope_sha256,
        }
        if previous is not None:
            attempt.update({
                "retry_of_attempt_id": previous.get("attempt_id"),
                "retry_count": int(previous.get("retry_count", 0)) + 1,
            })
        _atomic_json(path, attempt)
        return attempt

    def prepare_repair(
        self,
        previous_receipt: Mapping[str, Any],
        *,
        repair_id: str,
        repair_ref: str,
        repair_sha256: str,
    ) -> dict[str, Any]:
        task_id = _safe_slug(previous_receipt.get("task_id"), "task_id")
        unit_id = _safe_slug(previous_receipt.get("unit_id"), "unit_id")
        repair_id = _safe_slug(repair_id, "repair_id")
        suffix = f"repair-{repair_id}"
        path = self._attempt_path(task_id, unit_id, suffix)
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("state") in {"PREPARED", "DISPATCHING", "OUTCOME_UNKNOWN"}:
                raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
            raise FanoutError("FANOUT_REPLAY_FORBIDDEN")
        session_id = str(previous_receipt.get("session_id") or "")
        self.assert_session_owner(
            session_id,
            task_id=task_id,
            unit_id=unit_id,
            workspace_id=str(previous_receipt.get("workspace_id") or ""),
        )
        attempt = {
            "schema": DISPATCH_ATTEMPT_SCHEMA,
            "task_id": task_id,
            "unit_id": unit_id,
            "attempt_id": str(uuid.uuid4()),
            "mode": "REPAIR_CONTINUE",
            "repair_id": repair_id,
            "state": "PREPARED",
            "retry_safe": True,
            "session_id": session_id,
            "workspace_id": previous_receipt.get("workspace_id"),
            "workspace_path": previous_receipt.get("workspace_path"),
            "expected_head": previous_receipt.get("candidate_commit"),
            "repair_ref": repair_ref,
            "repair_sha256": repair_sha256,
            "parent_receipt_id": previous_receipt.get("receipt_id"),
        }
        _atomic_json(path, attempt)
        return attempt

    def mark_dispatching(
        self, attempt: Mapping[str, Any], *, suffix: str = "initial"
    ) -> dict[str, Any]:
        value = dict(attempt)
        value.update({"state": "DISPATCHING", "retry_safe": False})
        _atomic_json(self._attempt_path(value["task_id"], value["unit_id"], suffix), value)
        return value

    def finish_attempt(
        self,
        attempt: Mapping[str, Any],
        *,
        state: str,
        transport_status: str,
        suffix: str = "initial",
    ) -> dict[str, Any]:
        if state not in {
            "COMPLETED",
            "TERMINAL_BLOCKED",
            "FAILED",
            "RETRY_SAFE",
            "OUTCOME_UNKNOWN",
        }:
            raise FanoutError("INVALID_ATTEMPT_STATE")
        value = dict(attempt)
        value.update({
            "state": state,
            "retry_safe": state == "RETRY_SAFE",
            "transport_status": transport_status,
        })
        _atomic_json(self._attempt_path(value["task_id"], value["unit_id"], suffix), value)
        return value

    def claim_session(
        self, session_id: str, *, task_id: str, unit_id: str, workspace_id: str
    ) -> None:
        if not _SESSION_RE.fullmatch(session_id):
            raise FanoutError("INVALID_SESSION_ID")
        path = self._session_path(session_id)
        binding = {
            "session_id": session_id,
            "task_id": task_id,
            "unit_id": unit_id,
            "workspace_id": workspace_id,
            "provider": PROVIDER,
            "model": MODEL,
        }
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != binding:
                raise FanoutError("SESSION_BINDING_CONFLICT")
            return
        _atomic_json(path, binding)

    def assert_session_owner(
        self, session_id: str, *, task_id: str, unit_id: str, workspace_id: str
    ) -> None:
        path = self._session_path(session_id)
        if not path.exists():
            raise FanoutError("SESSION_BINDING_MISSING")
        binding = json.loads(path.read_text(encoding="utf-8"))
        if binding != {
            "session_id": session_id,
            "task_id": task_id,
            "unit_id": unit_id,
            "workspace_id": workspace_id,
            "provider": PROVIDER,
            "model": MODEL,
        }:
            raise FanoutError("SESSION_BINDING_CONFLICT")

    def write_receipt(self, receipt: Mapping[str, Any], *, suffix: str = "initial") -> Path:
        path = self._receipt_path(str(receipt["task_id"]), str(receipt["unit_id"]), suffix)
        _atomic_json(path, receipt)
        return path


class OpenCodeDeepSeekTransport:
    """Fresh OpenCode session per initial unit; exact-session continuation for repair only."""

    def __init__(self, executable: str = "opencode", *, model: str = MODEL, timeout: float = 300.0):
        if model != MODEL:
            raise FanoutError("MODEL_SUBSTITUTION_FORBIDDEN")
        self.executable = executable
        self.model = model
        self.timeout = float(timeout)

    def run_new(self, *, prompt: str, artifact_path: str, workspace_path: str) -> OpenCodeRunResult:
        return self._run(
            prompt=prompt, artifact_path=artifact_path, workspace_path=workspace_path, session_id=""
        )

    def continue_session(
        self,
        *,
        session_id: str,
        prompt: str,
        artifact_path: str,
        workspace_path: str,
    ) -> OpenCodeRunResult:
        if not _SESSION_RE.fullmatch(session_id):
            raise FanoutError("INVALID_SESSION_ID")
        return self._run(
            prompt=prompt,
            artifact_path=artifact_path,
            workspace_path=workspace_path,
            session_id=session_id,
        )

    def _run(
        self, *, prompt: str, artifact_path: str, workspace_path: str, session_id: str
    ) -> OpenCodeRunResult:
        # OpenCode 1.18.x defines --file as a variadic array. Keep the message
        # positional before -f so it cannot be consumed as another file path.
        argv = [
            self.executable,
            "run",
            prompt,
            "--model",
            self.model,
            "--format",
            "json",
            "--dir",
            workspace_path,
        ]
        if session_id:
            argv.extend(["--session", session_id])
        argv.extend(["-f", artifact_path])
        safe_argv = [self.executable, "run", "<compact-bootstrap>", *argv[3:]]
        argv_sha256 = _sha256(_canonical_json(safe_argv))
        try:
            process = subprocess.Popen(
                argv,
                cwd=workspace_path,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
                shell=False,
            )
        except FileNotFoundError as exc:
            return OpenCodeRunResult(
                status="OPENCODE_NOT_FOUND",
                argv_sha256=argv_sha256,
                process_started=False,
                retry_safe=True,
                error=str(exc),
            )
        try:
            try:
                stdout, stderr = process.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired as exc:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except (OSError, ProcessLookupError):
                    pass
                try:
                    stdout, stderr = process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except (OSError, ProcessLookupError):
                        pass
                    stdout, stderr = process.communicate()
                return OpenCodeRunResult(
                    status="OPENCODE_OUTCOME_UNKNOWN",
                    stdout_sha256=_sha256(stdout or ""),
                    stderr_sha256=_sha256(stderr or str(exc)),
                    argv_sha256=argv_sha256,
                    process_started=True,
                    outcome_unknown=True,
                    retry_safe=False,
                    error="provider_timeout",
                )
        finally:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

        stdout = stdout or ""
        stderr = stderr or ""
        if process.returncode != 0:
            return OpenCodeRunResult(
                status="OPENCODE_OUTCOME_UNKNOWN",
                stdout_sha256=_sha256(stdout),
                stderr_sha256=_sha256(stderr),
                argv_sha256=argv_sha256,
                process_started=True,
                outcome_unknown=True,
                retry_safe=False,
                error=f"provider_nonzero:{process.returncode}",
            )
        try:
            parsed_session, response_text = self._parse_events(stdout)
            if session_id and parsed_session != session_id:
                raise FanoutError("SESSION_CONTINUATION_MISMATCH")
            attestation = self._export_attestation(parsed_session, workspace_path)
        except (FanoutError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return OpenCodeRunResult(
                status="OPENCODE_ATTESTATION_UNKNOWN",
                stdout_sha256=_sha256(stdout),
                stderr_sha256=_sha256(stderr),
                argv_sha256=argv_sha256,
                process_started=True,
                outcome_unknown=True,
                retry_safe=False,
                error=str(exc),
            )
        return OpenCodeRunResult(
            status="COMPLETED",
            session_id=parsed_session,
            response_text=response_text,
            provider_id=attestation["provider_id"],
            model_id=attestation["model_id"],
            directory=attestation["directory"],
            version=attestation["version"],
            stdout_sha256=_sha256(stdout),
            stderr_sha256=_sha256(stderr),
            export_sha256=attestation["export_sha256"],
            argv_sha256=argv_sha256,
            process_started=True,
            outcome_unknown=False,
            retry_safe=False,
        )

    @staticmethod
    def _parse_events(stdout: str) -> tuple[str, str]:
        session_ids: set[str] = set()
        texts: list[str] = []
        finished = False
        for raw in stdout.splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if not isinstance(row, dict):
                raise FanoutError("OPENCODE_EVENT_INVALID")
            # OpenCode 1.18.x serializes the stream as domain events:
            #   {"type":"message.part.updated","data":{"sessionID":...,"part":{...}}}
            # Earlier CLI versions emitted flat per-part events:
            #   {"type":"text","sessionID":...,"part":{"text":...}}
            #   {"type":"step_finish","sessionID":...}
            data = row.get("data")
            if row.get("type") == "message.part.updated" and isinstance(data, Mapping):
                session = str(data.get("sessionID") or "")
                part = data.get("part")
                if session:
                    session_ids.add(session)
                if isinstance(part, Mapping):
                    part_type = part.get("type")
                    if part_type == "text" and isinstance(part.get("text"), str):
                        texts.append(part["text"])
                    if part_type in ("step-finish", "step_finish"):
                        finished = True
                continue
            session = str(row.get("sessionID") or "")
            if session:
                session_ids.add(session)
            if row.get("type") == "text":
                part = row.get("part")
                if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                    texts.append(part["text"])
            if row.get("type") == "step_finish":
                finished = True
        if len(session_ids) != 1 or not finished or not texts:
            raise FanoutError("OPENCODE_EVENT_INCOMPLETE")
        session_id = next(iter(session_ids))
        if not _SESSION_RE.fullmatch(session_id):
            raise FanoutError("INVALID_SESSION_ID")
        return session_id, texts[-1]

    def _db_json(self, query: str, *, cwd: str) -> list[dict[str, Any]]:
        result = subprocess.run(
            [self.executable, "db", query, "--format", "json"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=min(self.timeout, 60.0),
            check=False,
        )
        if result.returncode != 0:
            raise FanoutError("OPENCODE_DB_QUERY_FAILED")
        try:
            value = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise FanoutError("OPENCODE_DB_QUERY_INVALID") from exc
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise FanoutError("OPENCODE_DB_QUERY_INVALID")
        return value

    @staticmethod
    def _sql_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def reconcile_workspace(self, *, workspace_path: str) -> OpenCodeRunResult:
        expected_directory = str(Path(workspace_path).expanduser().resolve())
        directory_sql = self._sql_literal(expected_directory)
        sessions = self._db_json(
            "select id,directory,version,model,time_created,time_updated from session "
            f"where directory={directory_sql} order by time_created",
            cwd=workspace_path,
        )
        if len(sessions) != 1:
            raise FanoutError("OPENCODE_RECONCILE_SESSION_AMBIGUOUS")
        session = sessions[0]
        session_id = str(session.get("id") or "")
        if not _SESSION_RE.fullmatch(session_id):
            raise FanoutError("INVALID_SESSION_ID")
        try:
            model = json.loads(str(session.get("model") or "{}"))
        except json.JSONDecodeError as exc:
            raise FanoutError("OPENCODE_RECONCILE_MODEL_INVALID") from exc
        if not isinstance(model, Mapping):
            raise FanoutError("OPENCODE_RECONCILE_MODEL_INVALID")
        provider_id = str(model.get("providerID") or "")
        model_id = str(model.get("id") or "")
        if provider_id != PROVIDER_ID or model_id != MODEL_ID:
            raise FanoutError("OPENCODE_MODEL_ATTESTATION_MISMATCH")
        if (
            str(Path(str(session.get("directory") or "")).expanduser().resolve())
            != expected_directory
        ):
            raise FanoutError("OPENCODE_DIRECTORY_ATTESTATION_MISMATCH")

        session_sql = self._sql_literal(session_id)
        rows = self._db_json(
            "select m.id,"
            "json_extract(m.data,'$.finish') as finish,"
            "json_extract(m.data,'$.providerID') as provider_id,"
            "json_extract(m.data,'$.modelID') as model_id,"
            "json_extract(p.data,'$.text') as text "
            "from message m join part p on p.message_id=m.id "
            f"where m.session_id={session_sql} "
            "and json_extract(m.data,'$.role')='assistant' "
            "and json_extract(p.data,'$.type')='text' "
            "order by m.time_created desc,p.time_created desc limit 1",
            cwd=workspace_path,
        )
        if len(rows) != 1:
            raise FanoutError("OPENCODE_RECONCILE_MESSAGE_AMBIGUOUS")
        latest = rows[0]
        latest_message_id = str(latest.get("id") or "")
        response_text = str(latest.get("text") or "")
        if latest.get("finish") != "stop" or not latest_message_id or not response_text:
            raise FanoutError("OPENCODE_RECONCILE_NOT_TERMINAL")
        if (
            str(latest.get("provider_id") or "") != PROVIDER_ID
            or str(latest.get("model_id") or "") != MODEL_ID
        ):
            raise FanoutError("OPENCODE_MODEL_ATTESTATION_MISMATCH")
        evidence = {
            "session": session,
            "message_id": latest_message_id,
            "response_sha256": _sha256(response_text),
        }
        return OpenCodeRunResult(
            status="COMPLETED",
            session_id=session_id,
            response_text=response_text,
            provider_id=provider_id,
            model_id=model_id,
            directory=expected_directory,
            version=str(session.get("version") or ""),
            stdout_sha256=_sha256(response_text),
            stderr_sha256=_sha256(""),
            export_sha256=_sha256(_canonical_json(evidence)),
            argv_sha256=_sha256(_canonical_json([self.executable, "db", "<reconcile-workspace>"])),
            process_started=True,
            outcome_unknown=False,
            retry_safe=False,
        )

    def _export_attestation(self, session_id: str, workspace_path: str) -> dict[str, str]:
        result = subprocess.run(
            [self.executable, "export", session_id],
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=min(self.timeout, 60.0),
            check=False,
        )
        if result.returncode != 0:
            raise FanoutError("OPENCODE_EXPORT_FAILED")
        stdout = result.stdout or ""
        # OpenCode 1.18.x may cap `export` stdout at 64 KiB for large sessions.
        # The attestation fields live in the leading `info` object, so parse
        # that complete object directly instead of requiring the trailing
        # messages array to be present and valid JSON.
        info_key = stdout.find('"info"')
        if info_key < 0:
            raise FanoutError("OPENCODE_EXPORT_INVALID")
        info_start = stdout.find("{", info_key)
        if info_start < 0:
            raise FanoutError("OPENCODE_EXPORT_INVALID")
        try:
            info, _ = json.JSONDecoder().raw_decode(stdout, info_start)
        except json.JSONDecodeError as exc:
            raise FanoutError("OPENCODE_EXPORT_INVALID") from exc
        if not isinstance(info, Mapping):
            raise FanoutError("OPENCODE_EXPORT_INVALID")
        model = info.get("model")
        if not isinstance(model, Mapping):
            raise FanoutError("OPENCODE_EXPORT_MODEL_MISSING")
        observed_session = str(info.get("id") or "")
        provider_id = str(model.get("providerID") or "")
        model_id = str(model.get("id") or "")
        directory = str(Path(str(info.get("directory") or "")).expanduser().resolve())
        expected_directory = str(Path(workspace_path).expanduser().resolve())
        if observed_session != session_id:
            raise FanoutError("OPENCODE_EXPORT_SESSION_MISMATCH")
        if provider_id != PROVIDER_ID or model_id != MODEL_ID:
            raise FanoutError("OPENCODE_MODEL_ATTESTATION_MISMATCH")
        if directory != expected_directory:
            raise FanoutError("OPENCODE_DIRECTORY_ATTESTATION_MISMATCH")
        return {
            "provider_id": provider_id,
            "model_id": model_id,
            "directory": directory,
            "version": str(info.get("version") or ""),
            "export_sha256": _sha256(stdout),
        }


def _load_and_verify_artifact(path_value: str, expected_sha256: str) -> tuple[Path, str]:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise FanoutError("ARTIFACT_NOT_FOUND")
    raw = path.read_bytes()
    observed = _sha256(raw)
    if observed != expected_sha256:
        raise FanoutError("ARTIFACT_SHA256_MISMATCH")
    try:
        return path, raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FanoutError("ARTIFACT_UTF8_REQUIRED") from exc


def _verify_envelope_scope(unit: ExecutionUnit) -> Path:
    path = Path(unit.envelope_ref).expanduser().resolve()
    if not path.is_file():
        raise FanoutError("ARTIFACT_NOT_FOUND")
    try:
        text = path.read_text(encoding="utf-8")
        envelope = parse_external_execution_envelope(text)
    except UnicodeDecodeError as exc:
        raise FanoutError("ARTIFACT_UTF8_REQUIRED") from exc
    except ExternalIntelligenceError as exc:
        raise FanoutError("ENVELOPE_CONTRACT_INVALID") from exc
    if _sha256(_canonical_json(envelope)) != unit.envelope_sha256:
        raise FanoutError("ENVELOPE_SHA256_MISMATCH")
    if envelope.get("schema") != ENVELOPE_SCHEMA:
        raise FanoutError("ENVELOPE_CONTRACT_INVALID")
    binding = envelope.get("binding") or {}
    if binding.get("main_sha") != unit.expected_base_sha:
        raise FanoutError("ENVELOPE_BASE_MISMATCH")
    scope = envelope.get("scope_signal") or {}
    allowed = [
        *scope.get("production_edit_paths", []),
        *scope.get("required_test_edit_paths", []),
        *scope.get("conditional_migration_paths", []),
    ]
    forbidden = list(scope.get("forbidden_paths", []))
    for mutation in unit.mutation_paths:
        if not any(_path_matches(mutation, boundary) for boundary in allowed):
            raise FanoutError("UNIT_SCOPE_WIDENING_FORBIDDEN")
        if any(_paths_overlap(mutation, boundary) for boundary in forbidden):
            raise FanoutError("UNIT_FORBIDDEN_PATH")
    max_files = scope.get("max_files")
    if isinstance(max_files, int) and len(unit.mutation_paths) > max_files:
        raise FanoutError("UNIT_SCOPE_FILE_LIMIT_EXCEEDED")
    return path


def build_worker_bootstrap(unit: ExecutionUnit, workspace: WorkspaceLease) -> str:
    """Compact controller-to-worker bootstrap. The envelope body is never embedded."""
    return "\n".join([
        "You are DeepSeek V4 Flash, the bounded L2 Task Engineer for exactly one Nexus execution unit.",
        f"task_id={unit.task_id}",
        f"unit_id={unit.unit_id}",
        f"expected_base_sha={unit.expected_base_sha}",
        f"workspace_id={workspace.workspace_id}",
        f"envelope_artifact_ref={unit.envelope_ref}",
        f"envelope_sha256={unit.envelope_sha256}",
        "The full external_execution_envelope.v1 is attached as a file. Read it before editing and do not ask the controller to restate it.",
        "Read and follow the model_adaptation brief inside the attached envelope: role_contract, task_local_invariants, known_failure_guards, execution_strategy, forbidden_inferences, repair_policy.",
        f"authorized_mutation_paths={_canonical_json(list(unit.mutation_paths))}",
        "Do not modify any path outside authorized_mutation_paths. Do not commit, push, merge, approve, integrate, or spawn a replacement model.",
        "Use the attached envelope as semantic guidance but never widen the Task Card authority.",
        "Apply only the task-relevant known_failure_guards; encode one evidence-guided same-unit repair and no blind retry or auto-chain.",
        "When finished, return exactly one JSON object and no markdown/prose:",
        _canonical_json({
            "schema": WORKER_RESULT_SCHEMA,
            "task_id": unit.task_id,
            "unit_id": unit.unit_id,
            "status": "IMPLEMENTATION_COMPLETED|BLOCKED",
            "summary": "short factual summary",
        }),
    ])


def build_repair_bootstrap(
    previous_receipt: Mapping[str, Any], *, repair_id: str, repair_ref: str, repair_sha256: str
) -> str:
    return "\n".join([
        "Continue the exact same execution unit session for a bounded repair.",
        f"task_id={previous_receipt.get('task_id')}",
        f"unit_id={previous_receipt.get('unit_id')}",
        f"repair_id={repair_id}",
        f"repair_artifact_ref={repair_ref}",
        f"repair_sha256={repair_sha256}",
        f"parent_candidate_commit={previous_receipt.get('candidate_commit')}",
        "The repair artifact is attached. Do not widen mutation scope, do not change model/session, and do not commit/push/approve/integrate.",
        "Return exactly one JSON object with schema external_intelligence_worker_result.v1 and status IMPLEMENTATION_COMPLETED or BLOCKED.",
    ])


def _extract_worker_result_object(text: str) -> dict[str, Any]:
    """Return the single JSON object in worker text, tolerating surrounding prose.

    Live OpenCode 1.18.x workers sometimes prefix their final JSON result with a
    prose summary line. Keep fail-closed semantics: exactly one JSON object must
    be present; a full-text direct parse is tried first and stays authoritative.
    """
    if not isinstance(text, str) or not text.strip():
        raise FanoutError("WORKER_RESULT_PARSE_FAILED")
    try:
        direct = json.loads(text)
        if isinstance(direct, dict):
            return direct
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    index = 0
    while True:
        start = text.find("{", index)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            found.append(value)
        index = end
    if len(found) != 1:
        raise FanoutError("WORKER_RESULT_PARSE_FAILED")
    return found[0]


def parse_worker_result(text: str, *, task_id: str, unit_id: str) -> dict[str, str]:
    value = _extract_worker_result_object(text)
    required = {"schema", "task_id", "unit_id", "status", "summary"}
    if not isinstance(value, dict) or set(value) != required:
        raise FanoutError("WORKER_RESULT_PARSE_FAILED")
    if value.get("schema") != WORKER_RESULT_SCHEMA:
        raise FanoutError("WORKER_RESULT_PARSE_FAILED")
    if value.get("task_id") != task_id or value.get("unit_id") != unit_id:
        raise FanoutError("WORKER_RESULT_BINDING_MISMATCH")
    if value.get("status") not in {"IMPLEMENTATION_COMPLETED", "BLOCKED"}:
        raise FanoutError("WORKER_RESULT_STATUS_INVALID")
    if not isinstance(value.get("summary"), str) or len(value["summary"]) > 4000:
        raise FanoutError("WORKER_RESULT_PARSE_FAILED")
    return value


def _changed_paths(workspace: Path, base_sha: str) -> list[str]:
    tracked = _run_git(workspace, "diff", "--name-only", base_sha, "--")
    untracked = _run_git(workspace, "ls-files", "--others", "--exclude-standard")
    paths = [line.strip() for line in (tracked + "\n" + untracked).splitlines() if line.strip()]
    return sorted(dict.fromkeys(paths))


def _deleted_paths(workspace: Path, base_sha: str) -> list[str]:
    output = _run_git(workspace, "diff", "--name-status", base_sha, "--")
    deleted: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if parts and parts[0].startswith("D") and len(parts) >= 2:
            deleted.append(parts[-1])
    return deleted


def _capture_candidate(
    unit: ExecutionUnit,
    workspace: WorkspaceLease,
    *,
    expected_head: str,
) -> dict[str, Any]:
    root = Path(workspace.path)
    observed_head = _run_git(root, "rev-parse", "HEAD")
    if observed_head != expected_head:
        raise FanoutError("WORKER_COMMIT_FORBIDDEN")
    changed = _changed_paths(root, expected_head)
    if not changed:
        raise FanoutError("EMPTY_IMPLEMENTATION_RESULT")
    for path in changed:
        if not any(_path_matches(path, boundary) for boundary in unit.mutation_paths):
            raise FanoutError(f"OUT_OF_SCOPE_MUTATION:{path}")
    deleted = _deleted_paths(root, expected_head)
    if deleted and not unit.allow_deletions:
        raise FanoutError("DELETION_NOT_AUTHORIZED")

    subprocess.run(
        ["git", "add", "--", *changed], cwd=root, check=True, capture_output=True, text=True
    )
    check = subprocess.run(
        ["git", "diff", "--cached", "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0:
        raise FanoutError(
            f"CANDIDATE_DIFF_CHECK_FAILED:{(check.stdout or check.stderr).strip()[:1000]}"
        )
    staged = [
        line for line in _run_git(root, "diff", "--cached", "--name-only").splitlines() if line
    ]
    if sorted(staged) != sorted(changed):
        raise FanoutError("CANDIDATE_STAGED_SCOPE_MISMATCH")
    commit = subprocess.run(
        ["git", "commit", "-m", f"candidate: {unit.task_id}/{unit.unit_id}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        raise FanoutError(
            f"CANDIDATE_COMMIT_FAILED:{(commit.stderr or commit.stdout).strip()[:1000]}"
        )
    candidate_commit = _run_git(root, "rev-parse", "HEAD")
    candidate_tree = _run_git(root, "rev-parse", "HEAD^{tree}")
    diff = _run_git(root, "diff", "--binary", expected_head, candidate_commit)
    return {
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "candidate_diff_sha256": _sha256(diff),
        "changed_paths": changed,
        "deleted_paths": deleted,
        "parent_commit": expected_head,
    }


class AdaptiveDeepSeekFanoutRuntime:
    def __init__(
        self,
        *,
        allocator: GitWorktreeAllocator,
        store: FanoutStore,
        transport: OpenCodeDeepSeekTransport | Any | None = None,
    ):
        self.allocator = allocator
        self.store = store
        self.transport = transport or OpenCodeDeepSeekTransport()

    def run(
        self,
        units: Iterable[Mapping[str, Any] | ExecutionUnit],
        lease: CapacityLease,
    ) -> dict[str, Any]:
        parsed = [
            unit if isinstance(unit, ExecutionUnit) else ExecutionUnit.from_mapping(unit)
            for unit in units
        ]
        completed_ids: set[str] = set()
        for unit in parsed:
            existing_receipt = self.store.existing_initial_receipt(unit)
            if existing_receipt is not None:
                completed_ids.add(unit.unit_id)
        decision = plan_fanout(parsed, lease, completed_unit_ids=completed_ids)
        selected_ids = set(decision["admitted_units"])
        selected = [unit for unit in parsed if unit.unit_id in selected_ids]
        leases: dict[str, WorkspaceLease] = {}
        actions: dict[str, str] = {}
        receipts: dict[str, Any] = {
            unit.unit_id: self.store.existing_initial_receipt(unit)
            for unit in parsed
            if unit.unit_id in completed_ids
        }
        errors: dict[str, str] = {}
        seen_paths: set[str] = set()
        for unit in selected:
            existing_receipt = self.store.existing_initial_receipt(unit)
            if existing_receipt is not None:
                receipts[unit.unit_id] = existing_receipt
                continue
            existing_attempt = self.store.existing_initial_attempt(unit)
            if existing_attempt is not None:
                state = str(existing_attempt.get("state") or "")
                if state not in {
                    "PREPARED",
                    "DISPATCHING",
                    "RETRY_SAFE",
                    "OUTCOME_UNKNOWN",
                }:
                    errors[unit.unit_id] = "FANOUT_REPLAY_FORBIDDEN"
                    continue
                if state == "RETRY_SAFE":
                    # No provider process was started; retry with a fresh exact-base
                    # workspace so the new attempt cannot inherit stale residue.
                    workspace = self.allocator.allocate(unit)
                else:
                    workspace = WorkspaceLease(
                        workspace_id=str(existing_attempt.get("workspace_id") or ""),
                        path=str(existing_attempt.get("workspace_path") or ""),
                        expected_base_sha=str(existing_attempt.get("expected_base_sha") or ""),
                    )
                if (
                    not workspace.workspace_id
                    or not workspace.path
                    or workspace.expected_base_sha != unit.expected_base_sha
                ):
                    errors[unit.unit_id] = "FANOUT_ATTEMPT_WORKSPACE_INVALID"
                    continue
                actions[unit.unit_id] = (
                    "DISPATCH"
                    if state == "PREPARED"
                    else "RETRY"
                    if state == "RETRY_SAFE"
                    else "RECONCILE"
                )
            else:
                workspace = self.allocator.allocate(unit)
                actions[unit.unit_id] = "NEW"
            resolved = str(Path(workspace.path).resolve())
            if resolved in seen_paths:
                errors[unit.unit_id] = "WORKSPACE_REUSE_FORBIDDEN"
                continue
            seen_paths.add(resolved)
            leases[unit.unit_id] = workspace

        pending = [unit for unit in selected if unit.unit_id in leases]
        if pending:
            with ThreadPoolExecutor(
                max_workers=len(pending), thread_name_prefix="nexus-ei"
            ) as executor:
                futures = {
                    executor.submit(
                        self._reconcile_initial
                        if actions[unit.unit_id] == "RECONCILE"
                        else self._dispatch_initial,
                        unit,
                        leases[unit.unit_id],
                        actions[unit.unit_id] == "DISPATCH",
                    ): unit.unit_id
                    for unit in pending
                }
                for future in as_completed(futures):
                    unit_id = futures[future]
                    try:
                        receipts[unit_id] = future.result()
                    except Exception as exc:  # bounded per-unit failure; siblings are independent
                        errors[unit_id] = str(exc)
        result = {
            "schema": FANOUT_RUN_SCHEMA,
            "decision": decision,
            "receipts": receipts,
            "errors": errors,
            "claim_ceiling": CLAIM_CEILING,
        }
        result["run_sha256"] = _sha256(_canonical_json(result))
        return result

    def _dispatch_initial(
        self,
        unit: ExecutionUnit,
        workspace: WorkspaceLease,
        resume_prepared: bool = False,
    ) -> dict[str, Any]:
        artifact = _verify_envelope_scope(unit)
        if resume_prepared:
            attempt = self.store.existing_initial_attempt(unit)
            if attempt is None or attempt.get("state") != "PREPARED":
                raise FanoutError("FANOUT_PREPARED_ATTEMPT_REQUIRED")
        else:
            attempt = self.store.prepare_initial(unit, workspace)
        prompt = build_worker_bootstrap(unit, workspace)
        if artifact.read_text(encoding="utf-8") in prompt:
            raise FanoutError("FULL_ENVELOPE_IN_CONTROLLER_PROMPT")
        attempt = self.store.mark_dispatching(attempt)
        result: OpenCodeRunResult = self.transport.run_new(
            prompt=prompt,
            artifact_path=str(artifact),
            workspace_path=workspace.path,
        )
        return self._finalize_initial(unit, workspace, attempt, result)

    def _reconcile_initial(
        self,
        unit: ExecutionUnit,
        workspace: WorkspaceLease,
        _resume_prepared: bool = False,
    ) -> dict[str, Any]:
        _verify_envelope_scope(unit)
        attempt = self.store.existing_initial_attempt(unit)
        if attempt is None or attempt.get("state") not in {"DISPATCHING", "OUTCOME_UNKNOWN"}:
            raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
        result: OpenCodeRunResult = self.transport.reconcile_workspace(
            workspace_path=workspace.path
        )
        return self._finalize_initial(unit, workspace, attempt, result)

    def _finalize_initial(
        self,
        unit: ExecutionUnit,
        workspace: WorkspaceLease,
        attempt: Mapping[str, Any],
        result: OpenCodeRunResult,
    ) -> dict[str, Any]:
        if result.status != "COMPLETED":
            if not result.process_started and result.retry_safe:
                state = "RETRY_SAFE"
            else:
                state = "OUTCOME_UNKNOWN" if result.process_started else "FAILED"
            self.store.finish_attempt(attempt, state=state, transport_status=result.status)
            if result.process_started:
                raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
            raise FanoutError(result.status)
        if result.provider_id != PROVIDER_ID or result.model_id != MODEL_ID:
            self.store.finish_attempt(
                attempt, state="OUTCOME_UNKNOWN", transport_status="MODEL_ATTESTATION_MISMATCH"
            )
            raise FanoutError("MODEL_ATTESTATION_MISMATCH")
        if str(Path(result.directory).resolve()) != str(Path(workspace.path).resolve()):
            self.store.finish_attempt(
                attempt, state="OUTCOME_UNKNOWN", transport_status="WORKSPACE_ATTESTATION_MISMATCH"
            )
            raise FanoutError("WORKSPACE_ATTESTATION_MISMATCH")
        try:
            worker = parse_worker_result(
                result.response_text, task_id=unit.task_id, unit_id=unit.unit_id
            )
        except FanoutError:
            self.store.finish_attempt(
                attempt, state="OUTCOME_UNKNOWN", transport_status="WORKER_RESULT_INVALID"
            )
            raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
        self.store.claim_session(
            result.session_id,
            task_id=unit.task_id,
            unit_id=unit.unit_id,
            workspace_id=workspace.workspace_id,
        )
        if worker["status"] == "BLOCKED":
            receipt = self._build_receipt(
                unit=unit,
                workspace=workspace,
                attempt=attempt,
                result=result,
                worker=worker,
                candidate=None,
                status="WORKER_BLOCKED",
            )
            self.store.write_receipt(receipt)
            self.store.finish_attempt(
                attempt, state="TERMINAL_BLOCKED", transport_status=result.status
            )
            return receipt
        try:
            candidate = _capture_candidate(unit, workspace, expected_head=unit.expected_base_sha)
        except FanoutError as exc:
            hard_block = (
                str(exc) == "EMPTY_IMPLEMENTATION_RESULT"
                or str(exc) == "DELETION_NOT_AUTHORIZED"
                or str(exc).startswith("OUT_OF_SCOPE_MUTATION:")
            )
            if hard_block:
                blocked_worker = {
                    "status": "BLOCKED",
                    "summary": str(exc),
                }
                receipt = self._build_receipt(
                    unit=unit,
                    workspace=workspace,
                    attempt=attempt,
                    result=result,
                    worker=blocked_worker,
                    candidate=None,
                    status="WORKER_BLOCKED",
                )
                self.store.write_receipt(receipt)
                self.store.finish_attempt(
                    attempt, state="TERMINAL_BLOCKED", transport_status=str(exc)
                )
                return receipt
            self.store.finish_attempt(
                attempt, state="OUTCOME_UNKNOWN", transport_status="CANDIDATE_CAPTURE_FAILED"
            )
            raise
        receipt = self._build_receipt(
            unit=unit,
            workspace=workspace,
            attempt=attempt,
            result=result,
            worker=worker,
            candidate=candidate,
            status="CANDIDATE_READY_FOR_VERIFICATION",
        )
        self.store.write_receipt(receipt)
        self.store.finish_attempt(attempt, state="COMPLETED", transport_status=result.status)
        return receipt

    def continue_repair(
        self,
        previous_receipt: Mapping[str, Any],
        *,
        repair_id: str,
        repair_ref: str,
        repair_sha256: str,
    ) -> dict[str, Any]:
        if previous_receipt.get("schema") != WORKER_RECEIPT_SCHEMA:
            raise FanoutError("INVALID_PARENT_RECEIPT")
        if previous_receipt.get("status") != "CANDIDATE_READY_FOR_VERIFICATION":
            raise FanoutError("PARENT_CANDIDATE_REQUIRED")
        if previous_receipt.get("provider") != PROVIDER or previous_receipt.get("model") != MODEL:
            raise FanoutError("MODEL_SUBSTITUTION_FORBIDDEN")
        repair_path, _ = _load_and_verify_artifact(repair_ref, repair_sha256)
        task_id = _safe_slug(previous_receipt.get("task_id"), "task_id")
        unit_id = _safe_slug(previous_receipt.get("unit_id"), "unit_id")
        workspace = WorkspaceLease(
            workspace_id=str(previous_receipt.get("workspace_id") or ""),
            path=str(previous_receipt.get("workspace_path") or ""),
            expected_base_sha=str(previous_receipt.get("candidate_commit") or ""),
        )
        if _run_git(Path(workspace.path), "rev-parse", "HEAD") != workspace.expected_base_sha:
            raise FanoutError("REPAIR_WORKSPACE_HEAD_MISMATCH")
        if _run_git(Path(workspace.path), "status", "--porcelain=v1"):
            raise FanoutError("REPAIR_WORKSPACE_DIRTY")
        self.store.assert_session_owner(
            str(previous_receipt.get("session_id") or ""),
            task_id=task_id,
            unit_id=unit_id,
            workspace_id=workspace.workspace_id,
        )
        suffix = f"repair-{_safe_slug(repair_id, 'repair_id')}"
        attempt = self.store.prepare_repair(
            previous_receipt,
            repair_id=repair_id,
            repair_ref=str(repair_path),
            repair_sha256=repair_sha256,
        )
        attempt = self.store.mark_dispatching(attempt, suffix=suffix)
        prompt = build_repair_bootstrap(
            previous_receipt,
            repair_id=repair_id,
            repair_ref=str(repair_path),
            repair_sha256=repair_sha256,
        )
        result: OpenCodeRunResult = self.transport.continue_session(
            session_id=str(previous_receipt["session_id"]),
            prompt=prompt,
            artifact_path=str(repair_path),
            workspace_path=workspace.path,
        )
        if result.status != "COMPLETED" or result.session_id != previous_receipt["session_id"]:
            self.store.finish_attempt(
                attempt, state="OUTCOME_UNKNOWN", transport_status=result.status, suffix=suffix
            )
            raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
        if result.provider_id != PROVIDER_ID or result.model_id != MODEL_ID:
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status="MODEL_ATTESTATION_MISMATCH",
                suffix=suffix,
            )
            raise FanoutError("MODEL_ATTESTATION_MISMATCH")
        try:
            worker = parse_worker_result(result.response_text, task_id=task_id, unit_id=unit_id)
        except FanoutError:
            self.store.finish_attempt(
                attempt,
                state="OUTCOME_UNKNOWN",
                transport_status="WORKER_RESULT_INVALID",
                suffix=suffix,
            )
            raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
        unit = ExecutionUnit.from_mapping({
            "task_id": task_id,
            "unit_id": unit_id,
            "envelope_ref": previous_receipt["envelope_ref"],
            "envelope_sha256": previous_receipt["envelope_sha256"],
            "expected_base_sha": previous_receipt["base_sha"],
            "mutation_paths": previous_receipt["mutation_paths"],
            "allow_deletions": previous_receipt.get("allow_deletions", False),
        })
        if worker["status"] == "BLOCKED":
            receipt = self._build_receipt(
                unit=unit,
                workspace=workspace,
                attempt=attempt,
                result=result,
                worker=worker,
                candidate=None,
                status="WORKER_BLOCKED",
                parent_receipt_id=str(previous_receipt.get("receipt_id") or ""),
                repair_id=repair_id,
            )
            self.store.write_receipt(receipt, suffix=suffix)
            self.store.finish_attempt(
                attempt, state="TERMINAL_BLOCKED", transport_status=result.status, suffix=suffix
            )
            return receipt
        candidate = _capture_candidate(
            unit, workspace, expected_head=str(previous_receipt["candidate_commit"])
        )
        receipt = self._build_receipt(
            unit=unit,
            workspace=workspace,
            attempt=attempt,
            result=result,
            worker=worker,
            candidate=candidate,
            status="CANDIDATE_READY_FOR_VERIFICATION",
            parent_receipt_id=str(previous_receipt.get("receipt_id") or ""),
            repair_id=repair_id,
        )
        self.store.write_receipt(receipt, suffix=suffix)
        self.store.finish_attempt(
            attempt, state="COMPLETED", transport_status=result.status, suffix=suffix
        )
        return receipt

    @staticmethod
    def _build_receipt(
        *,
        unit: ExecutionUnit,
        workspace: WorkspaceLease,
        attempt: Mapping[str, Any],
        result: OpenCodeRunResult,
        worker: Mapping[str, Any],
        candidate: Mapping[str, Any] | None,
        status: str,
        parent_receipt_id: str = "",
        repair_id: str = "",
    ) -> dict[str, Any]:
        receipt = {
            "schema": WORKER_RECEIPT_SCHEMA,
            "status": status,
            "task_id": unit.task_id,
            "unit_id": unit.unit_id,
            "attempt_id": attempt["attempt_id"],
            "mode": attempt["mode"],
            "provider": PROVIDER,
            "model": MODEL,
            "provider_id": result.provider_id,
            "model_id": result.model_id,
            "session_id": result.session_id,
            "workspace_id": workspace.workspace_id,
            "workspace_path": workspace.path,
            "base_sha": unit.expected_base_sha,
            "envelope_ref": unit.envelope_ref,
            "envelope_sha256": unit.envelope_sha256,
            "mutation_paths": list(unit.mutation_paths),
            "allow_deletions": unit.allow_deletions,
            "worker_summary": worker["summary"],
            "argv_sha256": result.argv_sha256,
            "stdout_sha256": result.stdout_sha256,
            "export_sha256": result.export_sha256,
            "opencode_version": result.version,
            "parent_receipt_id": parent_receipt_id,
            "repair_id": repair_id,
            "claim_ceiling": CLAIM_CEILING,
            "candidate_commit": "",
            "candidate_tree": "",
            "candidate_diff_sha256": "",
            "changed_paths": [],
            "deleted_paths": [],
        }
        if candidate is not None:
            receipt.update(candidate)
        material = dict(receipt)
        receipt["receipt_id"] = _sha256(_canonical_json(material))
        return receipt


__all__ = [
    "CLAIM_CEILING",
    "DISPATCH_ATTEMPT_SCHEMA",
    "FANOUT_DECISION_SCHEMA",
    "FANOUT_RUN_SCHEMA",
    "MODEL",
    "MODEL_ID",
    "PROVIDER",
    "PROVIDER_ID",
    "WORKER_RECEIPT_SCHEMA",
    "WORKER_RESULT_SCHEMA",
    "AdaptiveDeepSeekFanoutRuntime",
    "CapacityLease",
    "ExecutionUnit",
    "FanoutError",
    "FanoutStore",
    "GitWorktreeAllocator",
    "OpenCodeDeepSeekTransport",
    "OpenCodeRunResult",
    "WorkspaceLease",
    "build_repair_bootstrap",
    "build_worker_bootstrap",
    "parse_worker_result",
    "plan_fanout",
]
