from __future__ import annotations

import hashlib
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from nexus.contracts.state_owner_transition import WriterTransitionRequest
from nexus.events.state_owner_manifest import (
    StateOwnerBinding,
    StateOwnerSelection,
    commit_owner_transaction,
    owner_transaction_guard,
)
from nexus.events.writer_generation import EventWriterGeneration, install_generation
from nexus.orchestrator.state_owner_transition_service import (
    LoadedRootTransition,
    StateOwnerTransitionService,
)
from nexus.orchestrator.writer_activation_cohort import (
    ActivationRoot,
    InitialActivationRootSpec,
    InitialTaskOwner,
    InitialRuntimeOwner,
    InitialEventOwner,
    WriterActivationCohort,
    WriterActivationError,
)
from nexus.orchestrator.writer_quiescence import (
    TaskStateWriterAdapter,
    WriterIdentity,
    WriterRegistry,
    current_process_start_identity,
)


# Authority isolation changes only fixture storage/remote readback. All A
# preflight/apply/reconcile and B/P6 operations below are the production methods.
class _IsolatedTransition(LoadedRootTransition):
    def _invoke(self, method):
        import subprocess

        from nexus.orchestrator import standing_grant_store as grants
        from nexus.orchestrator import state_owner_transition_authority as authority
        from nexus.orchestrator import state_owner_transition_service as service_module

        fixture = self.service._fixture
        registry = self.service._fixture_registry
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(authority, "MIRROR_ROOT", fixture / "mirror")
            patch.setattr(authority, "DURABLE_PATH", fixture / "authority.json")
            patch.setattr(
                authority,
                "_remote_main_head",
                lambda: subprocess.check_output(
                    ["git", "-C", str(fixture / "mirror"), "rev-parse", "HEAD"], text=True
                ).strip(),
            )
            patch.setattr(grants, "DEFAULT_RECEIPT_PATH", fixture / "grant/standing-grant.json")

            def collector(req):
                if getattr(self.service, "_fixture_restarted", False):
                    from nexus.orchestrator.writer_quiescence import WriterQuiescenceReceipt

                    # Original immutable A request evidence is historical; a
                    # separately finalized current B hold proves fresh drain.
                    fresh = self.service._fixture_cohort._current_drain()
                    assert fresh.drain_state == "DRAINED", fresh.to_bytes()
                    actual = WriterQuiescenceReceipt.from_bytes(
                        (fixture.parent / "original-drain.json").read_bytes()
                    )
                else:
                    actual = registry.load_finalized(self.service._fixture_hold.cohort_id)
                assert actual.drain_state == "DRAINED"
                assert actual.receipt_sha256 == req.drain_receipt_hash
                root = self.service._roots[req.root_id]
                return service_module._VerifiedCollectorEvidence({
                    **{
                        key: getattr(req, key)
                        for key in (
                            "drain_receipt_id",
                            "drain_receipt_hash",
                            "snapshot_receipt_id",
                            "snapshot_receipt_hash",
                            "rollback_receipt_id",
                            "rollback_receipt_hash",
                            "loaded_writer_plan_id",
                            "loaded_writer_plan_hash",
                        )
                    },
                    "request_digest": req.request_digest,
                    "drain_state": actual.drain_state,
                    "root_id": req.root_id,
                    "root_identity": req.expected_root_identity,
                    "source_head": req.expected_source_head,
                    "source_tree": req.expected_source_tree,
                    "generation": req.expected_generation,
                    "artifact_bytes": {
                        item.relative_path: (root / item.relative_path).read_bytes()
                        for item in req.selections
                    },
                    "source_receipt_bytes": b"accepted",
                })

            patch.setattr(service_module, "_COLLECTOR_LOADER", collector)
            return getattr(super(), method)()

    def preflight(self):
        return self._invoke("preflight")

    def apply(self):
        return self._invoke("apply")

    def reconcile(self):
        return self._invoke("reconcile")


