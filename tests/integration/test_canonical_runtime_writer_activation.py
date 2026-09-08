"""Physical caller-chain witnesses; providers are replaced only at invocation."""

from __future__ import annotations

import json
import threading

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
    WriterIdentity,
    WriterRegistry,
    current_process_start_identity,
    load_runtime_writer_factory,
)


def _loaded_runtime(root, *, effects=True):
    from nexus.events.effect_journal import EffectDispatchPort, EffectJournal, EffectReconcilePort

    generation = EventWriterGeneration(1, "runtime-writer")
    install_generation(root, generation)
    binding = StateOwnerBinding("runtime-owner", root.resolve(), 1, "bootstrap")
    with owner_transaction_guard(
        binding,
        writer_generation=generation,
        selections=(StateOwnerSelection("seed", "runtime_receipt", "seed.json"),),
    ) as context:
        commit_owner_transaction(context)
    registry = WriterRegistry(
        source_identity="fixture-source",
        server_identity="fixture",
        hold_store=root / "holds",
    )
    for role in ("runtime_receipt", "effect_journal"):
        identity = WriterIdentity(
            str(root.resolve()),
            role,
            "fixture-source",
            current_process_start_identity(),
            str(threading.get_ident()),
            1,
            "runtime-writer",
        )
        registry.register(identity, loaded_identity=lambda identity=identity: identity)
    effect_ports = {}
    if effects:
        effect_ports = dict(
            effect_journal=EffectJournal(root, generation),
            effect_dispatch=EffectDispatchPort(lambda operation: operation()),
            effect_reconcile=EffectReconcilePort(lambda _record: None),
        )
    factory = load_runtime_writer_factory(
        registry,
        binding=binding,
        writer_generation=generation,
        root=root,
        writer_id="runtime-writer",
        **effect_ports,
    )
    return factory, registry, generation


def _witness(monkeypatch, registry, root):
    import nexus.services.unified_runtime as runtime_module

    events = []
    write = runtime_module._write_receipt_atomic
    release = registry._release

    def active(role):
        assert len(registry._leases) == 1
        lease = next(iter(registry._leases.values()))
        lease.validate()
        identity = lease.observation.identity
        assert identity.root == str(root.resolve())
        assert identity.role == role
        assert identity.source_identity == "fixture-source"
        assert identity.process_start_identity == current_process_start_identity()
        assert identity.generation == 1
        assert read_manifest(root).transaction_id == lease.transaction_id
        assert read_manifest(root).state == "PREPARED"
        assert not registry._mutex._is_owned()
        return lease

    def write_witness(path, payload):
        active("runtime_receipt")
        events.append("receipt")
        return write(path, payload)

    def release_witness(lease, outcome):
        assert outcome == "committed"
        manifest = read_manifest(root)
        assert manifest.state == "COMMITTED"
        assert manifest.transaction_id == lease.transaction_id
        events.append("close:" + lease.observation.identity.role)
        return release(lease, outcome)

    monkeypatch.setattr(runtime_module, "_write_receipt_atomic", write_witness)
    monkeypatch.setattr(registry, "_release", release_witness)
    return active, events


@pytest.fixture(autouse=True)
def _no_external_transport(monkeypatch):
    # Avoid even Gateway's local Ollama discovery during constructor bootstrap.
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "codex")
    monkeypatch.setattr(
        "nexus.services.unified_runtime.build_registered_online_invoker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("fixture unsupported")),
    )


