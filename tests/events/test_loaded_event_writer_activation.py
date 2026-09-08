from __future__ import annotations

import threading
from pathlib import Path

import pytest

from nexus.events.log_store import JsonlEventLogStore
from nexus.events.state_owner_manifest import (
    StateOwnerBinding,
    StateOwnerSelection,
    commit_owner_transaction,
    owner_transaction_guard,
)
from nexus.events.transport import (
    NexusEventBus,
    load_event_writer_factory,
)
from nexus.events.writer_generation import (
    EventWriterGeneration,
    GenerationError,
    install_generation,
)
from nexus.orchestrator.writer_quiescence import WriterIdentity, WriterRegistry


@pytest.fixture(autouse=True)
def _reset_event_bus_binding():
    # NexusEventBus is intentionally process-scoped in production.  Isolate
    # this module's temporary source bindings so unrelated tests do not inherit
    # a loaded root after the fixture exits.
    NexusEventBus._writer_factory = None
    NexusEventBus._event_log_path = None
    NexusEventBus._log_store = JsonlEventLogStore()
    yield
    NexusEventBus._writer_factory = None
    NexusEventBus._event_log_path = None
    NexusEventBus._log_store = JsonlEventLogStore()


def _loaded_root(tmp_path: Path):
    root = tmp_path.resolve()
    generation = EventWriterGeneration(1, "event-writer")
    install_generation(root, generation)
    binding = StateOwnerBinding("owner", root, 1, "seed-transaction")
    with owner_transaction_guard(
        binding,
        writer_generation=generation,
        selections=(StateOwnerSelection("seed", "task_state", "seed.json"),),
    ) as context:
        (root / "seed.json").write_text("seed\n", encoding="utf-8")
        commit_owner_transaction(context)
    registry = WriterRegistry(source_identity="loaded-source")
    identity = WriterIdentity(
        str(root),
        "event_log",
        registry.source_identity,
        registry.process_start_identity,
        str(threading.get_ident()),
        1,
        generation.writer_id,
    )
    registry.register(identity, loaded_identity=lambda: identity)
    factory = load_event_writer_factory(
        registry,
        binding=binding,
        writer_generation=generation,
        root=root,
        writer_id=generation.writer_id,
    )
    return root, generation, factory


def test_loaded_event_factory_writes_through_real_bus_and_closes_lease(tmp_path: Path):
    root, generation, factory = _loaded_root(tmp_path)
    NexusEventBus.configure(root, writer_factory=factory)
    NexusEventBus.publish("test_event", {"value": "owned"})
    data = (root / ".nexus/events/event_log.jsonl").read_text(encoding="utf-8")
    assert '"owned"' in data
    assert '"_writer_generation": 1' in data
    assert not factory._adapter.registry._leases


