from pathlib import Path
import os
import threading
from contextlib import ExitStack

import pytest

from nexus.events.state_owner_manifest import (
    ManifestMalformed,
    OwnerConflict,
    StateOwnerBinding,
    StateOwnerSelection,
    assert_owner_write,
    commit_owner_transaction,
    owner_transaction_guard,
)
from nexus.events.log_store import JsonlEventLogStore
import nexus.events.log_store as log_store_module
import nexus.events.state_owner_manifest as manifest_module
from nexus.events.writer_generation import (
    EventWriterGeneration,
    GenerationError,
    event_store_lock,
    install_generation,
)


def test_owner_guard_is_registered_and_explicitly_committed(tmp_path: Path):
    root = tmp_path.resolve()
    token = EventWriterGeneration(1, "writer")
    install_generation(root, token)
    binding = StateOwnerBinding("owner", root, 1, "transaction")
    selections = (StateOwnerSelection("task:t1", "task_state", "state.json"),)

    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        assert_owner_write(context, role="task_state", relative_path="state.json")
        (root / "state.json").write_text("committed\n", encoding="utf-8")
        committed = commit_owner_transaction(context)
        assert committed.state == "COMMITTED"
        with pytest.raises(OwnerConflict):
            commit_owner_transaction(context)
        with pytest.raises(OwnerConflict):
            assert_owner_write(context, role="task_state", relative_path="state.json")

    with pytest.raises(OwnerConflict):
        assert_owner_write(context, role="task_state", relative_path="state.json")


def test_owner_guard_without_commit_leaves_prepared(tmp_path: Path):
    root = tmp_path.resolve()
    token = EventWriterGeneration(1, "writer")
    install_generation(root, token)
    binding = StateOwnerBinding("owner", root, 1, "transaction")
    selections = (StateOwnerSelection("task:t1", "task_state", "state.json"),)
    with owner_transaction_guard(binding, writer_generation=token, selections=selections):
        pass
    assert (root / ".nexus/events/state_owner.manifest.v1.json").exists()
    assert "PREPARED" in (root / ".nexus/events/state_owner.manifest.v1.json").read_text()


def test_owner_write_rechecks_target_after_prepare(tmp_path: Path):
    root = tmp_path.resolve()
    token = EventWriterGeneration(1, "writer")
    install_generation(root, token)
    binding = StateOwnerBinding("owner", root, 1, "transaction")
    selections = (StateOwnerSelection("task:t1", "task_state", "state.json"),)
    outside = root.parent / "owner-write-outside"
    outside.write_text("outside", encoding="utf-8")
    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        (root / "state.json").symlink_to(outside)
        with pytest.raises((ManifestMalformed, OwnerConflict)):
            assert_owner_write(context, role="task_state", relative_path="state.json")


def test_fork_child_clears_owner_registry_without_mutex_deadlock(tmp_path: Path):
    root = tmp_path.resolve()
    token = EventWriterGeneration(1, "writer")
    install_generation(root, token)
    binding = StateOwnerBinding("owner", root, 1, "fork-context")
    selections = (StateOwnerSelection("task:t1", "task_state", "state.json"),)
    entered = threading.Event()
    release = threading.Event()

    def hold_registry_lock():
        with manifest_module._OWNER_CONTEXTS_LOCK:
            entered.set()
            release.wait(2)

    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        holder = threading.Thread(target=hold_registry_lock)
        holder.start()
        assert entered.wait(1)
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                try:
                    assert_owner_write(context, role="task_state", relative_path="state.json")
                except OwnerConflict:
                    os.write(write_fd, b"OWNER_CONTEXT_REJECTED\n")
                else:
                    os.write(write_fd, b"UNEXPECTED_ACCEPT\n")
            finally:
                os._exit(0)
        _, status = os.waitpid(pid, 0)
        release.set()
        holder.join(timeout=2)
        os.close(write_fd)
        observed = os.read(read_fd, 128).decode().splitlines()
        os.close(read_fd)
        assert os.waitstatus_to_exitcode(status) == 0
        assert observed == ["OWNER_CONTEXT_REJECTED"]


def test_event_store_owner_context_append_and_commit(tmp_path: Path):
    root = tmp_path.resolve()
    token = EventWriterGeneration(1, "writer")
    install_generation(root, token)
    binding = StateOwnerBinding("owner", root, 1, "event-tx")
    selections = (StateOwnerSelection("events", "event_log", ".nexus/events/event_log.jsonl"),)
    record = {"event_type": "note", "payload": {"value": "owned"}}
    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        store = JsonlEventLogStore()
        store.configure(root, writer_generation=token, enforce_generation=True, owner_context=context)
        store.append_record(record)
        commit_owner_transaction(context)
    assert '"owned"' in (root / ".nexus/events/event_log.jsonl").read_text()


