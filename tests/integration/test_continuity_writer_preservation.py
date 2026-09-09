"""Continuity reads must preserve the loaded event-writer fence."""

import threading

import pytest

from nexus.events.contracts import build_attempt_transition_event
from nexus.events.state_owner_manifest import (
    StateOwnerBinding,
    StateOwnerSelection,
    commit_owner_transaction,
    owner_transaction_guard,
)
from nexus.events.log_store import DeveloperFeedbackDecisionStore, JsonlEventLogStore
from nexus.events.signal_queue_service import SignalQueueService
from nexus.events.transport import NexusEventBus, load_event_writer_factory
from nexus.events.writer_generation import EventWriterGeneration, install_generation
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.writer_quiescence import (
    WriterAdmissionDenied,
    WriterIdentity,
    WriterRegistry,
    current_process_start_identity,
)


@pytest.fixture(autouse=True)
def _reset_event_bus(monkeypatch):
    # Isolate every mutable facade slot; monkeypatch restores the complete
    # pre-test state, including the prior store and signal service objects.
    isolated = {
        "_production_event_root": None,
        "_configured_event_root": None,
        "_event_bind_mode": None,
        "_event_log_path": None,
        "_writer_factory": None,
        "_log_store": JsonlEventLogStore(),
        "_developer_feedback_store": DeveloperFeedbackDecisionStore(),
        "_signal_queue_svc": SignalQueueService(),
        "_subscribers": {},
        "_signal_queue": [],
        "_attempt_sequences": {},
        "_global_seq": 0,
        "_remote_broadcaster": None,
        "_observer_error_count": 0,
        "_last_observer_error": None,
    }
    for name, value in isolated.items():
        monkeypatch.setattr(NexusEventBus, name, value)
    yield


def _loaded_event_writer(root):
    root = root.resolve()
    event_path = root / ".nexus" / "events" / "event_log.jsonl"
    event_path.parent.mkdir(parents=True)
    event_path.write_text("")
    generation = EventWriterGeneration(1, "event-writer")
    install_generation(root, generation)
    binding = StateOwnerBinding("event-owner", root, 1, "bootstrap")
    with owner_transaction_guard(
        binding,
        writer_generation=generation,
        selections=(StateOwnerSelection("event_log", "event_log", ".nexus/events/event_log.jsonl"),),
    ) as context:
        commit_owner_transaction(context)
    registry = WriterRegistry(source_identity="continuity-test", server_identity="test-server")
    identity = WriterIdentity(
        str(root),
        "event_log",
        registry.source_identity,
        current_process_start_identity(),
        str(threading.get_ident()),
        1,
        generation.writer_id,
    )
    registry.register(
        identity,
        snapshot=lambda: event_path.read_bytes(),
        process_state=lambda: "alive",
        pending=lambda: tuple(registry._leases),
        loaded_identity=lambda: identity,
    )
    factory = load_event_writer_factory(
        registry,
        binding=binding,
        writer_generation=generation,
        root=root,
        writer_id=generation.writer_id,
    )
    NexusEventBus.configure(root, writer_factory=factory)
    return registry, factory


def test_continuity_read_preserves_writer_and_held_publish_denial(tmp_path):
    registry, factory = _loaded_event_writer(tmp_path)
    event = build_attempt_transition_event(
        task_id="continuity-task",
        attempt_id="attempt-1",
        sequence=1,
        state="RUNNING",
        source_revision="source",
        contract_revision="contract",
    )
    NexusEventBus.emit_attempt_transition(event)

    records = SelfHostedTaskService.read_canonical_attempt_events(
        "continuity-task", "attempt-1", project_root=tmp_path
    )
    assert len(records) == 1
    assert NexusEventBus._writer_factory is factory
    assert NexusEventBus._log_store._writer_factory is factory

    # A real subsequent publish still traverses the same loaded factory.
    NexusEventBus.publish("continuity_probe", {"task_id": "continuity-task"})
    assert NexusEventBus._writer_factory is factory

    registry.begin_hold((tmp_path.resolve(),), cohort_id="continuity-hold")
    with pytest.raises(WriterAdmissionDenied):
        NexusEventBus.publish("held_probe", {"task_id": "continuity-task"})
    assert NexusEventBus._writer_factory is factory
