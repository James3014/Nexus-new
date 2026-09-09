"""Regression coverage for the source-owned production writer assembly seam."""

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from nexus.contracts.state_owner_transition import WriterTransitionRequest
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.state_owner_transition_service import (
    StateOwnerTransitionService,
    TransitionServiceError,
)
from nexus.orchestrator.unified_mcp_gateway import (
    LoadedWriterCollectorPlan,
    UnifiedMCPGateway,
)
from nexus.orchestrator.writer_activation_assembly import (
    WriterAssemblyError,
    load_writer_assembly,
)
from tests.nexus.orchestrator.test_state_owner_transition_service import _setup


def _loaded_vector(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    raw["drain_receipt_id"] = raw["transaction_id"]
    request = WriterTransitionRequest.from_mapping(raw)
    plan = LoadedWriterCollectorPlan(
        request_digest=request.request_digest,
        cohort_id=request.transaction_id,
        root_id=request.root_id,
        root=root.resolve(),
        source_head=request.expected_source_head,
        source_tree=request.expected_source_tree,
        generation=request.expected_generation or 0,
        writer_id=request.expected_writer_id,
        source_receipt=(tmp_path / "source.receipt").resolve(),
        snapshot_receipt=(tmp_path / "snapshot.receipt").resolve(),
        rollback_receipt=(tmp_path / "rollback.receipt").resolve(),
        writer_plan_receipt=(tmp_path / "writer-plan.receipt").resolve(),
        artifacts=("state.json",),
    )
    return root, source_root, source, request, plan


def _real_gateway(tmp_path, source):
    root = tmp_path / "gateway-root"
    root.mkdir()
    service = SelfHostedTaskService(root, ephemeral=True, auto_reconcile=False)
    gateway = UnifiedMCPGateway(service=service)
    assert gateway.bootstrap_writer_admission() == "HELD"
    return root, service, gateway


def test_loaded_assembly_accepts_generic_two_root_vector(tmp_path, monkeypatch):
    root, source_root, source, request, plan = _loaded_vector(tmp_path, monkeypatch)
    second_root = tmp_path / "runtime"
    second_root.mkdir()
    second_request = replace(
        request,
        root_id="runtime",
        expected_root_identity=hashlib.sha256(str(second_root.resolve()).encode()).hexdigest(),
    )
    second_plan = replace(
        plan,
        request_digest=second_request.request_digest,
        root_id="runtime",
        root=second_root.resolve(),
        writer_id=second_request.expected_writer_id,
    )
    assembly = load_writer_assembly(
        source_root=source_root.resolve(),
        source_head=request.expected_source_head,
        source_tree=request.expected_source_tree,
        plans=(plan, second_plan),
        requests=(request, second_request),
    )
    assert assembly.ordered_roots == (root.resolve(), second_root.resolve())
    assert assembly.plan_for(second_request) is second_plan
    with pytest.raises(WriterAssemblyError, match="PRODUCTION_VECTOR_REQUIRED"):
        assembly.bind_production_transitions(None)


def test_loaded_assembly_rejects_duplicate_root(tmp_path, monkeypatch):
    _root, source_root, _source, request, plan = _loaded_vector(tmp_path, monkeypatch)
    with pytest.raises(WriterAssemblyError, match="ASSEMBLY_ROOTS_NOT_UNIQUE"):
        load_writer_assembly(
            source_root=source_root.resolve(),
            source_head=request.expected_source_head,
            source_tree=request.expected_source_tree,
            plans=(plan, plan),
            requests=(request, request),
        )


def test_loaded_assembly_rejects_duplicate_request_digest(tmp_path, monkeypatch):
    _root, source_root, _source, request, plan = _loaded_vector(tmp_path, monkeypatch)
    second_root = tmp_path / "runtime"
    second_root.mkdir()
    second_request = replace(
        request,
        root_id="runtime",
        expected_root_identity=hashlib.sha256(str(second_root.resolve()).encode()).hexdigest(),
    )
    duplicate_request = object.__new__(
        type("_DuplicateDigestRequest", (WriterTransitionRequest,), {})
    )
    for field in WriterTransitionRequest.__dataclass_fields__:
        object.__setattr__(duplicate_request, field, getattr(second_request, field))
    duplicate_request.__class__.request_digest = property(lambda self: request.request_digest)
    second_plan = replace(
        plan,
        root_id="runtime",
        root=second_root.resolve(),
        writer_id=second_request.expected_writer_id,
        # A duplicated digest must never make by_request_digest ambiguous.
        request_digest=plan.request_digest,
    )
    with pytest.raises(WriterAssemblyError, match="DIGEST"):
        load_writer_assembly(
            source_root=source_root.resolve(),
            source_head=request.expected_source_head,
            source_tree=request.expected_source_tree,
            plans=(plan, second_plan),
            requests=(request, duplicate_request),
        )


def test_transition_binds_real_gateway_collector_port(tmp_path, monkeypatch):
    _root, source_root, source, request, _plan = _loaded_vector(tmp_path, monkeypatch)
    root, service, gateway = _real_gateway(tmp_path, source)
    transition_service = StateOwnerTransitionService(
        roots={request.root_id: root},
        source=source,
        source_root=source_root,
        service=service,
    )
    transition_service.bind_collector_port(gateway._writer_transition_collector)
    assert transition_service._collector_port.__self__ is gateway


def test_transition_rejects_wrong_service_and_arbitrary_callback(tmp_path, monkeypatch):
    _root, source_root, source, request, _plan = _loaded_vector(tmp_path, monkeypatch)
    root, first, first_gateway = _real_gateway(tmp_path, source)
    other_root = tmp_path / "other"
    other_root.mkdir()
    second = SelfHostedTaskService(other_root, ephemeral=True, auto_reconcile=False)
    second_gateway = UnifiedMCPGateway(service=second)
    assert second_gateway.bootstrap_writer_admission() == "HELD"
    transition_service = StateOwnerTransitionService(
        roots={request.root_id: root},
        source=source,
        source_root=source_root,
        service=first,
    )
    with pytest.raises(TransitionServiceError, match="COLLECTOR_PORT_SERVICE_MISMATCH"):
        transition_service.bind_collector_port(second_gateway._writer_transition_collector)
    with pytest.raises(TypeError, match="source-owned collector port"):
        transition_service.bind_collector_port(lambda _request: {})


def _three_root_bridge(tmp_path, monkeypatch):
    """Real A authority stores, actual B callbacks and direct Gateway collector.

    Only publication storage/remote readback is isolated.  Neither A nor the
    collector result is substituted. No positive writer exists before A.
    """
    import json
    import subprocess
    import threading

    from nexus.events.effect_journal import EffectDispatchPort, EffectReconcilePort
    from nexus.events.log_store import JsonlEventLogStore
    from nexus.events.transport import NexusEventBus
    from nexus.orchestrator import state_owner_transition_authority as authority
    from nexus.orchestrator import state_owner_transition_service as transitions
    from nexus.orchestrator.writer_activation_cohort import (
        ActivationRoot,
        InitialActivationRootSpec,
        InitialEventOwner,
        InitialRuntimeOwner,
        InitialTaskOwner,
        WriterActivationCohort,
    )
    from nexus.orchestrator.writer_activation_producer import build_loaded_writer_collector_plan
    from nexus.orchestrator.writer_quiescence import WriterIdentity

    task_root, source_root, source, template = _setup(
        tmp_path, monkeypatch, card_scope={"root_ids": ["task", "event", "runtime"]}
    )
    event_root, runtime_root = tmp_path / "event-root", tmp_path / "runtime-root"
    event_root.mkdir()
    runtime_root.mkdir()
    service = SelfHostedTaskService(task_root, ephemeral=True, auto_reconcile=False)
    service.loaded_source_identity = source
    service.writer_roots = {"task": task_root, "event": event_root, "runtime": runtime_root}
    gateway = UnifiedMCPGateway(service=service)
    registry = gateway._writer_quiescence_registry

    class BridgeBus(NexusEventBus):
        _log_store = JsonlEventLogStore()
        _event_log_path = None
        _writer_factory = None
        _subscribers = {}
        _attempt_sequences = {}
        _production_event_root = None
        _configured_event_root = None

    owners = (
        InitialTaskOwner(service),
        InitialEventOwner(BridgeBus._log_store, BridgeBus),
        InitialRuntimeOwner(
            EffectDispatchPort(lambda operation: operation()),
            EffectReconcilePort(lambda record: None),
        ),
    )
    inventory = (
        (("task_state", "state.json", b'{"task_id":"state","status":"CANCELLED"}'),),
        (("event_log", ".nexus/events/event_log.jsonl", b""),),
        (
            ("runtime_receipt", "seed.json", b"{}"),
            (
                "effect_journal",
                ".nexus/events/effect_journal.v1.json",
                b'{"schema":"nexus.runtime_effect_journal.v1","records":{}}',
            ),
        ),
    )
    thread = threading.current_thread()
    for (root_id, root), entries in zip(service.writer_roots.items(), inventory):
        for role, relative, data in entries:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            identity = WriterIdentity(
                str(root.resolve()),
                role,
                registry.source_identity,
                registry.process_start_identity,
                str(thread.ident),
                0,
                f"old-{root_id}",
            )
            snapshot = (
                (
                    lambda: (
                        service.writer_quiescence_snapshot_bytes()
                        + gateway._writer_assist_snapshot_bytes()
                    )
                )
                if role == "task_state"
                else lambda path=path: path.read_bytes()
            )
            registry.register(
                identity,
                snapshot=snapshot,
                process_state=lambda: "alive" if thread.is_alive() else "dead",
                pending=(
                    lambda: (
                        *service.writer_quiescence_pending_work(),
                        *gateway._writer_assist_pending_work(),
                    )
                )
                if role == "task_state"
                else lambda: tuple(registry._leases),
                loaded_identity=lambda identity=identity: identity,
            )
    hold = registry.begin_hold(tuple(service.writer_roots.values()), cohort_id="bridge-cohort")
    for item in hold.selected:
        i = item.identity
        hold.acknowledge(i.writer_id, root=i.root, role=i.role, generation=i.generation)
    observed = hold.finalize()
    assert observed.drain_state == "DRAINED", observed.to_bytes()
    drain = registry.persist_finalized(hold)
    authority_template = json.loads((tmp_path / "authority.json").read_bytes())
    sources, plans, requests, loaded = {}, [], [], []
    source_receipt = tmp_path / "source.receipt"
    source_receipt.write_bytes(b"accepted")
    for (root_id, root), entries, owner in zip(service.writer_roots.items(), inventory, owners):
        evidence = {}
        raw = dict(template)
        for field in ("snapshot_receipt", "rollback_receipt", "loaded_writer_plan"):
            p = tmp_path / f"{root_id}-{field}.json"
            p.write_text(json.dumps({"receipt_id": f"{root_id}-{field}"}, sort_keys=True))
            raw[field + "_id"] = f"{root_id}-{field}"
            raw[field + "_hash"] = hashlib.sha256(p.read_bytes()).hexdigest()
            evidence[field] = p
        raw.update(
            root_id=root_id,
            expected_root_identity=hashlib.sha256(str(root.resolve()).encode()).hexdigest(),
            expected_generation=None,
            expected_manifest_sha256=None,
            expected_writer_id=f"old-{root_id}",
            next_generation=1,
            next_writer_id=f"new-{root_id}",
            transaction_id=hold.cohort_id,
            request_id=f"request-{root_id}",
            idempotency_key=f"idempotency-{root_id}",
            drain_receipt_id=hold.cohort_id,
            drain_receipt_hash=hashlib.sha256(drain.to_bytes()).hexdigest(),
            selections=[
                dict(
                    entry_id=role,
                    role=role,
                    relative_path=relative,
                    size=len(data),
                    expected_sha256=hashlib.sha256(data).hexdigest(),
                )
                for role, relative, data in entries
            ],
        )
        preliminary = WriterTransitionRequest.from_mapping(raw)
        payload = dict(authority_template)
        payload.update(
            root_id=root_id,
            authorization_intent_digest=preliminary.authorization_intent_digest,
            operation_digest=preliminary.authorization_intent_digest,
            effect_hash=authority._effect_hash(preliminary),
        )
        data = json.dumps(payload, sort_keys=True).encode()
        mirror = tmp_path / f"mirror-{root_id}"
        subprocess.run(["git", "clone", "--quiet", str(source_root), str(mirror)], check=True)
        for args in (
            ("config", "user.name", "Test"),
            ("config", "user.email", "test@example.invalid"),
            ("remote", "set-url", "origin", authority.EXPECTED_REMOTE),
        ):
            subprocess.run(["git", "-C", str(mirror), *args], check=True, capture_output=True)
        tracked = mirror / authority.TRACKED_RELATIVE
        tracked.parent.mkdir(parents=True, exist_ok=True)
        tracked.write_bytes(data)
        for args in (
            ("add", "."),
            ("commit", "-m", "publish exact bridge authority"),
            ("update-ref", "refs/remotes/origin/main", "HEAD"),
        ):
            subprocess.run(["git", "-C", str(mirror), *args], check=True, capture_output=True)
        durable = tmp_path / f"authority-{root_id}.json"
        durable.write_bytes(data)
        sources[root_id] = mirror, durable
        raw["authority_receipt_hash"] = hashlib.sha256(data).hexdigest()
        request = WriterTransitionRequest.from_mapping(raw)
        plans.append(
            build_loaded_writer_collector_plan(
                gateway=gateway,
                hold=hold,
                request=request,
                source_receipt=source_receipt,
                snapshot_receipt=evidence["snapshot_receipt"],
                rollback_receipt=evidence["rollback_receipt"],
                writer_plan_receipt=evidence["loaded_writer_plan"],
                artifacts=tuple(e[1] for e in entries),
            )
        )
        requests.append(request)
    real_load = authority.load_verified_writer_transition_authority

    def isolated_publication(*, request, loaded_source_identity):
        mirror, durable = sources[request.root_id]
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(authority, "MIRROR_ROOT", mirror)
            patch.setattr(authority, "DURABLE_PATH", durable)
            patch.setattr(
                authority,
                "_remote_main_head",
                lambda: subprocess.check_output(
                    ["git", "-C", str(mirror), "rev-parse", "HEAD"], text=True
                ).strip(),
            )
            return real_load(request=request, loaded_source_identity=loaded_source_identity)

    monkeypatch.setattr(
        transitions, "load_verified_writer_transition_authority", isolated_publication
    )
    monkeypatch.setattr(transitions, "_COLLECTOR_LOADER", None)
    assembly = load_writer_assembly(
        source_root=source_root.resolve(),
        source_head=source.source_head,
        source_tree=source.source_tree,
        plans=plans,
        requests=requests,
    )
    bound_transitions = assembly.bind_production_transitions(gateway)
    for (root_id, root), entries, owner, transition in zip(
        service.writer_roots.items(), inventory, owners, bound_transitions
    ):
        request = transition.request
        spec = InitialActivationRootSpec(
            str(root.resolve()),
            entries[0][0],
            transition,
            request.expected_root_identity,
            1,
            request.next_writer_id,
            owner,
        )
        loaded.append(
            ActivationRoot(
                str(root.resolve()),
                entries[0][0],
                transition,
                None,
                request.expected_root_identity,
                1,
                request.next_writer_id,
                None,
                initial_spec=spec,
            )
        )
    assembly.validate_cohort_inputs(registry, hold, loaded)
    return gateway, assembly, WriterActivationCohort(registry, hold, loaded)


def test_real_three_root_gateway_collector_direct_A_and_F_writes(tmp_path, monkeypatch):
    from nexus.contracts.state_owner_transition import ReceiptState
    from nexus.orchestrator.state_owner_transition_service import LoadedRootTransition
    from tests.integration.test_writer_activation_cohort import _write_four_roles

    gateway, assembly, cohort = _three_root_bridge(tmp_path, monkeypatch)
    assert len(assembly.ordered_roots) == 3
    assert len(cohort.hold.selected) == 4
    for root in cohort.roots:
        assert type(root.transition) is LoadedRootTransition
        ready = root.transition.preflight()
        assert ready.state is ReceiptState.PREFLIGHT_READY, ready.to_dict()
    active = cohort.activate()
    assert active.state == "ACTIVE", active.to_dict()
    assert len(active.transitions) == 3
    assert all(item["state"] == "COMMITTED" for item in active.transitions)
    assert cohort.release(active).state == "RELEASED"
    _write_four_roles(cohort, "real-direct-bridge")


def test_direct_loaded_A_apply_uses_bound_port_without_global_loader(tmp_path, monkeypatch):
    from nexus.contracts.state_owner_transition import ReceiptState
    from nexus.events.state_owner_manifest import read_manifest

    gateway, _assembly, cohort = _three_root_bridge(tmp_path, monkeypatch)
    transition = cohort.roots[2].transition  # both runtime roles, one real A
    result = transition.preflight()
    assert result.state is ReceiptState.PREFLIGHT_READY, result.to_dict()
    result = transition.apply()
    assert result.state is ReceiptState.COMMITTED, result.to_dict()
    assert read_manifest(Path(cohort.roots[2].root)).state == "COMMITTED"
    assert gateway._writer_quiescence_registry._held_roots[cohort.roots[2].root] is cohort.hold
    assert all(item.identity.generation == 0 for item in cohort.hold.selected)


@pytest.mark.parametrize("root_index", [1, 2])
def test_non_task_observer_drift_denies_real_A_before_any_commit(tmp_path, monkeypatch, root_index):
    from nexus.contracts.state_owner_transition import ReceiptState
    from nexus.events.state_owner_manifest import read_manifest

    _gateway, _assembly, cohort = _three_root_bridge(tmp_path, monkeypatch)
    root = cohort.roots[root_index]
    path = Path(root.root) / root.transition.request.selections[0].relative_path
    path.write_bytes(path.read_bytes() + b"\n")
    result = root.transition.preflight()
    assert result.state is not ReceiptState.PREFLIGHT_READY
    assert "LOADED_COLLECTOR_OBSERVATION_CHANGED" in str(result.to_dict())
    assert all(read_manifest(Path(item.root)) is None for item in cohort.roots)
    assert all(cohort.registry._held_roots[item.root] is cohort.hold for item in cohort.roots)


def test_direct_constructor_freezes_lists_and_rejects_untyped_items(tmp_path, monkeypatch):
    from nexus.orchestrator.writer_activation_assembly import LoadedWriterAssembly

    _root, source_root, _source, request, plan = _loaded_vector(tmp_path, monkeypatch)
    plans, requests = [plan], [request]
    assembly = LoadedWriterAssembly(
        source_root.resolve(), plan.source_head, plan.source_tree, plans, requests
    )
    plans.clear()
    requests.clear()
    assert assembly.plans == (plan,) and assembly.requests == (request,)
    with pytest.raises(WriterAssemblyError, match="TYPED_INPUT"):
        LoadedWriterAssembly(
            source_root.resolve(), plan.source_head, plan.source_tree, [object()], [request]
        )


@pytest.mark.parametrize(
    "field", ["cohort", "generation", "writer", "artifacts", "operation", "root_hash"]
)
def test_descriptor_rejects_exact_contract_drift(tmp_path, monkeypatch, field):
    from nexus.contracts.state_owner_transition import Operation

    _root, source_root, _source, request, plan = _loaded_vector(tmp_path, monkeypatch)
    if field == "cohort":
        plan = replace(plan, cohort_id="foreign")
    elif field == "generation":
        plan = replace(plan, generation=plan.generation + 1)
    elif field == "writer":
        plan = replace(plan, writer_id="foreign")
    elif field == "artifacts":
        plan = replace(plan, artifacts=("foreign.json",))
    elif field == "operation":
        request = replace(request, operation=Operation.PREFLIGHT)
        plan = replace(plan, request_digest=request.request_digest)
    else:
        request = replace(request, expected_root_identity="f" * 64)
        plan = replace(plan, request_digest=request.request_digest)
    with pytest.raises(WriterAssemblyError, match="PLAN_REQUEST_MISMATCH"):
        load_writer_assembly(
            source_root=source_root.resolve(),
            source_head=plan.source_head,
            source_tree=plan.source_tree,
            plans=(plan,),
            requests=(request,),
        )


def test_descriptor_rejects_nested_roots(tmp_path, monkeypatch):
    root, source_root, _source, request, plan = _loaded_vector(tmp_path, monkeypatch)
    nested = root / "nested"
    nested.mkdir()
    second = replace(
        request,
        root_id="nested",
        expected_root_identity=hashlib.sha256(str(nested).encode()).hexdigest(),
    )
    second_plan = replace(plan, root=nested, root_id="nested", request_digest=second.request_digest)
    with pytest.raises(WriterAssemblyError, match="ROOTS_OVERLAP"):
        load_writer_assembly(
            source_root=source_root.resolve(),
            source_head=plan.source_head,
            source_tree=plan.source_tree,
            plans=(plan, second_plan),
            requests=(request, second),
        )


def test_direct_port_rejects_lookalike_and_other_gateway_method(tmp_path, monkeypatch):
    _root, source_root, source, request, _plan = _loaded_vector(tmp_path, monkeypatch)
    root, service, gateway = _real_gateway(tmp_path, source)
    transition = StateOwnerTransitionService(
        roots={request.root_id: root}, source=source, source_root=source_root, service=service
    )

    class PretendGateway:
        def collector(self, _request):
            return {}

    pretend = PretendGateway()
    pretend.service = service
    pretend._writer_quiescence_registry = gateway._writer_quiescence_registry
    for port in (pretend.collector, gateway._gateway_status):
        with pytest.raises(TypeError, match="source-owned collector port"):
            transition.bind_collector_port(port)
    transition.bind_collector_port(gateway._writer_transition_collector)
    transition.bind_collector_port(gateway._writer_transition_collector)
