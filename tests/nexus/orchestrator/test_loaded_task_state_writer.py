from __future__ import annotations

import threading
from pathlib import Path

import pytest

from nexus.events.state_owner_manifest import (
    StateOwnerBinding,
    StateOwnerSelection,
    commit_owner_transaction,
    owner_transaction_guard,
    read_manifest,
)
from nexus.events.writer_generation import EventWriterGeneration, install_generation
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.writer_quiescence import (
    TaskStateWriterAdapter,
    TaskStateWriterFactory,
    WriterAdmissionDenied,
    WriterIdentity,
    WriterRegistry,
    current_process_start_identity,
)


def _activated_service(tmp_path: Path):
    service = SelfHostedTaskService(state_dir=tmp_path, ephemeral=True, auto_reconcile=False)
    generation = EventWriterGeneration(1, "task-writer")
    install_generation(tmp_path, generation)
    binding = StateOwnerBinding("task-owner", tmp_path.resolve(), 1, "bootstrap")
    with owner_transaction_guard(
        binding,
        writer_generation=generation,
        selections=(StateOwnerSelection("task-state:seed", "task_state", "seed.json"),),
    ) as context:
        commit_owner_transaction(context)
    identity = WriterIdentity(
        str(tmp_path),
        "task_state",
        "fixture-source",
        current_process_start_identity(),
        str(threading.get_ident()),
        1,
        "task-writer",
    )
    registry = WriterRegistry(
        source_identity="fixture-source", server_identity="fixture", hold_store=tmp_path / "holds"
    )
    registry.register(identity, loaded_identity=lambda: identity)
    adapter = TaskStateWriterAdapter(
        registry,
        binding=binding,
        writer_generation=generation,
        root=tmp_path,
        writer_id="task-writer",
        path_for_task=service._state_path,
        loaded_identity=lambda: identity,
    )
    service._writer_factory = TaskStateWriterFactory(adapter)
    return service, registry


def test_task_writes_lease_before_commit_and_use_fresh_transactions(tmp_path: Path):
    service, registry = _activated_service(tmp_path)
    service._write_state("first", {"task_id": "first", "status": "SUBMITTED"})
    service._write_state("second", {"task_id": "second", "status": "SUBMITTED"})
    service._mutate_state("first", lambda state: state.update(status="FINAL_BLOCK"))

    assert (tmp_path / "first.json").is_file()
    assert (tmp_path / "second.json").is_file()
    assert not (tmp_path / ".state.lock").exists()
    assert read_manifest(tmp_path).state == "COMMITTED"
    assert len(registry._lease_history) == 3
    assert len({lease.transaction_id for lease in registry._lease_history}) == 3
    assert all(lease.durable_outcome == "committed" for lease in registry._lease_history)


def test_activated_direct_locked_write_denies_before_bytes(tmp_path: Path):
    service, _ = _activated_service(tmp_path)
    with pytest.raises(WriterAdmissionDenied):
        service._write_state_locked("blocked", {"task_id": "blocked", "status": "SUBMITTED"})
    assert not (tmp_path / "blocked.json").exists()


def test_hold_closes_task_admission_before_bytes(tmp_path: Path):
    service, registry = _activated_service(tmp_path)
    identity = next(iter(registry._writers.values())).identity
    registry.begin_hold((identity.root,), cohort_id="fixture-cohort")
    with pytest.raises(WriterAdmissionDenied):
        service._write_state("held", {"task_id": "held", "status": "SUBMITTED"})
    assert not (tmp_path / "held.json").exists()


def test_real_prepare_write_and_commit_witness(tmp_path, monkeypatch):
    import nexus.events.state_owner_manifest as manifest_module
    import nexus.events.writer_generation as generation_module

    service, registry = _activated_service(tmp_path)
    prepare = manifest_module.prepare_manifest
    write = service._write_state_locked
    release = registry._release
    witnessed = []

    def leased():
        assert len(registry._leases) == 1
        lease = next(iter(registry._leases.values()))
        lease.validate()
        assert lease.observation.identity.root == str(tmp_path.resolve())
        assert lease.observation.identity.role == "task_state"
        assert lease.observation.identity.source_identity == "fixture-source"
        assert lease.observation.identity.process_start_identity == current_process_start_identity()
        assert lease.observation.identity.generation == 1
        assert not registry._mutex._is_owned()
        return lease

    def prepare_witness(*args, **kwargs):
        leased()
        assert any(lock.depth >= 2 for lock in generation_module._HELD_LOCKS.values())
        witnessed.append("prepare")
        return prepare(*args, **kwargs)

    def write_witness(*args, **kwargs):
        lease = leased()
        assert kwargs["owner_context"].transaction_id == lease.transaction_id
        assert read_manifest(tmp_path).state == "PREPARED"
        witnessed.append("write")
        return write(*args, **kwargs)

    def close_witness(lease, outcome):
        assert outcome == "committed"
        manifest = read_manifest(tmp_path)
        assert manifest.state == "COMMITTED"
        assert manifest.transaction_id == lease.transaction_id
        witnessed.append("close")
        return release(lease, outcome)

    monkeypatch.setattr(manifest_module, "prepare_manifest", prepare_witness)
    monkeypatch.setattr(service, "_write_state_locked", write_witness)
    monkeypatch.setattr(registry, "_release", close_witness)
    service._create_state("created", {"task_id": "created", "status": "SUBMITTED"})
    service._mutate_state("created", lambda state: state.update(status="FINAL_BLOCK"))
    assert witnessed == ["prepare", "write", "close"] * 2
    assert not (tmp_path / ".state.lock").exists()


