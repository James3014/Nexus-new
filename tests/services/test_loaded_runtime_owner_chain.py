from __future__ import annotations

import os
import threading
import time
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
from nexus.orchestrator.writer_quiescence import (
    RuntimeWriterAdapter,
    RuntimeWriterFactory,
    WriterAdmissionDenied,
    WriterIdentity,
    WriterRegistry,
    current_process_start_identity,
)


def _factory(root: Path) -> RuntimeWriterFactory:
    generation = EventWriterGeneration(1, "runtime-fixture")
    install_generation(root, generation)
    binding = StateOwnerBinding("runtime-owner", root.resolve(), 1, "bootstrap")
    with owner_transaction_guard(
        binding,
        writer_generation=generation,
        selections=(
            StateOwnerSelection("seed-receipt", "runtime_receipt", "seed.json"),
            StateOwnerSelection(
                "seed-effect", "effect_journal", ".nexus/events/effect_journal.v1.json"
            ),
        ),
    ) as context:
        commit_owner_transaction(context)
    registry = WriterRegistry(source_identity="fixture-source", server_identity="fixture")
    for role in ("runtime_receipt", "effect_journal"):
        identity = WriterIdentity(
            str(root),
            role,
            "fixture-source",
            current_process_start_identity(),
            str(threading.get_ident()),
            1,
            "runtime-fixture",
        )
        registry.register(identity, loaded_identity=lambda identity=identity: identity)
    return RuntimeWriterFactory(
        RuntimeWriterAdapter(
            registry,
            binding=binding,
            writer_generation=generation,
            root=root,
            writer_id="runtime-fixture",
        )
    )


def test_runtime_receipt_port_leases_and_commits_before_close(tmp_path: Path):
    factory = _factory(tmp_path)
    path = tmp_path / ".nexus" / "reports" / "task.json"
    with factory.for_operation("task", role="runtime_receipt", path=path) as context:
        assert context.owner_pid
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"task_id":"task"}\n', encoding="utf-8")
    history = factory._adapter.registry._lease_history
    assert len(history) == 1
    assert history[0].identity.role == "runtime_receipt"
    assert history[0].durable_outcome == "committed"


def test_unified_runtime_uses_factory_for_receipt_and_effect(tmp_path: Path):
    from nexus.events.effect_journal import EffectDispatchPort, EffectJournal, EffectReconcilePort
    from nexus.services.unified_runtime import UnifiedRuntime
    from tests.services.test_unified_runtime import _online, _Planner, _request

    factory = _factory(tmp_path)
    token = factory._adapter.writer_generation
    journal = EffectJournal(tmp_path, token)
    receipt_path = tmp_path / ".nexus" / "reports" / "runtime.json"
    output = UnifiedRuntime(planner=_Planner()).run(
        _request(),
        online_invoker=_online,
        receipt_path=receipt_path,
        runtime_writer_factory=factory,
        effect_journal=journal,
        effect_dispatch=EffectDispatchPort(lambda operation: operation()),
        effect_reconcile=EffectReconcilePort(lambda _record: None),
        effect_fenced=True,
        verifier=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence": "fixture",
        },
        learning=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence": "fixture",
        },
    )
    assert receipt_path.is_file()
    assert output["effect_journal_bindings"]
    assert [item.durable_outcome for item in factory._adapter.registry._lease_history] == [
        "committed",
        "committed",
    ]


def test_runtime_factory_rejects_hold_before_write(tmp_path: Path):
    factory = _factory(tmp_path)
    registry = factory._adapter.registry
    registry.begin_hold((str(tmp_path),), cohort_id="runtime-hold")
    with pytest.raises(WriterAdmissionDenied):
        factory.validate_entry(path=tmp_path / "receipt.json")
    assert not (tmp_path / "receipt.json").exists()


def test_runtime_adapter_rejects_symlinked_parent(tmp_path: Path):
    factory = _factory(tmp_path)
    outside = tmp_path.parent / "runtime-outside"
    outside.mkdir()
    link = tmp_path / "reports"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(WriterAdmissionDenied):
        with factory.for_operation("task", path=link / "receipt.json"):
            pass


def test_runtime_context_expiry_is_checked_before_bytes(tmp_path: Path):
    factory = _factory(tmp_path)
    path = tmp_path / "receipt.json"
    with pytest.raises(WriterAdmissionDenied):
        with factory.for_operation("task", path=path) as context:
            lease = next(iter(factory._adapter.registry._leases.values()))
            lease._deadline = time.monotonic() - 1
            factory.assert_context(context)
    assert not path.exists()


def test_runtime_context_cannot_cross_threads(tmp_path: Path):
    factory = _factory(tmp_path)
    path = tmp_path / "thread.json"
    result: list[str] = []
    with factory.for_operation("task", path=path) as context:

        def check() -> None:
            try:
                factory.assert_context(context)
            except WriterAdmissionDenied:
                result.append("denied")

        worker = threading.Thread(target=check)
        worker.start()
        worker.join()
    assert result == ["denied"]