def test_loaded_event_factory_mints_unique_transactions_for_same_trace(tmp_path: Path):
    root, _generation, factory = _loaded_root(tmp_path)
    NexusEventBus.configure(root, writer_factory=factory)
    NexusEventBus.publish("test_event", {"_trace_id": "same-causal-trace", "value": 1})
    NexusEventBus.publish("test_event", {"_trace_id": "same-causal-trace", "value": 2})
    records = (root / ".nexus/events/event_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(records) == 2
    assert not factory._adapter.registry._leases


def test_loaded_store_rejects_direct_append_without_operation_context(tmp_path: Path):
    root, generation, factory = _loaded_root(tmp_path)
    store = JsonlEventLogStore()
    store.configure(root, writer_generation=generation, writer_factory=factory)
    with pytest.raises(GenerationError, match="CONTEXT_REQUIRED"):
        store.append_record({"event_type": "unadapted", "payload": {}})
    assert not (root / ".nexus/events/event_log.jsonl").exists()


def test_fake_factory_is_rejected_before_path_creation(tmp_path: Path):
    root = tmp_path.resolve()
    store = JsonlEventLogStore()
    with pytest.raises(GenerationError, match="FACTORY_INVALID"):
        store.configure(root, writer_factory=object())
    assert not (root / ".nexus").exists()


def test_loaded_factory_cannot_configure_another_root(tmp_path: Path):
    root, generation, factory = _loaded_root(tmp_path / "bound")
    other = (tmp_path / "other").resolve()
    other.mkdir()
    store = JsonlEventLogStore()
    with pytest.raises(GenerationError, match="ROOT_MISMATCH"):
        store.configure(other, writer_generation=generation, writer_factory=factory)
    assert not (other / ".nexus").exists()


@pytest.mark.parametrize(
    "attribute,relative",
    [
        ("event_log_path", ".nexus/events/unselected.jsonl"),
        ("lock_path", "other/.nexus/events/event_log.lock"),
        ("_generation_manifest_path", "other/.nexus/events/writer_generation.json"),
    ],
)
def test_actual_store_paths_deny_before_any_store_lock(tmp_path, monkeypatch, attribute, relative):
    import nexus.events.log_store as module

    root, _, factory = _loaded_root(tmp_path)
    store = JsonlEventLogStore()
    store.configure(root, writer_factory=factory)
    with factory.for_operation("path-tamper"):
        setattr(store, attribute, root / relative)

        def forbidden(*args, **kwargs):
            pytest.fail("path tampering reached physical lock")

        monkeypatch.setattr(module, "event_store_lock", forbidden)
        with pytest.raises(GenerationError, match="PATH_MISMATCH"):
            store.append_record({"event_type": "tampered", "payload": {}})
    assert not (root / ".nexus/events/event_log.jsonl").exists()
    assert not (root / relative).exists()


def test_context_wrong_thread_fork_and_replay_deny_without_bytes(tmp_path):
    import os

    root, _, factory = _loaded_root(tmp_path)
    store = JsonlEventLogStore()
    store.configure(root, writer_factory=factory)
    errors = []
    with factory.for_operation("context-check", operation_id="one-operation") as context:

        def other_thread():
            try:
                store.append_record({"event_type": "thread"}, owner_context=context)
            except Exception as exc:
                errors.append(str(exc))

        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join(2)
        assert not thread.is_alive() and len(errors) == 1
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                try:
                    store.append_record({"event_type": "fork"}, owner_context=context)
                except Exception:
                    os.write(write_fd, b"denied")
            finally:
                os._exit(0)
        os.close(write_fd)
        import select

        assert select.select([read_fd], [], [], 3)[0]
        assert os.read(read_fd, 32) == b"denied"
        os.close(read_fd)
        assert os.waitpid(pid, 0)[1] == 0
    with pytest.raises(Exception, match="not active"):
        store.append_record({"event_type": "replay"}, owner_context=context)
    with pytest.raises(Exception, match="duplicate|replayed"):
        with factory.for_operation("again", operation_id="one-operation"):
            pytest.fail("replay admitted")
    assert not (root / ".nexus/events/event_log.jsonl").exists()


def test_expired_lease_denies_before_append_and_records_unresolved(tmp_path):
    import time

    root, _, factory = _loaded_root(tmp_path)
    store = JsonlEventLogStore()
    store.configure(root, writer_factory=factory)
    factory._adapter.registry.lease_lifetime_seconds = 0.02
    with pytest.raises(Exception, match="expired"):
        with factory.for_operation("expiry"):
            time.sleep(0.04)
            store.append_record({"event_type": "expired"})
    assert not (root / ".nexus/events/event_log.jsonl").exists()
    assert factory._adapter.registry._lease_history[-1].durable_outcome == "unresolved"


def test_reconfigure_other_loaded_root_and_physical_hold_deny(tmp_path):
    root, _, factory = _loaded_root(tmp_path / "one")
    other, _, other_factory = _loaded_root(tmp_path / "two")
    store = JsonlEventLogStore()
    store.configure(root, writer_factory=factory)
    with pytest.raises(GenerationError, match="RECONFIGURATION"):
        store.configure(other, writer_factory=other_factory)
    marker = root / ".nexus/writer-quiescence-hold.json"
    marker.write_text("corrupt")
    with pytest.raises(Exception, match="held"):
        with factory.for_operation("held"):
            pytest.fail("held writer admitted")
    assert not (root / ".nexus/events/event_log.jsonl").exists()


def test_lease_expiry_waiting_for_guard_does_not_prepare(tmp_path):
    from nexus.events.state_owner_manifest import read_manifest
    from nexus.events.writer_generation import event_store_lock

    root, _, factory = _loaded_root(tmp_path)
    previous = read_manifest(root)
    factory._adapter.registry.lease_lifetime_seconds = 0.04
    entered, release = threading.Event(), threading.Event()

    def lock_holder():
        with event_store_lock(root):
            entered.set()
            release.wait(2)

    holder = threading.Thread(target=lock_holder)
    holder.start()
    assert entered.wait(1)
    timer = threading.Timer(0.1, release.set)
    timer.start()
    try:
        with pytest.raises(Exception, match="expired"):
            with factory.for_operation("wait-expiry"):
                pytest.fail("expired admission reached prepare")
    finally:
        release.set()
        holder.join(2)
        timer.join(2)
    assert read_manifest(root) == previous
    assert factory._adapter.registry._lease_history[-1].durable_outcome == "unresolved"


@pytest.mark.parametrize("filename", ["event_log.jsonl", "event_log.lock"])
def test_symlink_after_prepare_denies_before_store_guard(tmp_path, monkeypatch, filename):
    import nexus.events.log_store as module

    root, _, factory = _loaded_root(tmp_path)
    store = JsonlEventLogStore()
    store.configure(root, writer_factory=factory)
    outside = root / "outside"
    outside.write_text("unchanged")
    with pytest.raises(Exception):
        with factory.for_operation("symlink"):
            path = root / ".nexus/events" / filename
            path.unlink(missing_ok=True)
            path.symlink_to(outside)

            def forbidden(*args, **kwargs):
                pytest.fail("symlink reached physical store guard")

            monkeypatch.setattr(module, "event_store_lock", forbidden)
            store.append_record({"event_type": "symlink"})
    assert outside.read_text() == "unchanged"


def test_stale_generation_and_replaced_root_deny(tmp_path):
    root, generation, factory = _loaded_root(tmp_path / "stale")
    install_generation(
        root, EventWriterGeneration(2, "successor"), expected_generation=generation.generation
    )
    with pytest.raises(Exception, match="stale"):
        with factory.for_operation("stale"):
            pytest.fail("stale generation admitted")
    root2, _, factory2 = _loaded_root(tmp_path / "replaced")
    root2.rename(tmp_path / "old-root")
    root2.mkdir()
    with pytest.raises(Exception, match="physical identity"):
        with factory2.for_operation("replaced"):
            pytest.fail("replacement root admitted")
    assert list(root2.iterdir()) == []


def test_unbound_store_with_generation_cannot_bypass_activated_owner(tmp_path):
    root, generation, _ = _loaded_root(tmp_path)
    store = JsonlEventLogStore()
    store.configure(root, writer_generation=generation)
    with pytest.raises(GenerationError, match="CONTEXT_REQUIRED"):
        store.append_record({"event_type": "unbound"})
    assert not (root / ".nexus/events/event_log.jsonl").exists()
