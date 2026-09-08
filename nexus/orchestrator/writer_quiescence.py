"""Source-owned writer admission and quiescence evidence.

This module deliberately owns evidence only.  It does not issue an activation
grant and it never reports ``ACTIVE``.  Production adapters register their
resolved writer identity before entering a lease; callers cannot select a
different root or identity through an observation payload.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROLES = frozenset({
    "task_state",
    "event_log",
    "runtime_receipt",
    "effect_journal",
    "gateway_assist",
})
UNKNOWN = "UNKNOWN"
UNRESOLVED = "UNRESOLVED"
DRAINED = "DRAINED"


class WriterQuiescenceError(RuntimeError):
    """Base error for fail-closed writer admission."""


class WriterAdmissionDenied(WriterQuiescenceError):
    """A writer or operation was not admitted by the source-owned registry."""


class UnknownWriter(WriterAdmissionDenied):
    """The supplied writer identity is absent or no longer current."""


class HoldConflict(WriterQuiescenceError):
    """A duplicate or overlapping logical hold was requested."""


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    result = value.strip()
    if not result or len(result) > 4096 or any(ord(c) < 32 for c in result):
        raise ValueError(f"{name} is required")
    return result


def _root(value: str | Path) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("root must be absolute")
    return str(path.resolve())


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("invalid sha256")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _parents(path: Path) -> None:
    for parent in (path.parent, *path.parent.parents):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise WriterAdmissionDenied("unsafe evidence parent")


def _safe_bytes(path: Path) -> bytes:
    _parents(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise WriterAdmissionDenied("evidence must be a regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def _exists(path: Path) -> bool:
    _parents(path)
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _sync_parent(path: Path) -> None:
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_bytes(path: Path, data: bytes, *, exclusive: bool = False) -> None:
    _parents(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _parents(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            # Hard-link publication is an atomic no-overwrite CAS. A crash leaves
            # a complete discoverable marker, never an empty successful marker.
            os.link(temporary, path, follow_symlinks=False)
        else:
            if _exists(path) and not stat.S_ISREG(path.lstat().st_mode):
                raise WriterAdmissionDenied("unsafe evidence target")
            os.replace(temporary, path)
        _sync_parent(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True, slots=True)
class WriterIdentity:
    root: str
    role: str
    source_identity: str
    process_start_identity: str
    thread_id: str
    generation: int
    writer_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", _root(self.root))
        object.__setattr__(self, "role", _text(self.role, "role"))
        if self.role not in ROLES:
            raise ValueError(f"unsupported writer role: {self.role}")
        for name in ("source_identity", "process_start_identity", "thread_id", "writer_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be a non-negative integer")

    def key(self) -> tuple[str, str, str]:
        return self.root, self.role, self.writer_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "role": self.role,
            "source_identity": self.source_identity,
            "process_start_identity": self.process_start_identity,
            "thread_id": self.thread_id,
            "generation": self.generation,
            "writer_id": self.writer_id,
        }


@dataclass(frozen=True, slots=True)
class LeaseObservation:
    operation_id: str
    transaction_id: str
    identity: WriterIdentity
    entered_at: float
    exited_at: float | None = None
    durable_outcome: str | None = None
    expires_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "transaction_id": self.transaction_id,
            **self.identity.to_dict(),
            "entered_at": self.entered_at,
            "exited_at": self.exited_at,
            "durable_outcome": self.durable_outcome,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True, slots=True)
class WriterObservation:
    identity: WriterIdentity
    snapshot_sha256: str | None
    process_state: str
    pending_work: tuple[str, ...] = ()
    acknowledged_epoch: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity.to_dict(),
            "snapshot_sha256": self.snapshot_sha256,
            "process_state": self.process_state,
            "pending_work": list(self.pending_work),
            "acknowledged_epoch": self.acknowledged_epoch,
        }


@dataclass(frozen=True, slots=True)
class WriterQuiescenceReceipt:
    schema: str
    cohort_id: str
    hold_epoch: int
    source_identity: str
    server_identity: str
    process_start_identity: str
    ordered_roots: tuple[str, ...]
    observations: tuple[WriterObservation, ...]
    leases: tuple[LeaseObservation, ...]
    unknowns: tuple[str, ...]
    drain_state: str
    receipt_sha256: str = field(default="", compare=True)

    def __post_init__(self) -> None:
        if self.schema != "writer-quiescence/v1":
            raise ValueError("unsupported receipt schema")
        for name in ("cohort_id", "source_identity", "server_identity", "process_start_identity"):
            _text(getattr(self, name), name)
        if type(self.hold_epoch) is not int or self.hold_epoch <= 0:
            raise ValueError("hold epoch must be positive")
        if not isinstance(self.ordered_roots, tuple) or not self.ordered_roots:
            raise ValueError("ordered roots must be nonempty")
        if any(_root(root) != root for root in self.ordered_roots):
            raise ValueError("root is not canonical")
        if len(set(self.ordered_roots)) != len(self.ordered_roots):
            raise ValueError("duplicate root")
        if self.drain_state not in {DRAINED, UNKNOWN, UNRESOLVED}:
            raise ValueError("invalid drain state")
        if not all(isinstance(x, str) and x for x in self.unknowns):
            raise ValueError("invalid unknown detail")
        keys = set()
        for observation in self.observations:
            if not isinstance(observation, WriterObservation):
                raise ValueError("untyped observation")
            identity = observation.identity
            if identity.key() in keys or identity.root not in self.ordered_roots:
                raise ValueError("duplicate or foreign writer")
            keys.add(identity.key())
            if (
                identity.source_identity != self.source_identity
                or identity.process_start_identity != self.process_start_identity
            ):
                raise ValueError("observation identity mismatch")
            if observation.snapshot_sha256 is not None:
                _digest(observation.snapshot_sha256)
            _text(observation.process_state, "process state")
            if not isinstance(observation.pending_work, tuple) or not all(
                isinstance(x, str) and x for x in observation.pending_work
            ):
                raise ValueError("invalid pending observation")
            if observation.acknowledged_epoch is not None and (
                type(observation.acknowledged_epoch) is not int
                or observation.acknowledged_epoch <= 0
            ):
                raise ValueError("invalid acknowledgement")
        operations = set()
        for lease in self.leases:
            if (
                not isinstance(lease, LeaseObservation)
                or lease.identity.root not in self.ordered_roots
            ):
                raise ValueError("untyped or foreign lease")
            _text(lease.operation_id, "operation id")
            _text(lease.transaction_id, "transaction id")
            if lease.operation_id in operations:
                raise ValueError("duplicate lease")
            operations.add(lease.operation_id)
            if type(lease.entered_at) not in (int, float) or not math.isfinite(lease.entered_at):
                raise ValueError("invalid lease start")
            if (
                type(lease.expires_at) not in (int, float)
                or not math.isfinite(lease.expires_at)
                or lease.expires_at <= lease.entered_at
            ):
                raise ValueError("invalid lease expiry")
            if lease.exited_at is not None and (
                type(lease.exited_at) not in (int, float)
                or not math.isfinite(lease.exited_at)
                or lease.exited_at < lease.entered_at
            ):
                raise ValueError("invalid lease end")
        if self.drain_state == DRAINED:
            if self.unknowns or {x.identity.root for x in self.observations} != set(
                self.ordered_roots
            ):
                raise ValueError("drained receipt has unknown or uncovered roots")
            for observation in self.observations:
                if (
                    observation.snapshot_sha256 is None
                    or observation.process_state not in {"alive", "idle"}
                    or observation.pending_work
                    or observation.acknowledged_epoch != self.hold_epoch
                ):
                    raise ValueError("writer is not acknowledged and drained")
            if any(
                x.exited_at is None
                or x.durable_outcome not in {"committed", "failed"}
                or x.exited_at > x.expires_at
                for x in self.leases
            ):
                raise ValueError("unresolved lease")
        computed = _hash(self._unsigned_bytes())
        if self.receipt_sha256 and self.receipt_sha256 != computed:
            raise ValueError("receipt digest mismatch")
        object.__setattr__(self, "receipt_sha256", computed)

    def _payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "cohort_id": self.cohort_id,
            "hold_epoch": self.hold_epoch,
            "source_identity": self.source_identity,
            "server_identity": self.server_identity,
            "process_start_identity": self.process_start_identity,
            "ordered_roots": list(self.ordered_roots),
            "observations": [x.to_dict() for x in self.observations],
            "leases": [x.to_dict() for x in self.leases],
            "unknowns": list(self.unknowns),
            "drain_state": self.drain_state,
        }

    def _unsigned_bytes(self) -> bytes:
        return json.dumps(self._payload(), sort_keys=True, separators=(",", ":")).encode()

    def to_bytes(self) -> bytes:
        payload = self._payload()
        payload["receipt_sha256"] = self.receipt_sha256
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    def verify(self) -> "WriterQuiescenceReceipt":
        """Recompute and validate the digest of already typed receipt bytes."""
        if _hash(self._unsigned_bytes()) != self.receipt_sha256:
            raise ValueError("receipt digest mismatch")
        return self

    @classmethod
    def from_bytes(cls, data: bytes) -> "WriterQuiescenceReceipt":
        raw = json.loads(data, object_pairs_hook=_unique_object)
        if not isinstance(raw, Mapping):
            raise ValueError("receipt must be an object")
        expected = {
            "schema",
            "cohort_id",
            "hold_epoch",
            "source_identity",
            "server_identity",
            "process_start_identity",
            "ordered_roots",
            "observations",
            "leases",
            "unknowns",
            "drain_state",
            "receipt_sha256",
        }
        if set(raw) != expected:
            raise ValueError("receipt fields are incomplete or unknown")
        _digest(raw["receipt_sha256"])
        for name in ("ordered_roots", "observations", "leases", "unknowns"):
            if not isinstance(raw[name], list):
                raise ValueError(f"{name} must be an array")
        identity_fields = {
            "root",
            "role",
            "source_identity",
            "process_start_identity",
            "thread_id",
            "generation",
            "writer_id",
        }
        for item in raw["observations"]:
            if (
                not isinstance(item, dict)
                or set(item)
                != identity_fields
                | {"snapshot_sha256", "process_state", "pending_work", "acknowledged_epoch"}
                or not isinstance(item["pending_work"], list)
            ):
                raise ValueError("invalid observation fields")
        for item in raw["leases"]:
            if not isinstance(item, dict) or set(item) != identity_fields | {
                "operation_id",
                "transaction_id",
                "entered_at",
                "exited_at",
                "durable_outcome",
                "expires_at",
            }:
                raise ValueError("invalid lease fields")
        # Receipt bytes are typed; this validates integrity, not provenance; do not accept arbitrary
        # observation dictionaries in place of the nested dataclasses.
        observations = tuple(
            WriterObservation(
                WriterIdentity(**{
                    k: item[k]
                    for k in (
                        "root",
                        "role",
                        "source_identity",
                        "process_start_identity",
                        "thread_id",
                        "generation",
                        "writer_id",
                    )
                }),
                item.get("snapshot_sha256"),
                item["process_state"],
                tuple(item.get("pending_work", ())),
                item.get("acknowledged_epoch"),
            )
            for item in raw.get("observations", ())
        )
        leases = tuple(
            LeaseObservation(
                item["operation_id"],
                item["transaction_id"],
                WriterIdentity(**{
                    k: item[k]
                    for k in (
                        "root",
                        "role",
                        "source_identity",
                        "process_start_identity",
                        "thread_id",
                        "generation",
                        "writer_id",
                    )
                }),
                item["entered_at"],
                item.get("exited_at"),
                item.get("durable_outcome"),
                item["expires_at"],
            )
            for item in raw.get("leases", ())
        )
        return cls(
            raw["schema"],
            raw["cohort_id"],
            raw["hold_epoch"],
            raw["source_identity"],
            raw["server_identity"],
            raw["process_start_identity"],
            tuple(raw["ordered_roots"]),
            observations,
            leases,
            tuple(raw.get("unknowns", ())),
            raw["drain_state"],
            raw.get("receipt_sha256", ""),
        )

    def persist(self, path: str | Path) -> None:
        self.verify()
        _atomic_bytes(Path(path), self.to_bytes())

    @classmethod
    def load(cls, path: str | Path) -> "WriterQuiescenceReceipt":
        return cls.from_bytes(_safe_bytes(Path(path)))


@dataclass(frozen=True, slots=True)
class WriterReacquisitionObservation:
    previous_identity: WriterIdentity
    loaded_identity: WriterIdentity | None
    manifest_sha256: str | None
    observed_generation: int | None
    observed_writer_id: str | None
    state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_identity": self.previous_identity.to_dict(),
            "loaded_identity": self.loaded_identity.to_dict() if self.loaded_identity else None,
            "manifest_sha256": self.manifest_sha256,
            "observed_generation": self.observed_generation,
            "observed_writer_id": self.observed_writer_id,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class WriterReacquisitionReceipt:
    cohort_id: str
    hold_epoch: int
    ordered_roots: tuple[str, ...]
    observations: tuple[WriterReacquisitionObservation, ...]
    unknowns: tuple[str, ...]

    @property
    def state(self) -> str:
        return (
            "REACQUIRED"
            if not self.unknowns
            and self.observations
            and all(x.state == "MATCHED" for x in self.observations)
            else UNKNOWN
        )

    def to_bytes(self) -> bytes:
        payload = {
            "schema": "writer-reacquisition/v1",
            "cohort_id": self.cohort_id,
            "hold_epoch": self.hold_epoch,
            "ordered_roots": list(self.ordered_roots),
            "observations": [x.to_dict() for x in self.observations],
            "unknowns": list(self.unknowns),
            "state": self.state,
        }
        return _json_bytes({**payload, "receipt_sha256": _hash(_json_bytes(payload))})


@dataclass(slots=True)
class _Registered:
    identity: WriterIdentity
    snapshot: Callable[[], bytes] | None = None
    process_state: Callable[[], str] | None = None
    pending: Callable[[], Sequence[str]] | None = None
    acknowledged_epoch: int | None = None
    loaded_identity: Callable[[], WriterIdentity] | None = None


class WriterLease:
    def __init__(
        self, registry: "WriterRegistry", registered: _Registered, observation: LeaseObservation
    ) -> None:
        self._registry = registry
        self.registered = registered
        self.operation_id = observation.operation_id
        self.transaction_id = observation.transaction_id
        self.observation = observation
        self._closed = False
        self._thread = threading.get_ident()
        self._pid = os.getpid()
        self._deadline = time.monotonic() + max(0.0, observation.expires_at - time.time())

    def validate(self) -> None:
        self._registry._check_process()
        if self._closed or os.getpid() != self._pid or threading.get_ident() != self._thread:
            raise WriterAdmissionDenied("lease is closed or belongs to another process/thread")
        if time.monotonic() >= self._deadline:
            self.observation = self._registry._release(self, "unresolved")
            self._closed = True
            raise WriterAdmissionDenied("writer lease expired; durable outcome unresolved")

    def close(self, durable_outcome: str = "committed") -> LeaseObservation:
        self._registry._check_process()
        if os.getpid() != self._pid or threading.get_ident() != self._thread:
            raise WriterAdmissionDenied("lease belongs to another process/thread")
        if self._closed and self.observation.durable_outcome == "unresolved":
            raise WriterAdmissionDenied("writer lease is unresolved")
        if not self._closed:
            self.validate()
            self.observation = self._registry._release(self, durable_outcome)
            self._closed = True
        return self.observation

    def __enter__(self) -> "WriterLease":
        self.validate()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close("failed" if exc else "committed")


class TaskStateWriterAdapter:
    """Short-lived task-state writer binding for one service operation.

    The registry, binding, generation and path resolver are source-owned at
    construction.  Callers can supply only an operation/task identifier; they
    cannot select a root, writer identity, or owner context.
    """

    def __init__(
        self,
        registry: "WriterRegistry",
        *,
        binding: Any,
        writer_generation: Any,
        root: str | Path,
        writer_id: str,
        path_for_task: Callable[[str], Path],
        loaded_identity: Callable[[], WriterIdentity] | None = None,
        selection_entry_id: str = "task-state",
    ) -> None:
        from nexus.events.state_owner_manifest import StateOwnerBinding
        from nexus.events.writer_generation import EventWriterGeneration

        if not isinstance(registry, WriterRegistry):
            raise TypeError("registry is required")
        if not isinstance(binding, StateOwnerBinding):
            raise TypeError("source-owned state owner binding is required")
        if not isinstance(writer_generation, EventWriterGeneration):
            raise TypeError("source-owned writer generation is required")
        canonical_root = _root(root)
        if binding.root.resolve() != Path(canonical_root):
            raise UnknownWriter("task writer root does not match owner binding")
        if writer_generation.generation != binding.generation:
            raise UnknownWriter("task writer generation does not match owner binding")
        self.registry = registry
        self.binding = binding
        self.writer_generation = writer_generation
        self.root = canonical_root
        self.writer_id = _text(writer_id, "writer_id")
        self._path_for_task = path_for_task
        self._loaded_identity = loaded_identity
        self._selection_entry_id = _text(selection_entry_id, "selection_entry_id")
        self._active_contexts: dict[int, tuple[Any, WriterLease]] = {}

    def assert_context(self, context: Any) -> None:
        active = self._active_contexts.get(id(context))
        if active is None or active[0] is not context:
            raise WriterAdmissionDenied("task context has no active source-owned lease")
        active[1].validate()

    @contextlib.contextmanager
    def operation(
        self,
        task_id: str,
        *,
        operation_id: str | None = None,
        transaction_id: str | None = None,
    ) -> Any:
        from nexus.events.state_owner_manifest import (
            StateOwnerSelection,
            commit_owner_transaction,
            owner_transaction_guard,
            read_manifest,
        )
        from nexus.events.writer_generation import event_store_lock

        task = _text(task_id, "task_id")
        destination = Path(self._path_for_task(task)).resolve()
        try:
            relative = destination.relative_to(Path(self.root)).as_posix()
        except ValueError as exc:
            raise WriterAdmissionDenied("task path escapes registered root") from exc
        if not relative or relative.startswith(".nexus/") or "/" in task:
            # Task ids are file names in this store; reject traversal before
            # lease/manifest work and therefore before any selected bytes.
            raise WriterAdmissionDenied("invalid task-state path")
        lease = self.registry.acquire(
            root=self.root,
            role="task_state",
            writer_id=self.writer_id,
            operation_id=operation_id,
            transaction_id=transaction_id,
            generation=self.writer_generation.generation,
        )
        prepared = False
        try:
            if self._loaded_identity is not None:
                loaded = self._loaded_identity()
                expected = lease.registered.identity
                if (
                    not isinstance(loaded, WriterIdentity)
                    or loaded.root != expected.root
                    or loaded.role != expected.role
                    or loaded.source_identity != expected.source_identity
                    or loaded.process_start_identity != expected.process_start_identity
                    or loaded.generation != expected.generation
                    or loaded.writer_id != expected.writer_id
                ):
                    raise UnknownWriter("loaded task writer identity changed")
            selection = StateOwnerSelection(f"{self._selection_entry_id}:{task}", "task_state", relative)
            # Each operation receives a fresh transaction identity.  The
            # binding's owner/root/generation remain source-owned, while the
            # lease transaction fences this operation's manifest history.
            operation_binding = replace(self.binding, transaction_id=lease.transaction_id)
            # CAS read and prepare share the same physical guard. Accepted
            # primitives reenter this guard; no second store lock is acquired.
            with event_store_lock(Path(self.root)):
                lease.validate()
                previous = read_manifest(Path(self.root))
                if previous is None or previous.state != "COMMITTED":
                    raise WriterAdmissionDenied("task owner manifest is not committed")
                # Preparation itself changes durable manifest/snapshot bytes;
                # any subsequent exception must retain an unresolved lease.
                prepared = True
                with owner_transaction_guard(
                    operation_binding,
                    writer_generation=self.writer_generation,
                    selections=(selection,),
                    previous_manifest_sha256=previous.manifest_sha256,
                ) as context:
                    self._active_contexts[id(context)] = (context, lease)
                    try:
                        lease.validate()
                        yield context
                        lease.validate()
                        outcome = commit_owner_transaction(context)
                        committed = read_manifest(Path(self.root))
                        if committed != outcome or committed.transaction_id != lease.transaction_id:
                            raise WriterAdmissionDenied("task owner transaction readback mismatch")
                    finally:
                        self._active_contexts.pop(id(context), None)
            lease.close("committed")
        except BaseException:
            if not lease._closed:
                lease.close("unresolved" if prepared else "failed")
            raise

    write_context = operation


class TaskStateWriterFactory:
    """Source-owned factory used by HTTP/worker operation threads."""

    def __init__(self, adapter: TaskStateWriterAdapter):
        if not isinstance(adapter, TaskStateWriterAdapter):
            raise TypeError("task writer adapter is required")
        self._adapter = adapter

    def assert_context(self, context: Any) -> None:
        self._adapter.assert_context(context)

    def for_operation(self, task_id: str, **kwargs: Any):
        return self._adapter.operation(task_id, **kwargs)

    __call__ = for_operation


class RuntimeWriterAdapter:
    """Source-owned, operation-scoped binding for Runtime durable writes."""

    def __init__(
        self,
        registry: "WriterRegistry",
        *,
        binding: Any,
        writer_generation: Any,
        root: str | Path,
        writer_id: str,
        loaded_identity: Callable[[str], WriterIdentity] | None = None,
    ) -> None:
        from nexus.events.state_owner_manifest import StateOwnerBinding
        from nexus.events.writer_generation import EventWriterGeneration

        if not isinstance(registry, WriterRegistry):
            raise TypeError("registry is required")
        if not isinstance(binding, StateOwnerBinding):
            raise TypeError("source-owned state owner binding is required")
        if not isinstance(writer_generation, EventWriterGeneration):
            raise TypeError("source-owned writer generation is required")
        canonical_root = _root(root)
        if binding.root.resolve() != Path(canonical_root):
            raise UnknownWriter("runtime writer root does not match owner binding")
        if writer_generation.generation != binding.generation:
            raise UnknownWriter("runtime writer generation does not match owner binding")
        self.registry = registry
        self.binding = binding
        self.writer_generation = writer_generation
        self.root = canonical_root
        root_stat = Path(canonical_root).stat()
        self._root_identity = (root_stat.st_dev, root_stat.st_ino)
        self.writer_id = _text(writer_id, "writer_id")
        self._loaded_identity = loaded_identity
        self._role_writer_ids: dict[str, str] = {}
        self._active_contexts: dict[int, WriterLease] = {}
        self._active_paths: dict[int, Path] = {}
        for role in ("runtime_receipt", "effect_journal"):
            role_writer_id = self.writer_id
            self._role_writer_ids[role] = role_writer_id
            key = (self.root, role, role_writer_id)
            registered = registry._writers.get(key)
            if registered is None:
                raise UnknownWriter("runtime writer role is not loaded")
            if registered.identity.generation != writer_generation.generation:
                raise UnknownWriter("runtime writer generation is stale")

    def _identity(self, role: str) -> WriterIdentity:
        writer_id = self._role_writer_ids.get(role)
        if writer_id is None:
            raise WriterAdmissionDenied("runtime writer role is not registered")
        item = self.registry._writers.get((self.root, role, writer_id))
        if item is None:
            raise UnknownWriter("runtime writer is unknown")
        if item.loaded_identity is None:
            raise UnknownWriter("runtime writer loaded identity is unavailable")
        loaded = item.loaded_identity()
        if not isinstance(loaded, WriterIdentity) or loaded != item.identity:
            raise UnknownWriter("loaded runtime writer identity changed")
        return item.identity

    def validate_path(self, path: str | Path) -> str:
        """Check lexical selection and the loaded physical root without mutation."""
        root = Path(self.root)
        candidate = Path(path)
        if not candidate.is_absolute() or ".." in candidate.parts:
            raise WriterAdmissionDenied("runtime path must be absolute without traversal")
        try:
            root_stat = root.stat()
            if root.is_symlink() or root.resolve(strict=True) != root or (root_stat.st_dev, root_stat.st_ino) != self._root_identity:
                raise WriterAdmissionDenied("loaded runtime root physical identity changed")
            relative = candidate.relative_to(root)
        except (OSError, ValueError) as exc:
            raise WriterAdmissionDenied("runtime writer path root mismatch") from exc
        if not relative.parts or relative.as_posix().startswith(".nexus/writer-quiescence"):
            raise WriterAdmissionDenied("invalid runtime writer path")
        cursor = root
        for index, part in enumerate(relative.parts):
            cursor = cursor / part
            if cursor.is_symlink():
                raise WriterAdmissionDenied("runtime writer path is symlinked")
            if cursor.exists() and index < len(relative.parts) - 1 and not cursor.is_dir():
                raise WriterAdmissionDenied("runtime writer parent is not a directory")
        return relative.as_posix()

    def assert_context(self, context: Any) -> None:
        lease = self._active_contexts.get(id(context))
        if lease is None:
            raise WriterAdmissionDenied("runtime context has no active source-owned lease")
        lease.validate()
        self.validate_path(self._active_paths[id(context)])

    @contextlib.contextmanager
    def operation(
        self,
        task_id: str,
        *,
        role: str = "runtime_receipt",
        path: str | Path | None = None,
        operation_id: str | None = None,
        transaction_id: str | None = None,
    ) -> Any:
        from nexus.events.state_owner_manifest import (
            StateOwnerSelection,
            commit_owner_transaction,
            owner_transaction_guard,
            read_manifest,
        )
        from nexus.events.writer_generation import event_store_lock

        task = _text(task_id, "task_id")
        if role not in {"runtime_receipt", "effect_journal"}:
            raise WriterAdmissionDenied("unsupported runtime writer role")
        destination = Path(path) if path is not None else (
            Path(self.root) / ".nexus" / "events" / "effect_journal.v1.json"
            if role == "effect_journal" else Path(self.root) / ".nexus" / "reports" / f"{task}.json"
        )
        relative = self.validate_path(destination)
        identity = self._identity(role)
        lease = self.registry.acquire(
            root=self.root, role=role, writer_id=identity.writer_id,
            operation_id=operation_id, transaction_id=transaction_id,
            generation=self.writer_generation.generation,
        )
        prepared = False
        try:
            selection = StateOwnerSelection(f"runtime:{role}:{task}", role, relative)
            operation_binding = replace(self.binding, transaction_id=lease.transaction_id)
            with event_store_lock(Path(self.root)):
                lease.validate()
                previous = read_manifest(Path(self.root))
                if previous is None or previous.state != "COMMITTED":
                    raise WriterAdmissionDenied("runtime owner manifest is not committed")
                prepared = True
                with owner_transaction_guard(
                    operation_binding,
                    writer_generation=self.writer_generation,
                    selections=(selection,),
                    previous_manifest_sha256=previous.manifest_sha256,
                ) as context:
                    lease.validate()
                    self._active_contexts[id(context)] = lease
                    self._active_paths[id(context)] = destination
                    try:
                        yield context
                        self.assert_context(context)
                        outcome = commit_owner_transaction(context)
                        committed = read_manifest(Path(self.root))
                        if committed != outcome or committed.transaction_id != lease.transaction_id:
                            raise WriterAdmissionDenied("runtime owner transaction readback mismatch")
                        self.assert_context(context)
                    finally:
                        self._active_contexts.pop(id(context), None)
                        self._active_paths.pop(id(context), None)
            lease.close("committed")
        except BaseException:
            if not lease._closed:
                lease.close("unresolved" if prepared else "failed")
            raise


@dataclass(frozen=True, slots=True)
class RuntimeEffectBinding:
    journal: Any
    dispatch: Any
    reconcile: Any


class RuntimeWriterFactory:
    """Short-lived factory carried internally through the Runtime call chain."""

    def __init__(self, adapter: RuntimeWriterAdapter, *, effect_journal: Any = None, effect_dispatch: Any = None, effect_reconcile: Any = None):
        if not isinstance(adapter, RuntimeWriterAdapter):
            raise TypeError("runtime writer adapter is required")
        supplied = (effect_journal, effect_dispatch, effect_reconcile)
        if any(value is not None for value in supplied) and not all(value is not None for value in supplied):
            raise ValueError("effect_binding_incomplete")
        self._effect_binding = None
        if all(value is not None for value in supplied):
            from nexus.events.effect_journal import (
                EffectDispatchPort,
                EffectJournal,
                EffectReconcilePort,
            )
            if not isinstance(effect_journal, EffectJournal) or not isinstance(effect_dispatch, EffectDispatchPort) or not isinstance(effect_reconcile, EffectReconcilePort):
                raise TypeError("effect_binding_types_invalid")
            if Path(effect_journal.project_root).resolve() != Path(adapter.root) or effect_journal.generation != adapter.writer_generation:
                raise UnknownWriter("effect_binding_root_or_generation_mismatch")
            self._effect_binding = RuntimeEffectBinding(effect_journal, effect_dispatch, effect_reconcile)
        self._adapter = adapter

    def for_operation(self, task_id: str, **kwargs: Any):
        return self._adapter.operation(task_id, **kwargs)

    def assert_context(self, context: Any) -> None:
        self._adapter.assert_context(context)

    def effect_binding(self) -> RuntimeEffectBinding | None:
        binding = self._effect_binding
        if binding is None:
            return None
        from nexus.events.effect_journal import (
            EffectDispatchPort,
            EffectJournal,
            EffectReconcilePort,
        )
        if not isinstance(binding.journal, EffectJournal) or not isinstance(binding.dispatch, EffectDispatchPort) or not isinstance(binding.reconcile, EffectReconcilePort):
            raise UnknownWriter("effect binding types changed")
        if Path(binding.journal.project_root).resolve() != Path(self._adapter.root) or binding.journal.generation != self._adapter.writer_generation:
            raise UnknownWriter("effect binding root or generation changed")
        return binding

    def validate_entry(self, *, path: str | Path | None = None, role: str = "runtime_receipt") -> None:
        adapter = self._adapter
        if os.getpid() != adapter.registry._pid:
            raise UnknownWriter("runtime writer factory belongs to another process")
        if adapter.root in adapter.registry._held_roots:
            raise WriterAdmissionDenied("runtime writer root is held")
        marker = Path(adapter.root) / ".nexus" / "writer-quiescence-hold.json"
        try:
            marker_info = marker.lstat()
        except FileNotFoundError:
            marker_info = None
        if marker_info is not None:
            import stat
            if stat.S_ISLNK(marker_info.st_mode) or not stat.S_ISREG(marker_info.st_mode):
                raise WriterAdmissionDenied("runtime writer hold marker is unsafe")
            raise WriterAdmissionDenied("runtime writer root is held")
        from nexus.events.state_owner_manifest import read_manifest
        from nexus.events.writer_generation import read_generation
        manifest = read_manifest(Path(adapter.root))
        generation = read_generation(Path(adapter.root))
        if manifest is None or manifest.state != "COMMITTED" or manifest.owner_id != adapter.binding.owner_id:
            raise UnknownWriter("runtime owner manifest is unavailable")
        if generation is None or generation.generation != adapter.writer_generation.generation or generation.writer_id != adapter.writer_generation.writer_id:
            raise UnknownWriter("runtime writer generation is stale")
        if manifest.generation != adapter.writer_generation.generation or manifest.writer_id != adapter.writer_generation.writer_id:
            raise UnknownWriter("runtime owner manifest binding mismatch")
        adapter._identity(role)
        adapter.validate_path(path if path is not None else Path(adapter.root) / "entry.json")

    __call__ = for_operation


_LOADED_RUNTIME_WRITER_FACTORIES: dict[str, RuntimeWriterFactory] = {}


def register_runtime_writer_factory(factory: RuntimeWriterFactory) -> RuntimeWriterFactory:
    """Register a factory owned by the loaded source instance."""
    if not isinstance(factory, RuntimeWriterFactory):
        raise TypeError("runtime writer factory is required")
    root = factory._adapter.root
    existing = _LOADED_RUNTIME_WRITER_FACTORIES.get(root)
    if existing is not None and existing is not factory:
        raise WriterAdmissionDenied("runtime writer factory already loaded for root")
    if os.getpid() != factory._adapter.registry._pid:
        raise UnknownWriter("runtime writer factory belongs to another process")
    if root in factory._adapter.registry._held_roots:
        raise WriterAdmissionDenied("runtime writer factory cannot load under hold")
    _LOADED_RUNTIME_WRITER_FACTORIES[root] = factory
    return factory


def lookup_runtime_writer_factory(project_root: str | Path) -> RuntimeWriterFactory | None:
    """Return only an exact loaded source binding; never constructs a fallback."""
    try:
        root = _root(project_root)
    except (TypeError, ValueError):
        return None
    return _LOADED_RUNTIME_WRITER_FACTORIES.get(root)


def load_runtime_writer_factory(
    registry: "WriterRegistry",
    *,
    binding: Any,
    writer_generation: Any,
    root: str | Path,
    writer_id: str,
    effect_journal: Any = None,
    effect_dispatch: Any = None,
    effect_reconcile: Any = None,
) -> RuntimeWriterFactory:
    """Construct a Runtime port from independently loaded role registrations."""
    return register_runtime_writer_factory(RuntimeWriterFactory(RuntimeWriterAdapter(
        registry,
        binding=binding,
        writer_generation=writer_generation,
        root=root,
        writer_id=writer_id,
    ), effect_journal=effect_journal, effect_dispatch=effect_dispatch, effect_reconcile=effect_reconcile))


@dataclass(slots=True)
class WriterHold:
    registry: "WriterRegistry"
    cohort_id: str
    roots: tuple[str, ...]
    epoch: int
    selected: tuple[_Registered, ...] = ()
    acknowledged: set[tuple[str, str, str]] = field(default_factory=set)
    released: bool = False

    def acknowledge(self, writer_id: str, *, root: str, role: str, generation: int) -> None:
        self.registry._check_process()
        key = (_root(root), _text(role, "role"), _text(writer_id, "writer_id"))
        with self.registry._mutex:
            self.registry._check_hold(self)
            item = self.registry._writers.get(key)
            if (
                item is None
                or not any(x is item for x in self.selected)
                or type(generation) is not int
                or item.identity.generation != generation
            ):
                raise UnknownWriter("writer acknowledgement is stale or unregistered")
            if any(x.registered is item for x in self.registry._leases.values()):
                raise WriterAdmissionDenied("writer still owns an active lease")
            item.acknowledged_epoch = self.epoch
            self.acknowledged.add(key)

    def wait_for_drain(self, timeout: float = 5.0) -> None:
        self.registry._check_process()
        deadline = time.monotonic() + timeout
        while True:
            with self.registry._mutex:
                self.registry._check_hold(self)
                active = bool(self.registry._leases_for(self.roots))
            if not active:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError("writer leases did not drain")
            time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    def finalize(self) -> WriterQuiescenceReceipt:
        return self.registry._finalize(self)

    def release(self) -> None:
        raise WriterQuiescenceError("hold release is owned by the cohort coordinator")


class WriterRegistry:
    """Source-owned adapter registry. This object is never a transport input.

    A lease is bound to its acquiring thread, while an adapter may be invoked
    from several actual service threads. Adapter registration identity records
    its loader thread; each lease records the observed operation thread.
    Existing durable holds or unfinished leases quarantine restarted writers.
    """

    def __init__(
        self,
        *,
        source_identity: str,
        process_start_identity: str | None = None,
        server_identity: str = "",
        hold_store: str | Path | None = None,
        lease_lifetime_seconds: float = 30.0,
    ) -> None:
        if (
            type(lease_lifetime_seconds) not in (int, float)
            or not math.isfinite(lease_lifetime_seconds)
            or not 0 < lease_lifetime_seconds <= 300
        ):
            raise ValueError("lease lifetime must be in (0, 300] seconds")
        self.lease_lifetime_seconds = float(lease_lifetime_seconds)
        self.source_identity = _text(source_identity, "source_identity")
        observed = current_process_start_identity()
        if process_start_identity is not None and process_start_identity != observed:
            raise UnknownWriter("process identity was not observed from this process")
        self.process_start_identity = observed
        self.server_identity = _text(server_identity or f"process:{observed}", "server identity")
        # This optional store is a source-owned construction seam, not a CLI or
        # Gateway override. It also owns durable operation records.
        self.hold_store = Path(_root(hold_store)) if hold_store is not None else None
        self._pid = os.getpid()
        self._mutex = threading.RLock()
        self._writers: dict[tuple[str, str, str], _Registered] = {}
        self._leases: dict[str, WriterLease] = {}
        self._held_roots: dict[str, WriterHold] = {}
        self._epoch = 0
        self._lease_history: list[LeaseObservation] = []
        self._finalized: dict[str, tuple[WriterHold, Path, str]] = {}

    def _check_process(self) -> None:
        if os.getpid() != self._pid:
            raise UnknownWriter("registry belongs to a different process instance")

    def register(
        self,
        identity: WriterIdentity,
        *,
        snapshot: Callable[[], bytes] | None = None,
        process_state: Callable[[], str] | None = None,
        pending: Callable[[], Sequence[str]] | None = None,
        loaded_identity: Callable[[], WriterIdentity] | None = None,
    ) -> WriterIdentity:
        self._check_process()
        if (
            not isinstance(identity, WriterIdentity)
            or identity.source_identity != self.source_identity
            or identity.process_start_identity != self.process_start_identity
            or identity.thread_id != str(threading.get_ident())
        ):
            raise UnknownWriter("writer identity does not match loaded source/process/thread")
        if any(
            x is not None and not callable(x)
            for x in (snapshot, process_state, pending, loaded_identity)
        ):
            raise ValueError("observers must be source-owned callables")
        with self._mutex:
            if identity.root in self._held_roots:
                raise WriterAdmissionDenied("cannot change registration under hold")
            if identity.key() in self._writers:
                raise WriterAdmissionDenied("writer is already registered")
            self._writers[identity.key()] = _Registered(
                identity, snapshot, process_state, pending, loaded_identity=loaded_identity
            )
        return identity

    register_writer = register

    def _marker_path(self, root: str) -> Path:
        if self.hold_store:
            return self.hold_store / f"{_hash(root.encode())}.json"
        return Path(root) / ".nexus" / "writer-quiescence-hold.json"

    def _lease_dir(self, root: str) -> Path:
        if self.hold_store:
            return self.hold_store / "leases" / _hash(root.encode())
        return Path(root) / ".nexus" / "writer-quiescence-leases"

    def _lease_path(self, root: str, operation_id: str) -> Path:
        return self._lease_dir(root) / f"{_hash(operation_id.encode())}.json"

    def _durable_leases(self, root: str) -> tuple[list[LeaseObservation], list[str]]:
        directory = self._lease_dir(root)
        _parents(directory / "probe")
        if not _exists(directory):
            return [], []
        leases, issues = [], []
        try:
            entries = list(directory.iterdir())
            for path in entries:
                if path.name.startswith("."):
                    continue
                raw = json.loads(_safe_bytes(path), object_pairs_hook=_unique_object)
                identity_keys = (
                    "root",
                    "role",
                    "source_identity",
                    "process_start_identity",
                    "thread_id",
                    "generation",
                    "writer_id",
                )
                identity = WriterIdentity(**{k: raw[k] for k in identity_keys})
                lease = LeaseObservation(
                    raw["operation_id"],
                    raw["transaction_id"],
                    identity,
                    raw["entered_at"],
                    raw["exited_at"],
                    raw["durable_outcome"],
                    raw["expires_at"],
                )
                if identity.root != root or path != self._lease_path(root, lease.operation_id):
                    raise ValueError("foreign operation record")
                leases.append(lease)
                if lease.exited_at is None or lease.durable_outcome not in {"committed", "failed"}:
                    issues.append(f"lease:unresolved:{lease.operation_id}")
                if identity.process_start_identity != self.process_start_identity:
                    issues.append(f"lease:foreign-process:{lease.operation_id}")
        except (OSError, ValueError, KeyError, TypeError, WriterQuiescenceError) as exc:
            issues.append(f"leases:unreadable:{root}:{type(exc).__name__}")
        return leases, issues

    def acquire(
        self,
        *,
        root: str | Path,
        role: str,
        writer_id: str,
        operation_id: str | None = None,
        transaction_id: str | None = None,
        generation: int,
        thread_id: str | None = None,
    ) -> WriterLease:
        self._check_process()
        actual_thread = str(threading.get_ident())
        if thread_id is not None and thread_id != actual_thread:
            raise UnknownWriter("operation thread identity is not current")
        key = (_root(root), _text(role, "role"), _text(writer_id, "writer_id"))
        with self._mutex:
            item = self._writers.get(key)
            if (
                item is None
                or type(generation) is not int
                or item.identity.generation != generation
            ):
                raise UnknownWriter("writer is unknown or generation is stale")
            if item.identity.root in self._held_roots or _exists(
                self._marker_path(item.identity.root)
            ):
                raise WriterAdmissionDenied("writer admission is durably held")
            _, unresolved = self._durable_leases(item.identity.root)
            # Current in-flight operations are admitted already. A foreign or
            # lost operation requires reconciliation, never an automatic retry.
            if any(
                not issue.startswith("lease:unresolved:")
                or issue.removeprefix("lease:unresolved:") not in self._leases
                for issue in unresolved
            ):
                raise WriterAdmissionDenied("unresolved durable writer operation")
            operation_id = _text(operation_id or uuid.uuid4().hex, "operation_id")
            transaction_id = _text(transaction_id or operation_id, "transaction_id")
            path = self._lease_path(item.identity.root, operation_id)
            if (
                operation_id in self._leases
                or any(x.operation_id == operation_id for x in self._lease_history)
                or _exists(path)
            ):
                raise WriterAdmissionDenied("duplicate or replayed operation")
            observation = LeaseObservation(
                operation_id,
                transaction_id,
                replace(item.identity, thread_id=actual_thread),
                time.time(),
                expires_at=time.time() + self.lease_lifetime_seconds,
            )
            try:
                _atomic_bytes(path, _json_bytes(observation.to_dict()), exclusive=True)
            except FileExistsError as exc:
                raise WriterAdmissionDenied("operation already exists") from exc
            lease = WriterLease(self, item, observation)
            self._leases[operation_id] = lease
            # A different process can publish a hold between the first check
            # and lease publication. Abort before caller receives a write lease.
            if _exists(self._marker_path(item.identity.root)):
                self._release(lease, "failed")
                raise WriterAdmissionDenied("hold raced writer admission")
            return lease

    enter_lease = acquire

    def _release(self, lease: WriterLease, outcome: str) -> LeaseObservation:
        self._check_process()
        if outcome not in {"committed", "failed", "unresolved"}:
            raise ValueError("invalid durable outcome")
        with self._mutex:
            if self._leases.get(lease.operation_id) is not lease:
                raise WriterAdmissionDenied("lease identity is not current")
            result = replace(lease.observation, exited_at=time.time(), durable_outcome=outcome)
            _atomic_bytes(
                self._lease_path(result.identity.root, result.operation_id),
                _json_bytes(result.to_dict()),
            )
            del self._leases[lease.operation_id]
            self._lease_history.append(result)
            return result

    def _hold_payload(self, root: str, hold: WriterHold) -> dict[str, Any]:
        return {
            "schema": "writer-quiescence-hold/v1",
            "cohort_id": hold.cohort_id,
            "hold_epoch": hold.epoch,
            "root": root,
            "ordered_roots": list(hold.roots),
            "source_identity": self.source_identity,
            "server_identity": self.server_identity,
            "process_start_identity": self.process_start_identity,
            "selected_writers": [x.identity.to_dict() for x in hold.selected],
        }

    def begin_hold(
        self, roots: Sequence[str | Path], *, cohort_id: str | None = None
    ) -> WriterHold:
        self._check_process()
        if isinstance(roots, (str, bytes)):
            raise ValueError("ordered roots must be a sequence")
        resolved = tuple(_root(root) for root in roots)
        if not resolved or len(set(resolved)) != len(resolved):
            raise HoldConflict("root vector is empty or contains duplicates")
        with self._mutex:
            if any(
                root in self._held_roots or _exists(self._marker_path(root)) for root in resolved
            ):
                raise HoldConflict("existing durable hold requires cohort reconciliation")
            selected_cohort = _text(cohort_id or uuid.uuid4().hex, "cohort_id")
            if any(hold.cohort_id == selected_cohort for hold in self._held_roots.values()):
                raise HoldConflict("cohort identity already holds a root vector")
            self._epoch += 1
            selected = tuple(
                sorted(
                    (x for x in self._writers.values() if x.identity.root in resolved),
                    key=lambda x: (resolved.index(x.identity.root), x.identity.key()),
                )
            )
            hold = WriterHold(
                self,
                selected_cohort,
                resolved,
                self._epoch,
                selected,
            )
            # Close admission for the full vector before persisting any root.
            # Failure retains the entire in-process hold plus published vector
            # markers. No physical domain lock spans multiple roots.
            self._held_roots.update({root: hold for root in resolved})
            for root in resolved:
                try:
                    _atomic_bytes(
                        self._marker_path(root),
                        _json_bytes(self._hold_payload(root, hold)),
                        exclusive=True,
                    )
                except OSError as exc:
                    raise HoldConflict("partial durable hold; reconciliation required") from exc
            return hold

    hold = begin_hold

    def _check_hold(self, hold: WriterHold) -> None:
        self._check_process()
        if (
            hold.registry is not self
            or hold.released
            or any(self._held_roots.get(root) is not hold for root in hold.roots)
        ):
            raise HoldConflict("hold is not current")
        for root in hold.roots:
            try:
                if _safe_bytes(self._marker_path(root)) != _json_bytes(
                    self._hold_payload(root, hold)
                ):
                    raise HoldConflict("durable hold differs from registered hold")
            except OSError as exc:
                raise HoldConflict("durable hold is missing or unreadable") from exc
        current = tuple(
            sorted(
                (x for x in self._writers.values() if x.identity.root in hold.roots),
                key=lambda x: (hold.roots.index(x.identity.root), x.identity.key()),
            )
        )
        if len(current) != len(hold.selected) or any(
            a is not b for a, b in zip(current, hold.selected)
        ):
            raise HoldConflict("registered writer vector changed under hold")

    def _observation(self, item: _Registered) -> tuple[WriterObservation, list[str]]:
        issues = []
        snapshot_hash = None
        try:
            if item.snapshot is None:
                raise ValueError("unavailable")
            data = item.snapshot()
            if not isinstance(data, bytes):
                raise ValueError("snapshot did not return bytes")
            snapshot_hash = _hash(data)
        except Exception as exc:
            issues.append(f"snapshot:{item.identity.writer_id}:{type(exc).__name__}")
        try:
            state = item.process_state() if item.process_state else UNKNOWN
            if state not in {"alive", "idle"}:
                state = UNKNOWN
                issues.append(f"process:{item.identity.writer_id}:unknown")
        except Exception as exc:
            state = UNKNOWN
            issues.append(f"process:{item.identity.writer_id}:{type(exc).__name__}")
        try:
            value = item.pending() if item.pending else None
            if (
                value is None
                or isinstance(value, (str, bytes))
                or not isinstance(value, Sequence)
                or not all(isinstance(x, str) and x for x in value)
            ):
                raise ValueError("pending observation unavailable")
            pending = tuple(value)
            if pending:
                issues.append(f"pending:{item.identity.writer_id}:not-empty")
        except Exception as exc:
            pending = (UNKNOWN,)
            issues.append(f"pending:{item.identity.writer_id}:{type(exc).__name__}")
        return WriterObservation(
            item.identity, snapshot_hash, state, pending, item.acknowledged_epoch
        ), issues

    def _finalize(self, hold: WriterHold) -> WriterQuiescenceReceipt:
        with self._mutex:
            self._check_hold(hold)
            selected = hold.selected
        observations, unknowns, leases = [], [], []
        for root in hold.roots:
            if not any(x.identity.root == root for x in selected):
                unknowns.append(f"writers:unregistered:{root}")
            observed_leases, issues = self._durable_leases(root)
            leases.extend(observed_leases)
            unknowns.extend(issues)
        # Observers may block on service/domain locks; never invoke them while
        # holding the registry mutex.
        for item in selected:
            observation, issues = self._observation(item)
            observations.append(observation)
            unknowns.extend(issues)
            if observation.acknowledged_epoch != hold.epoch:
                unknowns.append(f"ack:{item.identity.writer_id}:epoch-{hold.epoch}")
        with self._mutex:
            self._check_hold(hold)
            if self._leases_for(hold.roots):
                unknowns.append("leases:active")
            if any(x.acknowledged_epoch != hold.epoch for x in selected):
                unknowns.append("ack:changed")
        return WriterQuiescenceReceipt(
            "writer-quiescence/v1",
            hold.cohort_id,
            hold.epoch,
            self.source_identity,
            self.server_identity,
            self.process_start_identity,
            hold.roots,
            tuple(observations),
            tuple(sorted(leases, key=lambda x: x.operation_id)),
            tuple(sorted(set(unknowns))),
            DRAINED if not unknowns else UNKNOWN,
        )

    def observe_reacquisition(self, hold: WriterHold) -> WriterReacquisitionReceipt:
        """Observe loaded adapters against physical P6 bindings; retain hold.

        This neither changes a registered adapter nor installs a generation.
        Missing source-owned adapter observations remain UNKNOWN. F alone may
        consume these observations to decide all-root release.
        """
        from nexus.events.state_owner_manifest import COMMITTED, read_manifest
        from nexus.events.writer_generation import event_store_lock, read_generation

        with self._mutex:
            self._check_hold(hold)
            selected = hold.selected
            if self._leases_for(hold.roots):
                raise WriterAdmissionDenied("cannot observe reacquisition with active leases")
        observations, unknowns = [], []
        for root in hold.roots:
            items = [x for x in selected if x.identity.root == root]
            if not items:
                unknowns.append(f"writers:unregistered:{root}")
                continue
            # Exactly one existing domain guard; mutex is released before IO.
            for item in items:
                loaded, digest, generation, writer_id = None, None, None, None
                state = UNKNOWN
                try:
                    # Do not create a missing lock/root to make an absent P6
                    # installation appear observable.
                    if not _exists(Path(root) / ".nexus" / "events" / "event_log.lock"):
                        raise UnknownWriter("P6 guard is absent")
                    with event_store_lock(Path(root)):
                        manifest = read_manifest(Path(root))
                        installed = read_generation(Path(root))
                        if manifest is None or installed is None or manifest.state != COMMITTED:
                            raise UnknownWriter("committed P6 binding unavailable")
                        digest, generation, writer_id = (
                            manifest.manifest_sha256,
                            installed.generation,
                            installed.writer_id,
                        )
                        if (
                            manifest.root_identity != _hash(root.encode())
                            or manifest.generation != generation
                            or manifest.writer_id != writer_id
                        ):
                            raise UnknownWriter("physical P6 binding mismatch")
                        if item.loaded_identity is None:
                            raise UnknownWriter("loaded adapter binding unavailable")
                        loaded = item.loaded_identity()
                        if not isinstance(loaded, WriterIdentity):
                            loaded = None
                            raise UnknownWriter("loaded adapter binding untyped")
                        previous = item.identity
                        if (
                            loaded.root != root
                            or loaded.role != previous.role
                            or loaded.source_identity != previous.source_identity
                            or loaded.process_start_identity != self.process_start_identity
                            or loaded.generation != generation
                            or generation <= previous.generation
                            or loaded.writer_id != writer_id
                            or loaded.thread_id != str(threading.get_ident())
                            or previous.role not in {x.role for x in manifest.files}
                        ):
                            raise UnknownWriter(
                                "loaded adapter does not match advanced physical binding"
                            )
                        state = "MATCHED"
                except Exception as exc:
                    unknowns.append(f"reacquisition:{item.identity.writer_id}:{type(exc).__name__}")
                observations.append(
                    WriterReacquisitionObservation(
                        item.identity, loaded, digest, generation, writer_id, state
                    )
                )
        with self._mutex:
            self._check_hold(hold)
            if self._leases_for(hold.roots):
                raise WriterAdmissionDenied("lease appeared under hold")
        return WriterReacquisitionReceipt(
            hold.cohort_id, hold.epoch, hold.roots, tuple(observations), tuple(unknowns)
        )

    def persist_finalized(self, hold: WriterHold) -> WriterQuiescenceReceipt:
        """Explicit source-owned operation; never called by preflight loaders."""
        receipt = self._finalize(hold)
        if receipt.drain_state != DRAINED:
            raise WriterAdmissionDenied("COLLECTOR_NOT_DRAINED")
        path = (
            self._marker_path(hold.roots[0]).parent
            / "writer-quiescence-receipts"
            / f"{_hash(hold.cohort_id.encode())}.json"
        )
        with self._mutex:
            self._check_hold(hold)
            if hold.cohort_id in self._finalized:
                raise HoldConflict("cohort evidence already finalized")
            _atomic_bytes(path, receipt.to_bytes(), exclusive=True)
            self._finalized[hold.cohort_id] = (hold, path, _hash(receipt.to_bytes()))
        return receipt

    def load_finalized(self, cohort_id: str) -> WriterQuiescenceReceipt:
        """Read and rebind previously finalized bytes; no observation or write.

        A new process intentionally cannot adopt old registry evidence. It must
        reconcile the durable hold through the cohort owner before reacquiring.
        """
        self._check_process()
        with self._mutex:
            saved = self._finalized.get(_text(cohort_id, "cohort id"))
            if saved is None:
                raise UnknownWriter("MISSING_FINALIZED_WRITER_QUIESCENCE_RECEIPT")
            hold, path, expected_bytes_hash = saved
            self._check_hold(hold)
            data = _safe_bytes(path)
            if _hash(data) != expected_bytes_hash:
                raise WriterAdmissionDenied("FINALIZED_WRITER_QUIESCENCE_RECEIPT_CHANGED")
            receipt = WriterQuiescenceReceipt.from_bytes(data)
            if (
                receipt.drain_state != DRAINED
                or receipt.cohort_id != hold.cohort_id
                or receipt.hold_epoch != hold.epoch
                or receipt.ordered_roots != hold.roots
                or receipt.source_identity != self.source_identity
                or receipt.server_identity != self.server_identity
                or receipt.process_start_identity != self.process_start_identity
                or tuple(x.identity for x in receipt.observations)
                != tuple(x.identity for x in hold.selected)
                or self._leases_for(hold.roots)
            ):
                raise WriterAdmissionDenied("FINALIZED_WRITER_QUIESCENCE_BINDING_MISMATCH")
            return receipt

    def _leases_for(self, roots: Sequence[str]) -> list[WriterLease]:
        return [x for x in self._leases.values() if x.registered.identity.root in roots]

    def snapshot(self) -> dict[str, Any]:
        self._check_process()
        with self._mutex:
            roots = set(self._held_roots) | {x.identity.root for x in self._writers.values()}
            durable = [root for root in roots if _exists(self._marker_path(root))]
            return {
                "source_identity": self.source_identity,
                "process_start_identity": self.process_start_identity,
                "server_identity": self.server_identity,
                "writers": [
                    x.identity.to_dict()
                    for x in sorted(self._writers.values(), key=lambda x: x.identity.key())
                ],
                "active_leases": [x.observation.to_dict() for x in self._leases.values()],
                "held_roots": sorted(set(self._held_roots) | set(durable)),
                "hold_epoch": self._epoch,
            }


def current_process_start_identity() -> str:
    """Observe OS process start identity, refusing an unknown start time."""
    try:
        started = subprocess.check_output(
            ["ps", "-o", "lstart=", "-p", str(os.getpid())], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise UnknownWriter("process start identity unavailable") from exc
    if not started:
        raise UnknownWriter("process start identity unavailable")
    return f"pid:{os.getpid()}:start:{started}"


__all__ = [
    "DRAINED",
    "UNKNOWN",
    "UNRESOLVED",
    "ROLES",
    "HoldConflict",
    "UnknownWriter",
    "WriterAdmissionDenied",
    "WriterIdentity",
    "WriterLease",
    "WriterObservation",
    "WriterQuiescenceError",
    "WriterQuiescenceReceipt",
    "WriterRegistry",
    "WriterHold",
    "current_process_start_identity",
    "WriterReacquisitionObservation",
    "WriterReacquisitionReceipt",
]
