"""Source-owned multi-root writer activation barrier.

The state-owner transition service advances one physical root at a time.  This
module supplies the missing cohort boundary: a B hold is kept until every
root has a committed A receipt and every writer has been reacquired against
that receipt. Existing writers are supplied as loaded objects; generation-zero
roots supply typed owners from which provisional factories are constructed
under the original hold. It never constructs a registry or selects roots from
a request.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from nexus.orchestrator.state_owner_transition_service import LoadedRootTransition
from nexus.orchestrator.writer_quiescence import (
    DRAINED,
    WriterAdmissionDenied,
    WriterHold,
    WriterIdentity,
    WriterReacquisitionReceipt,
    WriterRegistry,
)


class WriterActivationError(RuntimeError):
    """A cohort cannot advance while its physical evidence is incomplete."""


class CohortConflict(WriterActivationError):
    pass


@dataclass(frozen=True, slots=True)
class InitialTaskOwner:
    """Typed source owner used to construct a task writer after A."""

    service: Any


@dataclass(frozen=True, slots=True)
class InitialRuntimeOwner:
    """Typed runtime effect ports used to construct a runtime writer after A."""

    effect_dispatch: Any
    effect_reconcile: Any


@dataclass(frozen=True, slots=True)
class InitialEventOwner:
    """Typed event store owner, with an optional source-owned event bus."""

    event_store: Any
    event_bus: Any = None


@dataclass(frozen=True, slots=True)
class InitialActivationRootSpec:
    """Cold-start A contract; no arbitrary materialization callback is accepted."""

    root: str
    role: str
    transition: LoadedRootTransition
    expected_root_identity: str
    expected_generation: int = 1
    expected_writer_id: str = ""
    owner: InitialTaskOwner | InitialRuntimeOwner | InitialEventOwner | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", _root(self.root))
        if not isinstance(self.transition, LoadedRootTransition):
            raise TypeError("typed loaded A transition required")
        request = self.transition.request
        if request.expected_generation is not None:
            raise WriterActivationError("INITIAL_REQUEST_EXPECTS_GENERATION_ZERO")
        if not isinstance(self.role, str) or not self.role.strip():
            raise ValueError("role is required")
        physical = self.transition.service._roots.get(request.root_id)
        if physical is None or _root(physical) != self.root:
            raise ValueError("transition root does not match initial root")
        if not isinstance(self.expected_root_identity, str) or len(self.expected_root_identity) != 64:
            raise ValueError("expected root identity is required")
        if request.expected_root_identity != self.expected_root_identity:
            raise ValueError("expected root identity does not match A request")
        if request.next_generation != self.expected_generation or request.next_writer_id != self.expected_writer_id:
            raise ValueError("expected next binding does not match A request")
        if type(self.expected_generation) is not int or self.expected_generation < 1:
            raise ValueError("expected generation is required")
        if not isinstance(self.expected_writer_id, str) or not self.expected_writer_id:
            raise ValueError("expected writer id is required")
        from nexus.events.effect_journal import EffectDispatchPort, EffectReconcilePort
        from nexus.events.log_store import JsonlEventLogStore
        from nexus.events.transport import NexusEventBus
        from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

        if isinstance(self.owner, InitialTaskOwner):
            if (self.role != "task_state"
                    or not isinstance(self.owner.service, SelfHostedTaskService)
                    or self.owner.service.state_dir.resolve() != Path(self.root)
                    or self.owner.service._writer_factory is not None):
                raise ValueError("initial task owner root or role mismatch")
        elif isinstance(self.owner, InitialRuntimeOwner):
            if (self.role not in {"runtime_receipt", "effect_journal"}
                    or not isinstance(self.owner.effect_dispatch, EffectDispatchPort)
                    or not isinstance(self.owner.effect_reconcile, EffectReconcilePort)):
                raise ValueError("initial runtime owner or role mismatch")
        elif isinstance(self.owner, InitialEventOwner):
            if (self.role != "event_log"
                    or not isinstance(self.owner.event_store, JsonlEventLogStore)
                    or self.owner.event_store._writer_factory is not None
                    or (self.owner.event_bus is not None and (
                        not isinstance(self.owner.event_bus, type)
                        or not issubclass(self.owner.event_bus, NexusEventBus)
                        or self.owner.event_bus._log_store is not self.owner.event_store))):
                raise ValueError("initial event owner or role mismatch")
        else:
            raise TypeError("typed initial owner required")


_LOADED_COHORTS: dict[tuple[int, str], "WriterActivationCohort"] = {}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _atomic(path: Path, payload: Mapping[str, Any]) -> None:
    _safe_parents(path)
    if path.is_symlink():
        raise WriterActivationError("COHORT_STATE_UNSAFE")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_json(payload) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def _safe_parents(path: Path) -> None:
    for parent in reversed(path.parents):
        if parent.is_symlink():
            raise WriterActivationError("COHORT_PARENT_SYMLINK")
        if parent.exists() and not parent.is_dir():
            raise WriterActivationError("COHORT_PARENT_UNSAFE")


def _safe_read(path: Path) -> bytes:
    _safe_parents(path)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise WriterActivationError("COHORT_STATE_UNSAFE")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        return os.read(fd, max(1, info.st_size + 1))
    finally:
        os.close(fd)


def _root(value: str | Path) -> str:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("root must be absolute without traversal")
    path = path.resolve()
    return str(path)


def _receipt_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    if hasattr(value, "to_bytes"):
        raw = value.to_bytes()
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise WriterActivationError("TYPED_RECEIPT_UNREADABLE") from exc
        if not isinstance(parsed, Mapping):
            raise WriterActivationError("TYPED_RECEIPT_UNREADABLE")
        return {"bytes_sha256": _sha(raw), "payload": dict(parsed)}
    if isinstance(value, Mapping):
        return dict(value)
    raise WriterActivationError("TYPED_RECEIPT_REQUIRED")


@dataclass(frozen=True, slots=True)
class ActivationRoot:
    """A coordinator-loaded root and its one-root A operation handles."""

    root: str
    role: str
    transition: LoadedRootTransition
    adapter: Any
    expected_root_identity: str
    expected_generation: int
    expected_writer_id: str
    expected_manifest_sha256: str | None = None
    factory: Any = None
    task_service: Any = None
    event_store: Any = None
    event_bus: Any = None
    initial_spec: InitialActivationRootSpec | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", _root(self.root))
        if not isinstance(self.role, str) or not self.role.strip():
            raise ValueError("role is required")
        if not isinstance(self.transition, LoadedRootTransition):
            raise TypeError("typed loaded A transition required")
        from nexus.events.transport import EventWriterAdapter
        from nexus.orchestrator.writer_quiescence import (
            RuntimeWriterAdapter,
            TaskStateWriterAdapter,
        )

        if self.adapter is None and self.initial_spec is None:
            raise TypeError("loaded typed writer adapter required")
        if self.adapter is not None and not isinstance(
            self.adapter, (TaskStateWriterAdapter, RuntimeWriterAdapter, EventWriterAdapter)
        ):
            raise TypeError("loaded typed writer adapter required")
        if self.initial_spec is not None:
            if self.initial_spec.root != self.root or self.initial_spec.transition is not self.transition:
                raise ValueError("initial spec does not match activation root")
            if (self.role != self.initial_spec.role
                    or self.expected_root_identity != self.initial_spec.expected_root_identity
                    or self.expected_generation != self.initial_spec.expected_generation
                    or self.expected_writer_id != self.initial_spec.expected_writer_id
                    or self.adapter is not None):
                raise ValueError("initial descriptor binding mismatch")
        request = self.transition.request
        physical = self.transition.service._roots.get(request.root_id)
        if physical is None or _root(physical) != self.root:
            raise ValueError("transition root does not match loaded physical root")
        if (
            not isinstance(self.expected_root_identity, str)
            or len(self.expected_root_identity) != 64
        ):
            raise ValueError("expected root identity is required")
        if type(self.expected_generation) is not int or self.expected_generation < 1:
            raise ValueError("expected generation is required")
        if not isinstance(self.expected_writer_id, str) or not self.expected_writer_id.strip():
            raise ValueError("expected writer id is required")
        if request.expected_root_identity != self.expected_root_identity:
            raise ValueError("expected root identity does not match A request")
        if (
            request.next_generation != self.expected_generation
            or request.next_writer_id != self.expected_writer_id
        ):
            raise ValueError("expected next binding does not match A request")
        if request.expected_manifest_sha256 != self.expected_manifest_sha256:
            raise ValueError("expected manifest does not match A request")

    def preflight(self) -> Any:
        return self.transition.preflight()

    def apply(self) -> Any:
        return self.transition.apply()

    def reconcile(self) -> Any:
        return self.transition.reconcile()

    def check_handles(self, registry: WriterRegistry, *, quiescent: bool = False) -> None:
        from nexus.events.log_store import JsonlEventLogStore
        from nexus.events.transport import (
            EventWriterAdapter,
            EventWriterFactory,
            lookup_event_writer_factory,
        )
        from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
        from nexus.orchestrator.writer_quiescence import (
            RuntimeWriterAdapter,
            RuntimeWriterFactory,
            TaskStateWriterAdapter,
            TaskStateWriterFactory,
            lookup_runtime_writer_factory,
        )

        adapter = self.adapter
        if adapter.registry is not registry or adapter.root != self.root:
            raise WriterActivationError("ADAPTER_REGISTRY_OR_ROOT_MISMATCH")
        if quiescent and (adapter._active_contexts or getattr(adapter, "_active_paths", {})):
            raise WriterActivationError("ADAPTER_HAS_ACTIVE_CONTEXTS")
        if getattr(self.factory, "_adapter", None) is not adapter:
            raise WriterActivationError("ACTUAL_FACTORY_REQUIRED")
        expected_roles = (
            {"task_state"}
            if isinstance(adapter, TaskStateWriterAdapter)
            else {"runtime_receipt", "effect_journal"}
            if isinstance(adapter, RuntimeWriterAdapter)
            else {"event_log"}
        )
        actual_roles = [
            item.identity.role
            for item in registry._writers.values()
            if item.identity.root == self.root
        ]
        if set(actual_roles) != expected_roles or len(actual_roles) != len(expected_roles):
            raise WriterActivationError("ACTUAL_ADAPTER_ROLE_VECTOR_MISMATCH")
        if self.role not in expected_roles:
            raise WriterActivationError("ACTUAL_ADAPTER_ROLE_MISMATCH")
        if isinstance(adapter, TaskStateWriterAdapter):
            if (
                not isinstance(self.factory, TaskStateWriterFactory)
                or not isinstance(self.task_service, SelfHostedTaskService)
                or self.task_service._writer_factory is not self.factory
                or self.task_service.state_dir.resolve() != Path(self.root)
            ):
                raise WriterActivationError("ACTUAL_TASK_SERVICE_REQUIRED")
        elif isinstance(adapter, RuntimeWriterAdapter):
            if (
                not isinstance(self.factory, RuntimeWriterFactory)
                or lookup_runtime_writer_factory(self.root) is not self.factory
            ):
                raise WriterActivationError("ACTUAL_RUNTIME_FACTORY_REQUIRED")
        elif isinstance(adapter, EventWriterAdapter):
            if (
                not isinstance(self.factory, EventWriterFactory)
                or lookup_event_writer_factory(self.root) is not self.factory
                or not isinstance(self.event_store, JsonlEventLogStore)
                or self.event_store._writer_factory is not self.factory
                or self.event_store._owner_context is not None
            ):
                raise WriterActivationError("ACTUAL_EVENT_STORE_REQUIRED")
            self.event_store._assert_selected_paths()
            if self.event_bus is not None and (
                self.event_bus._writer_factory is not self.factory
                or self.event_bus._log_store is not self.event_store
            ):
                raise WriterActivationError("ACTUAL_EVENT_BUS_MISMATCH")

    def loaded_identity(self, role: str, registry: WriterRegistry) -> WriterIdentity:
        """Read actual reloaded objects, never a captured proposed identity."""
        self.check_handles(registry)
        adapter = self.adapter
        token = adapter.writer_generation
        if (
            adapter.binding.root != Path(self.root)
            or adapter.binding.generation != token.generation
            or adapter.writer_id != token.writer_id
        ):
            raise WriterActivationError("LOADED_ADAPTER_FIELDS_MISMATCH")
        if self.task_service is not None:
            metadata = getattr(self.task_service, "loaded_task_writer_binding", None)
            if metadata is None or (
                metadata.root != Path(self.root)
                or metadata.generation != token.generation
                or metadata.writer_id != token.writer_id
                or metadata.owner_id != adapter.binding.owner_id
                or metadata.transaction_id != adapter.binding.transaction_id
            ):
                raise WriterActivationError("LOADED_TASK_METADATA_MISMATCH")
        if self.event_store is not None and self.event_store._writer_generation != token:
            raise WriterActivationError("LOADED_EVENT_STORE_GENERATION_MISMATCH")
        if hasattr(adapter, "_role_writer_ids"):
            if adapter._role_writer_ids.get(role) != token.writer_id:
                raise WriterActivationError("LOADED_RUNTIME_ROLE_MISMATCH")
            self.factory.effect_binding()
        return WriterIdentity(
            self.root,
            role,
            registry.source_identity,
            registry.process_start_identity,
            str(threading.get_ident()),
            token.generation,
            token.writer_id,
        )

    def rebind(self, manifest: Any, registry: WriterRegistry) -> None:
        """Reload real factories under the intact cohort admission hold."""
        from nexus.events.effect_journal import EffectJournal
        from nexus.events.state_owner_manifest import StateOwnerBinding
        from nexus.events.writer_generation import EventWriterGeneration
        from nexus.orchestrator.unified_mcp_gateway import LoadedTaskWriterBinding
        from nexus.orchestrator.writer_quiescence import RuntimeEffectBinding

        self.check_handles(registry, quiescent=True)
        adapter = self.adapter
        token = EventWriterGeneration(manifest.generation, manifest.writer_id)
        adapter.binding = StateOwnerBinding(
            manifest.owner_id, Path(self.root), manifest.generation, manifest.transaction_id
        )
        adapter.writer_generation, adapter.writer_id = token, token.writer_id
        if hasattr(adapter, "_role_writer_ids"):
            adapter._role_writer_ids = {role: token.writer_id for role in adapter._role_writer_ids}
            old_effect = self.factory._effect_binding
            if old_effect is not None:
                self.factory._effect_binding = RuntimeEffectBinding(
                    EffectJournal(Path(self.root), token), old_effect.dispatch, old_effect.reconcile
                )
        if self.task_service is not None:
            source = self.transition.service._source
            self.task_service.loaded_task_writer_binding = LoadedTaskWriterBinding(
                Path(self.root),
                manifest.owner_id,
                manifest.transaction_id,
                token.generation,
                token.writer_id,
                source.source_head,
                source.source_tree,
            )
        if self.event_store is not None:
            # No producer can enter a context while the whole cohort is held.
            self.event_store._writer_generation = token
            self.event_store._enforce_generation = True
        if hasattr(adapter, "_loaded_identity"):
            adapter._loaded_identity = lambda *args: self.loaded_identity(
                args[0] if args else self.role, registry
            )


@dataclass(frozen=True, slots=True)
class ActivationCohortReceipt:
    schema: str
    cohort_id: str
    hold_epoch: int
    ordered_roots: tuple[str, ...]
    source_identity: str
    server_identity: str
    process_start_identity: str
    state: str
    drain: Mapping[str, Any]
    transitions: tuple[Mapping[str, Any], ...] = ()
    reacquisition: Mapping[str, Any] | None = None
    release_state: str = "HELD"
    prior_digest: str = ""
    receipt_sha256: str = ""
    root_contracts: tuple[Mapping[str, Any], ...] = ()
    hold_markers: tuple[Mapping[str, Any], ...] = ()
    original_drain: Mapping[str, Any] | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "cohort_id": self.cohort_id,
            "hold_epoch": self.hold_epoch,
            "ordered_roots": list(self.ordered_roots),
            "source_identity": self.source_identity,
            "server_identity": self.server_identity,
            "process_start_identity": self.process_start_identity,
            "state": self.state,
            "drain": dict(self.drain),
            "transitions": [dict(x) for x in self.transitions],
            "reacquisition": dict(self.reacquisition) if self.reacquisition else None,
            "release_state": self.release_state,
            "prior_digest": self.prior_digest,
            "root_contracts": [dict(x) for x in self.root_contracts],
            "hold_markers": [dict(x) for x in self.hold_markers],
            "original_drain": dict(self.original_drain) if self.original_drain else None,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload()
        payload["receipt_sha256"] = self.receipt_sha256 or _sha(_json(payload))
        return payload


def _state_of(value: Any) -> str:
    state = getattr(value, "state", value)
    return getattr(state, "value", state) if not isinstance(state, str) else state


class WriterActivationCohort:
    """F-owned ordered cohort coordinator.

    ``registry`` and ``hold`` are deliberately required inputs.  Supplying a
    second registry, a request-selected root vector, or a generic release
    callback is rejected by this boundary.
    """

    SCHEMA = "nexus.writer_activation_cohort.v1"
    STATES = frozenset({
        "HOLDING",
        "APPLYING",
        "PARTIAL_UNKNOWN",
        "REACQUIRING",
        "ACTIVE",
        "RELEASE_INTENT",
        "RELEASED",
    })

    def __init__(
        self,
        registry: WriterRegistry,
        hold: WriterHold,
        roots: Sequence[ActivationRoot],
        *,
        state_path: str | Path | None = None,
        initial_specs: Sequence[InitialActivationRootSpec] = (),
    ) -> None:
        if not isinstance(registry, WriterRegistry) or not isinstance(hold, WriterHold):
            raise TypeError("cohort requires the actual loaded registry and hold")
        if hold.registry is not registry:
            raise CohortConflict("hold belongs to another registry")
        if not roots or any(not isinstance(x, ActivationRoot) for x in roots):
            raise ValueError("ordered loaded roots are required")
        ordered = tuple(x.root for x in roots)
        if ordered != hold.roots or len(set(ordered)) != len(ordered):
            raise CohortConflict("root vector does not exactly match B hold")
        self.registry, self.hold, self.roots = registry, hold, tuple(roots)
        self._initial_descriptors = tuple(roots)
        self._initial_materialized: dict[str, ActivationRoot] = {}
        self._initial_factories: dict[str, Any] = {}
        self._initial_recovery_proof = None
        self._initial_recovery_successor = None
        self._initial_recovery_adopted = False
        self._pending_recovery_receipt = None
        self._initial_specs = tuple(initial_specs) or tuple(
            x.initial_spec for x in roots if x.initial_spec is not None
        )
        if initial_specs and tuple(initial_specs) != tuple(x.initial_spec for x in roots):
            raise CohortConflict("INITIAL_DESCRIPTOR_VECTOR_MISMATCH")
        if self._initial_specs and len(self._initial_specs) != len(roots):
            raise CohortConflict("INITIAL_SPEC_VECTOR_MISMATCH")
        if self._initial_specs and tuple(x.root for x in self._initial_specs) != ordered:
            raise CohortConflict("INITIAL_SPEC_ORDER_MISMATCH")
        for spec in self._initial_specs:
            expected_roles = ({"task_state"} if isinstance(spec.owner, InitialTaskOwner)
                              else {"event_log"} if isinstance(spec.owner, InitialEventOwner)
                              else {"runtime_receipt", "effect_journal"})
            selected = [item.identity for item in hold.selected if item.identity.root == spec.root]
            if (len(selected) != len(expected_roles)
                    or {item.role for item in selected} != expected_roles
                    or any(item.generation != 0 for item in selected)):
                raise CohortConflict("INITIAL_OBSERVER_VECTOR_MISMATCH")
        if any(root.adapter is not None and root.adapter.registry is not registry for root in roots):
            raise CohortConflict("ADAPTER_REGISTRY_MISMATCH")
        base = self._default_state_path()
        if state_path is not None and Path(state_path).absolute() != base:
            raise ValueError("cohort state path is fixed by the loaded root")
        allowed = (self.registry.hold_store or (Path(self.roots[0].root) / ".nexus")).resolve()
        try:
            base.relative_to(allowed)
        except ValueError as exc:
            raise ValueError("cohort state must use the source-owned state location") from exc
        self.state_path = base
        self._last: ActivationCohortReceipt | None = None
        self._mutation_lock = threading.RLock()
        self._recovering = False
        self._recovery_ready = True
        with registry._mutex:
            registry._check_hold(hold)
        self._marker_payloads = tuple(
            json.loads(_safe_read(registry._marker_path(root))) for root in hold.roots
        )
        key = (id(registry), hold.cohort_id)
        prior = _LOADED_COHORTS.get(key)
        if prior is not None and prior is not self:
            raise CohortConflict("COHORT_ALREADY_LOADED")
        _LOADED_COHORTS[key] = self

    def _default_state_path(self) -> Path:
        store = self.registry.hold_store
        base = (
            store
            if store is not None
            else Path(self.roots[0].root) / ".nexus" / "writer-quiescence"
        )
        return base / "activation-cohorts" / f"{_sha(self.hold.cohort_id.encode())}.json"

    @property
    def cohort_id(self) -> str:
        return self.hold.cohort_id

    def _contracts(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            {
                "root": root.root,
                "root_id": root.transition.request.root_id,
                "request_digest": root.transition.request.request_digest,
                "drain_receipt_hash": root.transition.request.drain_receipt_hash,
                "transaction_id": root.transition.request.transaction_id,
                "generation": root.expected_generation,
                "writer_id": root.expected_writer_id,
                "root_identity": root.expected_root_identity,
            }
            for root in self.roots
        )

    def _save(self, receipt: ActivationCohortReceipt) -> ActivationCohortReceipt:
        self._advance_pending_recovery_receipt()
        if receipt.root_contracts != self._contracts():
            raise CohortConflict("COHORT_REQUEST_VECTOR_MISMATCH")
        _safe_parents(self.state_path)
        lock_path = self.state_path.with_suffix(self.state_path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                raise CohortConflict("COHORT_LOCK_UNSAFE")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                current = self.load_durable(self.state_path)
            except FileNotFoundError:
                current = None
            expected = self._last.receipt_sha256 if self._last else ""
            if (current.receipt_sha256 if current else "") != expected:
                raise CohortConflict("COHORT_STATE_CONCURRENT_UPDATE")
            if receipt.prior_digest != expected:
                raise CohortConflict("COHORT_STATE_CAS_MISMATCH")
            return self._save_unlocked(replace(receipt, receipt_sha256=""))
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def _save_unlocked(self, receipt: ActivationCohortReceipt) -> ActivationCohortReceipt:
        payload = receipt.to_dict()
        saved = replace(receipt, receipt_sha256=payload["receipt_sha256"])
        _atomic(self.state_path, saved.to_dict())
        data = _safe_read(self.state_path)
        if data.rstrip(b"\n") != _json(saved.to_dict()):
            raise WriterActivationError("COHORT_STATE_READBACK_FAILED")
        if self._initial_recovery_adopted:
            self._pending_recovery_receipt = (self._last.receipt_sha256, saved)
            self._advance_pending_recovery_receipt()
        else:
            self._last = saved
        return saved

    def _advance_pending_recovery_receipt(self) -> None:
        with self._mutation_lock:
            pending = self._pending_recovery_receipt
            if pending is None:
                return
            predecessor, saved = pending
            self.registry.advance_recovered_hold(
                self._initial_recovery_proof,
                expected_predecessor_sha256=predecessor,
                expected_successor_sha256=saved.receipt_sha256,
            )
            self._last = saved
            self._pending_recovery_receipt = None

    def _receipt(
        self,
        state: str,
        *,
        drain: Any,
        transitions: Iterable[Any] = (),
        reacquisition: Any = None,
        release_state: str = "HELD",
        prior: str = "",
    ) -> ActivationCohortReceipt:
        return ActivationCohortReceipt(
            self.SCHEMA,
            self.cohort_id,
            self.hold.epoch,
            self.hold.roots,
            self.registry.source_identity,
            self.registry.server_identity,
            self.registry.process_start_identity,
            state,
            _receipt_dict(drain),
            tuple(_receipt_dict(x) for x in transitions),
            _receipt_dict(reacquisition) if reacquisition is not None else None,
            release_state,
            prior,
            root_contracts=self._contracts(),
            hold_markers=self._marker_payloads,
            original_drain=(self._last.original_drain if self._last else _receipt_dict(drain)),
        )

    def activate(self) -> ActivationCohortReceipt:
        with self._mutation_lock:
            return self._activate()

    def _activate(self) -> ActivationCohortReceipt:
        """Advance the same held cohort; every incomplete path retains the hold."""
        self.registry._check_process()
        self._advance_pending_recovery_receipt()
        if self._recovering and not self._recovery_ready:
            self._finish_recovery()
        if self._last is None and self.state_path.exists():
            self.status()
        if self._last is not None and self._last.state in {"ACTIVE", "RELEASED"}:
            return self.status()
        if self._last is not None and self._last.state == "RELEASE_INTENT":
            raise WriterActivationError("RELEASE_RECOVERY_REQUIRED")
        self._check_f_hold()
        prior = self._last.receipt_sha256 if self._last else ""
        try:
            try:
                if self._recovering or self._admission_advanced():
                    raise WriterActivationError("CURRENT_RECOVERY_OBSERVATION_REQUIRED")
                drain = self.registry.load_finalized(self.hold.cohort_id)
            except Exception:
                drain = (
                    self._current_drain()
                    if self._recovering or self._admission_advanced()
                    else self.registry.persist_finalized(self.hold)
                )
            if drain.drain_state != DRAINED:
                raise WriterActivationError("COLLECTOR_NOT_DRAINED")
            existing_transitions = list(self._last.transitions) if self._last else []
            current = self._save(
                self._receipt(
                    "HOLDING" if self._last is None else self._last.state,
                    drain=drain,
                    transitions=existing_transitions,
                    prior=prior,
                )
            )
            transitions: list[Any] = list(current.transitions)
            for root in self.roots:
                current = self._save(
                    self._receipt(
                        "APPLYING",
                        drain=drain,
                        transitions=transitions,
                        prior=current.receipt_sha256,
                    )
                )
                previous = self._previous_transition(root)
                if root.transition.has_intent():
                    # A has already durably committed this exact request;
                    # reconcile its intent/readback instead of reapplying it.
                    result = root.reconcile()
                else:
                    ready = root.preflight()
                    if _state_of(ready) not in {"PREFLIGHT_READY", "COMMITTED", "RECONCILED"}:
                        raise WriterActivationError(f"PREFLIGHT_DENIED:{_state_of(ready)}")
                    result = root.apply()
                from nexus.contracts.state_owner_transition import TransitionReceipt

                if not isinstance(result, TransitionReceipt):
                    raise WriterActivationError("TYPED_A_RECEIPT_REQUIRED")
                if (
                    result.transaction_id != root.transition.request.transaction_id
                    or result.root_id != root.transition.request.root_id
                ):
                    raise WriterActivationError("A_RECEIPT_IDENTITY_MISMATCH")
                state = _state_of(result)
                if state not in {"COMMITTED", "RECONCILED"}:
                    raise WriterActivationError(f"ROOT_TRANSITION_{state}")
                result.require_claim_fields()
                manifest = self._physical(root)
                if result.observed_after_manifest_sha256 != manifest.manifest_sha256:
                    raise WriterActivationError("A_RECEIPT_MANIFEST_MISMATCH")
                prior_index = next(
                    (
                        index
                        for index, item in enumerate(transitions)
                        if isinstance(item, Mapping)
                        and item.get("root_id") == root.transition.request.root_id
                    ),
                    None,
                )
                if prior_index is None:
                    transitions.append(result)
                else:
                    transitions[prior_index] = result
                current = self._save(
                    self._receipt(
                        "APPLYING",
                        drain=drain,
                        transitions=transitions,
                        prior=current.receipt_sha256,
                    )
                )
            if self._initial_specs:
                self._materialize_initial_roots()
            self._prepare_reacquisition()
            reacquired = (
                self._observe_recovery()
                if self._recovering or self._admission_advanced()
                else self.registry.observe_reacquisition(self.hold)
            )
            current = self._save(
                self._receipt(
                    "REACQUIRING",
                    drain=drain,
                    transitions=transitions,
                    reacquisition=reacquired,
                    prior=current.receipt_sha256,
                )
            )
            if reacquired.state != "REACQUIRED":
                raise WriterActivationError("REACQUISITION_UNKNOWN")
            self._commit_reacquisition(reacquired)
            return self._save(
                self._receipt(
                    "ACTIVE",
                    drain=drain,
                    transitions=transitions,
                    reacquisition=reacquired,
                    prior=current.receipt_sha256,
                )
            )
        except Exception as exc:
            transitions = locals().get("transitions", [])
            drain = locals().get("drain", {})
            try:
                return self._save(
                    self._receipt(
                        "PARTIAL_UNKNOWN",
                        drain=drain,
                        transitions=transitions,
                        prior=self._last.receipt_sha256 if self._last else prior,
                    )
                )
            except Exception:
                raise WriterActivationError(str(exc)) from exc

    def _materialize_initial_roots(self) -> None:
        """Construct the real C/D/E writers under the unchanged B hold."""
        from nexus.events.effect_journal import EffectJournal, EffectDispatchPort, EffectReconcilePort
        from nexus.events.log_store import JsonlEventLogStore
        from nexus.events.state_owner_manifest import StateOwnerBinding, read_manifest
        from nexus.events.transport import EventWriterAdapter, EventWriterFactory, register_event_writer_factory
        from nexus.events.writer_generation import EventWriterGeneration, read_generation
        from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
        from nexus.orchestrator.writer_quiescence import (
            RuntimeWriterAdapter, RuntimeWriterFactory, TaskStateWriterAdapter,
            TaskStateWriterFactory, register_runtime_writer_factory,
        )

        actual: list[ActivationRoot] = []
        for spec in self._initial_specs:
            cached = self._initial_materialized.get(spec.root)
            if cached is not None:
                cached.check_handles(self.registry, quiescent=True)
                actual.append(cached)
                continue
            manifest = read_manifest(Path(spec.root))
            token = read_generation(Path(spec.root))
            req = spec.transition.request
            if (manifest is None or manifest.state != "COMMITTED" or token is None
                    or token.generation != spec.expected_generation
                    or token.writer_id != spec.expected_writer_id
                    or manifest.root_identity != spec.expected_root_identity
                    or manifest.transaction_id != req.transaction_id):
                raise WriterActivationError("INITIAL_COMMITTED_READBACK_FAILED")
            attachment = self.registry.issue_initial_attachment(
                self.hold, root=spec.root, generation=token.generation,
                writer_id=token.writer_id, manifest_sha256=manifest.manifest_sha256,
                recovery_proof=self._initial_recovery_proof,
            )
            binding = StateOwnerBinding(req.expected_owner_id, Path(spec.root), token.generation, req.transaction_id)
            factory = task_service = event_store = event_bus = None
            if isinstance(spec.owner, InitialTaskOwner):
                service = spec.owner.service
                if not isinstance(service, SelfHostedTaskService):
                    raise TypeError("initial task owner requires SelfHostedTaskService")
                adapter = TaskStateWriterAdapter(
                    self.registry, binding=binding, writer_generation=token, root=spec.root,
                    writer_id=token.writer_id, path_for_task=service._state_path,
                    initial_attachment=attachment,
                )
                factory = TaskStateWriterFactory(adapter)
                service._writer_factory = factory
                task_service = service
            elif isinstance(spec.owner, InitialRuntimeOwner):
                if not isinstance(spec.owner.effect_dispatch, EffectDispatchPort) or not isinstance(spec.owner.effect_reconcile, EffectReconcilePort):
                    raise TypeError("initial runtime owner requires typed effect ports")
                factory = self._initial_factories.get(spec.root)
                if factory is None:
                    journal = EffectJournal(Path(spec.root), token)
                    factory = RuntimeWriterFactory(
                        RuntimeWriterAdapter(self.registry, binding=binding, writer_generation=token,
                            root=spec.root, writer_id=token.writer_id, initial_attachment=attachment),
                        effect_journal=journal, effect_dispatch=spec.owner.effect_dispatch,
                        effect_reconcile=spec.owner.effect_reconcile,
                    )
                    self._initial_factories[spec.root] = factory
                register_runtime_writer_factory(factory, initial_attachment=attachment)
            else:
                if not isinstance(spec.owner.event_store, JsonlEventLogStore):
                    raise TypeError("initial event owner requires JsonlEventLogStore")
                adapter = EventWriterAdapter(self.registry, binding=binding, writer_generation=token,
                    root=spec.root, writer_id=token.writer_id, initial_attachment=attachment)
                factory = self._initial_factories.get(spec.root)
                if factory is None:
                    factory = EventWriterFactory(adapter)
                    self._initial_factories[spec.root] = factory
                register_event_writer_factory(factory)
                event_store = spec.owner.event_store
                event_store.configure(Path(spec.root), writer_generation=token,
                    enforce_generation=True, writer_factory=factory, initial_handle=attachment)
                event_bus = spec.owner.event_bus
                if event_bus is not None:
                    event_bus.configure(Path(spec.root), writer_generation=token,
                        enforce_generation=True, writer_factory=factory, initial_handle=attachment)
            adapter = factory._adapter
            actual.append(ActivationRoot(spec.root, spec.role, spec.transition, adapter,
                spec.expected_root_identity, spec.expected_generation, spec.expected_writer_id,
                req.expected_manifest_sha256, factory=factory, task_service=task_service,
                event_store=event_store, event_bus=event_bus))
            self._initial_materialized[spec.root] = actual[-1]
        for root in actual:
            root.check_handles(self.registry, quiescent=True)
        self.roots = tuple(actual)

    def _check_f_hold(self, *, allow_missing: bool = False, require_absent: bool = False) -> None:
        """Validate frozen B markers separately from reloaded admission fields."""
        self.registry._check_process()
        if self.hold.registry is not self.registry:
            raise CohortConflict("COHORT_FOREIGN_HOLD")
        selected = tuple(
            item
            for item in self.registry._writers.values()
            if item.identity.root in self.hold.roots
        )
        if {id(item) for item in selected} != {id(item) for item in self.hold.selected}:
            raise CohortConflict("COHORT_REGISTERED_VECTOR_CHANGED")
        if not self.hold.released and any(
            self.registry._held_roots.get(root) is not self.hold for root in self.hold.roots
        ):
            raise CohortConflict("COHORT_ADMISSION_HOLD_MISSING")
        seen_present = False
        for root, payload in zip(self.hold.roots, self._marker_payloads):
            marker = self.registry._marker_path(root)
            try:
                actual = _safe_read(marker)
            except FileNotFoundError:
                if not allow_missing or seen_present:
                    raise CohortConflict("COHORT_HOLD_MARKER_MISSING")
                continue
            if require_absent or (self._last is not None and self._last.state == "RELEASED"):
                raise CohortConflict("RELEASED_HOLD_MARKER_PRESENT")
            seen_present = True
            if actual != _json(payload):
                raise CohortConflict("COHORT_HOLD_MARKER_CHANGED")

    def _admission_advanced(self) -> bool:
        return any(
            item.identity.generation == root.expected_generation
            and item.identity.writer_id == root.expected_writer_id
            for root in self.roots
            for item in self.hold.selected
            if item.identity.root == root.root
        )

    def _current_drain(self):
        from nexus.orchestrator.writer_quiescence import WriterQuiescenceReceipt

        self._check_f_hold()
        observations, leases, unknowns = [], [], []
        for root in self.hold.roots:
            rows, issues = self.registry._durable_leases(root)
            leases.extend(rows)
            unknowns.extend(issues)
        for item in self.hold.selected:
            observation, issues = self.registry._observation(item)
            observations.append(observation)
            unknowns.extend(issues)
        if self.registry._leases_for(self.hold.roots):
            unknowns.append("leases:active")
        self._check_f_hold()
        return WriterQuiescenceReceipt(
            "writer-quiescence/v1",
            self.cohort_id,
            self.hold.epoch,
            self.registry.source_identity,
            self.registry.server_identity,
            self.registry.process_start_identity,
            self.hold.roots,
            tuple(observations),
            tuple(leases),
            tuple(unknowns),
            DRAINED if not unknowns else "UNKNOWN",
        )

    def _observe_recovery(self, *, allow_missing: bool = False):
        from nexus.orchestrator.writer_quiescence import WriterReacquisitionObservation

        observations = []
        self._check_f_hold(allow_missing=allow_missing)
        old = self._marker_payloads[0]["selected_writers"]
        for root in self.roots:
            manifest = self._physical(root, activation_transaction=not allow_missing)
            for raw in old:
                previous = WriterIdentity(**raw)
                if previous.root != root.root:
                    continue
                loaded = root.loaded_identity(previous.role, self.registry)
                if loaded.generation <= previous.generation:
                    raise WriterActivationError("RECOVERY_GENERATION_NOT_ADVANCED")
                observations.append(
                    WriterReacquisitionObservation(
                        previous,
                        loaded,
                        manifest.manifest_sha256,
                        manifest.generation,
                        manifest.writer_id,
                        "MATCHED",
                    )
                )
        return WriterReacquisitionReceipt(
            self.cohort_id, self.hold.epoch, self.hold.roots, tuple(observations), ()
        )

    @classmethod
    def recover(cls, registry: WriterRegistry, roots: Sequence[ActivationRoot], *, cohort_id: str):
        """Resume an exact durable cohort only after the prior OS process died."""
        if not isinstance(registry, WriterRegistry) or not roots:
            raise TypeError("actual loaded registry and roots required")
        existing = _LOADED_COHORTS.get((id(registry), cohort_id))
        if existing is not None:
            same_roots = any(len(roots) == len(saved) and all(a is b for a, b in zip(roots, saved))
                             for saved in (existing.roots, existing._initial_descriptors))
            if not same_roots or not existing._recovering:
                raise CohortConflict("RECOVERY_LOADED_OBJECT_MISMATCH")
            existing._finish_recovery()
            return existing
        ordered = tuple(root.root for root in roots)
        base = registry.hold_store or (Path(ordered[0]) / ".nexus" / "writer-quiescence")
        path = base / "activation-cohorts" / f"{_sha(cohort_id.encode())}.json"
        durable = cls.load_durable(path)
        if (
            durable.cohort_id != cohort_id
            or durable.ordered_roots != ordered
            or durable.source_identity != registry.source_identity
        ):
            raise CohortConflict("RECOVERY_COHORT_IDENTITY_MISMATCH")
        _prove_process_absent(durable.process_start_identity)
        if len(durable.hold_markers) != len(ordered):
            raise CohortConflict("RECOVERY_MARKER_VECTOR_MISSING")
        old_vector = durable.hold_markers[0]["selected_writers"]
        expected_roles = {(row["root"], row["role"]) for row in old_vector}
        selected = tuple(
            sorted(
                (item for item in registry._writers.values() if item.identity.root in ordered),
                key=lambda item: (ordered.index(item.identity.root), item.identity.key()),
            )
        )
        if {(item.identity.root, item.identity.role) for item in selected} != expected_roles:
            raise CohortConflict("RECOVERY_WRITER_VECTOR_MISMATCH")
        if len(selected) != len(expected_roles):
            raise CohortConflict("RECOVERY_WRITER_COLLISION")
        if registry._held_roots or registry._leases_for(ordered):
            raise CohortConflict("RECOVERY_REGISTRY_ALREADY_ACTIVE")
        # Physical markers are checked before adopting any in-process hold.
        present_seen = False
        for root, payload in zip(ordered, durable.hold_markers):
            if (
                payload.get("root") != root
                or payload.get("cohort_id") != cohort_id
                or tuple(payload.get("ordered_roots", ())) != ordered
                or payload.get("selected_writers") != old_vector
            ):
                raise CohortConflict("RECOVERY_MARKER_CONTRACT_MISMATCH")
            try:
                raw = _safe_read(registry._marker_path(root))
            except FileNotFoundError:
                if durable.state not in {"RELEASE_INTENT", "RELEASED"} or present_seen:
                    raise CohortConflict("RECOVERY_HOLD_MARKER_MISSING")
            else:
                if durable.state == "RELEASED":
                    raise CohortConflict("RELEASED_HOLD_MARKER_PRESENT")
                present_seen = True
                if raw != _json(payload):
                    raise CohortConflict("RECOVERY_HOLD_MARKER_CHANGED")
        _qualified_terminal_records(registry, durable)

        hold = WriterHold(registry, cohort_id, ordered, durable.hold_epoch, selected)
        # Construct without requiring absent release-prefix markers to reappear.
        obj = cls.__new__(cls)
        obj.registry, obj.hold, obj.roots = registry, hold, tuple(roots)
        obj._initial_descriptors = tuple(roots)
        obj._initial_specs = tuple(x.initial_spec for x in roots if x.initial_spec is not None)
        obj._initial_materialized = {}
        obj._initial_factories = {}
        obj._initial_recovery_proof = (registry.prepare_hold_recovery(
            cohort_id=cohort_id, ordered_roots=ordered,
            expected_receipt_sha256=durable.receipt_sha256,
        ) if obj._initial_specs else None)
        obj._initial_recovery_successor = None
        obj._initial_recovery_adopted = False
        obj._pending_recovery_receipt = None
        obj.state_path, obj._last = path, durable
        obj._mutation_lock, obj._recovering = threading.RLock(), True
        obj._recovery_ready = False
        obj._marker_payloads = tuple(durable.hold_markers)
        if obj._contracts() != durable.root_contracts:
            raise CohortConflict("RECOVERY_REQUEST_VECTOR_MISMATCH")
        if obj._initial_recovery_proof is None:
            registry._held_roots.update({root: hold for root in ordered})
            registry._epoch = max(registry._epoch, hold.epoch)
            for item in selected:
                item.acknowledged_epoch = hold.epoch
        _LOADED_COHORTS[(id(registry), cohort_id)] = obj
        # Preserve historical drain/markers and record the new observed process
        # with a prior-digest CAS. No filesystem generation is rolled backward.
        obj._save(
            replace(
                durable,
                server_identity=registry.server_identity,
                process_start_identity=registry.process_start_identity,
                prior_digest=durable.receipt_sha256,
                receipt_sha256="",
            )
        )
        obj._initial_recovery_successor = obj._last.receipt_sha256
        obj._finish_recovery()
        return obj

    def _finish_recovery(self) -> None:
        """Retry on the same registered object after an adoption CAS succeeds."""
        with self._mutation_lock:
            if self._recovery_ready:
                return
            self._advance_pending_recovery_receipt()
            current = self.load_durable(self.state_path)
            if (
                current.process_start_identity != self.registry.process_start_identity
                or current.receipt_sha256 != self._last.receipt_sha256
            ):
                raise CohortConflict("RECOVERY_ADOPTION_DRIFT")
            if self._initial_recovery_proof is not None:
                self.hold = self.registry.adopt_recovered_hold(
                    self._initial_recovery_proof,
                    expected_successor_sha256=self._initial_recovery_successor or current.receipt_sha256,
                )
                self._initial_recovery_adopted = True
            pins = _qualified_terminal_records(self.registry, current)
            if pins:
                reconcile_history = getattr(self.registry, "reconcile_terminal_history", None)
                if reconcile_history is None:
                    raise CohortConflict("TERMINAL_HISTORY_RECONCILIATION_REQUIRED")
                reconcile_history(self)
            if current.state in {"ACTIVE", "RELEASE_INTENT", "RELEASED"}:
                if self._initial_specs:
                    self._materialize_initial_roots()
                missing = current.state != "ACTIVE"
                self._prepare_reacquisition(allow_missing=missing)
                self._commit_reacquisition(
                    self._observe_recovery(allow_missing=missing), allow_missing=missing
                )
                self._verify_active_physical(allow_missing=missing)
                if current.state == "RELEASED":
                    with self.registry._mutex:
                        for root in self.hold.roots:
                            self.registry._held_roots.pop(root, None)
                        self.hold.released = True
            self._recovery_ready = True

    def _previous_transition(self, root: ActivationRoot) -> Mapping[str, Any] | None:
        if self._last is None:
            return None
        root_id = root.transition.request.root_id
        for item in self._last.transitions:
            if isinstance(item, Mapping) and item.get("root_id") == root_id:
                return item
        return None

    def _physical(self, root: ActivationRoot, *, activation_transaction: bool = True):
        from nexus.events.state_owner_manifest import read_manifest
        from nexus.events.writer_generation import event_store_lock, read_generation

        with event_store_lock(Path(root.root)):
            manifest, token = read_manifest(Path(root.root)), read_generation(Path(root.root))
            req = root.transition.request
            if (
                manifest is None
                or manifest.state != "COMMITTED"
                or token is None
                or manifest.root_identity != root.expected_root_identity
                or manifest.owner_id != req.expected_owner_id
                or (activation_transaction and manifest.transaction_id != req.transaction_id)
                or token.generation != root.expected_generation
                or token.writer_id != root.expected_writer_id
                or manifest.generation != token.generation
                or manifest.writer_id != token.writer_id
            ):
                raise WriterActivationError("COHORT_PHYSICAL_BINDING_MISMATCH")
            roles = {item.role for item in manifest.files}
            selected = [item for item in self.hold.selected if item.identity.root == root.root]
            if not selected or (
                activation_transaction and any(item.identity.role not in roles for item in selected)
            ):
                raise WriterActivationError("COHORT_PHYSICAL_ROLE_MISSING")
            return manifest

    def _prepare_reacquisition(self, *, allow_missing: bool = False) -> None:
        with self.registry._mutex:
            self._check_f_hold(allow_missing=allow_missing)
            if self.registry._leases_for(self.hold.roots):
                raise WriterActivationError("REACQUISITION_HAS_LEASES")
        physical = [
            (root, self._physical(root, activation_transaction=not allow_missing))
            for root in self.roots
        ]
        for root, _ in physical:
            root.check_handles(self.registry, quiescent=True)
        for root, manifest in physical:
            root.rebind(manifest, self.registry)
            for item in self.hold.selected:
                if item.identity.root == root.root:
                    role = item.identity.role
                    item.loaded_identity = lambda root=root, role=role: root.loaded_identity(
                        role, self.registry
                    )

    def _commit_reacquisition(
        self, receipt: WriterReacquisitionReceipt, *, allow_missing: bool = False
    ) -> None:
        """Update the existing B registration objects only after physical match."""
        with self.registry._mutex:
            self._check_f_hold(allow_missing=allow_missing)
            updates: list[tuple[Any, Any, WriterIdentity]] = []
            old_keys: set[tuple[str, str, str]] = set()
            new_keys: set[tuple[str, str, str]] = set()
            for observation in receipt.observations:
                if observation.state != "MATCHED" or observation.loaded_identity is None:
                    raise WriterActivationError("REACQUISITION_NOT_MATCHED")
                old = observation.previous_identity
                item = next(
                    (
                        candidate
                        for candidate in self.hold.selected
                        if candidate.identity.root == old.root
                        and candidate.identity.role == old.role
                    ),
                    None,
                )
                if item is None or (
                    not self._recovering and item.identity not in (old, observation.loaded_identity)
                ):
                    raise WriterActivationError("REACQUISITION_REGISTRATION_DRIFT")
                loaded = observation.loaded_identity
                if (
                    loaded.root != old.root
                    or loaded.role != old.role
                    or loaded.source_identity != old.source_identity
                ):
                    raise WriterActivationError("REACQUISITION_IDENTITY_MISMATCH")
                if old.key() in old_keys or loaded.key() in new_keys:
                    raise WriterActivationError("REACQUISITION_DUPLICATE")
                existing = self.registry._writers.get(loaded.key())
                if existing is not None and existing is not item:
                    raise WriterActivationError("REACQUISITION_KEY_COLLISION")
                old_keys.add(old.key())
                new_keys.add(loaded.key())
                updates.append((item, item.identity, loaded))
            if {id(item) for item, _, _ in updates} != {id(item) for item in self.hold.selected}:
                raise WriterActivationError("REACQUISITION_INCOMPLETE_VECTOR")
            if self.registry._leases_for(self.hold.roots):
                raise WriterActivationError("REACQUISITION_HAS_LEASES")
            for item, _, loaded in updates:
                if item.loaded_identity is None or item.loaded_identity() != loaded:
                    raise WriterActivationError("REACQUISITION_LOADED_DRIFT")
            # No registry mutation occurs until the complete vector is known
            # to be valid.  A partial in-memory identity update is unsafe.
            for item, old, loaded in updates:
                self.registry._writers.pop(old.key())
                item.identity = loaded
                self.registry._writers[loaded.key()] = item
            self._check_f_hold(allow_missing=allow_missing)
            if self._initial_recovery_proof is not None:
                self.registry.confirm_recovered_reacquisition(self._initial_recovery_proof, receipt)

    def _verify_active_physical(self, *, allow_missing: bool = False) -> None:
        """Recheck new physical bindings before removing any hold marker."""
        from nexus.events.state_owner_manifest import COMMITTED, read_manifest
        from nexus.events.writer_generation import event_store_lock, read_generation

        with self.registry._mutex:
            self._check_f_hold(allow_missing=allow_missing)
            selected = tuple(self.hold.selected)
        for item in selected:
            root = Path(item.identity.root)
            _, unresolved = self.registry._durable_leases(str(root))
            if any(
                issue.removeprefix("lease:unresolved:") not in self.registry._leases
                for issue in unresolved
            ):
                raise WriterActivationError("ACTIVE_UNRESOLVED_LEASES")
            if not (root / ".nexus/events/event_log.lock").is_file():
                raise WriterActivationError("ACTIVE_PHYSICAL_GUARD_MISSING")
            with event_store_lock(root):
                manifest = read_manifest(root)
                generation = read_generation(root)
                if (
                    manifest is None
                    or manifest.state != COMMITTED
                    or manifest.root_identity != _sha(str(root).encode())
                    or manifest.owner_id
                    != next(
                        entry.transition.request.expected_owner_id
                        for entry in self.roots
                        if entry.root == str(root)
                    )
                    or generation is None
                    or generation.generation != item.identity.generation
                    or generation.writer_id != item.identity.writer_id
                ):
                    raise WriterActivationError("ACTIVE_PHYSICAL_BINDING_MISMATCH")
                loaded = item.loaded_identity() if item.loaded_identity else None
                if loaded != item.identity:
                    raise WriterActivationError("ACTIVE_LOADED_IDENTITY_MISMATCH")

    def release(self, active: ActivationCohortReceipt | None = None) -> ActivationCohortReceipt:
        with self._mutation_lock:
            return self._release(active)

    def _release(self, active: ActivationCohortReceipt | None = None) -> ActivationCohortReceipt:
        """Release only a durably read-back ACTIVE cohort through F ownership."""
        active = active or self._last
        if active is None or active.state != "ACTIVE" or active.cohort_id != self.cohort_id:
            raise WriterActivationError("ACTIVE_RECEIPT_REQUIRED")
        current = self.status()
        if active.to_dict() != current.to_dict():
            raise WriterActivationError("ACTIVE_RECEIPT_STALE_OR_FORGED")
        self.registry._check_process()
        with self.registry._mutex:
            self._check_f_hold()
            if self.registry._leases_for(self.hold.roots):
                raise WriterAdmissionDenied("ACTIVE_RELEASE_HAS_LEASES")
        self._verify_active_physical()
        intent = self._save(
            replace(
                active,
                state="RELEASE_INTENT",
                release_state="RELEASE_PENDING",
                prior_digest=active.receipt_sha256,
                receipt_sha256="",
            )
        )
        try:
            with self.registry._mutex:
                self._check_f_hold()
                for root in self.hold.roots:
                    marker = self.registry._marker_path(root)
                    raw = _safe_read(marker)
                    expected = _json(self._marker_payloads[self.hold.roots.index(root)])
                    if raw != expected:
                        raise WriterActivationError("HOLD_MARKER_CHANGED")
                    marker.unlink()
                    dfd = os.open(marker.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    try:
                        os.fsync(dfd)
                    finally:
                        os.close(dfd)
            released = self._save(
                replace(
                    intent,
                    state="RELEASED",
                    release_state="RELEASED",
                    prior_digest=intent.receipt_sha256,
                    receipt_sha256="",
                )
            )
            self._finish_release_admission()
            return released
        except Exception:
            # Preserve the latest durable release phase and keep admission
            # held until its exact readback/proof advancement succeeds.
            raise

    @classmethod
    def load_durable(cls, path: str | Path) -> ActivationCohortReceipt:
        """Read durable evidence without treating it as current loaded truth."""

        def closed_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise WriterActivationError("COHORT_DUPLICATE_JSON_KEY")
                result[key] = value
            return result

        raw = json.loads(_safe_read(Path(path)), object_pairs_hook=closed_pairs)
        fields = {
            "schema",
            "cohort_id",
            "hold_epoch",
            "ordered_roots",
            "source_identity",
            "server_identity",
            "process_start_identity",
            "state",
            "drain",
            "transitions",
            "reacquisition",
            "release_state",
            "prior_digest",
            "receipt_sha256",
            "root_contracts",
            "hold_markers",
            "original_drain",
        }
        if (
            not isinstance(raw, Mapping)
            or set(raw) != fields
            or raw.get("schema") != cls.SCHEMA
            or raw.get("state") not in cls.STATES
            or type(raw.get("hold_epoch")) is not int
            or raw["hold_epoch"] < 1
            or raw.get("release_state") not in {"HELD", "RELEASE_PENDING", "RELEASED"}
        ):
            raise WriterActivationError("COHORT_STATE_MALFORMED")
        for key in ("cohort_id", "source_identity", "server_identity", "process_start_identity"):
            if not isinstance(raw[key], str) or not raw[key]:
                raise WriterActivationError("COHORT_IDENTITY_MALFORMED")
        roots = raw["ordered_roots"]
        if (
            not isinstance(roots, list)
            or not roots
            or len(set(roots)) != len(roots)
            or any(not isinstance(root, str) or not Path(root).is_absolute() for root in roots)
            or not isinstance(raw["root_contracts"], list)
            or len(raw["root_contracts"]) != len(roots)
            or not isinstance(raw["drain"], dict)
            or not isinstance(raw["transitions"], list)
        ):
            raise WriterActivationError("COHORT_VECTOR_MALFORMED")
        if not isinstance(raw["hold_markers"], list) or len(raw["hold_markers"]) != len(roots):
            raise WriterActivationError("COHORT_MARKER_VECTOR_MALFORMED")
        contracts = raw["root_contracts"]
        for root, contract, marker in zip(roots, contracts, raw["hold_markers"]):
            if (
                not isinstance(contract, dict)
                or set(contract)
                != {
                    "root",
                    "root_id",
                    "request_digest",
                    "drain_receipt_hash",
                    "transaction_id",
                    "generation",
                    "writer_id",
                    "root_identity",
                }
                or contract["root"] != root
                or type(contract["generation"]) is not int
                or contract["generation"] < 1
                or not isinstance(marker, dict)
                or marker.get("root") != root
                or marker.get("cohort_id") != raw["cohort_id"]
                or marker.get("hold_epoch") != raw["hold_epoch"]
                or marker.get("ordered_roots") != roots
            ):
                raise WriterActivationError("COHORT_ROOT_CONTRACT_MALFORMED")
            for key in ("request_digest", "root_identity", "drain_receipt_hash"):
                if not isinstance(contract[key], str) or not re.fullmatch(
                    r"[0-9a-f]{64}", contract[key]
                ):
                    raise WriterActivationError("COHORT_ROOT_HASH_MALFORMED")
        if raw["state"] in {"ACTIVE", "RELEASE_INTENT", "RELEASED"}:
            reacquisition = raw["reacquisition"]
            if (
                len(raw["transitions"]) != len(roots)
                or not isinstance(reacquisition, dict)
                or not isinstance(reacquisition.get("payload"), dict)
                or reacquisition["payload"].get("state") != "REACQUIRED"
            ):
                raise WriterActivationError("COHORT_ACTIVE_EVIDENCE_MISSING")
            payload = dict(reacquisition["payload"])
            if _sha(_json(payload)) != reacquisition.get("bytes_sha256"):
                raise WriterActivationError("COHORT_REACQUISITION_BYTES_MISMATCH")
            inner = payload.pop("receipt_sha256", None)
            if (
                inner != _sha(_json(payload))
                or payload.get("cohort_id") != raw["cohort_id"]
                or payload.get("hold_epoch") != raw["hold_epoch"]
                or payload.get("ordered_roots") != roots
                or payload.get("unknowns")
            ):
                raise WriterActivationError("COHORT_REACQUISITION_CONTRACT_MISMATCH")
            for contract, transition in zip(contracts, raw["transitions"]):
                unsigned = dict(transition)
                inner = unsigned.pop("receipt_digest", None)
                if (
                    inner != _sha(_json(unsigned))
                    or transition.get("state") not in {"COMMITTED", "RECONCILED"}
                    or transition.get("root_id") != contract["root_id"]
                    or transition.get("transaction_id") != contract["transaction_id"]
                    or transition.get("next_generation") != contract["generation"]
                    or transition.get("next_writer_id") != contract["writer_id"]
                    or transition.get("expected_root_identity") != contract["root_identity"]
                ):
                    raise WriterActivationError("COHORT_TRANSITION_CONTRACT_MISMATCH")
        expected = dict(raw)
        digest = expected.pop("receipt_sha256")
        if not isinstance(digest, str) or digest != _sha(_json(expected)):
            raise WriterActivationError("COHORT_STATE_TAMPERED")
        return ActivationCohortReceipt(
            raw["schema"],
            raw["cohort_id"],
            raw["hold_epoch"],
            tuple(raw["ordered_roots"]),
            raw["source_identity"],
            raw["server_identity"],
            raw["process_start_identity"],
            raw["state"],
            raw["drain"],
            tuple(raw.get("transitions", ())),
            raw.get("reacquisition"),
            raw.get("release_state", "HELD"),
            raw.get("prior_digest", ""),
            digest,
            tuple(raw["root_contracts"]),
            tuple(raw["hold_markers"]),
            raw["original_drain"],
        )

    def status(self) -> ActivationCohortReceipt:
        """Return current same-process evidence, or fail closed on drift."""
        self._advance_pending_recovery_receipt()
        receipt = self.load_durable(self.state_path)
        if self._last is not None and receipt.receipt_sha256 != self._last.receipt_sha256:
            raise CohortConflict("COHORT_DURABLE_STATE_CHANGED")
        if receipt.cohort_id != self.cohort_id or receipt.ordered_roots != self.hold.roots:
            raise CohortConflict("COHORT_VECTOR_MISMATCH")
        if (
            receipt.root_contracts != self._contracts()
            or receipt.source_identity != self.registry.source_identity
            or receipt.server_identity != self.registry.server_identity
            or receipt.process_start_identity != self.registry.process_start_identity
            or receipt.hold_epoch != self.hold.epoch
        ):
            raise CohortConflict("COHORT_LOADED_IDENTITY_MISMATCH")
        self.registry._check_process()
        self._check_f_hold(
            allow_missing=receipt.state in {"RELEASED", "RELEASE_INTENT"},
            require_absent=receipt.state == "RELEASED",
        )
        if receipt.state in {"ACTIVE", "RELEASE_INTENT", "RELEASED"}:
            self._verify_active_physical(allow_missing=receipt.state != "ACTIVE")
        self._last = receipt
        return receipt

    def reconcile(self) -> ActivationCohortReceipt:
        """Read-only reconciliation of this exact held cohort."""
        current = self.status()
        if current.state == "RELEASED":
            return current
        if current.state == "ACTIVE":
            self._verify_active_physical()
            return current
        self._check_f_hold(allow_missing=current.state == "RELEASE_INTENT")
        return current

    def resume_activation(self) -> ActivationCohortReceipt:
        """Source-owner mutation entrypoint for the same held cohort."""
        return self.activate()

    def resume_release(self) -> ActivationCohortReceipt:
        with self._mutation_lock:
            return self._resume_release()

    def _resume_release(self) -> ActivationCohortReceipt:
        """Complete an existing release intent after a lost acknowledgement."""
        current = self.status()
        if current.state == "RELEASED":
            self._finish_release_admission()
            return current
        if current.state != "RELEASE_INTENT":
            raise WriterActivationError("RELEASE_INTENT_REQUIRED")
        self.registry._check_process()
        self._verify_active_physical(allow_missing=True)
        with self.registry._mutex:
            self._check_f_hold(allow_missing=True)
            if self.registry._leases_for(self.hold.roots):
                raise WriterAdmissionDenied("RELEASE_RECOVERY_HAS_LEASES")
            for root in self.hold.roots:
                marker = self.registry._marker_path(root)
                if not marker.exists():
                    continue
                if _safe_read(marker) != _json(self._marker_payloads[self.hold.roots.index(root)]):
                    raise WriterActivationError("HOLD_MARKER_CHANGED")
            for root in self.hold.roots:
                marker = self.registry._marker_path(root)
                if marker.exists():
                    marker.unlink()
                    dfd = os.open(marker.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    try:
                        os.fsync(dfd)
                    finally:
                        os.close(dfd)
        released = self._save(
            replace(
                current,
                state="RELEASED",
                release_state="RELEASED",
                prior_digest=current.receipt_sha256,
                receipt_sha256="",
            )
        )

        self._finish_release_admission()
        return released

    def reconcile_read_only(self) -> ActivationCohortReceipt:
        """Explicit name for the non-mutating operational bridge."""
        return self.reconcile()

    def _finish_release_admission(self) -> None:
        """Drop admission only after the complete RELEASED receipt is durable."""
        if self._last is None or self._last.state != "RELEASED":
            raise WriterActivationError("RELEASED_RECEIPT_REQUIRED")
        with self.registry._mutex:
            self._check_f_hold(allow_missing=True, require_absent=True)
            if self.hold.released:
                return
            if self.registry._leases_for(self.hold.roots):
                raise WriterActivationError("RELEASE_HAS_LEASES")
            for root in self.hold.roots:
                self.registry._held_roots.pop(root)
            self.hold.released = True


def _prove_process_absent(identity: str) -> None:
    match = re.fullmatch(r"pid:([0-9]+):start:(.+)", identity)
    if match is None:
        raise CohortConflict("PREVIOUS_PROCESS_IDENTITY_UNKNOWN")
    pid = int(match.group(1))
    try:
        observed = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            check=False,
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CohortConflict("PREVIOUS_PROCESS_ABSENCE_UNKNOWN") from exc
    if observed.returncode not in (0, 1) or observed.stdout.strip():
        raise CohortConflict("PREVIOUS_PROCESS_STILL_EXISTS_OR_UNKNOWN")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    except OSError as exc:
        raise CohortConflict("PREVIOUS_PROCESS_ABSENCE_UNKNOWN") from exc
    raise CohortConflict("PREVIOUS_PROCESS_STILL_EXISTS")


def _qualified_terminal_records(registry: WriterRegistry, receipt: ActivationCohortReceipt):
    """Qualify original replay-fence bytes; never rewrite or remove history."""
    from nexus.orchestrator.writer_quiescence import WriterQuiescenceReceipt

    original = receipt.original_drain
    if not isinstance(original, Mapping) or not isinstance(original.get("payload"), Mapping):
        raise CohortConflict("ORIGINAL_DRAIN_REQUIRED")
    raw = _json(original["payload"])
    if _sha(raw) != original.get("bytes_sha256"):
        raise CohortConflict("ORIGINAL_DRAIN_BYTES_MISMATCH")
    drain = WriterQuiescenceReceipt.from_bytes(raw)
    if (
        drain.drain_state != DRAINED
        or drain.cohort_id != receipt.cohort_id
        or drain.hold_epoch != receipt.hold_epoch
        or drain.ordered_roots != receipt.ordered_roots
        or drain.source_identity != registry.source_identity
        or any(
            contract["drain_receipt_hash"] != drain.receipt_sha256
            for contract in receipt.root_contracts
        )
    ):
        raise CohortConflict("ORIGINAL_DRAIN_VECTOR_MISMATCH")
    frozen = {lease.operation_id: lease for lease in drain.leases}
    # Every previously sealed terminal record remains the persistent replay
    # fence. Missing entries are corruption, even if directory scanning finds
    # no unknown records.
    for lease in frozen.values():
        path = registry._lease_path(lease.identity.root, lease.operation_id)
        if _safe_read(path) != _json(lease.to_dict()):
            raise CohortConflict("ORIGINAL_TERMINAL_REPLAY_FENCE_CHANGED")
    pins = []
    proved = set()
    for root in receipt.ordered_roots:
        leases, issues = registry._durable_leases(root)
        if any(not issue.startswith("lease:foreign-process:") for issue in issues):
            raise CohortConflict("RECOVERY_UNRESOLVED_LEASES")
        for lease in leases:
            if lease.identity.process_start_identity == registry.process_start_identity:
                continue
            expected = frozen.get(lease.operation_id)
            if (
                expected != lease
                or lease.exited_at is None
                or lease.durable_outcome not in {"committed", "failed"}
                or lease.expires_at is None
                or not lease.entered_at <= lease.exited_at <= lease.expires_at
            ):
                raise CohortConflict("RECOVERY_FOREIGN_LEASE_NOT_IN_DRAIN")
            path = registry._lease_path(root, lease.operation_id)
            data = _safe_read(path)
            if data != _json(expected.to_dict()):
                raise CohortConflict("RECOVERY_TERMINAL_LEASE_BYTES_MISMATCH")
            if lease.identity.process_start_identity not in proved:
                _prove_process_absent(lease.identity.process_start_identity)
                proved.add(lease.identity.process_start_identity)
            pins.append((str(path), _sha(data)))
    return tuple(pins)


def verify_loaded_cohort_terminal_history(
    registry: WriterRegistry, coordinator: WriterActivationCohort
):
    """Fixed B consumer seam: only the actual loaded recovering F owner qualifies pins."""
    if (
        type(coordinator) is not WriterActivationCohort
        or coordinator.registry is not registry
        or not coordinator._recovering
        or _LOADED_COHORTS.get((id(registry), coordinator.cohort_id)) is not coordinator
    ):
        raise CohortConflict("LOADED_RECOVERY_COORDINATOR_REQUIRED")
    registry._check_process()
    if coordinator.hold.released or registry._leases_for(coordinator.hold.roots):
        raise CohortConflict("TERMINAL_RECONCILIATION_REQUIRES_DRAINED_HOLD")
    current = coordinator.load_durable(coordinator.state_path)
    if (
        current.receipt_sha256 != coordinator._last.receipt_sha256
        or current.process_start_identity != registry.process_start_identity
        or current.source_identity != registry.source_identity
        or current.root_contracts != coordinator._contracts()
    ):
        raise CohortConflict("RECOVERY_RECEIPT_CHANGED")
    coordinator._check_f_hold(allow_missing=current.state in {"RELEASE_INTENT", "RELEASED"})
    return _qualified_terminal_records(registry, current)


def status_loaded_cohort(coordinator: WriterActivationCohort) -> ActivationCohortReceipt:
    """Read-only current status from an already loaded coordinator.

    A CLI may call this bridge after its owning process has supplied the real
    registry/hold/coordinator.  Passing a path, root list, or durable JSON to
    this function is intentionally impossible.
    """
    if not isinstance(coordinator, WriterActivationCohort):
        raise TypeError("loaded cohort coordinator required")
    return coordinator.status()


def reconcile_loaded_cohort(coordinator: WriterActivationCohort) -> ActivationCohortReceipt:
    """Read-only reconcile of the exact loaded cohort; never mint a second one."""
    if not isinstance(coordinator, WriterActivationCohort):
        raise TypeError("loaded cohort coordinator required")
    return coordinator.reconcile_read_only()


def get_loaded_writer_activation_cohort() -> WriterActivationCohort | None:
    """Return the sole source-owned, same-process loaded cohort, if any.

    This has no request arguments by design.  A CLI cannot select a root,
    state file, registry, or cohort identity.  The loaded owner is responsible
    for constructing the coordinator; this function only validates its
    process binding and returns the existing object.
    """
    current: list[WriterActivationCohort] = []
    for coordinator in tuple(_LOADED_COHORTS.values()):
        if coordinator.registry._pid != os.getpid():
            continue
        coordinator.registry._check_process()
        if coordinator.state_path.exists():
            coordinator.status()
        else:
            coordinator._check_f_hold()
        current.append(coordinator)
    if len(current) > 1:
        raise CohortConflict("MULTIPLE_LOADED_COHORTS")
    return current[0] if current else None


ActivationCohort = WriterActivationCohort
WriterActivationRoot = ActivationRoot


def release_hold_after_active(
    registry: WriterRegistry,
    hold: WriterHold,
    active_cohort_receipt: ActivationCohortReceipt,
) -> ActivationCohortReceipt:
    """F-owned release seam for an already loaded registry and hold.

    It intentionally does not accept roots, a state path, or a replacement
    registry.  Callers that need the durable state transition should use the
    coordinator's ``release`` method; this seam is only for the same-process
    coordinator after its ACTIVE readback.
    """
    if not isinstance(registry, WriterRegistry) or not isinstance(hold, WriterHold):
        raise TypeError("actual loaded registry and hold required")
    if active_cohort_receipt.state != "ACTIVE" or active_cohort_receipt.cohort_id != hold.cohort_id:
        raise WriterActivationError("ACTIVE_RECEIPT_REQUIRED")
    coordinator = _LOADED_COHORTS.get((id(registry), hold.cohort_id))
    if coordinator is None or coordinator.hold is not hold:
        raise WriterActivationError("LOADED_COHORT_REQUIRED")
    return coordinator.release(active_cohort_receipt)


__all__ = [
    "ActivationCohortReceipt",
    "ActivationRoot",
    "InitialActivationRootSpec",
    "InitialTaskOwner",
    "InitialRuntimeOwner",
    "InitialEventOwner",
    "CohortConflict",
    "WriterActivationCohort",
    "WriterActivationError",
    "WriterActivationRoot",
    "release_hold_after_active",
    "status_loaded_cohort",
    "reconcile_loaded_cohort",
    "get_loaded_writer_activation_cohort",
]
