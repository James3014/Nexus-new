"""Cold-start registration of a provisional runtime writer factory."""

import copy
import importlib
import threading

import pytest

from nexus.events.state_owner_manifest import (
    StateOwnerBinding,
    StateOwnerSelection,
    commit_owner_transaction,
    owner_transaction_guard,
)
from nexus.events.writer_generation import EventWriterGeneration, install_generation
from nexus.orchestrator.writer_quiescence import (
    RecoveryHoldProof,
    RuntimeWriterAdapter,
    RuntimeWriterFactory,
    WriterAdmissionDenied,
    WriterIdentity,
    WriterRegistry,
)


def _registry_module(registry):
    """Patch the module that defines the loaded registry implementation."""
    return importlib.import_module(type(registry).__module__)


def _held_runtime(tmp_path, *, historical=False):
    root = tmp_path.resolve()
    (root / ".nexus" / "events").mkdir(parents=True)
    (root / ".nexus" / "reports").mkdir()
    (root / ".nexus" / "events" / "event_log.jsonl").touch()
    (root / ".nexus" / "events" / "effect_journal.v1.json").touch()
    registry = WriterRegistry(source_identity="test-source")
    identity = WriterIdentity(
        str(root), "runtime_receipt", registry.source_identity,
        registry.process_start_identity, str(threading.get_ident()), 0, "writer-0"
    )
    registry.register(identity, snapshot=lambda: b"", process_state=lambda: "idle", pending=lambda: ())
    effect = WriterIdentity(
        str(root), "effect_journal", registry.source_identity,
        registry.process_start_identity, identity.thread_id, 0, "writer-0"
    )
    registry.register(effect, snapshot=lambda: b"", process_state=lambda: "idle", pending=lambda: ())
    if historical:
        def previous_operation():
            registry.acquire(root=root,role="runtime_receipt",writer_id="writer-0",generation=0,operation_id="historical-operation",transaction_id="historical-tx").close("failed")
        if historical == "thread":
            worker = threading.Thread(target=previous_operation)
            worker.start()
            worker.join()
        else:
            previous_operation()
    hold = registry.begin_hold((root,), cohort_id="cold-start")
    for item in hold.selected:
        hold.acknowledge(item.identity.writer_id, root=root, role=item.identity.role, generation=0)
    registry.persist_finalized(hold)
    token = EventWriterGeneration(1, "writer-1")
    install_generation(root, token)
    binding = StateOwnerBinding("owner", root, 1, "cold-start-transaction")
    selections = (
        StateOwnerSelection("runtime", "runtime_receipt", ".nexus/reports/entry.json"),
        StateOwnerSelection("effects", "effect_journal", ".nexus/events/effect_journal.v1.json"),
    )
    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        manifest = commit_owner_transaction(context)
    attachment = registry.issue_initial_attachment(
        hold, root=str(root), generation=1, writer_id=token.writer_id,
        manifest_sha256=manifest.manifest_sha256,
    )
    adapter = RuntimeWriterAdapter(
        registry, binding=binding, writer_generation=token, root=root,
        writer_id=token.writer_id, initial_attachment=attachment,
    )
    return registry, hold, attachment, RuntimeWriterFactory(adapter)


def test_held_runtime_factory_registration_requires_exact_attachment(tmp_path):
    registry, hold, attachment, factory = _held_runtime(tmp_path)
    before = (dict(registry._writers), dict(registry._initial_attachments), dict(registry._held_roots))
    from nexus.orchestrator.writer_quiescence import register_runtime_writer_factory

    assert register_runtime_writer_factory(factory, initial_attachment=attachment) is factory
    assert (registry._writers, registry._initial_attachments, registry._held_roots) == before
    with pytest.raises(WriterAdmissionDenied):
        with factory.for_operation("entry"):
            pass


def test_default_copy_and_foreign_attachment_are_denied(tmp_path):
    registry, hold, attachment, factory = _held_runtime(tmp_path)
    from nexus.orchestrator.writer_quiescence import register_runtime_writer_factory

    with pytest.raises(WriterAdmissionDenied):
        register_runtime_writer_factory(factory)
    with pytest.raises((WriterAdmissionDenied, TypeError)):
        register_runtime_writer_factory(factory, initial_attachment=copy.copy(attachment))
    foreign_registry, _, foreign_attachment, _ = _held_runtime(tmp_path / "foreign")
    with pytest.raises(WriterAdmissionDenied):
        register_runtime_writer_factory(factory, initial_attachment=foreign_attachment)


