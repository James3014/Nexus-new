"""Cold-start producer for the source-owned writer activation boundary.

The normal activation cohort assumes that adapters already exist.  A freshly
created state root cannot satisfy that assumption: generation zero is useful
only as an observation.  This module keeps that observation separate from the
typed A transition and exposes a handle for constructing real writers only
after physical COMMITTED readback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from nexus.events.state_owner_manifest import read_manifest
from nexus.events.writer_generation import EventWriterGeneration, read_generation
from nexus.orchestrator.state_owner_transition_service import LoadedRootTransition
from nexus.orchestrator.writer_quiescence import (
    DRAINED,
    InitialWriterAttachment,
    WriterHold,
    WriterRegistry,
)


class InitialActivationError(RuntimeError):
    """The initial activation prefix is incomplete or physically inconsistent."""


@dataclass(frozen=True, slots=True)
class InitialActivationRoot:
    """A source-owned A handle for a root with no previous generation."""

    root: str
    root_id: str
    transition: Any
    registry: WriterRegistry
    hold: WriterHold

    def __post_init__(self) -> None:
        path = Path(self.root)
        if not path.is_absolute() or path.resolve() != path:
            raise ValueError("initial activation root must be canonical and absolute")
        if not isinstance(self.transition, LoadedRootTransition):
            raise TypeError("typed initial A transition required")
        if not isinstance(self.registry, WriterRegistry) or not isinstance(self.hold, WriterHold):
            raise TypeError("source-owned registry and hold required")
        if self.hold.registry is not self.registry or self.hold.roots != (str(path),):
            raise InitialActivationError("INITIAL_ROOT_HOLD_MISMATCH")
        request = self.transition.request
        if request.root_id != self.root_id or request.expected_generation is not None:
            raise InitialActivationError("INITIAL_REQUEST_IS_NOT_EMPTY_ROOT")

    def preflight(self) -> Any:
        self._check_empty()
        return self.transition.preflight()

    def apply(self) -> Any:
        self._check_empty()
        return self.transition.apply()

    def reconcile(self) -> Any:
        return self.transition.reconcile()

    def _check_empty(self) -> None:
        if self.registry._held_roots.get(str(Path(self.root))) is not self.hold:
            raise InitialActivationError("INITIAL_ROOT_NOT_HELD")
        if (
            read_manifest(Path(self.root)) is not None
            or read_generation(Path(self.root)) is not None
        ):
            raise InitialActivationError("INITIAL_ROOT_ALREADY_ACTIVATED")


@dataclass(frozen=True, slots=True)
class InitialActivationHandle:
    """Capability issued only after A's physical positive-generation readback."""

    root: str
    generation: EventWriterGeneration
    manifest_sha256: str
    transaction_id: str
    attachment: InitialWriterAttachment

    def __post_init__(self) -> None:
        if self.generation.generation < 1 or not self.manifest_sha256:
            raise ValueError("committed positive generation is required")
        if not isinstance(self.attachment, InitialWriterAttachment):
            raise TypeError("opaque initial attachment is required")


class WriterActivationProducer:
    """Run initial A while the source-owned hold remains intact."""

    def __init__(
        self,
        root: InitialActivationRoot,
        *,
        materialize: Callable[[InitialActivationHandle], Mapping[str, Any] | None],
    ) -> None:
        if not isinstance(root, InitialActivationRoot) or not callable(materialize):
            raise TypeError("initial root and materialize callback are required")
        self.root = root
        self.materialize = materialize

    def activate(self) -> Mapping[str, Any] | None:
        self.root.hold.wait_for_drain(timeout=0.0)
        try:
            drained = self.root.registry.load_finalized(self.root.hold.cohort_id)
        except (FileNotFoundError, KeyError):
            drained = self.root.registry.persist_finalized(self.root.hold)
        if drained.drain_state != DRAINED:
            raise InitialActivationError("INITIAL_DRAIN_NOT_COMPLETE")
        ready = self.root.preflight()
        state = getattr(getattr(ready, "state", ready), "value", getattr(ready, "state", ready))
        if state not in {"PREFLIGHT_READY", "COMMITTED", "RECONCILED"}:
            raise InitialActivationError(f"INITIAL_PREFLIGHT_DENIED:{state}")
        result = self.root.apply()
        state = getattr(getattr(result, "state", result), "value", getattr(result, "state", result))
        if state not in {"COMMITTED", "RECONCILED"}:
            raise InitialActivationError(f"INITIAL_APPLY_DENIED:{state}")
        manifest = read_manifest(Path(self.root.root))
        generation = read_generation(Path(self.root.root))
        if (
            manifest is None
            or manifest.state != "COMMITTED"
            or generation is None
            or generation.generation < 1
            or generation.generation != manifest.generation
            or generation.writer_id != manifest.writer_id
            or manifest.owner_id != self.root.transition.request.expected_owner_id
            or manifest.root_identity != self.root.transition.request.expected_root_identity
            or manifest.transaction_id != self.root.transition.request.transaction_id
        ):
            raise InitialActivationError("INITIAL_COMMITTED_READBACK_FAILED")
        handle = InitialActivationHandle(
            self.root.root,
            generation,
            manifest.manifest_sha256,
            manifest.transaction_id,
            self.root.registry.issue_initial_attachment(
                self.root.hold,
                root=self.root.root,
                generation=generation.generation,
                writer_id=generation.writer_id,
                manifest_sha256=manifest.manifest_sha256,
            ),
        )
        # Factories are materialized only at this point, while the whole hold
        # is still installed.  A callback cannot replace the source handle.
        return self.materialize(handle)


def build_loaded_writer_collector_plan(
    *,
    gateway: Any,
    hold: WriterHold,
    request: Any,
    source_receipt: Path,
    snapshot_receipt: Path,
    rollback_receipt: Path,
    writer_plan_receipt: Path,
    artifacts: tuple[str, ...],
) -> Any:
    """Build and validate a collector plan from one finalized cold-start hold.

    All identifiers and source/root values are read from the typed request and
    the gateway's registered physical hold.  The function performs no
    authorization and accepts no caller-selected root or digest.
    """
    from nexus.orchestrator.unified_mcp_gateway import LoadedWriterCollectorPlan

    registry = getattr(gateway, "_writer_quiescence_registry", None)
    if registry is None or not isinstance(hold, WriterHold):
        raise InitialActivationError("INITIAL_COLLECTOR_REGISTRY_REQUIRED")
    finalized = registry.load_finalized(hold.cohort_id)
    root = Path(gateway.service.state_dir).resolve()
    identities = [
        item.identity for item in registry._writers.values() if item.identity.root == str(root)
    ]
    if len(identities) != 1 or finalized.drain_state != DRAINED:
        raise InitialActivationError("INITIAL_COLLECTOR_HOLD_INVALID")
    identity = identities[0]
    return LoadedWriterCollectorPlan(
        request_digest=request.request_digest,
        cohort_id=hold.cohort_id,
        root_id=request.root_id,
        root=root,
        source_head=request.expected_source_head,
        source_tree=request.expected_source_tree,
        generation=identity.generation,
        writer_id=identity.writer_id,
        source_receipt=Path(source_receipt).resolve(),
        snapshot_receipt=Path(snapshot_receipt).resolve(),
        rollback_receipt=Path(rollback_receipt).resolve(),
        writer_plan_receipt=Path(writer_plan_receipt).resolve(),
        artifacts=tuple(artifacts),
    )


__all__ = [
    "InitialActivationError",
    "InitialActivationHandle",
    "InitialActivationRoot",
    "WriterActivationProducer",
    "build_loaded_writer_collector_plan",
]