def test_owner_context_rejects_wrong_root_and_postcommit_append(tmp_path: Path):
    root = tmp_path.resolve()
    other = (tmp_path / "other").resolve()
    other.mkdir()
    token = EventWriterGeneration(1, "writer")
    install_generation(root, token)
    binding = StateOwnerBinding("owner", root, 1, "event-tx")
    selections = (StateOwnerSelection("events", "event_log", ".nexus/events/event_log.jsonl"),)
    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        store = JsonlEventLogStore()
        with pytest.raises(GenerationError, match="ROOT_MISMATCH"):
            store.configure(other, writer_generation=token, owner_context=context)
        store.configure(root, writer_generation=token, owner_context=context)
        store.append_record({"event_type": "before"})
        commit_owner_transaction(context)
        before = (root / ".nexus/events/event_log.jsonl").read_bytes()
        with pytest.raises(OwnerConflict):
            store.append_record({"event_type": "after"}, owner_context=context)
        assert (root / ".nexus/events/event_log.jsonl").read_bytes() == before


def test_opt_in_store_does_not_silently_downgrade_or_accept_falsey_context(tmp_path: Path):
    root = tmp_path.resolve()
    token = EventWriterGeneration(1, "writer")
    install_generation(root, token)
    binding = StateOwnerBinding("owner", root, 1, "event-tx")
    selections = (StateOwnerSelection("events", "event_log", ".nexus/events/event_log.jsonl"),)
    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        store = JsonlEventLogStore()
        store.configure(root, writer_generation=token, owner_context=context)
        # Reconfiguration without an explicit context retains the opt-in mode.
        store.configure(root, writer_generation=token)
        with pytest.raises(OwnerConflict):
            store.append_record({"event_type": "forged"}, owner_context=False)  # type: ignore[arg-type]
        store.append_record({"event_type": "valid"})
        commit_owner_transaction(context)


def test_configure_rechecks_context_after_reentrant_interleave(tmp_path: Path, monkeypatch):
    root = tmp_path.resolve()
    token = EventWriterGeneration(1, "writer")
    install_generation(root, token)
    store = JsonlEventLogStore()
    binding = StateOwnerBinding("owner", root, 1, "interleave")
    selections = (StateOwnerSelection("events", "event_log", ".nexus/events/event_log.jsonl"),)
    entered = False
    stack = ExitStack()
    original_lock = log_store_module.event_store_lock

    def controlled_lock(project_root, *, timeout=5.0):
        nonlocal entered
        if not entered:
            entered = True
            context = stack.enter_context(owner_transaction_guard(binding, writer_generation=token, selections=selections))
            store.configure(root, writer_generation=token, owner_context=context)
        return original_lock(project_root, timeout=timeout)

    monkeypatch.setattr(log_store_module, "event_store_lock", controlled_lock)
    store.configure(root, writer_generation=token)
    assert store._owner_context is not None
    stack.close()


def test_append_wrong_root_has_no_legacy_root_lock_side_effect(tmp_path: Path, monkeypatch):
    root_a = (tmp_path / "a").resolve()
    root_b = (tmp_path / "b").resolve()
    root_a.mkdir(); root_b.mkdir()
    token = EventWriterGeneration(1, "writer")
    install_generation(root_a, token)
    binding = StateOwnerBinding("owner", root_a, 1, "wrong-root")
    selections = (StateOwnerSelection("events", "event_log", ".nexus/events/event_log.jsonl"),)
    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        store = JsonlEventLogStore()
        store.configure(root_b)
        event_path = root_b / ".nexus/events/event_log.jsonl"
        lock_path = root_b / ".nexus/events/event_log.lock"
        before_event = event_path.read_bytes() if event_path.exists() else None
        before_lock = lock_path.read_bytes() if lock_path.exists() else None
        lock_calls = []

        def unexpected_lock(*args, **kwargs):
            lock_calls.append(args)
            raise AssertionError("wrong-root append reached event lock")

        monkeypatch.setattr(log_store_module, "event_store_lock", unexpected_lock)
        with pytest.raises(GenerationError, match="ROOT_MISMATCH"):
            store.append_record({"event_type": "wrong"}, owner_context=context)
        assert lock_calls == []
        assert (event_path.read_bytes() if event_path.exists() else None) == before_event
        assert (lock_path.read_bytes() if lock_path.exists() else None) == before_lock


def test_event_store_lock_reenters_same_thread_and_releases(tmp_path: Path):
    root = tmp_path.resolve()
    with event_store_lock(root, timeout=0.2):
        with event_store_lock(root, timeout=0.2):
            pass
    # A fresh acquisition proves the outer descriptor was released.
    with event_store_lock(root, timeout=0.2):
        pass


def test_event_store_lock_rejects_symlink(tmp_path: Path):
    events = tmp_path / ".nexus/events"
    events.mkdir(parents=True)
    (events / "event_log.lock").symlink_to(tmp_path / "outside.lock")
    with pytest.raises(GenerationError, match="GENERATION_LOCK_UNSAFE"):
        with event_store_lock(tmp_path, timeout=0.1):
            pass