def _real_cohort(tmp_path, roles=("task_state", "event_log", "runtime_receipt"), *, cold=False):
    import json
    import subprocess

    from nexus.events.effect_journal import EffectDispatchPort, EffectJournal, EffectReconcilePort
    from nexus.events.log_store import JsonlEventLogStore
    from nexus.events.state_owner_manifest import MANIFEST_NAME
    from nexus.events.transport import NexusEventBus, load_event_writer_factory
    from nexus.orchestrator import state_owner_transition_authority as authority
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    from nexus.orchestrator.writer_quiescence import (
        TaskStateWriterFactory,
        load_runtime_writer_factory,
    )
    from tests.nexus.orchestrator.test_state_owner_transition_service import _setup

    registry = WriterRegistry(
        source_identity="cohort-fixture-source", server_identity="fixture-server"
    )
    specs = []
    for index, role in enumerate(roles):
        name = "root-" + str(index)
        fixture = tmp_path / name
        fixture.mkdir()
        with pytest.MonkeyPatch.context() as patch:
            root, source_root, source, raw = _setup(fixture, patch, card_scope={"root_ids": [name]})
        paths = {
            "task_state": [
                ("task_state", "state.json", b'{"task_id":"state","status":"SUBMITTED"}')
            ],
            "event_log": [("event_log", ".nexus/events/event_log.jsonl", b"")],
            "runtime_receipt": [
                ("runtime_receipt", "seed.json", b"{}"),
                (
                    "effect_journal",
                    ".nexus/events/effect_journal.v1.json",
                    b'{"schema":"nexus.runtime_effect_journal.v1","records":{}}',
                ),
            ],
        }[role]
        selections = []
        for selected_role, relative, data in paths:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            selections.append(StateOwnerSelection(selected_role, selected_role, relative))
        generation = EventWriterGeneration(1, "old-" + name)
        before = None
        if not cold:
            install_generation(root, generation)
            binding = StateOwnerBinding("owner", root.resolve(), 1, "bootstrap-" + name)
            with owner_transaction_guard(
                binding, writer_generation=generation, selections=tuple(selections)
            ) as context:
                before = commit_owner_transaction(context)
        raw.update(
            root_id=name,
            expected_generation=None if cold else 1,
            next_generation=1 if cold else 2,
            expected_writer_id=generation.writer_id,
            next_writer_id="new-" + name,
            expected_manifest_sha256=None if cold else before.manifest_sha256,
            transaction_id="tx-" + name,
            request_id="request-" + name,
            idempotency_key="idempotency-" + name,
            selections=[
                dict(
                    entry_id=r,
                    role=r,
                    relative_path=p,
                    expected_sha256=hashlib.sha256(data).hexdigest(),
                    size=len(data),
                )
                for r, p, data in paths
            ],
        )
        identities = []
        for selected_role, _, _ in paths:
            identity = WriterIdentity(
                str(root.resolve()),
                selected_role,
                registry.source_identity,
                current_process_start_identity(),
                str(threading.get_ident()),
                0 if cold else 1,
                generation.writer_id,
            )
            registry.register(
                identity,
                snapshot=lambda root=root: (root / MANIFEST_NAME).read_bytes() if (root / MANIFEST_NAME).exists() else b"initial",
                process_state=lambda: (
                    "alive" if threading.current_thread().is_alive() else "unknown"
                ),
                pending=lambda: tuple(registry._leases),
                loaded_identity=lambda identity=identity: identity,
            )
            identities.append(identity)
        extra = {}
        if cold:
            adapter = None
            if role == "task_state":
                owner = InitialTaskOwner(SelfHostedTaskService(
                    state_dir=root, ephemeral=True, auto_reconcile=False))
            elif role == "runtime_receipt":
                owner = InitialRuntimeOwner(EffectDispatchPort(lambda operation: operation()),
                                            EffectReconcilePort(lambda record: None))
            else:
                class ColdBus(NexusEventBus):
                    _log_store = JsonlEventLogStore()
                    _event_log_path = None
                    _writer_factory = None
                    _subscribers = {}
                    _attempt_sequences = {}
                owner = InitialEventOwner(ColdBus._log_store, ColdBus)
            extra = dict(cold_owner=owner)
        else:
            if role == "task_state":
                task_service = SelfHostedTaskService(
                    state_dir=root, ephemeral=True, auto_reconcile=False
                )
                adapter = TaskStateWriterAdapter(
                    registry,
                    binding=binding,
                    writer_generation=generation,
                    root=root,
                    writer_id=generation.writer_id,
                    path_for_task=task_service._state_path,
                    loaded_identity=lambda identity=identities[0]: identity,
                )
                factory = TaskStateWriterFactory(adapter)
                task_service._writer_factory = factory
                extra = dict(factory=factory, task_service=task_service)
            elif role == "event_log":
                factory = load_event_writer_factory(
                    registry,
                    binding=binding,
                    writer_generation=generation,
                    root=root,
                    writer_id=generation.writer_id,
                )

                class FixtureBus(NexusEventBus):
                    _log_store = JsonlEventLogStore()
                    _event_log_path = None
                    _writer_factory = None
                    _subscribers = {}
                    _attempt_sequences = {}

                FixtureBus.configure(root, writer_factory=factory)
                adapter = factory._adapter
                extra = dict(factory=factory, event_store=FixtureBus._log_store, event_bus=FixtureBus)
            else:
                factory = load_runtime_writer_factory(
                    registry,
                    binding=binding,
                    writer_generation=generation,
                    root=root,
                    writer_id=generation.writer_id,
                    effect_journal=EffectJournal(root, generation),
                    effect_dispatch=EffectDispatchPort(lambda operation: operation()),
                    effect_reconcile=EffectReconcilePort(lambda record: None),
                )
                adapter = factory._adapter
                extra = dict(factory=factory)
        if role == "task_state" and not cold:
            # Real C write creates an actual committed durable B lease before
            # the hold; restart must reconcile this history, not an empty file set.
            task_service._write_state("state", {"task_id": "state", "status": "SUBMITTED"})
            # A second real admission is cancelled before any physical write.
            # Both terminal states are present in the original drain evidence.
            cancelled = registry.acquire(
                root=str(root.resolve()),
                role="task_state",
                writer_id=generation.writer_id,
                generation=1,
            )
            cancelled.close("failed")
            from nexus.events.state_owner_manifest import read_manifest

            raw["expected_manifest_sha256"] = read_manifest(root).manifest_sha256
            paths = [
                (selected_role, relative, (root / relative).read_bytes())
                for selected_role, relative, _ in paths
            ]
            raw["selections"] = [
                dict(
                    entry_id=r,
                    role=r,
                    relative_path=p,
                    expected_sha256=hashlib.sha256(data).hexdigest(),
                    size=len(data),
                )
                for r, p, data in paths
            ]
        specs.append((fixture, root, source_root, source, raw, adapter, extra, paths))
    hold = registry.begin_hold(tuple(item[1] for item in specs), cohort_id="fixture-cohort")
    for item in registry._writers.values():
        identity = item.identity
        hold.acknowledge(identity.writer_id, root=identity.root, role=identity.role, generation=identity.generation)
    drain = registry.persist_finalized(hold)
    (tmp_path / "original-drain.json").write_bytes(drain.to_bytes())
    loaded = []
    for fixture, root, source_root, source, raw, adapter, extra, paths in specs:
        raw.update(drain_receipt_id=drain.cohort_id, drain_receipt_hash=drain.receipt_sha256)
        request = WriterTransitionRequest.from_mapping(raw)
        payload = json.loads((fixture / "authority.json").read_bytes())
        payload.update(
            root_id=request.root_id,
            authorization_intent_digest=request.authorization_intent_digest,
            operation_digest=request.authorization_intent_digest,
            effect_hash=authority._effect_hash(request),
        )
        data = json.dumps(payload, sort_keys=True).encode()
        tracked = fixture / "mirror" / authority.TRACKED_RELATIVE
        tracked.write_bytes(data)
        for args in (
            ("add", "."),
            ("commit", "-m", "fixture cohort authority"),
            ("update-ref", "refs/remotes/origin/main", "HEAD"),
        ):
            subprocess.run(
                ["git", "-C", str(fixture / "mirror"), *args],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        (fixture / "authority.json").write_bytes(data)
        raw["authority_receipt_hash"] = hashlib.sha256(data).hexdigest()
        request = WriterTransitionRequest.from_mapping(raw)
        (fixture / "request.json").write_text(json.dumps(raw))
        service = StateOwnerTransitionService(
            roots={request.root_id: root}, source=source, source_root=source_root
        )
        service._fixture = fixture
        service._fixture_registry = registry
        service._fixture_hold = hold
        transition = _IsolatedTransition(service, request)
        if cold:
            initial = InitialActivationRootSpec(str(root), paths[0][0], transition,
                request.expected_root_identity, request.next_generation,
                request.next_writer_id, extra.pop("cold_owner"))
            extra["initial_spec"] = initial
        loaded.append(
            ActivationRoot(
                str(root),
                paths[0][0],
                transition,
                adapter,
                request.expected_root_identity,
                request.next_generation,
                request.next_writer_id,
                request.expected_manifest_sha256,
                **extra,
            )
        )
    return WriterActivationCohort(registry, hold, tuple(loaded)), loaded


def _watch_domain_locks(monkeypatch):
    from contextlib import contextmanager

    import nexus.events.effect_journal as effect_module
    import nexus.events.log_store as log_module
    import nexus.events.state_owner_manifest as manifest_module
    import nexus.events.writer_generation as generation_module

    original = generation_module.event_store_lock
    held, seen = [], []

    @contextmanager
    def checked(root, **kwargs):
        actual = str(Path(root).resolve())
        assert not held or held[-1] == actual, ("DISTINCT_SECOND_DOMAIN", held, actual)
        with original(root, **kwargs):
            seen.append((actual, len(held)))
            held.append(actual)
            try:
                yield
            finally:
                assert held.pop() == actual

    for module in (generation_module, manifest_module, log_module, effect_module):
        monkeypatch.setattr(module, "event_store_lock", checked)
    monkeypatch.setattr(generation_module, "event_store_guard", checked)
    return seen


def test_actual_three_root_activation_rebind_release_and_writes(tmp_path, monkeypatch):
    from nexus.events.state_owner_manifest import read_manifest

    cohort, roots = _real_cohort(tmp_path)
    lock_observations = _watch_domain_locks(monkeypatch)
    old_bindings = [(item.adapter.binding, item.adapter.writer_generation) for item in roots]
    old_journal = roots[2].factory.effect_binding().journal
    result = cohort.activate()
    assert result.state == "ACTIVE", result
    assert result.release_state == "HELD"
    assert tuple(item.root for item in roots) == result.ordered_roots
    for item in roots:
        manifest = read_manifest(Path(item.root))
        assert manifest.state == "COMMITTED"
        assert manifest.generation == 2
        assert manifest.writer_id == item.expected_writer_id
        assert item.adapter.writer_generation.generation == 2
    released = cohort.release(result)
    assert released.release_state == "RELEASED"
    write_witness = []

    def active(role):
        leases = list(cohort.registry._leases.values())
        assert len(leases) == 1
        lease = leases[0]
        lease.validate()
        identity = lease.observation.identity
        assert identity.role == role and identity.generation == 2
        assert identity.root in result.ordered_roots
        assert identity.source_identity == cohort.registry.source_identity
        assert identity.process_start_identity == current_process_start_identity()
        assert identity.thread_id == str(threading.get_ident())
        assert read_manifest(Path(identity.root)).transaction_id == lease.transaction_id
        write_witness.append((role, lease.transaction_id))

    close = cohort.registry._release

    def checked_close(lease, outcome):
        assert outcome == "committed"
        manifest = read_manifest(Path(lease.observation.identity.root))
        assert manifest.state == "COMMITTED"
        assert manifest.transaction_id == lease.transaction_id
        return close(lease, outcome)

    monkeypatch.setattr(cohort.registry, "_release", checked_close)
    task_write = roots[0].task_service._write_state_locked

    def checked_task(*args, **kwargs):
        active("task_state")
        return task_write(*args, **kwargs)

    monkeypatch.setattr(roots[0].task_service, "_write_state_locked", checked_task)
    append = roots[1].event_store.append_record

    def checked_event(*args, **kwargs):
        active("event_log")
        return append(*args, **kwargs)

    monkeypatch.setattr(roots[1].event_store, "append_record", checked_event)
    import nexus.services.unified_runtime as runtime_module

    receipt_write = runtime_module._write_receipt_atomic

    def checked_receipt(*args, **kwargs):
        active("runtime_receipt")
        return receipt_write(*args, **kwargs)

    monkeypatch.setattr(runtime_module, "_write_receipt_atomic", checked_receipt)
    effect_dispatch = roots[2].factory.effect_binding().dispatch
    dispatch = effect_dispatch.dispatch

    def checked_dispatch(operation):
        active("effect_journal")
        return dispatch(operation)

    monkeypatch.setattr(effect_dispatch, "dispatch", checked_dispatch)
    roots[0].task_service._write_state("after", {"task_id": "after", "status": "SUBMITTED"})
    roots[1].event_bus.publish("after", {"task_id": "after"})
    from nexus.services.unified_runtime import UnifiedRuntime
    from tests.services.test_unified_runtime import _online, _Planner, _request

    factory = roots[2].factory
    effects = factory.effect_binding()
    output = UnifiedRuntime(planner=_Planner()).run(
        _request(),
        online_invoker=_online,
        receipt_path=Path(roots[2].root) / "runtime.json",
        runtime_writer_factory=factory,
        effect_journal=effects.journal,
        effect_dispatch=effects.dispatch,
        effect_reconcile=effects.reconcile,
        effect_fenced=True,
    )
    assert output["effect_journal_bindings"]
    assert {role for role, _ in write_witness} == {
        "task_state",
        "event_log",
        "runtime_receipt",
        "effect_journal",
    }
    from nexus.events.writer_generation import GenerationError

    for item, (old_binding, old_token) in zip(roots, old_bindings):
        with pytest.raises((GenerationError, RuntimeError)):
            with owner_transaction_guard(
                old_binding,
                writer_generation=old_token,
                selections=(StateOwnerSelection("stale", "task_state", "stale.json"),),
            ):
                pytest.fail("stale owner entered")
        assert not (Path(item.root) / "stale.json").exists()
    with pytest.raises(GenerationError):
        old_journal._check_generation()
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    unbound = SelfHostedTaskService(
        state_dir=Path(roots[0].root), ephemeral=True, auto_reconcile=False
    )
    with pytest.raises(RuntimeError):
        unbound._write_state("bypass", {"task_id": "bypass"})
    assert not (Path(roots[0].root) / "bypass.json").exists()
    assert (Path(roots[2].root) / "runtime.json").is_file()
    assert any(depth > 0 for _, depth in lock_observations)
    assert {root for root, _ in lock_observations} == {item.root for item in roots}
    assert {lease.identity.role for lease in cohort.registry._lease_history} >= {
        "task_state",
        "event_log",
        "runtime_receipt",
        "effect_journal",
    }


def test_same_role_distinct_roots_are_legal_and_ordered(tmp_path, monkeypatch):
    cohort, roots = _real_cohort(tmp_path, ("task_state", "task_state"))
    calls = []
    apply = _IsolatedTransition.apply

    def observed_apply(self):
        calls.append(self.request.root_id)
        return apply(self)

    monkeypatch.setattr(_IsolatedTransition, "apply", observed_apply)
    result = cohort.activate()
    assert result.state == "ACTIVE", result
    assert calls == [root.transition.request.root_id for root in roots]
    assert len(result.transitions) == 2
    # Lost acknowledgement is read back, not a second A application.
    assert cohort.activate() == result
    assert len(calls) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("root", "/foreign-root"),
        ("expected_generation", 99),
        ("expected_writer_id", "forged"),
        ("expected_root_identity", "0" * 64),
    ],
)
def test_loaded_root_identity_tamper_denies(tmp_path, field, value):
    cohort, roots = _real_cohort(tmp_path, ("task_state",))
    with pytest.raises((ValueError, WriterActivationError)):
        replace(roots[0], **{field: value})
    assert Path(cohort.registry._marker_path(roots[0].root)).exists()


