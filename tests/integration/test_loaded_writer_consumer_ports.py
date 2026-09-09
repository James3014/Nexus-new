"""Assembly-owned consumer port binding remains immutable and exact."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.orchestrator.writer_activation_consumers import (
    ConsumerPortBindingError,
    LoadedWriterConsumerPorts,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService


def _ports(tmp_path):
    event_root = (tmp_path / "event").resolve()
    runtime_root = (tmp_path / "runtime").resolve()
    event_store = SimpleNamespace(_writer_factory=None)
    event_factory = SimpleNamespace(_adapter=SimpleNamespace(root=event_root))
    event_store._writer_factory = event_factory
    event_bus = SimpleNamespace(
        _log_store=event_store,
        _writer_factory=event_factory,
        _configured_event_root=event_root,
    )
    runtime_factory = SimpleNamespace(_adapter=SimpleNamespace(root=runtime_root))
    journal = SimpleNamespace(project_root=runtime_root)
    return dict(
        task_writer_factory=SimpleNamespace(),
        event_bus=event_bus,
        event_store=event_store,
        event_root=event_root,
        runtime_writer_factory=runtime_factory,
        effect_journal=journal,
        effect_dispatch=SimpleNamespace(),
        effect_reconcile=SimpleNamespace(),
    )


def test_loaded_ports_bind_service_and_runtime_defaults(tmp_path):
    ports = LoadedWriterConsumerPorts(**_ports(tmp_path))
    service = SimpleNamespace()
    assert ports.bind_service(service) is service
    assert service._consumer_ports is ports
    assert service._writer_factory is ports.task_writer_factory
    assert service._event_bus is ports.event_bus
    assert service._event_store is ports.event_store
    assert ports.runtime_kwargs()["runtime_writer_factory"] is ports.runtime_writer_factory

    with pytest.raises((AttributeError, TypeError)):
        ports.event_root = Path("/other")

    real_service = SelfHostedTaskService(
        state_dir=tmp_path / "task-service",
        ephemeral=True,
        auto_reconcile=False,
        consumer_ports=ports,
    )
    assert real_service._consumer_ports is ports
    assert real_service._event_bus is ports.event_bus
    assert real_service._event_store is ports.event_store


@pytest.mark.parametrize("field", ["event_store", "runtime_writer_factory", "effect_journal"])
def test_loaded_ports_reject_singleton_or_root_drift(tmp_path, field):
    values = _ports(tmp_path)
    if field == "event_store":
        values[field] = SimpleNamespace(_writer_factory=values["event_bus"]._writer_factory)
    elif field == "runtime_writer_factory":
        values[field] = SimpleNamespace(_adapter=SimpleNamespace(root=tmp_path / "foreign"))
    else:
        values[field] = SimpleNamespace(project_root=tmp_path / "foreign")
    with pytest.raises(ConsumerPortBindingError):
        LoadedWriterConsumerPorts(**values)
