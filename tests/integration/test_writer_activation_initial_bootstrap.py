"""Initial empty-root writer activation coverage."""

import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.events.log_store import JsonlEventLogStore
from nexus.events.state_owner_manifest import (
    StateOwnerBinding,
    StateOwnerSelection,
    commit_owner_transaction,
    owner_transaction_guard,
)
from nexus.events.transport import EventWriterAdapter, EventWriterFactory
from nexus.events.writer_generation import EventWriterGeneration, install_generation
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.state_owner_transition_service import LoadedRootTransition
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from nexus.orchestrator.writer_activation_producer import (
    InitialActivationRoot,
    WriterActivationProducer,
    build_loaded_writer_collector_plan,
)


def _bind_real_source_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the installed payload a real, isolated Git source identity."""
    import nexus
    from nexus.orchestrator import unified_mcp_gateway as gateway_module

    source_root = tmp_path / "source-fixture"
    shutil.copytree(Path(nexus.__file__).resolve().parent, source_root / "nexus")
    subprocess.check_call(["git", "-C", str(source_root), "init", "-b", "main"])
    subprocess.check_call(["git", "-C", str(source_root), "config", "user.name", "Test"])
    subprocess.check_call(
        ["git", "-C", str(source_root), "config", "user.email", "test@example.invalid"]
    )
    subprocess.check_call(["git", "-C", str(source_root), "add", "nexus"])
    subprocess.check_call(["git", "-C", str(source_root), "commit", "-m", "source"])
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", source_root)


def test_real_loaded_transition_preflights_after_gateway_hold(tmp_path, monkeypatch):
    from nexus.contracts.state_owner_transition import WriterTransitionRequest
    from nexus.orchestrator.state_owner_transition_service import StateOwnerTransitionService
    from tests.nexus.orchestrator.test_state_owner_transition_service import _setup
    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    # Make the actual service observer terminal before opening the gateway
    # hold.  Rebind the source-owned authority blob to the changed selection;
    # its source head remains an ancestor, which is the transition service's
    # supported card-only freshness rule.
    state = b'{"status":"DIRECT_COMPLETED","task_id":"task"}'
    (root / "state.json").write_bytes(state)
    raw["selections"][0].update(expected_sha256=hashlib.sha256(state).hexdigest(), size=len(state))
    request = WriterTransitionRequest.from_mapping(raw)
    from nexus.orchestrator import state_owner_transition_authority as authority
    mirror_root = tmp_path / "mirror"
    authority_path = mirror_root / authority.TRACKED_RELATIVE
    authority_payload = json.loads(authority_path.read_text())
    authority_payload["authorization_intent_digest"] = request.authorization_intent_digest
    authority_payload["operation_digest"] = request.authorization_intent_digest
    authority_payload["effect_hash"] = authority._effect_hash(request)
    authority_bytes = json.dumps(authority_payload, sort_keys=True).encode()
    authority_path.write_bytes(authority_bytes)
    subprocess.check_call(["git", "-C", str(mirror_root), "add", str(authority.TRACKED_RELATIVE)])
    subprocess.check_call(["git", "-C", str(mirror_root), "commit", "-m", "rebind transition fixture"])
    subprocess.check_call(["git", "-C", str(mirror_root), "update-ref", "refs/remotes/origin/main", "HEAD"])
    raw["authority_receipt_hash"] = hashlib.sha256(authority_bytes).hexdigest()
    (tmp_path / "authority.json").write_bytes(authority_bytes)
    request = WriterTransitionRequest.from_mapping(raw)
    monkeypatch.setattr(authority, "MIRROR_ROOT", mirror_root)
    transition_service = StateOwnerTransitionService(
        roots={request.root_id: root}, source=source, source_root=source_root
    )
    transition = transition_service.loaded_root_transition(request)
    service = SelfHostedTaskService(root, ephemeral=True, auto_reconcile=False)
    service.loaded_source_identity = transition_service._source
    gateway = UnifiedMCPGateway(service=service)
    assert gateway.bootstrap_writer_admission() == "HELD"
    # Bind A's collector to the gateway's finalized physical hold receipt;
    # the source transition must consume the same DRAINED evidence that gated
    # ingress rather than the fixture's earlier collector lambda.
    import nexus.orchestrator.state_owner_transition_service as transition_module
    monkeypatch.setattr(transition_module, "_COLLECTOR_LOADER", lambda req: gateway._writer_transition_collector(req))
    registry = gateway._writer_quiescence_registry
    hold = registry._held_roots[str(root.resolve())]
    assert registry.load_finalized(hold.cohort_id).drain_state == "DRAINED"

    # Materialize the source-owned evidence files before binding the plan.
    # Their IDs and hashes are copied into the typed request below; the
    # collector consequently reads the same bytes that A is authorized to
    # consume.
    evidence = tmp_path / "writer-evidence"
    evidence.mkdir()
    evidence_paths = {}
    for name, payload in {
        "snapshot": {"receipt_id": "snapshot-cold-start", "root": str(root.resolve())},
        "rollback": {"receipt_id": "rollback-cold-start", "root": str(root.resolve())},
        "writer-plan": {"receipt_id": "writer-plan-cold-start", "root": str(root.resolve())},
    }.items():
        path = evidence / f"{name}.json"
        path.write_bytes(json.dumps(payload, sort_keys=True).encode())
        evidence_paths[name] = path
    raw.update(
        drain_receipt_id=hold.cohort_id,
        drain_receipt_hash=hashlib.sha256(registry.load_finalized(hold.cohort_id).to_bytes()).hexdigest(),
        snapshot_receipt_id="snapshot-cold-start",
        snapshot_receipt_hash=hashlib.sha256(evidence_paths["snapshot"].read_bytes()).hexdigest(),
        rollback_receipt_id="rollback-cold-start",
        rollback_receipt_hash=hashlib.sha256(evidence_paths["rollback"].read_bytes()).hexdigest(),
        loaded_writer_plan_id="writer-plan-cold-start",
        loaded_writer_plan_hash=hashlib.sha256(evidence_paths["writer-plan"].read_bytes()).hexdigest(),
        transaction_id=hold.cohort_id,
    )
    identity = next(
        item.identity
        for item in registry._writers.values()
        if item.identity.root == str(root.resolve())
    )
    raw["expected_writer_id"] = identity.writer_id
    request = WriterTransitionRequest.from_mapping(raw)
    authority_payload = json.loads(authority_path.read_text())
    authority_payload["authorization_intent_digest"] = request.authorization_intent_digest
    authority_payload["operation_digest"] = request.authorization_intent_digest
    authority_payload["effect_hash"] = authority._effect_hash(request)
    authority_bytes = json.dumps(authority_payload, sort_keys=True).encode()
    authority_path.write_bytes(authority_bytes)
    subprocess.check_call(["git", "-C", str(mirror_root), "add", str(authority.TRACKED_RELATIVE)])
    subprocess.check_call(["git", "-C", str(mirror_root), "commit", "-m", "bind cold-start evidence"])
    subprocess.check_call(["git", "-C", str(mirror_root), "update-ref", "refs/remotes/origin/main", "HEAD"])
    raw["authority_receipt_hash"] = hashlib.sha256(authority_bytes).hexdigest()
    (tmp_path / "authority.json").write_bytes(authority_bytes)
    request = WriterTransitionRequest.from_mapping(raw)
    transition = transition_service.loaded_root_transition(request)
    plan = build_loaded_writer_collector_plan(
        gateway=gateway,
        hold=hold,
        request=request,
        source_receipt=tmp_path / "accepted-source.receipt",
        snapshot_receipt=evidence_paths["snapshot"],
        rollback_receipt=evidence_paths["rollback"],
        writer_plan_receipt=evidence_paths["writer-plan"],
        artifacts=("state.json",),
    )
    (tmp_path / "accepted-source.receipt").write_bytes(b"accepted")
    service.loaded_writer_collector_plan = plan
    gateway._bind_loaded_writer_collector_plan()
    preflight = transition.preflight()
    assert preflight.state.value == "PREFLIGHT_READY", preflight.error
    committed = transition.apply()
    assert committed.state.value == "COMMITTED"
    assert registry._held_roots[str(root.resolve())] is hold
    from nexus.events.state_owner_manifest import read_manifest
    from nexus.events.writer_generation import read_generation
    manifest = read_manifest(root)
    generation = read_generation(root)
    assert manifest is not None and manifest.state == "COMMITTED"
    assert generation is not None and generation.generation == request.next_generation
    drift_path = gateway._assist_root() / "drift.json"
    drift_path.write_text(json.dumps({"task_id": "drift", "status": "PENDING"}))
    with pytest.raises(Exception):
        gateway._writer_transition_collector(request)
    drift_path.unlink()
    attachment = registry.issue_initial_attachment(
        hold,
        root=str(root.resolve()),
        generation=generation.generation,
        writer_id=generation.writer_id,
        manifest_sha256=manifest.manifest_sha256,
    )
    from nexus.events.log_store import JsonlEventLogStore
    from nexus.events.state_owner_manifest import StateOwnerBinding
    from nexus.events.transport import EventWriterAdapter, EventWriterFactory
    factory = EventWriterFactory(EventWriterAdapter(
        registry,
        binding=StateOwnerBinding(request.expected_owner_id, root.resolve(), generation.generation, request.transaction_id),
        writer_generation=generation,
        root=root.resolve(),
        writer_id=generation.writer_id,
        initial_attachment=attachment,
    ))
    store = JsonlEventLogStore()
    store.configure(root.resolve(), writer_generation=generation, enforce_generation=True,
                    writer_factory=factory, initial_handle=attachment)
    with pytest.raises(Exception):
        store.append_record({"event_type": "test_event", "payload": {}})


def test_empty_root_holds_generation_zero_until_a_and_materialization(tmp_path, monkeypatch):
    _bind_real_source_fixture(tmp_path, monkeypatch)
    service = SelfHostedTaskService(tmp_path, ephemeral=True, auto_reconcile=False)
    token = EventWriterGeneration(1, "initial-writer")
    transaction = "initial-transaction"
    paths = {
        "task_state": "task-state.bin",
        "runtime_receipt": "runtime-receipt.bin",
        "event_log": ".nexus/events/event_log.jsonl",
        "effect_journal": ".nexus/events/effect_journal.v1.json",
    }
    for relative in paths.values():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    gateway = UnifiedMCPGateway(service=service)
    assert gateway.bootstrap_writer_admission() == "HELD"
    registry = gateway._writer_quiescence_registry
    hold = registry._held_roots[str(tmp_path.resolve())]
    observed = {"held_during_materialize": False}

    class InitialA(LoadedRootTransition):
        def __init__(self):
            object.__setattr__(self, "request", SimpleNamespace(
                root_id="root", transaction_id=transaction, expected_generation=None,
                expected_owner_id="owner",
                expected_root_identity=hashlib.sha256(str(tmp_path.resolve()).encode()).hexdigest(),
            ))

        def preflight(self):
            return SimpleNamespace(state="PREFLIGHT_READY")

        def apply(self):
            install_generation(tmp_path, token, expected_generation=None)
            binding = StateOwnerBinding("owner", tmp_path.resolve(), 1, transaction)
            selections = tuple(
                StateOwnerSelection(role, role, relative) for role, relative in paths.items()
            )
            with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
                return SimpleNamespace(
                    state="COMMITTED",
                    committed=commit_owner_transaction(context),
                )

        def reconcile(self):
            return self.apply()

    def materialize(handle):
        observed["held_during_materialize"] = str(tmp_path.resolve()) in registry._held_roots
        assert handle.generation == token
        factory = EventWriterFactory(EventWriterAdapter(
            registry,
            binding=StateOwnerBinding("owner", tmp_path.resolve(), 1, transaction),
            writer_generation=token,
            root=tmp_path.resolve(),
            writer_id=token.writer_id,
            initial_attachment=handle.attachment,
        ))
        store = JsonlEventLogStore()
        store.configure(tmp_path.resolve(), writer_generation=token,
                        enforce_generation=True, writer_factory=factory,
                        initial_handle=handle.attachment)
        with pytest.raises(Exception):
            store.append_record({"event_type": "test_event", "payload": {}})
        with pytest.raises(Exception):
            store.configure(tmp_path.resolve(), writer_generation=token,
                            enforce_generation=True, writer_factory=factory,
                            initial_handle=copy.copy(handle.attachment))
        return {"factory_roles": tuple(paths)}

    root = InitialActivationRoot(str(tmp_path.resolve()), "root", InitialA(), registry, hold)
    result = WriterActivationProducer(root, materialize=materialize).activate()
    assert result["factory_roles"] == tuple(paths)
    assert observed["held_during_materialize"]


def test_generation_zero_observer_cannot_acquire_a_write_lease(tmp_path, monkeypatch):
    _bind_real_source_fixture(tmp_path, monkeypatch)
    service = SelfHostedTaskService(tmp_path, ephemeral=True, auto_reconcile=False)
    gateway = UnifiedMCPGateway(service=service)
    assert gateway.bootstrap_writer_admission() == "HELD"
    registry = gateway._writer_quiescence_registry
    identity = next(iter(registry._writers.values())).identity
    try:
        registry.acquire(
            root=identity.root,
            role=identity.role,
            writer_id=identity.writer_id,
            generation=0,
        )
    except Exception as exc:
        assert type(exc).__name__ == "WriterAdmissionDenied"
    else:
        raise AssertionError("generation zero must remain observational")