def test_failure_after_prepare_is_unresolved_and_blocks_restart(tmp_path, monkeypatch):
    import nexus.events.state_owner_manifest as manifests

    service, registry = _activated_service(tmp_path)
    monkeypatch.setattr(
        manifests, "commit_owner_transaction", lambda _: (_ for _ in ()).throw(OSError("crash"))
    )
    with pytest.raises(OSError, match="crash"):
        service._write_state("partial", {"task_id": "partial", "status": "SUBMITTED"})
    assert (tmp_path / "partial.json").exists()
    assert read_manifest(tmp_path).state == "PREPARED"
    assert registry._lease_history[-1].durable_outcome == "unresolved"
    with pytest.raises(WriterAdmissionDenied):
        service._write_state("again", {"task_id": "again"})
    restarted = SelfHostedTaskService(state_dir=tmp_path, ephemeral=True, auto_reconcile=False)
    with pytest.raises(WriterAdmissionDenied):
        restarted._write_state("restart", {"task_id": "restart"})
    assert not (tmp_path / "restart.json").exists()


def test_context_wrong_thread_expired_and_replayed_denied(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from nexus.events.state_owner_manifest import OwnerConflict

    service, registry = _activated_service(tmp_path)
    factory = service._writer_factory
    with factory.for_operation("thread", operation_id="one") as context:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                service._write_state_locked, "thread", {"task_id": "thread"}, owner_context=context
            )
            with pytest.raises((OwnerConflict, WriterAdmissionDenied)):
                future.result(timeout=3)
        assert not (tmp_path / "thread.json").exists()
    with pytest.raises((OwnerConflict, WriterAdmissionDenied)):
        service._write_state_locked("thread", {"task_id": "thread"}, owner_context=context)
    with pytest.raises(WriterAdmissionDenied):
        with factory.for_operation("thread", operation_id="one"):
            pytest.fail("replayed operation entered")
    registry.lease_lifetime_seconds = 0.000001
    with pytest.raises(WriterAdmissionDenied):
        service._write_state("expired", {"task_id": "expired"})
    assert not (tmp_path / "expired.json").exists()


def test_wrong_root_and_generation_deny_before_state_bytes(tmp_path):
    from dataclasses import replace

    from nexus.events.state_owner_manifest import OwnerConflict

    service, registry = _activated_service(tmp_path)
    adapter = service._writer_factory._adapter
    adapter._path_for_task = lambda task: tmp_path.parent / (task + ".json")
    with pytest.raises(WriterAdmissionDenied):
        service._write_state("escape", {"task_id": "escape"})
    adapter._path_for_task = service._state_path
    adapter.writer_generation = replace(adapter.writer_generation, generation=2)
    with pytest.raises((WriterAdmissionDenied, OwnerConflict)):
        service._write_state("stale", {"task_id": "stale"})
    assert not list(tmp_path.glob("*.json"))


def test_reconciliation_enters_fresh_lease_before_repair_write(tmp_path, monkeypatch):
    service, registry = _activated_service(tmp_path)
    service._create_state("lost", {"task_id": "lost", "status": "WORKER_RUNNING"})
    write = service._write_state_locked
    observed = []

    def witness(*args, **kwargs):
        lease = next(iter(registry._leases.values()))
        assert kwargs["owner_context"].transaction_id == lease.transaction_id
        observed.append(lease.transaction_id)
        return write(*args, **kwargs)

    monkeypatch.setattr(service, "_write_state_locked", witness)
    service.reconcile_tasks()
    assert observed
    assert all(item.durable_outcome == "committed" for item in registry._lease_history)
    assert set(observed).isdisjoint({registry._lease_history[0].transaction_id})
    assert not (tmp_path / ".state.lock").exists()


def test_forked_adapter_denies_before_task_creation(tmp_path):
    import os

    service, _ = _activated_service(tmp_path)
    pid = os.fork()
    if pid == 0:
        try:
            service._write_state("forked", {"task_id": "forked"})
        except WriterAdmissionDenied:
            os._exit(0)
        except BaseException:
            os._exit(2)
        os._exit(1)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert not (tmp_path / "forked.json").exists()


