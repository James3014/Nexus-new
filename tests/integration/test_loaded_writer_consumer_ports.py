"""Assembly-owned consumer port binding remains immutable and exact."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.writer_activation_consumers import (
    ConsumerPortBindingError,
    LoadedWriterConsumerPorts,
)
from nexus.orchestrator.writer_quiescence import WriterAdmissionDenied


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


def test_real_cohort_consumers_write_readback_and_hold_denial(tmp_path):
    """Exercise the actual A/F factories returned by the cohort fixture."""
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    from nexus.services.unified_runtime import UnifiedRuntime
    from tests.integration.test_writer_activation_cohort import _real_cohort
    from tests.services.test_unified_runtime import _online, _Planner, _request

    cohort, roots = _real_cohort(tmp_path)
    active = cohort.activate()
    assert active.state == "ACTIVE"
    cohort.release(active)
    task_root, event_root, runtime_root = roots
    effects = runtime_root.factory.effect_binding()
    ports = LoadedWriterConsumerPorts(
        task_writer_factory=task_root.factory,
        event_bus=event_root.event_bus,
        event_store=event_root.event_store,
        event_root=event_root.root,
        runtime_writer_factory=runtime_root.factory,
        effect_journal=effects.journal,
        effect_dispatch=effects.dispatch,
        effect_reconcile=effects.reconcile,
    )
    service = SelfHostedTaskService(
        state_dir=task_root.root, ephemeral=True, auto_reconcile=False, consumer_ports=ports
    )
    service._write_state(
        "consumer-port-task", {"task_id": "consumer-port-task", "status": "SUBMITTED"}
    )
    service._emit_bound_attempt_transition(
        {
            "task_id": "consumer-port-task",
            "attempt_id": "attempt-1",
            "status": "RUNNING",
            "source_revision": "source",
            "contract_revision": "contract",
        },
        "consumer-port-task",
    )
    records = service.read_canonical_attempt_events(
        "consumer-port-task",
        "attempt-1",
        project_root=event_root.root,
        event_bus=ports.event_bus,
        event_store=ports.event_store,
    )
    assert records[0]["payload"]["task_id"] == "consumer-port-task"
    runtime = UnifiedRuntime(planner=_Planner(), consumer_ports=ports)
    with pytest.raises(ValueError, match="loaded_writer_runtime_writer_factory_override_denied"):
        runtime.run(
            _request(),
            online_invoker=_online,
            runtime_writer_factory=object(),
            receipt_path=Path(runtime_root.root) / "foreign.json",
        )
    output = runtime.run(
        _request(), online_invoker=_online, receipt_path=Path(runtime_root.root) / "consumer.json"
    )
    assert output["effect_journal_bindings"]
    assert (Path(runtime_root.root) / "consumer.json").read_bytes()
    assert (Path(runtime_root.root) / ".nexus/events/effect_journal.v1.json").read_bytes()

    before_task = Path(task_root.root, "consumer-port-task.json").read_bytes()
    before_event = event_root.event_store.event_log_path.read_bytes()
    before_receipt = Path(runtime_root.root, "consumer.json").read_bytes()
    before_effects = Path(runtime_root.root, ".nexus/events/effect_journal.v1.json").read_bytes()
    cohort.registry.begin_hold(tuple(root.root for root in roots), cohort_id="consumer-port-hold")
    with pytest.raises(WriterAdmissionDenied):
        service._write_state("held-task", {"task_id": "held-task", "status": "SUBMITTED"})
    with pytest.raises(WriterAdmissionDenied):
        event_root.event_bus.publish("held-event", {"task_id": "consumer-port-task"})
    with pytest.raises(WriterAdmissionDenied):
        runtime.run(
            _request(),
            online_invoker=_online,
            receipt_path=Path(runtime_root.root) / "held-runtime.json",
        )
    assert not (Path(task_root.root) / "held-task.json").exists()
    assert before_task == Path(task_root.root, "consumer-port-task.json").read_bytes()
    assert before_event == event_root.event_store.event_log_path.read_bytes()
    assert before_receipt == Path(runtime_root.root, "consumer.json").read_bytes()
    assert (
        before_effects
        == Path(runtime_root.root, ".nexus/events/effect_journal.v1.json").read_bytes()
    )
    assert not Path(runtime_root.root, "held-runtime.json").exists()


def test_production_service_uses_bound_event_root_for_continuity(tmp_path, monkeypatch):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    from tests.integration.test_writer_activation_cohort import _real_cohort

    cohort, roots = _real_cohort(tmp_path)
    active = cohort.activate()
    assert active.state == "ACTIVE"
    cohort.release(active)
    task_root, event_root, runtime_root = roots
    effects = runtime_root.factory.effect_binding()
    ports = LoadedWriterConsumerPorts(
        task_writer_factory=task_root.factory,
        event_bus=event_root.event_bus,
        event_store=event_root.event_store,
        event_root=event_root.root,
        runtime_writer_factory=runtime_root.factory,
        effect_journal=effects.journal,
        effect_dispatch=effects.dispatch,
        effect_reconcile=effects.reconcile,
    )
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", task_root.root)
    service = SelfHostedTaskService(
        state_dir=task_root.root, ephemeral=False, auto_reconcile=False, consumer_ports=ports
    )
    service._write_state("production-bound", {"task_id": "production-bound", "status": "SUBMITTED"})
    service._emit_bound_attempt_transition(
        {
            "task_id": "production-bound",
            "attempt_id": "attempt-1",
            "status": "RUNNING",
            "source_revision": "source",
            "contract_revision": "contract",
        },
        "production-bound",
    )
    projection = service.rehydrate_task_continuation("production-bound", "attempt-1")
    assert projection
    assert projection.get("continuity", {}).get("task_id", "production-bound") == "production-bound"
    assert b"production-bound" in event_root.event_store.event_log_path.read_bytes()
    assert event_root.event_bus._writer_factory is event_root.factory
