from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from dataclasses import replace

import pytest

from nexus.orchestrator.writer_quiescence import (
    DRAINED,
    UNKNOWN,
    HoldConflict,
    UnknownWriter,
    WriterAdmissionDenied,
    WriterIdentity,
    WriterQuiescenceError,
    WriterQuiescenceReceipt,
    WriterRegistry,
    current_process_start_identity,
)


def _registry(tmp_path, *, role="task_state", pending=lambda: (), snapshot=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    state = tmp_path / "state.bin"
    state.write_bytes(b"state-v1")
    registry = WriterRegistry(source_identity="source@tree", server_identity="srv")
    identity = WriterIdentity(
        str(tmp_path.resolve()),
        role,
        registry.source_identity,
        registry.process_start_identity,
        str(threading.get_ident()),
        7,
        f"{role}-writer",
    )
    registry.register(
        identity,
        snapshot=snapshot or state.read_bytes,
        process_state=lambda: "alive",
        pending=pending,
    )
    return registry, identity, state


def _acquire(registry, identity, **kwargs):
    return registry.acquire(
        root=identity.root,
        role=identity.role,
        writer_id=identity.writer_id,
        generation=identity.generation,
        **kwargs,
    )


def _ack(hold, identity):
    hold.acknowledge(
        identity.writer_id, root=identity.root, role=identity.role, generation=identity.generation
    )


def test_real_write_lease_and_durable_receipt_round_trip(tmp_path):
    registry, identity, state = _registry(tmp_path)
    with _acquire(registry, identity, operation_id="op-1", transaction_id="tx-1") as lease:
        assert lease.observation.exited_at is None
        with state.open("wb") as stream:
            stream.write(b"state-v2")
            stream.flush()
            os.fsync(stream.fileno())
        assert state.read_bytes() == b"state-v2"
    hold = registry.begin_hold([identity.root], cohort_id="cohort-1")
    _ack(hold, identity)
    receipt = hold.finalize()
    assert receipt.drain_state == DRAINED
    assert receipt.observations[0].snapshot_sha256 == hashlib.sha256(b"state-v2").hexdigest()
    assert receipt.leases[0].durable_outcome == "committed"
    assert receipt.leases[0].identity.thread_id == str(threading.get_ident())
    destination = tmp_path / "receipt.json"
    receipt.persist(destination)
    assert WriterQuiescenceReceipt.load(destination) == receipt
    assert receipt.verify() is receipt


def test_every_role_on_same_root_requires_ack_and_snapshot(tmp_path):
    registry, identity, state = _registry(tmp_path)
    second = replace(identity, role="event_log", writer_id="event-writer")
    event = tmp_path / "events.jsonl"
    event.write_bytes(b"{}\n")
    registry.register(
        second, snapshot=event.read_bytes, process_state=lambda: "idle", pending=lambda: ()
    )
    hold = registry.begin_hold([tmp_path])
    _ack(hold, identity)
    assert hold.finalize().drain_state == UNKNOWN
    _ack(hold, second)
    receipt = hold.finalize()
    assert receipt.drain_state == DRAINED
    assert {x.identity.role for x in receipt.observations} == {"task_state", "event_log"}
    assert {x.snapshot_sha256 for x in receipt.observations} == {
        hashlib.sha256(state.read_bytes()).hexdigest(),
        hashlib.sha256(event.read_bytes()).hexdigest(),
    }


def test_hold_closes_admission_and_waits_without_mutex(tmp_path):
    registry, identity, _ = _registry(tmp_path)
    entered, finish = threading.Event(), threading.Event()
    errors = []

    def worker():
        try:
            with _acquire(registry, identity):
                entered.set()
                assert finish.wait(3)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(2)
    hold = registry.begin_hold([tmp_path])
    with pytest.raises(WriterAdmissionDenied):
        _acquire(registry, identity)
    with pytest.raises(WriterAdmissionDenied):
        _ack(hold, identity)
    with pytest.raises(TimeoutError):
        hold.wait_for_drain(0.01)
    assert hold.finalize().drain_state == UNKNOWN
    finish.set()
    hold.wait_for_drain(2)
    thread.join(2)
    assert not thread.is_alive() and not errors
    _ack(hold, identity)
    assert hold.finalize().drain_state == DRAINED


def test_observation_callback_runs_outside_registry_mutex(tmp_path):
    registry, identity, state = _registry(tmp_path)
    second = replace(identity, writer_id="second")

    def snapshot():
        done = threading.Event()
        thread = threading.Thread(target=lambda: (registry.snapshot(), done.set()))
        thread.start()
        assert done.wait(1), "registry mutex held across observer"
        thread.join(1)
        return state.read_bytes()

    registry.register(second, snapshot=snapshot, process_state=lambda: "alive", pending=lambda: ())
    hold = registry.begin_hold([tmp_path])
    _ack(hold, identity)
    _ack(hold, second)
    assert hold.finalize().drain_state == DRAINED


def test_duplicate_replay_wrong_thread_and_forged_lease_denied(tmp_path):
    registry, identity, _ = _registry(tmp_path)
    lease = _acquire(registry, identity, operation_id="same")
    with pytest.raises(WriterAdmissionDenied):
        _acquire(registry, identity, operation_id="same")
    with pytest.raises(UnknownWriter):
        _acquire(registry, identity, thread_id="not-current")
    failures = []

    def wrong_thread():
        try:
            lease.close()
        except WriterAdmissionDenied:
            failures.append(True)

    thread = threading.Thread(target=wrong_thread)
    thread.start()
    thread.join(2)
    assert failures == [True] and len(registry.snapshot()["active_leases"]) == 1
    lease.close()
    with pytest.raises(WriterAdmissionDenied):
        _acquire(registry, identity, operation_id="same")


def test_actual_fork_cannot_reuse_registry(tmp_path):
    registry, identity, _ = _registry(tmp_path)
    child = os.fork()
    if child == 0:
        try:
            _acquire(registry, identity)
        except UnknownWriter:
            os._exit(0)
        os._exit(2)
    _, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert not registry.snapshot()["active_leases"]


def test_fabricated_process_and_registration_thread_denied(tmp_path):
    with pytest.raises(UnknownWriter):
        WriterRegistry(source_identity="s", process_start_identity="fake")
    registry, identity, _ = _registry(tmp_path)
    with pytest.raises(UnknownWriter):
        registry.register(replace(identity, writer_id="other", thread_id="fake"))
    with pytest.raises(UnknownWriter):
        _acquire(registry, replace(identity, generation=6))
    assert current_process_start_identity() == registry.process_start_identity


def test_hold_survives_new_registry_and_corruption(tmp_path):
    registry, identity, _ = _registry(tmp_path)
    hold = registry.begin_hold([tmp_path])
    _ack(hold, identity)
    assert hold.finalize().drain_state == DRAINED
    restarted = WriterRegistry(source_identity="source@tree", server_identity="srv")
    restarted.register(identity)
    with pytest.raises(WriterAdmissionDenied):
        _acquire(restarted, identity)
    with pytest.raises(HoldConflict):
        restarted.begin_hold([tmp_path])
    marker = tmp_path / ".nexus" / "writer-quiescence-hold.json"
    marker.write_bytes(b"corrupt")
    with pytest.raises(WriterAdmissionDenied):
        _acquire(restarted, identity)
    with pytest.raises(HoldConflict):
        hold.finalize()
    assert restarted.snapshot()["held_roots"] == [str(tmp_path.resolve())]


def test_registration_frozen_and_release_owned_by_cohort(tmp_path):
    registry, identity, _ = _registry(tmp_path)
    hold = registry.begin_hold([tmp_path])
    with pytest.raises(WriterAdmissionDenied):
        registry.register(replace(identity, writer_id="new"))
    with pytest.raises(HoldConflict):
        registry.begin_hold([tmp_path])
    with pytest.raises(WriterQuiescenceError):
        hold.release()
    assert "ACTIVE" not in hold.finalize().to_bytes().decode()


@pytest.mark.parametrize("pending", [None, lambda: None, lambda: "", lambda: ["job-1"]])
def test_missing_or_pending_observation_is_unknown(tmp_path, pending):
    registry, identity, _ = _registry(tmp_path, pending=pending)
    hold = registry.begin_hold([tmp_path])
    _ack(hold, identity)
    assert hold.finalize().drain_state == UNKNOWN


def test_unregistered_root_cannot_be_empty_drained(tmp_path):
    registry = WriterRegistry(source_identity="s")
    hold = registry.begin_hold([tmp_path])
    receipt = hold.finalize()
    assert receipt.drain_state == UNKNOWN
    assert any(x.startswith("writers:unregistered:") for x in receipt.unknowns)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw.pop("receipt_sha256"),
        lambda raw: raw.update(schema="anything"),
        lambda raw: raw.update(hold_epoch=True),
        lambda raw: raw.update(ordered_roots=[]),
        lambda raw: raw.update(observations=[]),
        lambda raw: raw["observations"][0].pop("pending_work"),
        lambda raw: raw["observations"][0].update(acknowledged_epoch=999),
        lambda raw: raw["observations"][0].update(snapshot_sha256=None),
    ],
)
def test_receipt_forgery_is_rejected_even_when_rehashed(tmp_path, mutation):
    registry, identity, _ = _registry(tmp_path)
    hold = registry.begin_hold([tmp_path])
    _ack(hold, identity)
    raw = json.loads(hold.finalize().to_bytes())
    mutation(raw)
    if "receipt_sha256" in raw:
        del raw["receipt_sha256"]
        raw["receipt_sha256"] = hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    with pytest.raises((ValueError, KeyError)):
        WriterQuiescenceReceipt.from_bytes(json.dumps(raw).encode())