@pytest.mark.parametrize(
    "artifact", [".nexus/events/state_owner.manifest.v1.json", ".nexus/writer-quiescence-hold.json"]
)
def test_unadapted_corrupt_or_symlink_policy_cannot_fall_back_to_legacy(tmp_path, artifact):
    service = SelfHostedTaskService(state_dir=tmp_path, ephemeral=True, auto_reconcile=False)
    marker = tmp_path / artifact
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("malformed")
    with pytest.raises(WriterAdmissionDenied):
        service._create_state("denied", {"task_id": "denied"})
    marker.unlink()
    marker.symlink_to(tmp_path / "missing")
    with pytest.raises(WriterAdmissionDenied):
        service._write_state("denied", {"task_id": "denied"})
    assert not (tmp_path / "denied.json").exists()
    assert not (tmp_path / ".state.lock").exists()


def test_concurrent_claim_and_duplicate_create_keep_benign_semantics(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from tests.nexus.orchestrator.test_self_hosted_task_service import _claim_request

    service, registry = _activated_service(tmp_path)
    service._create_state("claim-task", {"task_id": "claim-task", "status": "SUBMITTED"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.acquire_work_claim(_claim_request()), range(2)))
    assert sorted(result["status"] for result in results) == ["ALREADY_CLAIMED", "CLAIMED"]
    assert service.acquire_work_claim(_claim_request(worker_id="other"))["status"] == "BLOCKED"
    with ThreadPoolExecutor(max_workers=2) as pool:
        created = list(
            pool.map(
                lambda _: service._create_state(
                    "duplicate", {"task_id": "duplicate", "status": "SUBMITTED"}
                )[1],
                range(2),
            )
        )
    assert sorted(created) == [False, True]
    service._mutate_state("duplicate", lambda state: state.update(status="FINAL_BLOCK"))
    assert all(lease.durable_outcome == "committed" for lease in registry._lease_history)
    assert not (tmp_path / ".state.lock").exists()


def test_missing_claim_release_does_not_claim_success(tmp_path):
    service, _ = _activated_service(tmp_path)
    with pytest.raises(FileNotFoundError):
        service.release_work_claim({"task_id": "missing"})


def test_expiry_during_mutator_denies_before_state_bytes(tmp_path):
    service, registry = _activated_service(tmp_path)
    service._write_state("expiring", {"task_id": "expiring", "status": "SUBMITTED"})
    before = (tmp_path / "expiring.json").read_bytes()

    def expire(state):
        state["status"] = "FINAL_BLOCK"
        next(iter(registry._leases.values()))._deadline = 0

    with pytest.raises(WriterAdmissionDenied):
        service._mutate_state("expiring", expire)
    assert (tmp_path / "expiring.json").read_bytes() == before
    assert registry._lease_history[-1].durable_outcome == "unresolved"
    assert not service._writer_factory._adapter._active_contexts


def test_bootstrap_source_fallback_must_match_binding(tmp_path):
    from nexus.orchestrator.state_owner_transition_authority import LoadedSourceIdentity
    from nexus.orchestrator.unified_mcp_gateway import LoadedTaskWriterBinding, UnifiedMCPGateway

    service, _ = _activated_service(tmp_path)
    service.source_identity = LoadedSourceIdentity(
        "James3014/Nexus-new", "a" * 40, "b" * 40, "card", "c" * 64
    )
    manifest = read_manifest(tmp_path)
    service.loaded_task_writer_binding = LoadedTaskWriterBinding(
        root=tmp_path.resolve(),
        owner_id=manifest.owner_id,
        transaction_id=manifest.transaction_id,
        generation=1,
        writer_id="task-writer",
        source_head="d" * 40,
        source_tree="b" * 40,
    )
    gateway = UnifiedMCPGateway(service=service)
    with pytest.raises(RuntimeError, match="SOURCE_MISMATCH"):
        gateway.bootstrap_writer_admission()
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize("owned", [True, False])
def test_gateway_owned_legacy_reconciles_once_and_supplied_service_waits(
    tmp_path, monkeypatch, owned
):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    service = SelfHostedTaskService(state_dir=tmp_path, ephemeral=True, auto_reconcile=False)
    events = []
    monkeypatch.setattr(service, "reconcile_tasks", lambda: events.append("reconcile"))

    def construct(**kwargs):
        assert kwargs == {"auto_reconcile": False}
        events.append("construct")
        return service

    monkeypatch.setattr(gateway_module, "SelfHostedTaskService", construct)
    gateway = (
        gateway_module.UnifiedMCPGateway()
        if owned
        else gateway_module.UnifiedMCPGateway(service=service)
    )
    assert events == (["construct", "reconcile"] if owned else [])
    gateway.bootstrap_writer_admission()
    assert events == (["construct", "reconcile"] if owned else ["reconcile"])
    gateway.bootstrap_writer_admission()
    assert events.count("reconcile") == 1