def test_recovery_proof_is_registry_opaque(tmp_path):
    registry, _, _, _ = _held_runtime(tmp_path)
    forged = RecoveryHoldProof(
        registry,
        cohort_id="cold-start",
        roots=(str(tmp_path.resolve()),),
        path=tmp_path / "missing-recovery.json",
        predecessor={}, predecessor_sha="0" * 64, markers=(None,), selected=(),
    )
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(forged)
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(copy.copy(forged))


def _recovery(tmp_path, *, historical=False):
    import hashlib
    import json
    from dataclasses import replace
    from nexus.orchestrator.writer_quiescence import WriterQuiescenceReceipt

    old_registry, hold, _, _ = _held_runtime(tmp_path,historical=historical)
    dead = "pid:99999999:start:deceased"
    drain = old_registry.load_finalized(hold.cohort_id)
    drain = replace(drain, process_start_identity=dead, observations=tuple(
        replace(x, identity=replace(x.identity, process_start_identity=dead)) for x in drain.observations
    ), leases=tuple(replace(x,identity=replace(x.identity,process_start_identity=dead)) for x in drain.leases), receipt_sha256="")
    for lease in drain.leases:
        old_registry._lease_path(lease.identity.root,lease.operation_id).write_bytes(json.dumps(lease.to_dict(),sort_keys=True,separators=(",", ":")).encode())
    drain_path = old_registry._finalized[hold.cohort_id][1]
    drain_path.write_bytes(drain.to_bytes())
    marker_path = old_registry._marker_path(str(tmp_path))
    marker = json.loads(marker_path.read_bytes())
    marker["process_start_identity"] = dead
    marker["selected_writers"] = [x.identity.to_dict() for x in drain.observations]
    marker_path.write_bytes(json.dumps(marker, sort_keys=True, separators=(",", ":")).encode())
    payload = dict(schema="writer-activation-cohort/v1", cohort_id=hold.cohort_id,
        hold_epoch=hold.epoch, ordered_roots=list(hold.roots), source_identity=old_registry.source_identity,
        server_identity=old_registry.server_identity, process_start_identity=dead, state="HOLDING",
        hold_markers=[marker], original_drain={"bytes_sha256": hashlib.sha256(drain.to_bytes()).hexdigest(), "payload":json.loads(drain.to_bytes())},
        root_contracts=[dict(root=str(tmp_path),root_id="test-root",request_digest="a"*64,drain_receipt_hash="b"*64,transaction_id="cold-start-transaction",generation=1,writer_id="writer-1",root_identity="c"*64)], transitions=[], drain={"bytes_sha256":hashlib.sha256(drain.to_bytes()).hexdigest(),"payload":json.loads(drain.to_bytes())}, reacquisition=None, release_state="HELD", prior_digest="")
    path = tmp_path / ".nexus/writer-quiescence/activation-cohorts" / (hashlib.sha256(hold.cohort_id.encode()).hexdigest()+".json")
    path.parent.mkdir(parents=True)
    def save(value):
        value = dict(value)
        value.pop("receipt_sha256", None)
        value["receipt_sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        path.write_text(json.dumps(value,sort_keys=True,separators=(",", ":")))
        return value
    payload = save(payload)
    registry = WriterRegistry(source_identity=old_registry.source_identity)
    for item in hold.selected:
        registry.register(item.identity, snapshot=lambda:b"", process_state=lambda:"idle", pending=lambda:())
    def prepare():
        return registry.prepare_hold_recovery(cohort_id=hold.cohort_id,ordered_roots=hold.roots,expected_receipt_sha256=payload["receipt_sha256"])
    return registry, prepare, payload, save, path


@pytest.mark.parametrize("field,value", [("_path", "/tmp/forged"), ("_current_sha", "a"*64), ("_markers",()), ("_selected",()), ("_roots",()), ("_predecessor_sha","b"*64)])
def test_issued_recovery_proof_mutations_denied(tmp_path, field, value):
    registry, prepare, _, _, _ = _recovery(tmp_path)
    proof = prepare()
    setattr(proof,field,value)
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(proof)


def test_issued_recovery_proof_copy_foreign_and_nested_mutation(tmp_path):
    registry, prepare, _, _, _ = _recovery(tmp_path)
    proof = prepare()
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(copy.copy(proof))
    with pytest.raises(WriterAdmissionDenied):
        WriterRegistry(source_identity="test-source")._verify_recovery_proof(proof)
    proof._predecessor["state"] = "RELEASED"
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(proof)


def test_recovery_exact_cas_and_qualified_progression(tmp_path):
    registry, prepare, payload, save, path = _recovery(tmp_path)
    proof = prepare()
    successor = save(dict(payload,prior_digest=payload["receipt_sha256"], process_start_identity=registry.process_start_identity,server_identity=registry.server_identity))
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(proof)
    hold = registry.adopt_recovered_hold(proof,expected_successor_sha256=successor["receipt_sha256"])
    assert registry.adopt_recovered_hold(proof,expected_successor_sha256=successor["receipt_sha256"]) is hold
    next_receipt = save(dict(successor,state="APPLYING",prior_digest=successor["receipt_sha256"]))
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(proof)
    registry.advance_recovered_hold(proof,expected_predecessor_sha256=successor["receipt_sha256"],expected_successor_sha256=next_receipt["receipt_sha256"])
    registry.advance_recovered_hold(proof,expected_predecessor_sha256=successor["receipt_sha256"],expected_successor_sha256=next_receipt["receipt_sha256"])
    registry._verify_recovery_proof(proof)
    path.write_bytes(path.read_bytes()+b"\n")
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(proof)


def test_recovery_physical_marker_selection_and_pid_fail_closed(tmp_path, monkeypatch):
    registry, prepare, _, _, _ = _recovery(tmp_path)
    proof = prepare()
    marker = registry._marker_path(str(tmp_path))
    raw = marker.read_bytes()
    marker.unlink()
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(proof)
    marker.write_bytes(raw)
    item = next(iter(registry._writers.values()))
    registry._writers.pop(item.identity.key())
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(proof)
    registry._writers[item.identity.key()] = item
    registry._pid += 1
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(proof)


@pytest.mark.parametrize("damage", ["drain", "marker_vector", "alive"])
def test_recovery_prepare_rejects_invalid_physical_evidence(tmp_path, damage):
    registry, prepare, payload, save, _ = _recovery(tmp_path)
    if damage == "drain":
        next((tmp_path / ".nexus/writer-quiescence-receipts").iterdir()).write_bytes(b"{}")
    elif damage == "marker_vector":
        payload["hold_markers"] = []
        payload.update(save(payload))
    else:
        payload["process_start_identity"] = registry.process_start_identity
        payload.update(save(payload))
    with pytest.raises(WriterAdmissionDenied):
        prepare()


def test_recovery_proof_rechecks_original_drain_after_issue(tmp_path):
    registry, prepare, _, _, _ = _recovery(tmp_path)
    proof = prepare()
    next((tmp_path / ".nexus/writer-quiescence-receipts").iterdir()).write_bytes(b"{}")
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(proof)


def test_recovery_advance_rejects_self_consistent_contract_drift(tmp_path):
    registry, prepare, payload, save, _ = _recovery(tmp_path)
    proof = prepare()
    successor = save(dict(payload,prior_digest=payload["receipt_sha256"], process_start_identity=registry.process_start_identity,server_identity=registry.server_identity))
    registry.adopt_recovered_hold(proof,expected_successor_sha256=successor["receipt_sha256"])
    drift = save(dict(successor,state="APPLYING",root_contracts=[{"root":"forged"}],prior_digest=successor["receipt_sha256"]))
    with pytest.raises(WriterAdmissionDenied):
        registry.advance_recovered_hold(proof,expected_predecessor_sha256=successor["receipt_sha256"],expected_successor_sha256=drift["receipt_sha256"])


def test_recovery_reacquisition_requires_complete_physical_vector(tmp_path):
    import hashlib
    import json
    from dataclasses import replace
    from nexus.events.state_owner_manifest import read_manifest
    from nexus.orchestrator.writer_quiescence import WriterReacquisitionObservation, WriterReacquisitionReceipt
    registry, prepare, payload, save, _ = _recovery(tmp_path)
    proof = prepare()
    successor = save(dict(payload,prior_digest=payload["receipt_sha256"], process_start_identity=registry.process_start_identity,server_identity=registry.server_identity))
    registry.adopt_recovered_hold(proof,expected_successor_sha256=successor["receipt_sha256"])
    applying = save(dict(successor,state="APPLYING",prior_digest=successor["receipt_sha256"]))
    registry.advance_recovered_hold(proof,expected_predecessor_sha256=successor["receipt_sha256"],expected_successor_sha256=applying["receipt_sha256"])
    manifest = read_manifest(tmp_path)
    observations = []
    updates = []
    for row in payload["hold_markers"][0]["selected_writers"]:
        old = WriterIdentity(**row)
        item = registry._writers[old.key()]
        loaded = replace(item.identity,generation=manifest.generation,writer_id=manifest.writer_id)
        observations.append(WriterReacquisitionObservation(old,loaded,manifest.manifest_sha256,loaded.generation,loaded.writer_id,"MATCHED"))
        updates.append((item,loaded))
    receipt = WriterReacquisitionReceipt(proof._cohort_id,1,proof._roots,tuple(observations),())
    reacquiring = save(dict(applying,state="REACQUIRING",prior_digest=applying["receipt_sha256"],reacquisition={"bytes_sha256":hashlib.sha256(receipt.to_bytes()).hexdigest(),"payload":json.loads(receipt.to_bytes())}))
    registry.advance_recovered_hold(proof,expected_predecessor_sha256=applying["receipt_sha256"],expected_successor_sha256=reacquiring["receipt_sha256"])
    with pytest.raises(WriterAdmissionDenied):
        registry.confirm_recovered_reacquisition(proof,receipt)
    for item,loaded in updates:
        registry._writers.pop(item.identity.key())
        item.identity = loaded
        item.loaded_identity = lambda loaded=loaded: loaded
        registry._writers[loaded.key()] = item
    with pytest.raises(WriterAdmissionDenied):
        registry._verify_recovery_proof(proof)
    with pytest.raises(WriterAdmissionDenied):
        registry.confirm_recovered_reacquisition(proof,replace(receipt,observations=receipt.observations[:1]))
    registry.confirm_recovered_reacquisition(proof,receipt)
    registry._verify_recovery_proof(proof)
    registry.confirm_recovered_reacquisition(proof,receipt)
    contract = payload["root_contracts"][0]
    transition = dict(schema="nexus.state_owner_transition_receipt.v1",state="COMMITTED",root_id=contract["root_id"],request_digest=contract["request_digest"],transaction_id=contract["transaction_id"],next_generation=contract["generation"],next_writer_id=contract["writer_id"],expected_root_identity=contract["root_identity"],drain_receipt_hash=contract["drain_receipt_hash"])
    transition["receipt_digest"] = hashlib.sha256(json.dumps(transition,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    active = save(dict(reacquiring,state="ACTIVE",transitions=[transition],prior_digest=reacquiring["receipt_sha256"]))
    registry.advance_recovered_hold(proof,expected_predecessor_sha256=reacquiring["receipt_sha256"],expected_successor_sha256=active["receipt_sha256"])
    registry.confirm_recovered_reacquisition(proof,receipt)
    altered = replace(receipt,observations=(replace(receipt.observations[0],manifest_sha256="0"*64), *receipt.observations[1:]))
    with pytest.raises(WriterAdmissionDenied,match="historical durable result"):
        registry.confirm_recovered_reacquisition(proof,altered)


@pytest.mark.parametrize("damage", ["missing_reacquisition", "drain_hash", "release_state", "transition_hash"])
def test_recovery_advance_rejects_nested_evidence_tampering(tmp_path, damage):
    registry, prepare, payload, save, _ = _recovery(tmp_path)
    proof = prepare()
    successor = save(dict(payload,prior_digest=payload["receipt_sha256"],process_start_identity=registry.process_start_identity,server_identity=registry.server_identity))
    registry.adopt_recovered_hold(proof,expected_successor_sha256=successor["receipt_sha256"])
    altered = dict(successor,state="APPLYING",prior_digest=successor["receipt_sha256"])
    if damage == "missing_reacquisition":
        intermediate = save(altered)
        registry.advance_recovered_hold(proof,expected_predecessor_sha256=successor["receipt_sha256"],expected_successor_sha256=intermediate["receipt_sha256"])
        reacquiring = save(dict(intermediate,state="REACQUIRING",prior_digest=intermediate["receipt_sha256"]))
        registry.advance_recovered_hold(proof,expected_predecessor_sha256=intermediate["receipt_sha256"],expected_successor_sha256=reacquiring["receipt_sha256"])
        successor = reacquiring
        altered = dict(successor,state="ACTIVE",prior_digest=successor["receipt_sha256"],reacquisition=None)
    elif damage == "drain_hash":
        altered["drain"] = dict(altered["drain"],bytes_sha256="0"*64)
    elif damage == "release_state":
        altered["release_state"] = "RELEASED"
    else:
        altered["transitions"] = [{"receipt_digest":"0"*64}]
    damaged = save(altered)
    with pytest.raises(WriterAdmissionDenied):
        registry.advance_recovered_hold(proof,expected_predecessor_sha256=successor["receipt_sha256"],expected_successor_sha256=damaged["receipt_sha256"])


def _released_registry(tmp_path):
    import hashlib
    import json
    from dataclasses import replace
    from nexus.events.state_owner_manifest import read_manifest
    from nexus.orchestrator.writer_quiescence import WriterReacquisitionObservation, WriterReacquisitionReceipt
    registry, hold, _, _ = _held_runtime(tmp_path)
    drain = registry.load_finalized(hold.cohort_id)
    manifest = read_manifest(tmp_path)
    marker_path = registry._marker_path(str(tmp_path))
    marker = json.loads(marker_path.read_bytes())
    observations = []
    for item in hold.selected:
        old = item.identity
        loaded = replace(old,generation=1,writer_id="writer-1")
        observations.append(WriterReacquisitionObservation(old,loaded,manifest.manifest_sha256,1,"writer-1","MATCHED"))
        registry._writers.pop(old.key())
        item.identity = loaded
        item.loaded_identity = lambda loaded=loaded: loaded
        registry._writers[loaded.key()] = item
    reacquired = WriterReacquisitionReceipt(hold.cohort_id,hold.epoch,hold.roots,tuple(observations),())
    contract = dict(root=str(tmp_path),root_id="root",request_digest="a"*64,drain_receipt_hash=drain.receipt_sha256,transaction_id=manifest.transaction_id,generation=1,writer_id="writer-1",root_identity="c"*64)
    transition = dict(schema="nexus.state_owner_transition_receipt.v1",state="COMMITTED",root_id="root",request_digest="a"*64,transaction_id=manifest.transaction_id,next_generation=1,next_writer_id="writer-1",expected_root_identity="c"*64,drain_receipt_hash=drain.receipt_sha256)
    transition["receipt_digest"] = hashlib.sha256(json.dumps(transition,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    wrapped_drain = dict(payload=json.loads(drain.to_bytes()),bytes_sha256=hashlib.sha256(drain.to_bytes()).hexdigest())
    intent = dict(schema="writer-activation-cohort/v1",cohort_id=hold.cohort_id,hold_epoch=hold.epoch,ordered_roots=list(hold.roots),source_identity=registry.source_identity,server_identity=registry.server_identity,process_start_identity=registry.process_start_identity,state="RELEASE_INTENT",release_state="RELEASE_PENDING",root_contracts=[contract],hold_markers=[marker],original_drain=wrapped_drain,drain=wrapped_drain,transitions=[transition],reacquisition=dict(payload=json.loads(reacquired.to_bytes()),bytes_sha256=hashlib.sha256(reacquired.to_bytes()).hexdigest()),prior_digest="d"*64)
    receipt_path = registry._cohort_receipt_path(hold.roots,hold.cohort_id)
    receipt_path.parent.mkdir(parents=True)
    def save(payload):
        payload = dict(payload)
        payload.pop("receipt_sha256",None)
        payload["receipt_sha256"] = hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        receipt_path.write_text(json.dumps(payload,sort_keys=True,separators=(",", ":")))
        return payload
    intent = save(intent)
    anchor = registry.prepare_released_history(hold,expected_intent_sha256=intent["receipt_sha256"])
    marker_path.unlink()
    released = save(dict(intent,state="RELEASED",release_state="RELEASED",prior_digest=intent["receipt_sha256"]))
    registry.bind_released_history(anchor,expected_released_sha256=released["receipt_sha256"])
    registry._held_roots.clear()
    hold.released = True
    return registry, registry._cohort_history_path(hold.roots,hold.cohort_id)


def _history_lease(registry, root, operation="operation"):
    return registry.acquire(root=root,role="runtime_receipt",writer_id="writer-1",generation=1,operation_id=operation,transaction_id="tx-"+operation)


def test_released_history_records_admission_and_exact_terminal_replay_fence(tmp_path):
    registry,path = _released_registry(tmp_path)
    lease = _history_lease(registry,tmp_path)
    data,_ = registry._history_read(path)
    assert data["operations"]["operation"]["phase"] == "ADMITTED"
    lease.close("committed")
    data,_ = registry._history_read(path)
    row = data["operations"]["operation"]
    assert row["phase"] == "TERMINAL"
    assert registry._history_validate_rows(data,recover=True) == {row["path"]:row["terminal_sha256"]}
    with pytest.raises(WriterAdmissionDenied):
        _history_lease(registry,tmp_path)
    from pathlib import Path
    Path(row["path"]).unlink()
    with pytest.raises(WriterAdmissionDenied):
        registry._history_validate_rows(data,recover=True)


@pytest.mark.parametrize("damage",["role","generation","process","outcome","terminal_hash"])
def test_released_history_rejects_indexed_identity_or_terminal_drift(tmp_path,damage):
    registry,path = _released_registry(tmp_path)
    _history_lease(registry,tmp_path).close("committed")
    data,_ = registry._history_read(path)
    row = data["operations"]["operation"]
    if damage == "role": row["active"]["role"] = "gateway_assist"
    elif damage == "generation": row["active"]["generation"] = 77
    elif damage == "process": row["active"]["process_start_identity"] = "pid:1:start:forged"
    elif damage == "outcome": row["terminal"]["durable_outcome"] = "unresolved"
    else: row["terminal_sha256"] = "0"*64
    with pytest.raises(WriterAdmissionDenied):
        registry._history_validate_rows(data,recover=True)


def test_released_history_terminal_intent_reconciles_exact_final_bytes(tmp_path,monkeypatch):
    registry,path = _released_registry(tmp_path)
    lease = _history_lease(registry,tmp_path)
    real_closed = registry._history_closed
    monkeypatch.setattr(registry,"_history_closed",lambda result: (_ for _ in ()).throw(OSError("lost index commit")))
    with pytest.raises(OSError): lease.close("committed")
    data,raw = registry._history_read(path)
    assert data["operations"]["operation"]["phase"] == "TERMINAL_INTENT"
    pins = registry._history_validate_rows(data,recover=True)
    assert pins and data["operations"]["operation"]["phase"] == "TERMINAL"
    registry._history_write(path,data,raw)
    monkeypatch.setattr(registry,"_history_closed",real_closed)
    lease.close("committed")


def test_released_history_unentered_intent_is_cancelled_but_entered_is_unresolved(tmp_path,monkeypatch):
    registry,path = _released_registry(tmp_path)
    module = _registry_module(registry)
    atomic = module._atomic_bytes
    def fail_lease(path, raw, **kwargs):
        if path.parent == registry._lease_dir(str(tmp_path)):
            raise OSError("before lease publication")
        return atomic(path,raw,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(module,"_atomic_bytes",fail_lease)
        with pytest.raises(OSError): _history_lease(registry,tmp_path)
    data,raw = registry._history_read(path)
    registry._history_validate_rows(data,recover=True)
    assert data["operations"]["operation"]["phase"] == "CANCELLED_BEFORE_ENTRY"
    registry._history_write(path,data,raw)
    with pytest.raises(WriterAdmissionDenied): _history_lease(registry,tmp_path)
    _history_lease(registry,tmp_path,"entered")
    data,_ = registry._history_read(path)
    with pytest.raises(WriterAdmissionDenied,match="unresolved"):
        registry._history_validate_rows(data,recover=True)


def test_released_history_terminal_intent_replays_only_exact_active_bytes(tmp_path,monkeypatch):
    registry,path = _released_registry(tmp_path)
    module = _registry_module(registry)
    lease = _history_lease(registry,tmp_path)
    lease_path = registry._lease_path(str(tmp_path),lease.operation_id)
    original = lease_path.read_bytes()
    atomic = module._atomic_bytes
    def fail_terminal(path, raw, **kwargs):
        if path == lease_path:
            raise OSError("after terminal intent before lease CAS")
        return atomic(path,raw,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(module,"_atomic_bytes",fail_terminal)
        with pytest.raises(OSError): lease.close("committed")
    assert lease_path.read_bytes() == original
    data,raw = registry._history_read(path)
    assert data["operations"]["operation"]["phase"] == "TERMINAL_INTENT"
    pins = registry._history_validate_rows(data,recover=True)
    assert lease_path.read_bytes() != original
    assert pins and data["operations"]["operation"]["phase"] == "TERMINAL"
    registry._history_write(path,data,raw)
    lease.close("committed")


def test_unentered_published_lease_is_cancelled_without_fabricating_terminal(tmp_path,monkeypatch):
    registry,path = _released_registry(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(registry,"_history_admitted",lambda observation: (_ for _ in ()).throw(OSError("before admitted fsync")))
        with pytest.raises(OSError): _history_lease(registry,tmp_path)
    lease_path = registry._lease_path(str(tmp_path),"operation")
    original = lease_path.read_bytes()
    data,raw = registry._history_read(path)
    assert registry._history_validate_rows(data,recover=True) == {}
    registry._history_write(path,data,raw)
    assert lease_path.read_bytes() == original
    assert registry._durable_leases(str(tmp_path)) == ([],[])
    with pytest.raises(WriterAdmissionDenied): _history_lease(registry,tmp_path)
    _history_lease(registry,tmp_path,"next-operation").close("committed")


def test_released_history_physical_index_mutation_denies_next_admission(tmp_path):
    registry,path = _released_registry(tmp_path)
    _history_lease(registry,tmp_path).close("committed")
    path.write_bytes(path.read_bytes()+b"\n")
    with pytest.raises(WriterAdmissionDenied):
        _history_lease(registry,tmp_path,"next-operation")


def test_terminal_intent_recovery_validates_entire_inventory_before_writing(tmp_path,monkeypatch):
    registry,path = _released_registry(tmp_path)
    module = _registry_module(registry)
    lease = _history_lease(registry,tmp_path)
    lease_path = registry._lease_path(str(tmp_path),lease.operation_id)
    original = lease_path.read_bytes()
    atomic = module._atomic_bytes
    with monkeypatch.context() as patch:
        def fail_terminal(path,raw,**kwargs):
            if path == lease_path: raise OSError("terminal write crash")
            return atomic(path,raw,**kwargs)
        patch.setattr(module,"_atomic_bytes",fail_terminal)
        with pytest.raises(OSError): lease.close("committed")
    data,_ = registry._history_read(path)
    extra = registry._lease_path(str(tmp_path),"unindexed")
    extra.write_bytes(original)
    with pytest.raises(WriterAdmissionDenied,match="unindexed"):
        registry._history_validate_rows(data,recover=True)
    assert lease_path.read_bytes() == original


def test_released_history_session_membership_requires_receipt_chain(tmp_path):
    registry,path = _released_registry(tmp_path)
    data,_ = registry._history_read(path)
    data["sessions"].append("pid:99999999:start:forged")
    with pytest.raises(WriterAdmissionDenied):
        registry._history_validate_rows(data,recover=True)
    data,_ = registry._history_read(path)
    data["released"]["prior_digest"] = "0"*64
    with pytest.raises(WriterAdmissionDenied):
        registry._history_validate_rows(data,recover=True)


@pytest.mark.parametrize("historical", [True, "thread"])
def test_b_terminal_reconciliation_uses_issued_proof_without_host_module(tmp_path,monkeypatch,historical):
    import builtins
    registry,prepare,payload,save,_ = _recovery(tmp_path,historical=historical)
    proof = prepare()
    successor = save(dict(payload,prior_digest=payload["receipt_sha256"],process_start_identity=registry.process_start_identity,server_identity=registry.server_identity))
    registry.adopt_recovered_hold(proof,expected_successor_sha256=successor["receipt_sha256"])
    real_import = builtins.__import__
    def no_host(name,*args,**kwargs):
        if "writer_activation_cohort" in name:
            raise ImportError("host package intentionally unavailable")
        return real_import(name,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(builtins,"__import__",no_host)
        assert registry.reconcile_terminal_history(proof) == 1
        assert registry.reconcile_terminal_history(proof) == 1
    assert registry._durable_leases(str(tmp_path))[1] == []
    with pytest.raises(WriterAdmissionDenied):
        registry.reconcile_terminal_history(copy.copy(proof))
    historical = registry._lease_path(str(tmp_path),"historical-operation")
    historical.write_bytes(historical.read_bytes()+b"\n")
    with pytest.raises(WriterAdmissionDenied):
        registry.reconcile_terminal_history(proof)