def test_real_canonical_chain_commits_receipt_with_live_lease(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    factory, registry, _ = _loaded_runtime(tmp_path)
    active, events = _witness(monkeypatch, registry, tmp_path)
    binding = factory.effect_binding()

    def dispatch(operation):
        active("effect_journal")
        events.append("effect")
        return operation()

    monkeypatch.setattr(binding.dispatch, "_dispatch", dispatch)
    execute_canonical_product_task(
        "audit bounded runtime integration",
        tmp_path,
        execution_context={
            "task_id": "canonical-proof",
            "verifier_command": ["python3", "-c", "raise SystemExit(1)"],
            "workspace_revision": "fixture-revision",
            "local_assist_mode": "disabled",
            "online_policy": "auto",
        },
    )
    path = tmp_path / ".nexus/reports/run/canonical-proof.canonical_runtime.json"
    receipt = json.loads(path.read_text())
    assert receipt["canonical_execution"]["execution_decision_authority"] == "CapabilityPlanner"
    assert events == ["effect", "close:effect_journal", "receipt", "close:runtime_receipt"]
    assert len(registry._lease_history) == 2
    assert receipt["effect_journal_bindings"]
    for item in receipt["effect_journal_bindings"]:
        assert binding.journal.get(item["effect_id"])["state"] == "COMPLETED"
    assert not registry._leases
    assert read_manifest(tmp_path).state == "COMMITTED"


def test_real_canonical_missing_binding_denies_before_dispatch_and_bytes(monkeypatch, tmp_path):
    import nexus.orchestrator.writer_quiescence as writers
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    _loaded_runtime(tmp_path)
    monkeypatch.delitem(writers._LOADED_RUNTIME_WRITER_FACTORIES, str(tmp_path.resolve()))
    attempts = []
    monkeypatch.setattr(
        "nexus.services.unified_runtime.build_registered_online_invoker",
        lambda *args, **kwargs: attempts.append("dispatch") or pytest.fail("must not dispatch"),
    )
    with pytest.raises(ValueError, match="runtime_writer_factory_required"):
        execute_canonical_product_task(
            "audit bounded runtime integration",
            tmp_path,
            execution_context={
                "task_id": "denied",
                "workspace_revision": "fixture-revision",
                "local_assist_mode": "disabled",
                "online_policy": "auto",
            },
        )
    assert not (tmp_path / ".nexus/reports").exists()
    assert attempts == []


def test_gateway_mainchain_effect_replan_and_finalize_keep_real_binding(monkeypatch, tmp_path):
    from dataclasses import replace

    from nexus.events.effect_journal import EffectDispatchPort, EffectJournal, EffectReconcilePort
    from nexus.services.gateway import BattlesuitGateway
    from nexus.services.mainchain_entry import run_mainchain_replan
    from nexus.services.unified_runtime import UnifiedRuntime, normalize_online_invoker_payload
    from tests.services.test_mainchain_entry import _admit_mainchain_request
    from tests.services.test_unified_runtime import _learning, _request, _verifier

    factory, registry, generation = _loaded_runtime(tmp_path)
    active, events = _witness(monkeypatch, registry, tmp_path)
    journal = EffectJournal(tmp_path, generation)
    dispatches = []

    def dispatch(operation):
        active("effect_journal")
        events.append("effect")
        dispatches.append("fixture-effect")
        return operation()

    def unsupported(context):
        # Actual effect reservation/readback even though no provider is invoked.
        return normalize_online_invoker_payload(
            provider="codex",
            task_id=context["task_id"],
            invoked=False,
            output_delivered=False,
            gate_passed=False,
            provider_call_count=0,
            response="",
            error="fixture_unsupported",
            evidence_refs=["fixture:no-provider"],
        )

    unsupported.online_invoker_provider = "codex"
    ports = dict(
        runtime_writer_factory=factory,
        effect_journal=journal,
        effect_dispatch=EffectDispatchPort(dispatch),
        effect_reconcile=EffectReconcilePort(lambda _record: None),
        effect_fenced=True,
    )
    request = _admit_mainchain_request(
        replace(_request(), task_statement="audit runtime integration")
    )
    request = replace(
        request, route={**request.route, "online_policy": "auto", "with_nexus_armor": True}
    )
    path = tmp_path / ".nexus/reports/run/effect-chain.json"

    def failed_verifier(context):
        return {**_verifier(context), "gate_passed": False, "status": "FAILED"}

    receipt = BattlesuitGateway(project_root=tmp_path).ask_unified(
        request,
        online_invoker=unsupported,
        receipt_path=path,
        verifier=failed_verifier,
        learning=_learning,
        **ports,
    )
    assert receipt["effect_journal_bindings"]
    assert dispatches == ["fixture-effect"]
    assert events == ["effect", "close:effect_journal", "receipt", "close:runtime_receipt"]
    for item in receipt["effect_journal_bindings"]:
        assert journal.get(item["effect_id"])["state"] == "COMPLETED"
    assert json.loads(path.read_text())["task_id"] == request.task_id
    replay = BattlesuitGateway(project_root=tmp_path).ask_unified(
        request,
        online_invoker=unsupported,
        receipt_path=path,
        verifier=failed_verifier,
        learning=_learning,
        **ports,
    )
    assert replay["effect_journal_bindings"] == receipt["effect_journal_bindings"]
    assert dispatches == ["fixture-effect"]
    retried = run_mainchain_replan(
        receipt,
        request,
        online_invoker=unsupported,
        receipt_path=path,
        verifier=_verifier,
        learning=_learning,
        **ports,
    )
    assert retried["execution_attempt"]["attempt_number"] == 2
    assert len(dispatches) == 2
    finalized = UnifiedRuntime().finalize_receipt(
        retried,
        verifier={"invoked": False},
        learning={"invoked": False},
        receipt_path=path,
        runtime_writer_factory=factory,
        effect_journal=journal,
    )
    assert json.loads(path.read_text())["finalization"] == finalized["finalization"]
    assert len(dispatches) == 2
    assert events[-2:] == ["receipt", "close:runtime_receipt"]
    assert len(registry._lease_history) == 7
    assert len({lease.transaction_id for lease in registry._lease_history}) == 7
    assert all(lease.durable_outcome == "committed" for lease in registry._lease_history)


@pytest.mark.parametrize("invalid", ["held", "stale", "wrong_root", "forged"])
def test_canonical_invalid_binding_denies_before_gateway_construction(
    monkeypatch, tmp_path, invalid
):
    import nexus.orchestrator.writer_quiescence as writers
    from nexus.engine.canonical_task_seam import execute_canonical_product_task
    from nexus.orchestrator.writer_quiescence import WriterAdmissionDenied

    root = tmp_path / "selected"
    root.mkdir()
    _, registry, _ = _loaded_runtime(root)
    if invalid == "held":
        registry.begin_hold((str(root.resolve()),), cohort_id="held-canonical")
    elif invalid == "stale":
        install_generation(root, EventWriterGeneration(2, "runtime-writer"), expected_generation=1)
    elif invalid == "wrong_root":
        other = tmp_path / "other"
        other.mkdir()
        other_factory, _, _ = _loaded_runtime(other)
        monkeypatch.setitem(
            writers._LOADED_RUNTIME_WRITER_FACTORIES, str(root.resolve()), other_factory
        )
    else:
        monkeypatch.setitem(writers._LOADED_RUNTIME_WRITER_FACTORIES, str(root.resolve()), object())

    monkeypatch.setattr(
        "nexus.services.gateway.BattlesuitGateway.__init__",
        lambda *_a, **_kw: pytest.fail(
            "binding must be validated before Gateway creates directories"
        ),
    )
    with pytest.raises((WriterAdmissionDenied, ValueError)):
        execute_canonical_product_task(
            "audit bounded runtime integration",
            root,
            execution_context={
                "task_id": "invalid",
                "workspace_revision": "fixture-revision",
                "local_assist_mode": "disabled",
                "online_policy": "auto",
            },
        )
    assert not (root / ".nexus/reports").exists()


@pytest.mark.parametrize("invalid", ["missing", "root_changed", "generation_changed"])
def test_canonical_missing_or_incompatible_effect_binding_denies_before_construction(
    monkeypatch, tmp_path, invalid
):
    from nexus.engine.canonical_task_seam import execute_canonical_product_task
    from nexus.orchestrator.writer_quiescence import WriterAdmissionDenied

    factory, registry, _ = _loaded_runtime(tmp_path, effects=invalid != "missing")
    if invalid == "root_changed":
        factory.effect_binding().journal.project_root = tmp_path / "other"
    elif invalid == "generation_changed":
        factory.effect_binding().journal.generation = EventWriterGeneration(2, "runtime-writer")
    monkeypatch.setattr(
        "nexus.services.gateway.BattlesuitGateway.__init__",
        lambda *_a, **_kw: pytest.fail("incompatible effect port reached Gateway construction"),
    )
    with pytest.raises((WriterAdmissionDenied, ValueError)):
        execute_canonical_product_task(
            "audit bounded runtime integration",
            tmp_path,
            execution_context={
                "task_id": "effect-denied",
                "workspace_revision": "fixture-revision",
                "local_assist_mode": "disabled",
                "online_policy": "auto",
            },
        )
    assert registry._lease_history == []
    assert not (tmp_path / ".nexus/reports").exists()
