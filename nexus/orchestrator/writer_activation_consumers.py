"""Immutable bindings for consumers of an activated writer cohort."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConsumerPortBindingError(ValueError):
    """Raised when loaded consumer ports do not describe one cohort."""


@dataclass(frozen=True, slots=True)
class LoadedWriterConsumerPorts:
    """Source-owned, immutable bindings passed from assembly into consumers."""

    task_writer_factory: Any
    event_bus: Any
    event_store: Any
    event_root: Path
    runtime_writer_factory: Any
    effect_journal: Any
    effect_dispatch: Any
    effect_reconcile: Any

    def __post_init__(self) -> None:
        root = Path(self.event_root).expanduser().resolve()
        object.__setattr__(self, "event_root", root)
        if self.event_bus is None or self.event_store is None:
            raise ConsumerPortBindingError("event_consumer_ports_required")
        if getattr(self.event_bus, "_log_store", None) is not self.event_store:
            raise ConsumerPortBindingError("event_store_singleton_mismatch")
        configured = getattr(self.event_bus, "_configured_event_root", None)
        if configured is not None and Path(configured).resolve() != root:
            raise ConsumerPortBindingError("event_root_singleton_mismatch")
        event_factory = getattr(self.event_bus, "_writer_factory", None)
        if event_factory is None or event_factory is not getattr(
            self.event_store, "_writer_factory", None
        ):
            raise ConsumerPortBindingError("event_writer_factory_singleton_mismatch")
        event_adapter = getattr(event_factory, "_adapter", None)
        if event_adapter is None or Path(event_adapter.root).resolve() != root:
            raise ConsumerPortBindingError("event_writer_root_mismatch")
        if self.runtime_writer_factory is None:
            raise ConsumerPortBindingError("runtime_writer_factory_required")
        runtime_adapter = getattr(self.runtime_writer_factory, "_adapter", None)
        if runtime_adapter is None:
            raise ConsumerPortBindingError("runtime_writer_factory_invalid")
        runtime_root = Path(runtime_adapter.root).resolve()
        journal_root = getattr(self.effect_journal, "project_root", None)
        if journal_root is None or Path(journal_root).resolve() != runtime_root:
            raise ConsumerPortBindingError("effect_journal_root_mismatch")
        if self.effect_dispatch is None or self.effect_reconcile is None:
            raise ConsumerPortBindingError("effect_ports_required")
        if self.task_writer_factory is None:
            raise ConsumerPortBindingError("task_writer_factory_required")

    def bind_service(self, service: Any) -> Any:
        """Install exact task/event bindings on a service instance."""
        existing_task = getattr(service, "_writer_factory", None)
        if existing_task is not None and existing_task is not self.task_writer_factory:
            raise ConsumerPortBindingError("task_writer_factory_rebind_denied")
        existing_bus = getattr(service, "_event_bus", None)
        if existing_bus is not None and existing_bus is not self.event_bus:
            raise ConsumerPortBindingError("event_bus_rebind_denied")
        existing_store = getattr(service, "_event_store", None)
        if existing_store is not None and existing_store is not self.event_store:
            raise ConsumerPortBindingError("event_store_rebind_denied")
        service._consumer_ports = self
        service._writer_factory = self.task_writer_factory
        service._event_bus = self.event_bus
        service._event_store = self.event_store
        return service

    def runtime_kwargs(self) -> dict[str, Any]:
        """Return the captured runtime ports for UnifiedRuntime.run/run_replan."""
        return {
            "runtime_writer_factory": self.runtime_writer_factory,
            "effect_journal": self.effect_journal,
            "effect_dispatch": self.effect_dispatch,
            "effect_reconcile": self.effect_reconcile,
            "effect_fenced": True,
        }


def bind_loaded_writer_consumers(**kwargs: Any) -> LoadedWriterConsumerPorts:
    """Validate and freeze the assembly-owned consumer port vector."""
    return LoadedWriterConsumerPorts(**kwargs)