@pytest.mark.parametrize("kind", ["traversal", "parent_symlink", "leaf_symlink", "wrong_root"])
def test_runtime_unsafe_path_denies_before_planner_or_bytes(tmp_path, kind):
    from nexus.services.unified_runtime import UnifiedRuntime
    from tests.services.test_unified_runtime import _request

    factory = _factory(tmp_path)
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    if kind == "traversal":
        path = tmp_path / ".." / outside.name / "receipt.json"
    elif kind == "parent_symlink":
        (tmp_path / "link").symlink_to(outside, target_is_directory=True)
        path = tmp_path / "link" / "receipt.json"
    elif kind == "leaf_symlink":
        path = tmp_path / "receipt.json"
        path.symlink_to(outside / "receipt.json")
    else:
        path = outside / "receipt.json"

    class NoPlanner:
        def __getattr__(self, name):
            pytest.fail("planner reached before unsafe path denial: " + name)

    with pytest.raises(WriterAdmissionDenied):
        UnifiedRuntime(planner=NoPlanner()).run(
            _request(), receipt_path=path, runtime_writer_factory=factory
        )
    with pytest.raises(WriterAdmissionDenied):
        with factory.for_operation("denied", path=path):
            pytest.fail("unsafe operation admitted")
    assert not (outside / "receipt.json").exists()
    assert not factory._adapter.registry._lease_history


def test_runtime_loaded_root_replacement_denied(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    factory = _factory(root)
    root.rename(tmp_path / "original")
    root.mkdir()
    with pytest.raises(WriterAdmissionDenied, match="physical identity"):
        factory._adapter.validate_path(root / "receipt.json")


def test_runtime_replayed_context_and_operation_denied(tmp_path):
    factory = _factory(tmp_path)
    path = tmp_path / "receipt.json"
    with factory.for_operation("task", path=path, operation_id="once") as context:
        factory.assert_context(context)
    with pytest.raises(WriterAdmissionDenied, match="active"):
        factory.assert_context(context)
    with pytest.raises(WriterAdmissionDenied):
        with factory.for_operation("task", path=path, operation_id="once"):
            pytest.fail("replayed operation admitted")
    assert not path.exists()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires actual fork")
def test_runtime_forked_factory_and_context_denied(tmp_path):
    factory = _factory(tmp_path)
    path = tmp_path / "fork.json"
    with factory.for_operation("task", path=path) as context:
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(read_fd)
            denied = 0
            try:
                for check in (
                    lambda: factory.validate_entry(path=path),
                    lambda: factory.assert_context(context),
                ):
                    try:
                        check()
                    except WriterAdmissionDenied:
                        denied += 1
                os.write(write_fd, str(denied).encode())
            finally:
                os._exit(0)
        os.close(write_fd)
        result = os.read(read_fd, 10)
        os.close(read_fd)
        _, status = os.waitpid(pid, 0)
        assert status == 0
        assert result == b"2"
    assert not path.exists()


@pytest.mark.parametrize("marker_kind", ["file", "directory", "symlink"])
def test_runtime_without_factory_denies_physical_hold_before_planner(tmp_path, marker_kind):
    from nexus.services.unified_runtime import UnifiedRuntime
    from tests.services.test_unified_runtime import _request

    marker = tmp_path / ".nexus" / "writer-quiescence-hold.json"
    marker.parent.mkdir()
    if marker_kind == "file":
        marker.write_text("corrupt")
    elif marker_kind == "directory":
        marker.mkdir()
    else:
        marker.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="runtime_writer_factory_required"):
        UnifiedRuntime(planner=object()).run(
            _request(), receipt_path=tmp_path / "new" / "receipt.json"
        )
    assert not (tmp_path / "new").exists()


def test_explicit_p6_context_keeps_receipt_and_effect_compatibility(tmp_path):
    from dataclasses import replace

    from nexus.events.effect_journal import EffectDispatchPort, EffectJournal, EffectReconcilePort
    from nexus.services.unified_runtime import UnifiedRuntime
    from tests.services.test_unified_runtime import _online, _Planner, _request

    factory = _factory(tmp_path)
    adapter = factory._adapter
    path = tmp_path / "receipt.json"
    journal = EffectJournal(tmp_path, adapter.writer_generation)
    calls = []
    with owner_transaction_guard(
        replace(adapter.binding, transaction_id="explicit"),
        previous_manifest_sha256=read_manifest(tmp_path).manifest_sha256,
        writer_generation=adapter.writer_generation,
        selections=(
            StateOwnerSelection("receipt", "runtime_receipt", "receipt.json"),
            StateOwnerSelection("effect", "effect_journal", ".nexus/events/effect_journal.v1.json"),
        ),
    ) as context:

        def online(payload):
            calls.append(payload["task_id"])
            return _online(payload)

        output = UnifiedRuntime(planner=_Planner()).run(
            _request(),
            online_invoker=online,
            receipt_path=path,
            owner_context=context,
            effect_journal=journal,
            effect_dispatch=EffectDispatchPort(lambda operation: operation()),
            effect_reconcile=EffectReconcilePort(lambda _record: None),
            effect_fenced=True,
        )
        commit_owner_transaction(context)
    assert len(calls) == 1
    assert path.is_file()
    assert output["effect_journal_bindings"]
    assert all(
        journal.get(item["effect_id"])["state"] == "COMPLETED"
        for item in output["effect_journal_bindings"]
    )
    assert not adapter.registry._lease_history