def test_symlink_hold_does_not_reopen_admission(tmp_path):
    registry, identity, _ = _registry(tmp_path)
    directory = tmp_path / ".nexus"
    directory.mkdir()
    (directory / "writer-quiescence-hold.json").symlink_to(tmp_path / "absent")
    with pytest.raises(WriterAdmissionDenied):
        _acquire(registry, identity)
    with pytest.raises(HoldConflict):
        registry.begin_hold([tmp_path])


def test_child_crash_preserves_unresolved_operation_and_hold(tmp_path):
    script = """
import os,sys,threading
from pathlib import Path
from nexus.orchestrator.writer_quiescence import WriterRegistry,WriterIdentity
root=Path(sys.argv[1]).resolve()
r=WriterRegistry(source_identity="source@tree",server_identity="srv")
i=WriterIdentity(str(root),"task_state",r.source_identity,r.process_start_identity,str(threading.get_ident()),7,"task_state-writer")
r.register(i,snapshot=lambda:b"observed",process_state=lambda:"alive",pending=lambda:())
r.acquire(root=root,role=i.role,writer_id=i.writer_id,generation=7,operation_id="crashed")
r.begin_hold([root],cohort_id="crashed-cohort")
os._exit(23)
"""
    child = subprocess.run(
        [sys.executable, "-B", "-c", script, str(tmp_path)], timeout=10, capture_output=True
    )
    assert child.returncode == 23, child.stderr.decode()
    marker = json.loads((tmp_path / ".nexus" / "writer-quiescence-hold.json").read_bytes())
    assert marker["cohort_id"] == "crashed-cohort"
    lease_files = list((tmp_path / ".nexus" / "writer-quiescence-leases").glob("*.json"))
    assert len(lease_files) == 1
    assert json.loads(lease_files[0].read_bytes())["exited_at"] is None
    registry, identity, _ = _registry(tmp_path)
    with pytest.raises(WriterAdmissionDenied):
        _acquire(registry, identity)
    with pytest.raises(HoldConflict):
        registry.begin_hold([tmp_path])


