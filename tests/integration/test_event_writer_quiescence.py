from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.engine.pipeline import NexusPipeline
from nexus.events.state_owner_manifest import (
    StateOwnerBinding,
    StateOwnerSelection,
    commit_owner_transaction,
    owner_transaction_guard,
    read_manifest,
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
from nexus.feedback.contracts import DeveloperFeedbackDecision, FeedbackDecision
from nexus.orchestrator.writer_quiescence import (
    WriterAdmissionDenied,
    WriterIdentity,
    WriterRegistry,
    current_process_start_identity,
)
from nexus.reactions.async_feedback import AsyncFeedbackRouter
from nexus.research.flow.governance_packets import governance_events_packet


@pytest.fixture(autouse=True)
def _reset_bus():
    NexusEventBus._subscribers = {}
    NexusEventBus._signal_queue = []
    NexusEventBus._event_log_path = None
    NexusEventBus._writer_factory = None
    NexusEventBus._log_store = __import__(
        "nexus.events.log_store", fromlist=["JsonlEventLogStore"]
    ).JsonlEventLogStore()
    NexusEventBus._attempt_sequences = {}
    yield
    NexusEventBus._event_log_path = None
    NexusEventBus._writer_factory = None


def _activated_event_root(tmp_path: Path):
    events = tmp_path / ".nexus" / "events"
    events.mkdir(parents=True)
    generation = EventWriterGeneration(1, "event-writer")
    install_generation(tmp_path, generation)
    binding = StateOwnerBinding("event-owner", tmp_path.resolve(), 1, "bootstrap")
    with owner_transaction_guard(
        binding,
        writer_generation=generation,
        selections=(
            StateOwnerSelection("event:seed", "event_log", ".nexus/events/event_log.jsonl"),
        ),
    ) as context:
        commit_owner_transaction(context)
    identity = WriterIdentity(
        str(tmp_path.resolve()),
        "event_log",
        "event-fixture",
        current_process_start_identity(),
        str(threading.get_ident()),
        1,
        "event-writer",
    )
    registry = WriterRegistry(
        source_identity="event-fixture",
        server_identity="event-fixture-server",
        hold_store=tmp_path / "holds",
    )
    registry.register(identity, loaded_identity=lambda: identity)
    factory = load_event_writer_factory(
        registry,
        binding=binding,
        writer_generation=generation,
        root=tmp_path,
        writer_id="event-writer",
    )
    return registry, factory


def _records(root: Path):
    path = root / ".nexus" / "events" / "event_log.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_pipeline_feedback_and_governance_use_loaded_event_writer(tmp_path: Path, monkeypatch):
    registry, factory = _activated_event_root(tmp_path)
    witness: list[tuple[str, str]] = []
    acquire = registry.acquire
    release = registry._release

    def witnessed_acquire(**kwargs):
        path = tmp_path / ".nexus" / "events" / "event_log.jsonl"
        before = path.read_bytes() if path.exists() else b""
        lease = acquire(**kwargs)
        identity = lease.observation.identity
        assert identity.root == str(tmp_path.resolve())
        assert identity.role == "event_log"
        assert identity.source_identity == "event-fixture"
        assert identity.process_start_identity == current_process_start_identity()
        assert identity.thread_id == str(threading.get_ident())
        assert identity.generation == 1
        assert (path.read_bytes() if path.exists() else b"") == before
        witness.append(("lease", lease.transaction_id))
        return lease

    def witnessed_release(lease, outcome):
        assert outcome == "committed"
        assert read_manifest(tmp_path).state == "COMMITTED"
        witness.append(("close", lease.transaction_id))
        return release(lease, outcome)

    registry.acquire = witnessed_acquire
    registry._release = witnessed_release

    from nexus.events.log_store import JsonlEventLogStore, current_event_owner_context

    append = JsonlEventLogStore.append_record
    append_witnesses = []

    def witnessed_append(store, record, **kwargs):
        context = current_event_owner_context()
        assert context is not None
        live = list(registry._leases.values())
        assert len(live) == 1
        lease = live[0]
        lease.validate()
        assert context.binding.transaction_id == lease.transaction_id
        assert witness[-1] == ("lease", lease.transaction_id)
        before = store.event_log_path.read_bytes() if store.event_log_path.exists() else b""
        result = append(store, record, **kwargs)
        lease.validate()
        assert store.event_log_path.read_bytes() != before
        append_witnesses.append(record["event_type"])
        return result

    monkeypatch.setattr(JsonlEventLogStore, "append_record", witnessed_append)

    # The actual pipeline caller performs configure and is then allowed to
    # publish through the loaded source-owned factory.
    engine = SimpleNamespace(
        project_root=tmp_path,
        policy_manager=SimpleNamespace(apply_policy_to_state=lambda state, task: None),
        state_io=SimpleNamespace(save_global_state=lambda state: None),
        commander=SimpleNamespace(next_step=lambda **kwargs: None),
        hub=None,
        accumulator=None,
        health_evaluator=None,
        research_policy=None,
        phases={"P": None, "X": None, "R": None},
    )
    pipeline = NexusPipeline(engine)
    ctx = pipeline._init_pipeline_state(
        "pipeline-task", "trace", "span", "verify event writer", "bug", None
    )
    pipeline._prepare_repair_context(ctx, repair_attempts=2)
    assert ctx.pack["force_deep_diagnosis"] is True

    router = AsyncFeedbackRouter(tmp_path)
    assert router.simulate_ci_failure("trace") is True

    packet = governance_events_packet(
        repo_root=tmp_path,
        task_id="governance-task",
        receipt_slug="receipt",
        artifact_verified=True,
        claim_probe={},
    )

    event_count = len(_records(tmp_path))
    NexusEventBus.emit_developer_feedback_decision(
        DeveloperFeedbackDecision(
            task_id="feedback-task",
            decision_id="feedback-decision",
            decision=FeedbackDecision.KEEP,
            reason_codes=("TEST",),
        )
    )
    assert len(_records(tmp_path)) == event_count
    assert (tmp_path / ".nexus" / "events" / "developer_feedback_decision.v1.jsonl").exists()

    records = _records(tmp_path)
    assert len(append_witnesses) == len(records)
    assert len(records) >= 3
    assert any(item["event_type"] == "repair_failed" for item in records)
    assert packet["summary"]["emission_status"] == "emitted"
    assert packet["summary"]["emitted_count"] == 2
    assert all(item["_writer_generation"] == 1 for item in records)
    assert all(item["_writer_id"] == "event-writer" for item in records)
    assert all(item.durable_outcome == "committed" for item in registry._lease_history)
    assert read_manifest(tmp_path).state == "COMMITTED"
    assert not (tmp_path / ".nexus" / "writer-quiescence-hold.json").exists()
    assert [kind for kind, _ in witness].count("lease") == [kind for kind, _ in witness].count(
        "close"
    )
    assert all(a[1] == b[1] for a, b in zip(witness[::2], witness[1::2]))


def test_loaded_event_writer_denies_direct_append_and_hold_before_bytes(tmp_path: Path):
    registry, factory = _activated_event_root(tmp_path)
    NexusEventBus.configure(tmp_path, writer_factory=factory)
    log_path = tmp_path / ".nexus" / "events" / "event_log.jsonl"
    before = log_path.read_bytes() if log_path.exists() else b""
    with pytest.raises(GenerationError, match="EVENT_WRITER_CONTEXT_REQUIRED"):
        NexusEventBus._log_store.append_record({
            "event_type": "direct",
            "timestamp": 1,
            "seq": 1,
            "payload": {},
        })
    assert (log_path.read_bytes() if log_path.exists() else b"") == before

    identity = next(iter(registry._writers.values())).identity
    registry.begin_hold((identity.root,), cohort_id="event-hold")
    with pytest.raises(WriterAdmissionDenied):
        NexusEventBus.publish("held", {"source": "fixture"})
    assert (log_path.read_bytes() if log_path.exists() else b"") == before


def test_governance_reports_partial_event_emission(tmp_path: Path, monkeypatch):
    _activated_event_root(tmp_path)
    calls = {"count": 0}

    def fail_second(*args, **kwargs):
        calls["count"] += 1
        raise WriterAdmissionDenied("fixture second append denied")

    monkeypatch.setattr(NexusEventBus, "emit_learning_decision", fail_second)
    packet = governance_events_packet(
        repo_root=tmp_path,
        task_id="partial-task",
        receipt_slug="partial",
        artifact_verified=True,
        claim_probe={},
    )
    assert packet["summary"]["emission_status"] == "partial"
    assert packet["summary"]["emitted_count"] == 1
    assert packet["summary"]["emission_error"].startswith("WriterAdmissionDenied:")
    assert len(_records(tmp_path)) == 1


def test_two_child_cross_domain_paths_are_bounded_and_deduplicated(tmp_path: Path):
    """Two concurrent processes, independent inventories, two actual roots each.

    State->event is the existing service failure transition; event->state is a
    test subscriber on the public bus API, not a claimed production subscriber.
    """
    script = textwrap.dedent(
        r"""
        import sys, threading, time, json, os
        from pathlib import Path
        from contextlib import contextmanager
        import nexus.events.writer_generation as wg
        import nexus.events.state_owner_manifest as sm
        import nexus.events.log_store as ls
        from nexus.events.transport import NexusEventBus, load_event_writer_factory
        from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
        from nexus.orchestrator.writer_quiescence import (TaskStateWriterAdapter,
            TaskStateWriterFactory, WriterIdentity, WriterRegistry,
            current_process_start_identity, WriterAdmissionDenied)

        base, mode, phase = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
        state, event = base / mode / 'state', base / mode / 'event'
        if phase == 'restart':
            # A fresh process has no authority to adopt an old collector hold.
            registry = WriterRegistry(source_identity='child-source')
            before = (state / 'task.json').read_bytes(), (event / '.nexus/events/event_log.jsonl').read_bytes()
            service = SelfHostedTaskService(state_dir=state, ephemeral=True, auto_reconcile=False)
            try:
                service._write_state('task', {'task_id': 'task', 'status': 'ESCAPED'})
            except (WriterAdmissionDenied, RuntimeError):
                pass
            else:
                raise AssertionError('restarted task writer escaped hold')
            try:
                ls.JsonlEventLogStore().configure(event)
            except (RuntimeError, wg.GenerationError):
                pass
            else:
                raise AssertionError('restarted unbound event writer configured held root')
            assert before == ((state / 'task.json').read_bytes(), (event / '.nexus/events/event_log.jsonl').read_bytes())
            try:
                registry.load_finalized('hold-' + mode)
            except Exception:
                pass
            else:
                raise AssertionError('restart adopted prior process collector receipt')
            print('restart-denied')
            sys.exit(0)

        # Patch all imported aliases of the actual physical domain lock.
        original = wg.event_store_lock
        stack, locks = [], []
        @contextmanager
        def checked_lock(root, **kwargs):
            key = str(Path(root).resolve())
            assert not stack or stack[-1] == key, ('second-domain-lock', stack, key)
            with original(root, **kwargs):
                locks.append((key, len(stack)))
                stack.append(key)
                try:
                    yield
                finally:
                    assert stack.pop() == key
        wg.event_store_lock = checked_lock
        wg.event_store_guard = checked_lock
        sm.event_store_lock = checked_lock
        ls.event_store_lock = checked_lock
        registry = WriterRegistry(source_identity='child-source')
        identities = []
        bindings = {}
        for root, role, relative in ((state, 'task_state', 'task.json'),
                                    (event, 'event_log', '.nexus/events/event_log.jsonl')):
            root.mkdir(parents=True)
            generation = wg.EventWriterGeneration(1, role + '-writer')
            wg.install_generation(root, generation)
            binding = sm.StateOwnerBinding(role + '-owner', root.resolve(), 1, 'seed')
            with sm.owner_transaction_guard(binding, writer_generation=generation,
                    selections=(sm.StateOwnerSelection(role + ':seed', role, relative),)) as context:
                sm.commit_owner_transaction(context)
            identity = WriterIdentity(str(root.resolve()), role, 'child-source',
                current_process_start_identity(), str(threading.get_ident()), 1, generation.writer_id)
            # Only this child's two fixture writers exist in this explicit inventory.
            registry.register(identity,
                snapshot=lambda root=root: (root / sm.MANIFEST_NAME).read_bytes(),
                process_state=lambda: 'alive' if threading.current_thread().is_alive() else 'unknown',
                pending=lambda: tuple(registry._leases), loaded_identity=lambda identity=identity: identity)
            identities.append(identity)
            bindings[role] = binding, generation
        service = SelfHostedTaskService(state_dir=state, ephemeral=True, auto_reconcile=False)
        binding, generation = bindings['task_state']
        adapter = TaskStateWriterAdapter(registry, binding=binding,
            writer_generation=generation, root=state, writer_id=generation.writer_id,
            path_for_task=service._state_path, loaded_identity=lambda: identities[0])
        service._writer_factory = TaskStateWriterFactory(adapter)
        writes = []
        close = registry._release
        def checked_close(lease, outcome):
            assert outcome == 'committed'
            manifest = sm.read_manifest(Path(lease.observation.identity.root))
            assert manifest.state == 'COMMITTED'
            assert manifest.transaction_id == lease.transaction_id
            return close(lease, outcome)
        registry._release = checked_close
        def active_witness(role, root, context):
            leases = list(registry._leases.values())
            assert len(leases) == 1
            lease = leases[0]
            lease.validate()
            identity = lease.observation.identity
            assert identity.root == str(root.resolve()) and identity.role == role
            assert identity.source_identity == 'child-source'
            assert identity.process_start_identity == current_process_start_identity()
            assert identity.thread_id == str(threading.get_ident()) and identity.generation == 1
            assert context.binding.transaction_id == lease.transaction_id
            writes.append((role, lease.transaction_id))
        write_state = service._write_state_locked
        def checked_state(task_id, value, **kwargs):
            active_witness('task_state', state, kwargs['owner_context'])
            return write_state(task_id, value, **kwargs)
        service._write_state_locked = checked_state
        append = ls.JsonlEventLogStore.append_record
        def checked_append(store, record, **kwargs):
            active_witness('event_log', event, ls.current_event_owner_context())
            return append(store, record, **kwargs)
        ls.JsonlEventLogStore.append_record = checked_append
        binding, generation = bindings['event_log']
        factory = load_event_writer_factory(registry, binding=binding,
            writer_generation=generation, root=event, writer_id=generation.writer_id)
        NexusEventBus.configure(event, writer_factory=factory)
        service._write_state('task', {'task_id': 'task', 'attempt_id': 'attempt', 'status': 'SUBMITTED'})
        (base / (mode + '.ready')).write_text(str(os.getpid()))
        deadline = time.monotonic() + 12
        while not (base / 'go').exists():
            assert time.monotonic() < deadline, 'barrier deadline'
            time.sleep(.01)
        if mode == 'state_event':
            result = service.record_canonical_action_failure('task', 'fixture-blocker')
            assert result['status'] == 'DIRECT_RECONCILE_REQUIRED'
        else:
            called = []
            def test_subscriber(payload):
                assert not stack, 'subscriber entered while event domain held'
                service._mutate_state('task', lambda value: value.update(status='CALLBACK_WRITTEN'))
                called.append(payload['_seq'])
            NexusEventBus.subscribe('test_event_state', test_subscriber)
            NexusEventBus.publish('test_event_state', {'task_id': 'task'})
            assert len(called) == 1  # Observer errors cannot masquerade as success.
        assert not stack
        assert [role for role, _ in writes].count('task_state') == 2
        assert [role for role, _ in writes].count('event_log') == 1
        assert len({tx for _, tx in writes}) == 3
        assert any(depth > 0 for _, depth in locks), 'same-lock P6 reentry was not exercised'
        assert {key for key, _ in locks} == {str(state.resolve()), str(event.resolve())}
        assert all(item.durable_outcome == 'committed' for item in registry._lease_history)
        hold = registry.begin_hold((state, event), cohort_id='hold-' + mode)
        hold.wait_for_drain(timeout=1)
        for identity in identities:
            hold.acknowledge(identity.writer_id, root=identity.root, role=identity.role, generation=1)
        assert hold.finalize().drain_state == 'DRAINED', hold.finalize().to_bytes()
        receipt = registry.persist_finalized(hold)
        assert receipt.drain_state == 'DRAINED', receipt.to_bytes()
        assert registry.load_finalized(hold.cohort_id) == receipt
        before = (event / '.nexus/events/event_log.jsonl').read_bytes()
        try:
            NexusEventBus.publish('held', {})
        except WriterAdmissionDenied:
            pass
        else:
            raise AssertionError('hold escaped')
        assert before == (event / '.nexus/events/event_log.jsonl').read_bytes()
        (base / (mode + '.receipt.json')).write_bytes(receipt.to_bytes())
        print('ok')
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    children = []
    try:
        for mode in ("state_event", "event_state"):
            children.append(
                subprocess.Popen(
                    [sys.executable, "-B", "-c", script, str(tmp_path), mode, "run"],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        import time

        deadline = time.monotonic() + 12
        while not all(
            (tmp_path / (mode + ".ready")).exists() for mode in ("state_event", "event_state")
        ):
            for child in children:
                if child.poll() is not None:
                    stdout, stderr = child.communicate()
                    pytest.fail(f"child failed before barrier: {stdout} {stderr}")
            assert time.monotonic() < deadline, "children did not reach barrier"
            time.sleep(0.01)
        assert all(child.poll() is None for child in children)
        (tmp_path / "go").write_text("release both live children")
        for child in children:
            stdout, stderr = child.communicate(timeout=max(1, deadline - time.monotonic()))
            assert child.returncode == 0, stderr
            assert stdout.strip() == "ok"
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=3)
    for mode in ("state_event", "event_state"):
        rows = _records(tmp_path / mode / "event")
        assert len(rows) == 1
        assert rows[0]["payload"]["task_id"] == "task"
        assert read_manifest(tmp_path / mode / "state").state == "COMMITTED"
        assert read_manifest(tmp_path / mode / "event").state == "COMMITTED"
        result = subprocess.run(
            [sys.executable, "-B", "-c", script, str(tmp_path), mode, "restart"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "restart-denied"
        assert len(_records(tmp_path / mode / "event")) == 1