def test_partial_root_failure_retains_every_hold_and_reconciles_first(tmp_path, monkeypatch):

    from nexus.events.state_owner_manifest import read_manifest

    cohort, roots = _real_cohort(tmp_path, ("task_state", "task_state"))
    authority_path = roots[1].transition.service._fixture / "authority.json"
    original = authority_path.read_bytes()
    authority_path.write_bytes(b"{}")  # actual authority loader denial, not a fake A outcome
    result = cohort.activate()
    assert result.state == "PARTIAL_UNKNOWN"
    assert read_manifest(Path(roots[0].root)).generation == 2
    assert read_manifest(Path(roots[1].root)).generation == 1
    assert all(Path(cohort.registry._marker_path(item.root)).exists() for item in roots)
    with pytest.raises(WriterActivationError):
        cohort.release(result)
    authority_path.write_bytes(original)
    calls = []
    apply = _IsolatedTransition.apply

    def observed_apply(self):
        calls.append(self.request.root_id)
        return apply(self)

    monkeypatch.setattr(_IsolatedTransition, "apply", observed_apply)
    resumed = cohort.resume_activation()
    assert resumed.state == "ACTIVE", resumed
    assert calls == [roots[1].transition.request.root_id]


def test_forged_active_receipt_and_rehashed_durable_schema_deny(tmp_path):
    import json

    cohort, roots = _real_cohort(tmp_path, ("task_state",))
    result = cohort.activate()
    assert result.state == "ACTIVE", result
    with pytest.raises((WriterActivationError, ValueError)):
        cohort.release(replace(result, ordered_roots=(str(tmp_path),)))
    raw = json.loads(cohort.state_path.read_bytes())
    raw["unexpected_authority"] = True
    unsigned = dict(raw)
    unsigned.pop("receipt_sha256", None)
    raw["receipt_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    cohort.state_path.write_text(json.dumps(raw))
    with pytest.raises((WriterActivationError, ValueError)):
        cohort.status()
    assert Path(cohort.registry._marker_path(roots[0].root)).exists()


def _reload_task_cohort(base, *, capture=None):
    """Reconstruct real loaded writers; F validates absence of original child."""
    import json

    from nexus.events.state_owner_manifest import MANIFEST_NAME, read_manifest
    from nexus.events.writer_generation import read_generation
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    from nexus.orchestrator.state_owner_transition_authority import LoadedSourceIdentity
    from nexus.orchestrator.writer_quiescence import TaskStateWriterFactory

    registry = WriterRegistry(
        source_identity="cohort-fixture-source", server_identity="fixture-server"
    )
    loaded = []
    for fixture in sorted(base.glob("root-*")):
        raw = json.loads((fixture / "request.json").read_bytes())
        request = WriterTransitionRequest.from_mapping(raw)
        root = fixture / "root"
        generation = read_generation(root)
        manifest = read_manifest(root)
        cold = request.expected_generation is None
        binding = (None if cold else StateOwnerBinding(
            manifest.owner_id, root.resolve(), generation.generation, "reload"
        ))
        roles = tuple(dict.fromkeys(item.role for item in request.selections))
        for role in roles:
            identity = WriterIdentity(
                str(root.resolve()),
                role,
                registry.source_identity,
                current_process_start_identity(),
                str(threading.get_ident()),
                0 if cold else generation.generation,
                request.expected_writer_id if cold else generation.writer_id,
            )
            registry.register(
                identity,
                snapshot=lambda root=root: (root / MANIFEST_NAME).read_bytes() if (root / MANIFEST_NAME).exists() else b"initial",
                process_state=lambda: "alive" if threading.current_thread().is_alive() else "unknown",
                pending=lambda: tuple(registry._leases),
                loaded_identity=lambda identity=identity: identity,
            )
        task = SelfHostedTaskService(state_dir=root, ephemeral=True, auto_reconcile=False)
        adapter = factory = None
        if not cold:
            adapter = TaskStateWriterAdapter(
                registry,
                binding=binding,
                writer_generation=generation,
                root=root,
                writer_id=generation.writer_id,
                path_for_task=task._state_path,
                loaded_identity=lambda identity=identity: identity,
            )
            factory = TaskStateWriterFactory(adapter)
            task._writer_factory = factory
        source = LoadedSourceIdentity(
            "James3014/Nexus-new",
            request.expected_source_head,
            request.expected_source_tree,
            request.card_path,
            request.card_sha256,
        )
        service = StateOwnerTransitionService(
            roots={request.root_id: root}, source=source, source_root=fixture / "source"
        )
        service._fixture = fixture
        service._fixture_registry = registry
        service._fixture_restarted = True
        transition = _IsolatedTransition(service, request)
        extra = dict(factory=factory, task_service=task)
        if cold:
            if roles == ("task_state",):
                owner = InitialTaskOwner(task)
            elif roles == ("event_log",):
                from nexus.events.transport import NexusEventBus
                from nexus.events.log_store import JsonlEventLogStore
                class ReloadBus(NexusEventBus):
                    _log_store = JsonlEventLogStore()
                    _event_log_path = None
                    _writer_factory = None
                    _subscribers = {}
                    _attempt_sequences = {}
                owner = InitialEventOwner(ReloadBus._log_store, ReloadBus)
            else:
                from nexus.events.effect_journal import EffectDispatchPort, EffectReconcilePort
                owner = InitialRuntimeOwner(EffectDispatchPort(lambda operation: operation()),
                                            EffectReconcilePort(lambda record: None))
            extra = dict(initial_spec=InitialActivationRootSpec(
                str(root), roles[0], transition, request.expected_root_identity,
                request.next_generation, request.next_writer_id, owner))
        loaded.append(
            ActivationRoot(
                str(root),
                roles[0],
                transition,
                adapter,
                request.expected_root_identity,
                request.next_generation,
                request.next_writer_id,
                request.expected_manifest_sha256,
                **extra,
            )
        )
    if capture is not None:
        capture.update(registry=registry, roots=tuple(loaded))
    cohort = WriterActivationCohort.recover(registry, tuple(loaded), cohort_id="fixture-cohort")
    for root in loaded:
        root.transition.service._fixture_hold = cohort.hold
        root.transition.service._fixture_cohort = cohort
    return cohort, loaded


def _crash_child(base, boundary, *, cold=False):
    import os

    from nexus.events.state_owner_manifest import read_manifest

    cohort, roots = _real_cohort(base, ("task_state", "event_log", "runtime_receipt") if cold else ("task_state", "task_state"), cold=cold)
    if boundary == "RELEASED:2":
        for index, root in enumerate(roots):
            (base / f"original-marker-{index}.json").write_bytes(
                Path(cohort.registry._marker_path(root.root)).read_bytes()
            )
    save = cohort._save
    apply = _IsolatedTransition.apply

    # Kill only this owned child, after physical writes/readbacks at exact
    # phase boundaries. Original A methods still run; no fake apply results.
    def crash_save(receipt):
        result = save(receipt)
        point = f"{result.state}:{len(result.transitions)}"
        if boundary == point:
            os._exit(71)
        return result

    cohort._save = crash_save
    if boundary.startswith("lost-ack:"):
        wanted = boundary.split(":", 1)[1]

        def crash_apply(self):
            result = apply(self)
            if self.request.root_id == wanted:
                assert read_manifest(self.service._roots[self.request.root_id]).state == "COMMITTED"
                os._exit(71)
            return result

        _IsolatedTransition.apply = crash_apply
    if boundary.startswith("marker:"):
        target = int(boundary.split(":")[1])
        unlink = Path.unlink
        count = 0
        markers = {Path(cohort.registry._marker_path(root.root)) for root in roots}

        def crash_unlink(path, *args, **kwargs):
            nonlocal count
            result = unlink(path, *args, **kwargs)
            if path in markers:
                count += 1
                if count == target:
                    os._exit(71)
            return result

        Path.unlink = crash_unlink
    active = cohort.activate()
    assert active.state == "ACTIVE", active
    cohort.release(active)
    raise AssertionError("crash boundary was never reached")


@pytest.mark.parametrize(
    "boundary",
    [
        "HOLDING:0",
        "APPLYING:1",
        "APPLYING:2",
        "REACQUIRING:2",
        "ACTIVE:2",
        "lost-ack:root-0",
        "lost-ack:root-1",
        "marker:1",
        "marker:2",
    ],
)
def test_child_crash_resumes_same_cohort_without_reapply(tmp_path, boundary, monkeypatch):
    import subprocess
    import sys

    from nexus.events.state_owner_manifest import read_manifest

    script = (
        "from pathlib import Path; import sys; "
        "from tests.integration.test_writer_activation_cohort import _crash_child; "
        "_crash_child(Path(sys.argv[1]), sys.argv[2])"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(tmp_path), boundary],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 71, result.stderr
    # subprocess.run has waited/reaped this exact PID. Recovery must establish
    # that old producer absence itself, rather than accepting our assertion.
    from nexus.events.writer_generation import GenerationError, read_generation

    for fixture in sorted(tmp_path.glob("root-*")):
        physical_root = fixture / "root"
        generation = read_generation(physical_root)
        marker = physical_root / ".nexus/writer-quiescence-hold.json"
        if generation.generation == 1:
            assert marker.exists(), "old generation exposed without a hold"
        else:
            # Even a marker-free RELEASE_INTENT prefix cannot admit an old P6
            # owner token. Exercise actual admission before recovery repairs it.
            old = EventWriterGeneration(1, "old-" + fixture.name)
            binding = StateOwnerBinding("owner", physical_root.resolve(), 1, "stale-restart")
            with pytest.raises((GenerationError, RuntimeError)):
                with owner_transaction_guard(
                    binding,
                    writer_generation=old,
                    selections=(StateOwnerSelection("stale", "task_state", "stale.json"),),
                ):
                    pytest.fail("old generation entered after crash")
            assert not (physical_root / "stale.json").exists()
    original_markers = {
        path: path.read_bytes()
        for path in tmp_path.glob("root-*/root/.nexus/writer-quiescence-hold.json")
    }
    original_history = {
        path: path.read_bytes()
        for path in tmp_path.glob("root-*/root/.nexus/writer-quiescence-leases/*.json")
    }
    assert len(original_history) >= 4  # committed + failed for both original writers
    cohort, roots = _reload_task_cohort(tmp_path)
    assert all(path.read_bytes() == data for path, data in original_markers.items())
    assert cohort.cohort_id == "fixture-cohort"
    original_epoch = cohort.hold.epoch
    committed_before = {
        item.transition.request.root_id
        for item in roots
        if read_manifest(Path(item.root)).generation == 2
    }
    calls = []
    apply = _IsolatedTransition.apply

    def observed_apply(self):
        calls.append(self.request.root_id)
        return apply(self)

    monkeypatch.setattr(_IsolatedTransition, "apply", observed_apply)
    if cohort.status().state == "RELEASE_INTENT":
        done = cohort.resume_release()
    else:
        active = cohort.resume_activation()
        assert active.state == "ACTIVE", active
        done = cohort.release(active)
    assert done.release_state == "RELEASED"
    assert done.hold_epoch == original_epoch
    assert not committed_before.intersection(calls)
    assert all(path.read_bytes() == data for path, data in original_history.items())
    import json

    from nexus.orchestrator.writer_quiescence import WriterAdmissionDenied

    replay = json.loads(next(iter(original_history.values())))
    actual = next(item for item in roots if item.root == replay["root"])
    count_before = len(cohort.registry._lease_history)
    with pytest.raises(WriterAdmissionDenied, match="duplicate or replayed"):
        cohort.registry.acquire(
            root=actual.root,
            role="task_state",
            writer_id=actual.expected_writer_id,
            generation=2,
            operation_id=replay["operation_id"],
            transaction_id=replay["transaction_id"],
        )
    assert len(cohort.registry._lease_history) == count_before
    assert all(read_manifest(Path(item.root)).generation == 2 for item in roots)
    assert all(not Path(cohort.registry._marker_path(item.root)).exists() for item in roots)
    for item in roots:
        item.task_service._write_state("after", {"task_id": "after", "status": "SUBMITTED"})
        assert (Path(item.root) / "after.json").is_file()


def test_recovery_rejects_still_live_producer_without_changing_markers(tmp_path):
    cohort, roots = _real_cohort(tmp_path, ("task_state", "task_state"))
    assert cohort.activate().state == "ACTIVE"
    before = {
        item.root: Path(cohort.registry._marker_path(item.root)).read_bytes() for item in roots
    }
    with pytest.raises(WriterActivationError, match="PREVIOUS_PROCESS_STILL_EXISTS"):
        _reload_task_cohort(tmp_path)
    assert before == {
        item.root: Path(cohort.registry._marker_path(item.root)).read_bytes() for item in roots
    }


@pytest.mark.parametrize("tamper", ["source", "role"])
def test_mismatched_actual_loaded_writer_denies_active(tmp_path, tamper):
    cohort, roots = _real_cohort(tmp_path, ("task_state",))
    if tamper == "source":
        cohort.registry.source_identity = "foreign-source"
    else:
        # The exact loaded C service is still a task writer; re-labelling the
        # frozen root cannot turn it into an event writer.
        object.__setattr__(roots[0], "role", "event_log")
    try:
        result = cohort.activate()
    except (WriterActivationError, ValueError, RuntimeError):
        pass
    else:
        assert result.state != "ACTIVE"
    assert Path(cohort.registry._marker_path(roots[0].root)).exists()


def test_recovery_interrupted_after_process_cas_can_resume_same_owner(tmp_path, monkeypatch):
    import subprocess
    import sys

    script = (
        "from pathlib import Path; import sys; "
        "from tests.integration.test_writer_activation_cohort import _crash_child; "
        "_crash_child(Path(sys.argv[1]), 'ACTIVE:2')"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 71, result.stderr
    prepare = WriterActivationCohort._prepare_reacquisition
    fail_once = {"pending": True}

    def interrupted_prepare(self, *args, **kwargs):
        if fail_once["pending"]:
            fail_once["pending"] = False
            raise RuntimeError("fixture interruption after current-process CAS")
        return prepare(self, *args, **kwargs)

    monkeypatch.setattr(WriterActivationCohort, "_prepare_reacquisition", interrupted_prepare)
    captured = {}
    with pytest.raises(RuntimeError, match="fixture interruption"):
        _reload_task_cohort(tmp_path, capture=captured)
    # Exact same process/registry/root handles own the interrupted recovery.
    # A second live process is forbidden, but this owner must be resumable.
    cohort = WriterActivationCohort.recover(
        captured["registry"], captured["roots"], cohort_id="fixture-cohort"
    )
    for item in captured["roots"]:
        item.transition.service._fixture_hold = cohort.hold
        item.transition.service._fixture_cohort = cohort
    assert cohort.release(cohort.status()).release_state == "RELEASED"


@pytest.mark.parametrize("tamper", ["unresolved", "unknown-operation"])
def test_restart_rejects_lease_history_outside_frozen_drain(tmp_path, tamper):
    import json
    import subprocess
    import sys

    script = (
        "from pathlib import Path; import sys; "
        "from tests.integration.test_writer_activation_cohort import _crash_child; "
        "_crash_child(Path(sys.argv[1]), 'HOLDING:0')"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 71, result.stderr
    first = tmp_path / "root-0/root"
    leases = sorted((first / ".nexus/writer-quiescence-leases").glob("*.json"))
    assert leases, "fixture must contain actual previous writer activity"
    raw = json.loads(leases[0].read_bytes())
    if tamper == "unresolved":
        raw["durable_outcome"] = "unresolved"
    else:
        raw["operation_id"] = "unknown-operation"
    leases[0].write_text(json.dumps(raw))
    markers = sorted(tmp_path.glob("root-*/root/.nexus/writer-quiescence-hold.json"))
    before = [path.read_bytes() for path in markers]
    with pytest.raises(WriterActivationError):
        _reload_task_cohort(tmp_path)
    assert [path.read_bytes() for path in markers] == before


@pytest.mark.parametrize("tamper", ["missing", "mutated"])
def test_reconciled_terminal_pin_changes_deny_real_writer_admission(tmp_path, tamper):
    import subprocess
    import sys

    from nexus.events.state_owner_manifest import MANIFEST_NAME
    from nexus.orchestrator.writer_quiescence import WriterAdmissionDenied

    script = (
        "from pathlib import Path; import sys; "
        "from tests.integration.test_writer_activation_cohort import _crash_child; "
        "_crash_child(Path(sys.argv[1]), 'ACTIVE:2')"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 71, result.stderr
    cohort, roots = _reload_task_cohort(tmp_path)
    assert cohort.release(cohort.status()).release_state == "RELEASED"
    pins = cohort.registry._reconciled_terminal_records
    assert len(pins) >= 4
    selected = roots[0]
    pin = next(Path(path) for path in pins if Path(path).is_relative_to(Path(selected.root)))
    if tamper == "missing":
        pin.unlink()
    else:
        pin.write_bytes(pin.read_bytes() + b" ")
    manifest_path = Path(selected.root) / MANIFEST_NAME
    before = manifest_path.read_bytes()
    with pytest.raises(WriterAdmissionDenied):
        selected.task_service._write_state("tamper-blocked", {"task_id": "tamper-blocked"})
    assert not (Path(selected.root) / "tamper-blocked.json").exists()
    assert manifest_path.read_bytes() == before


@pytest.mark.parametrize("method", ["activate", "resume_activation"])
@pytest.mark.parametrize("drift", ["generation", "durable"])
@pytest.mark.parametrize("released", [False, True])
def test_completed_activation_reentry_revalidates_current_state(tmp_path, method, drift, released):
    import json

    cohort, roots = _real_cohort(tmp_path, ("task_state",))
    receipt = cohort.activate()
    assert receipt.state == "ACTIVE"
    if released:
        receipt = cohort.release(receipt)
    # Unchanged completed operations remain idempotent with fresh readback.
    assert getattr(cohort, method)() == receipt
    if drift == "generation":
        install_generation(
            Path(roots[0].root), EventWriterGeneration(3, "drifted-writer"), expected_generation=2
        )
    else:
        raw = json.loads(cohort.state_path.read_bytes())
        raw["prior_digest"] = "f" * 64
        unsigned = dict(raw)
        unsigned.pop("receipt_sha256", None)
        raw["receipt_sha256"] = hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        cohort.state_path.write_text(json.dumps(raw))
    with pytest.raises((WriterActivationError, RuntimeError)):
        getattr(cohort, method)()


@pytest.mark.parametrize("method", ["status", "activate", "resume_activation"])
def test_released_cohort_rejects_restored_original_hold_marker(tmp_path, method):
    cohort, roots = _real_cohort(tmp_path, ("task_state", "task_state"))
    marker = Path(cohort.registry._marker_path(roots[-1].root))
    original = marker.read_bytes()
    active = cohort.activate()
    assert active.state == "ACTIVE"
    released = cohort.release(active)
    assert released.release_state == "RELEASED"
    assert not marker.exists()
    assert getattr(cohort, method)() == released
    # Restoring only the LAST marker forms a legal RELEASE_INTENT prefix.
    # It must still be rejected once the durable phase is RELEASED.
    marker.write_bytes(original)
    before = cohort.state_path.read_bytes()
    with pytest.raises(WriterActivationError):
        getattr(cohort, method)()
    assert marker.read_bytes() == original
    assert cohort.state_path.read_bytes() == before


def test_fresh_recovery_rejects_restored_marker_after_durable_released(tmp_path):
    import subprocess
    import sys

    script = (
        "from pathlib import Path; import sys; "
        "from tests.integration.test_writer_activation_cohort import _crash_child; "
        "_crash_child(Path(sys.argv[1]), 'RELEASED:2')"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 71, result.stderr
    marker = tmp_path / "root-1/root/.nexus/writer-quiescence-hold.json"
    assert not marker.exists()
    original = (tmp_path / "original-marker-1.json").read_bytes()
    marker.write_bytes(original)
    state_path = next(
        (tmp_path / "root-0/root/.nexus/writer-quiescence/activation-cohorts").glob("*.json")
    )
    before = state_path.read_bytes()
    with pytest.raises(WriterActivationError):
        _reload_task_cohort(tmp_path)
    assert marker.read_bytes() == original
    # Rejected recovery must not publish a new process-adoption CAS.
    assert state_path.read_bytes() == before


def test_cold_start_spec_is_typed_and_rejects_nonempty_request(tmp_path):
    """The cold-start seam cannot be used to re-materialize an existing generation."""
    from types import SimpleNamespace

    class _Transition(LoadedRootTransition):
        def __init__(self):
            service = SimpleNamespace(_roots={"root": tmp_path})
            object.__setattr__(self, "service", service)
            object.__setattr__(self, "request", SimpleNamespace(
                root_id="root", expected_generation=1,
                expected_root_identity="a" * 64,
            ))

    with pytest.raises(WriterActivationError, match="INITIAL_REQUEST_EXPECTS_GENERATION_ZERO"):
        InitialActivationRootSpec(
            str(tmp_path), "task_state", _Transition(), "a" * 64,
            owner=InitialTaskOwner(object()),
        )


@pytest.mark.parametrize("failure_prefix", [None, "after_first_A", "after_event_configure", "after_runtime_register"])
def test_generation_zero_three_root_full_activation_and_four_role_writes(tmp_path, monkeypatch, failure_prefix):
    from nexus.events.state_owner_manifest import read_manifest
    from nexus.events.writer_generation import read_generation
    from nexus.services.unified_runtime import UnifiedRuntime
    from tests.services.test_unified_runtime import _online, _Planner, _request

    cohort, descriptors = _real_cohort(tmp_path, cold=True)
    original_epoch = cohort.hold.epoch
    failures = []
    save = cohort._save
    def checked_save(receipt):
        import sys
        if receipt.state == "PARTIAL_UNKNOWN":
            failures.append(repr(sys.exception()))
        return save(receipt)
    monkeypatch.setattr(cohort, "_save", checked_save)
    markers = [cohort.registry._marker_path(root.root).read_bytes() for root in descriptors]
    assert all(read_generation(Path(root.root)) is None for root in descriptors)
    assert all(read_manifest(Path(root.root)) is None for root in descriptors)
    assert {item.identity.generation for item in cohort.hold.selected} == {0}
    assert cohort.registry.load_finalized(cohort.cohort_id).drain_state == "DRAINED"
    commit = cohort._commit_reacquisition
    commits = []

    def checked_commit(receipt, **kwargs):
        assert {item.identity.generation for item in cohort.hold.selected} == {0}
        assert len(receipt.observations) == 4
        assert all(item.state == "MATCHED" for item in receipt.observations)
        assert cohort.hold.epoch == original_epoch
        commits.append(receipt)
        return commit(receipt, **kwargs)

    monkeypatch.setattr(cohort, "_commit_reacquisition", checked_commit)
    failed_factory = None
    if failure_prefix == "after_first_A":
        preflight = descriptors[1].transition.preflight
        attempts = []
        def interrupted_preflight():
            if not attempts:
                attempts.append(True)
                raise RuntimeError("injected after first committed A")
            return preflight()
        monkeypatch.setattr(descriptors[1].transition, "preflight", interrupted_preflight)
    elif failure_prefix == "after_event_configure":
        bus = descriptors[1].initial_spec.owner.event_bus
        configure = bus.configure
        attempts = []
        def interrupted_configure(*args, **kwargs):
            result = configure(*args, **kwargs)
            if not attempts:
                attempts.append(True)
                raise RuntimeError("injected after event store and bus configured")
            return result
        monkeypatch.setattr(bus, "configure", interrupted_configure)
    elif failure_prefix == "after_runtime_register":
        import nexus.orchestrator.writer_quiescence as writer_module
        register = writer_module.register_runtime_writer_factory
        attempts = []
        def interrupted_register(*args, **kwargs):
            result = register(*args, **kwargs)
            if not attempts:
                attempts.append(True)
                raise RuntimeError("injected after runtime global factory registration")
            return result
        monkeypatch.setattr(writer_module, "register_runtime_writer_factory", interrupted_register)
    result = cohort.activate()
    if failure_prefix:
        assert result.state == "PARTIAL_UNKNOWN"
        assert not commits
        assert {item.identity.generation for item in cohort.hold.selected} == {0}
        assert [cohort.registry._marker_path(root.root).read_bytes() for root in descriptors] == markers
        if failure_prefix == "after_first_A":
            assert read_manifest(Path(descriptors[0].root)).state == "COMMITTED"
            assert read_manifest(Path(descriptors[1].root)) is None
            assert cohort._initial_materialized == {}
        elif failure_prefix == "after_event_configure":
            failed_factory = descriptors[1].initial_spec.owner.event_store._writer_factory
            assert failed_factory is not None
        else:
            failed_factory = cohort._initial_factories[descriptors[2].root]
        result = cohort.activate()
    assert result.state == "ACTIVE", (result, failures)
    assert not failures or failure_prefix, failures
    assert len(commits) == 1
    if failed_factory is not None:
        assert cohort.roots[2 if failure_prefix == "after_runtime_register" else 1].factory is failed_factory
    assert result.release_state == "HELD"
    assert cohort.hold.epoch == original_epoch
    assert [cohort.registry._marker_path(root.root).read_bytes() for root in descriptors] == markers
    roots = cohort.roots
    assert all(root.adapter is not None for root in roots)
    assert {item.identity.generation for item in cohort.hold.selected} == {1}
    for root in roots:
        root.check_handles(cohort.registry)
        assert read_manifest(Path(root.root)).state == "COMMITTED"
        with pytest.raises(Exception):
            cohort.registry.acquire(root=root.root, role=root.role,
                writer_id=root.expected_writer_id, generation=1)
    cohort.release(result)
    roots[0].task_service._write_state("after", {"task_id": "after", "status": "SUBMITTED"})
    roots[1].event_bus.publish("after", {"task_id": "after"})
    factory = roots[2].factory
    effects = factory.effect_binding()
    output = UnifiedRuntime(planner=_Planner()).run(
        _request(), online_invoker=_online,
        receipt_path=Path(roots[2].root) / "runtime.json",
        runtime_writer_factory=factory, effect_journal=effects.journal,
        effect_dispatch=effects.dispatch, effect_reconcile=effects.reconcile,
        effect_fenced=True)
    assert output["effect_journal_bindings"]
    import json
    assert json.loads((Path(roots[2].root) / ".nexus/events/effect_journal.v1.json").read_bytes())["records"]
    assert b'after' in (Path(roots[0].root) / "after.json").read_bytes()
    assert b'after' in roots[1].event_store.event_log_path.read_bytes()
    assert (Path(roots[2].root) / "runtime.json").read_bytes()
    assert {item.identity.role for item in cohort.registry._lease_history} == {
        "task_state", "event_log", "runtime_receipt", "effect_journal"}
    for root in roots:
        assert read_manifest(Path(root.root)).state == "COMMITTED"


@pytest.mark.parametrize("boundary", ["APPLYING:1", "ACTIVE:3", "ACTIVE:3:retry", "ACTIVE:3:release_ack"])
def test_generation_zero_child_crash_recovers_original_hold(tmp_path, boundary, monkeypatch):
    import subprocess
    import sys
    from nexus.events.state_owner_manifest import read_manifest

    script = (
        "from pathlib import Path; import sys; "
        "from tests.integration.test_writer_activation_cohort import _crash_child; "
        "_crash_child(Path(sys.argv[1]), sys.argv[2], cold=True)"
    )
    child = subprocess.run([sys.executable, "-B", "-c", script, str(tmp_path), boundary.removesuffix(":retry").removesuffix(":release_ack")],
                           capture_output=True, text=True, timeout=40)
    assert child.returncode == 71, child.stderr
    markers = [(tmp_path / f"root-{i}/root/.nexus/writer-quiescence-hold.json").read_bytes()
               for i in range(3)]
    committed_before = {f"root-{i}" for i in range(3)
                        if read_manifest(tmp_path / f"root-{i}/root") is not None}
    apply = _IsolatedTransition.apply
    def checked_apply(self):
        assert self.request.root_id not in committed_before, "committed A was reapplied"
        return apply(self)
    monkeypatch.setattr(_IsolatedTransition, "apply", checked_apply)
    if boundary.endswith(":retry"):
        verify = WriterActivationCohort._verify_active_physical
        attempts = []
        def interrupted_verify(self, *args, **kwargs):
            if not attempts:
                attempts.append(True)
                assert all(root.adapter is not None for root in self.roots)
                raise RuntimeError("injected after recovered root swap")
            return verify(self, *args, **kwargs)
        monkeypatch.setattr(WriterActivationCohort, "_verify_active_physical", interrupted_verify)
        captured = {}
        with pytest.raises(RuntimeError, match="recovered root swap"):
            _reload_task_cohort(tmp_path, capture=captured)
        cohort = WriterActivationCohort.recover(captured["registry"], captured["roots"],
                                               cohort_id="fixture-cohort")
        for root in cohort.roots:
            root.transition.service._fixture_hold = cohort.hold
            root.transition.service._fixture_cohort = cohort
    else:
        cohort, _ = _reload_task_cohort(tmp_path)
    active = cohort.activate()
    assert active.state == "ACTIVE", active
    assert [(Path(root.root) / ".nexus/writer-quiescence-hold.json").read_bytes()
            for root in cohort.roots] == markers
    assert cohort.hold.epoch == active.hold_epoch == 1
    if boundary.endswith(":release_ack"):
        save = cohort._save
        attempts = []
        def lost_release_ack(receipt):
            result = save(receipt)
            if result.state == "RELEASED" and not attempts:
                attempts.append(True)
                raise RuntimeError("injected after durable RELEASED")
            return result
        monkeypatch.setattr(cohort, "_save", lost_release_ack)
        with pytest.raises(RuntimeError, match="durable RELEASED"):
            cohort.release(active)
        assert not cohort.hold.released
        assert all(cohort.registry._held_roots[root.root] is cohort.hold for root in cohort.roots)
        cohort.resume_release()
    else:
        cohort.release(active)
    roots = cohort.roots
    roots[0].task_service._write_state("recovered", {"task_id": "recovered"})
    roots[1].event_bus.publish("recovered", {"task_id": "recovered"})
    from nexus.services.unified_runtime import UnifiedRuntime
    from tests.services.test_unified_runtime import _online, _Planner, _request
    effects = roots[2].factory.effect_binding()
    output = UnifiedRuntime(planner=_Planner()).run(
        _request(), online_invoker=_online,
        receipt_path=Path(roots[2].root) / "recovered.json",
        runtime_writer_factory=roots[2].factory, effect_journal=effects.journal,
        effect_dispatch=effects.dispatch, effect_reconcile=effects.reconcile,
        effect_fenced=True)
    assert output["effect_journal_bindings"]
    import json
    assert json.loads((Path(roots[2].root) / ".nexus/events/effect_journal.v1.json").read_bytes())["records"]
    assert (Path(roots[0].root) / "recovered.json").read_bytes()
    assert b"recovered" in roots[1].event_store.event_log_path.read_bytes()
    assert (Path(roots[2].root) / "recovered.json").read_bytes()
    for root in roots:
        assert read_manifest(Path(root.root)).state == "COMMITTED"


def test_initial_descriptors_reject_owner_role_and_request_drift(tmp_path):
    cohort, roots = _real_cohort(tmp_path, cold=True)
    initial = roots[0].initial_spec
    with pytest.raises(ValueError, match="task owner root or role"):
        replace(initial, role="event_log")
    with pytest.raises(ValueError, match="task owner root or role"):
        replace(initial, owner=InitialTaskOwner(roots[1].initial_spec.owner.event_store))
    with pytest.raises(ValueError, match="initial descriptor"):
        replace(roots[0], role="event_log")
    with pytest.raises(ValueError, match="expected manifest"):
        replace(roots[0], expected_manifest_sha256="a" * 64)
    with pytest.raises(ValueError, match="initial descriptor"):
        replace(roots[0], expected_writer_id="foreign")
    assert {item.identity.generation for item in cohort.hold.selected} == {0}
    from nexus.events.state_owner_manifest import read_manifest
    assert all(read_manifest(Path(root.root)) is None for root in roots)


def test_cold_cached_factory_physical_drift_keeps_original_admission_held(tmp_path, monkeypatch):
    import nexus.orchestrator.writer_quiescence as writer_module

    cohort, descriptors = _real_cohort(tmp_path, cold=True)
    markers = [cohort.registry._marker_path(root.root).read_bytes() for root in descriptors]
    register = writer_module.register_runtime_writer_factory
    def interrupted_register(*args, **kwargs):
        register(*args, **kwargs)
        raise RuntimeError("injected before complete factory vector")
    monkeypatch.setattr(writer_module, "register_runtime_writer_factory", interrupted_register)
    assert cohort.activate().state == "PARTIAL_UNKNOWN"
    cached = dict(cohort._initial_factories)
    install_generation(Path(descriptors[1].root), EventWriterGeneration(2, "foreign"),
                       expected_generation=1)
    monkeypatch.setattr(writer_module, "register_runtime_writer_factory", register)
    assert cohort.activate().state == "PARTIAL_UNKNOWN"
    assert cohort._initial_factories == cached
    assert {item.identity.generation for item in cohort.hold.selected} == {0}
    assert [cohort.registry._marker_path(root.root).read_bytes() for root in descriptors] == markers
    assert cohort.registry._lease_history == []