def test_pure_finalized_loader_has_no_write_or_callback(tmp_path):
    calls = []
    registry, identity, _ = _registry(tmp_path, snapshot=lambda: (calls.append(1), b"bytes")[1])
    with pytest.raises(UnknownWriter, match="MISSING_FINALIZED"):
        registry.load_finalized("absent")
    assert not (tmp_path / ".nexus").exists()
    hold = registry.begin_hold([tmp_path], cohort_id="c")
    _ack(hold, identity)
    receipt = registry.persist_finalized(hold)
    calls.clear()
    before = {str(x): x.read_bytes() for x in tmp_path.rglob("*") if x.is_file()}
    assert registry.load_finalized("c") == receipt
    assert calls == []
    assert before == {str(x): x.read_bytes() for x in tmp_path.rglob("*") if x.is_file()}
    destination = next((tmp_path / ".nexus" / "writer-quiescence-receipts").glob("*.json"))
    destination.write_bytes(receipt.to_bytes() + b" ")
    with pytest.raises(WriterAdmissionDenied, match="RECEIPT_CHANGED"):
        registry.load_finalized("c")


@pytest.mark.parametrize("race_hold", [False, True])
def test_two_process_opposite_domain_paths_release_before_next_lock(tmp_path, race_hold):
    # Two source-owned in-process registries have explicitly separate fixture
    # operation stores. Both touch the SAME physical state/event roots. This
    # tests B lease/guard ordering, not absence of unregistered live writers.
    script = r"""
import contextlib,json,os,sys,threading
from pathlib import Path
from nexus.events.writer_generation import event_store_lock
from nexus.orchestrator.writer_quiescence import WriterRegistry,WriterIdentity,WriterAdmissionDenied
base=Path(sys.argv[1]).resolve()
index=int(sys.argv[2])
roots=[base/"state",base/"events"]
registry=WriterRegistry(source_identity="fixture-source",server_identity=f"child-{index}",hold_store=base/f"store-{index}")
identities=[]
for root,role in zip(roots,("task_state","event_log")):
    identity=WriterIdentity(str(root),role,registry.source_identity,registry.process_start_identity,str(threading.get_ident()),1,f"{role}-{index}")
    registry.register(identity,snapshot=lambda root=root:(root/"marks.jsonl").read_bytes(),process_state=lambda:"alive",pending=lambda:())
    identities.append(identity)
held=[]
@contextlib.contextmanager
def guard(root):
    if held and held[-1] != root:
        raise AssertionError("distinct second physical domain lock")
    with event_store_lock(root,timeout=2):
        held.append(root)
        try:
            yield
        finally:
            held.pop()
written=[]
for position in ([0,1] if index == 0 else [1,0]):
    identity=identities[position]
    try:
        with registry.acquire(root=identity.root,role=identity.role,writer_id=identity.writer_id,generation=1,operation_id=f"{index}-{position}"):
            root=roots[position]
            with guard(root):
                # Actual P6 same-underlying-lock reentry remains valid.
                with guard(root):
                    if not written:
                        print("entered",flush=True)
                        assert sys.stdin.readline().strip() == "continue"
                    token=f"{index}-{position}"
                    with (root/"marks.jsonl").open("ab") as stream:
                        stream.write((json.dumps({"token":token})+"\n").encode())
                        stream.flush()
                        os.fsync(stream.fileno())
                    written.append(token)
    except WriterAdmissionDenied:
        assert written, "hold must race an already admitted first operation"
        break
assert not held
print(json.dumps({"written":written}),flush=True)
"""
    for name in ("state", "events"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "marks.jsonl").write_bytes(b"")
    children = [
        subprocess.Popen(
            [sys.executable, "-B", "-c", script, str(tmp_path), str(i)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(2)
    ]
    try:
        # Select ensures a broken/deadlocked child cannot stall the verifier.
        import select

        for child in children:
            assert select.select([child.stdout], [], [], 5)[0], (
                "child failed to enter before deadline"
            )
            assert child.stdout.readline().strip() == "entered"
        if race_hold:
            for index in range(2):
                registry = WriterRegistry(
                    source_identity="fixture-source", hold_store=tmp_path / f"store-{index}"
                )
                registry.begin_hold(
                    [tmp_path / "state", tmp_path / "events"], cohort_id=f"hold-{index}"
                )
        for child in children:
            child.stdin.write("continue\n")
            child.stdin.flush()
        results = []
        for child in children:
            stdout, stderr = child.communicate(timeout=5)
            assert child.returncode == 0, stderr
            results.extend(json.loads(stdout.strip())["written"])
        assert len(results) == (2 if race_hold else 4)
        observed = []
        for name in ("state", "events"):
            observed.extend(
                json.loads(line)["token"]
                for line in (tmp_path / name / "marks.jsonl").read_text().splitlines()
            )
        assert sorted(observed) == sorted(results)
        assert len(observed) == len(set(observed))
        if race_hold:
            for index in range(2):
                restarted = WriterRegistry(
                    source_identity="fixture-source", hold_store=tmp_path / f"store-{index}"
                )
                with pytest.raises(HoldConflict):
                    restarted.begin_hold([tmp_path / "state", tmp_path / "events"])
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=3)


def test_expired_lease_is_durable_unresolved_not_success(tmp_path):
    import time

    registry = WriterRegistry(source_identity="source", lease_lifetime_seconds=0.02)
    identity = WriterIdentity(
        str(tmp_path.resolve()),
        "task_state",
        registry.source_identity,
        registry.process_start_identity,
        str(threading.get_ident()),
        1,
        "writer",
    )
    registry.register(
        identity,
        snapshot=lambda: b"actual fixture bytes",
        process_state=lambda: "alive",
        pending=lambda: (),
    )
    lease = _acquire(registry, identity, operation_id="expires")
    lease.validate()
    time.sleep(0.03)
    with pytest.raises(WriterAdmissionDenied, match="expired"):
        lease.close()
    with pytest.raises(WriterAdmissionDenied, match="unresolved"):
        lease.close()
    assert lease.observation.durable_outcome == "unresolved"
    hold = registry.begin_hold([tmp_path])
    _ack(hold, identity)
    receipt = hold.finalize()
    assert receipt.drain_state == UNKNOWN
    assert receipt.leases[0].expires_at < receipt.leases[0].exited_at
    assert WriterQuiescenceReceipt.from_bytes(receipt.to_bytes()) == receipt
    with pytest.raises(WriterAdmissionDenied, match="NOT_DRAINED"):
        registry.persist_finalized(hold)


@pytest.mark.parametrize("lifetime", [0, -1, 301, True, float("nan"), float("inf")])
def test_invalid_source_owned_lease_lifetime(lifetime):
    with pytest.raises(ValueError):
        WriterRegistry(source_identity="source", lease_lifetime_seconds=lifetime)


@pytest.mark.parametrize("mode", ["match", "missing", "stale", "physical-mismatch"])
def test_reacquisition_observes_actual_advanced_p6_without_release(tmp_path, mode):
    from nexus.events.state_owner_manifest import (
        StateOwnerBinding,
        commit_manifest,
        prepare_manifest,
    )
    from nexus.events.writer_generation import EventWriterGeneration, install_generation

    # Only the fixture transaction installs physical generations. The B observer
    # is independently checked to leave all resulting bytes unchanged.
    registry = WriterRegistry(source_identity="source", server_identity="server")
    state = tmp_path / "state.json"
    state.write_bytes(b"{}\n")
    identity = WriterIdentity(
        str(tmp_path.resolve()),
        "task_state",
        registry.source_identity,
        registry.process_start_identity,
        str(threading.get_ident()),
        1,
        "writer",
    )
    event_identity = replace(identity, role="event_log")
    loaded = [identity, event_identity]
    registry.register(
        identity,
        snapshot=state.read_bytes,
        process_state=lambda: "alive",
        pending=lambda: (),
        loaded_identity=lambda: loaded[0],
    )
    install_generation(tmp_path, EventWriterGeneration(1, "writer"))
    event = tmp_path / ".nexus" / "events" / "event_log.jsonl"
    event.write_bytes(b"{}\n")
    registry.register(
        event_identity,
        snapshot=event.read_bytes,
        process_state=lambda: "alive",
        pending=lambda: (),
        loaded_identity=None if mode == "missing" else lambda: loaded[1],
    )
    selected_files = {"task_state": "state.json", "event_log": ".nexus/events/event_log.jsonl"}
    initial_binding = StateOwnerBinding("owner", tmp_path.resolve(), 1, "first")
    initial = commit_manifest(
        initial_binding,
        prepare_manifest(initial_binding, writer_id="writer", files=selected_files),
    )
    hold = registry.begin_hold([tmp_path], cohort_id="reacquire")
    _ack(hold, identity)
    _ack(hold, event_identity)
    install_generation(tmp_path, EventWriterGeneration(2, "writer"), expected_generation=1)
    next_binding = StateOwnerBinding("owner", tmp_path.resolve(), 2, "next")
    commit_manifest(
        next_binding,
        prepare_manifest(
            next_binding,
            writer_id="writer",
            files=selected_files,
            previous_manifest_sha256=initial.manifest_sha256,
        ),
    )
    loaded[0] = replace(identity, generation=2)
    if mode != "stale":
        loaded[1] = replace(event_identity, generation=2)
    if mode == "physical-mismatch":
        install_generation(tmp_path, EventWriterGeneration(3, "writer"), expected_generation=2)
    before = {str(x): x.read_bytes() for x in tmp_path.rglob("*") if x.is_file()}
    receipt = registry.observe_reacquisition(hold)
    assert receipt.state == ("REACQUIRED" if mode == "match" else UNKNOWN)
    assert len(receipt.observations) == 2
    assert receipt.observations[0].manifest_sha256
    assert before == {str(x): x.read_bytes() for x in tmp_path.rglob("*") if x.is_file()}
    assert registry.snapshot()["writers"][0]["generation"] == 1
    assert registry.snapshot()["held_roots"] == [str(tmp_path.resolve())]
    with pytest.raises(WriterAdmissionDenied):
        _acquire(registry, identity)
    with pytest.raises(WriterQuiescenceError):
        hold.release()
    assert "ACTIVE" not in receipt.to_bytes().decode()
