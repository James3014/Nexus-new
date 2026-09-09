"""B pre-F recovery using real registry markers/drain and a dead subprocess."""

import hashlib
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from nexus.orchestrator.writer_quiescence import (
    WriterAdmissionDenied,
    WriterIdentity,
    WriterRegistry,
)

SOURCE = "installed-source@tree"
COHORT = "pre-F-bootstrap"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class FileOwner:
    """Actual file snapshot/pending owner, no fabricated ownership proof."""

    def __init__(self, registry, root, role="task_state"):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f"{role}.json"
        if not self.path.exists():
            self.path.write_bytes(b"{}")
        self.jobs = []
        self.identity = WriterIdentity(
            str(root),
            role,
            registry.source_identity,
            registry.process_start_identity,
            str(threading.get_ident()),
            0,
            "old-writer",
        )
        registry.register(
            self.identity,
            snapshot=self.path.read_bytes,
            pending=self.pending,
            process_state=self.process,
            loaded_identity=self.loaded,
        )

    def pending(self):
        return self.jobs

    def process(self):
        return "idle"

    def loaded(self):
        return self.identity


def setup(base, source=SOURCE):
    registry = WriterRegistry(source_identity=source)
    owners = [
        FileOwner(registry, base / name, role)
        for name, role in (
            ("task", "task_state"),
            ("runtime", "effect_journal"),
            ("runtime", "runtime_receipt"),
            ("event", "event_log"),
        )
    ]
    return registry, owners


def publish(base, phase="DRAINED"):
    registry, owners = setup(base)
    roots = list(dict.fromkeys(owner.identity.root for owner in owners))
    hold = registry.begin_hold(roots, cohort_id=COHORT)
    for owner in owners:
        identity = owner.identity
        hold.acknowledge(identity.writer_id, root=identity.root, role=identity.role, generation=0)
    registry.persist_finalized(hold)
    intents = [
        {
            "root_id": f"root-{i}",
            "root": root,
            "root_identity": digest(root.encode()),
            "owner_id": f"owner-{i}",
            "roles": [owner.identity.role for owner in owners if owner.identity.root == root],
            "selections": [
                {
                    "entry_id": f"entry-{owner.identity.role}",
                    "role": owner.identity.role,
                    "relative_path": owner.path.name,
                }
                for owner in owners
                if owner.identity.root == root
            ],
            "expected_generation": None,
            "expected_writer_id": "old-writer",
            "expected_manifest_sha256": None,
            "next_generation": 1,
            "next_writer_id": "next-writer",
        }
        for i, root in enumerate(roots)
    ]
    record = registry.persist_pre_activation_preparation(
        hold, installed_inventory_sha256="a" * 64, root_intents=intents, phase=phase
    )
    return registry, owners, record


def dead_predecessor(base, phase="DRAINED"):
    script = (
        "import runpy; from pathlib import Path; m=runpy.run_path(%r); m['publish'](Path(%r), %r)"
        % (str(Path(__file__).resolve()), str(base), phase)
    )
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
    path = (
        base / "task" / ".nexus/writer-quiescence/preparations" / f"{digest(COHORT.encode())}.json"
    )
    return path, json.loads(path.read_bytes())


def prepare(registry, record):
    return registry.prepare_pre_activation_hold_recovery(
        cohort_id=COHORT,
        ordered_roots=record["ordered_roots"],
        expected_preparation_sha256=record["receipt_sha256"],
    )


@pytest.mark.parametrize("phase", ["DRAINED", "AUTHORITY_WAITING"])
def test_dead_process_adopts_exact_epoch_preserves_original_drain_and_hold(tmp_path, phase):
    path, record = dead_predecessor(tmp_path, phase)
    registry, owners = setup(tmp_path)
    marker_bytes = [registry._marker_path(o.identity.root).read_bytes() for o in owners]
    proof = prepare(registry, record)
    successor = registry.persist_pre_activation_hold_successor(proof)
    assert successor["prior_digest"] == record["receipt_sha256"]
    assert json.loads(path.read_bytes()) == successor
    hold = registry.adopt_pre_activation_hold(
        proof, expected_successor_sha256=successor["receipt_sha256"]
    )
    assert hold.epoch == record["hold_epoch"]
    assert registry.load_finalized(COHORT).to_bytes() == encoded(
        record["original_drain"]["payload"]
    )
    assert [registry._marker_path(o.identity.root).read_bytes() for o in owners] == marker_bytes
    for owner in owners:
        with pytest.raises(WriterAdmissionDenied):
            registry.acquire(
                root=owner.identity.root,
                role=owner.identity.role,
                writer_id="old-writer",
                generation=0,
            )
    with pytest.raises(WriterAdmissionDenied, match="one-use"):
        registry.adopt_pre_activation_hold(
            proof, expected_successor_sha256=successor["receipt_sha256"]
        )


def test_live_predecessor_denied(tmp_path):
    _, _, record = publish(tmp_path)
    registry, _ = setup(tmp_path)
    with pytest.raises(WriterAdmissionDenied, match="not absent"):
        prepare(registry, record)


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "root",
        "marker",
        "drain",
        "pending",
        "snapshot",
        "loaded",
        "missing_callback",
        "early_prefix",
        "selfhash",
        "raw",
        "generation",
    ],
)
def test_recovery_denies_changed_or_unknown_evidence(tmp_path, mutation):
    path, record = dead_predecessor(tmp_path)
    registry, owners = setup(tmp_path, source="wrong-source" if mutation == "source" else SOURCE)
    if mutation == "root":
        old = tmp_path / "event"
        old.rename(tmp_path / "event-old")
        old.mkdir()
    elif mutation == "marker":
        registry._marker_path(owners[0].identity.root).write_bytes(b"{}")
    elif mutation == "drain":
        (
            tmp_path / "task/.nexus/writer-quiescence-receipts" / f"{digest(COHORT.encode())}.json"
        ).write_bytes(b"{}")
    elif mutation == "pending":
        owners[0].jobs.append("unknown-pending-job")
    elif mutation == "snapshot":
        owners[0].path.write_bytes(b"changed")
    elif mutation == "loaded":
        owners[0].identity = owners[1].identity
    elif mutation == "missing_callback":
        registry._writers[owners[0].identity.key()].loaded_identity = None
    elif mutation in {"early_prefix", "generation"}:
        if mutation == "early_prefix":
            record["phase"] = "PREPARING"
            record["original_drain"] = None
            registry._marker_path(owners[-1].identity.root).unlink()
        else:
            record["root_states"][0]["generation"] = 1
        record.pop("receipt_sha256")
        record["receipt_sha256"] = digest(encoded(record))
        path.write_bytes(encoded(record))
    elif mutation == "selfhash":
        record["installed_inventory_sha256"] = "b" * 64
        path.write_bytes(encoded(record))
    elif mutation == "raw":
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises((WriterAdmissionDenied, OSError)):
        prepare(registry, record)
    assert registry._held_roots == {}


@pytest.mark.parametrize("stage", ["prepare", "successor", "proof"])
def test_raw_cas_and_opaque_proof_tampering_deny(tmp_path, stage):
    path, record = dead_predecessor(tmp_path)
    registry, _ = setup(tmp_path)
    proof = prepare(registry, record)
    if stage == "proof":
        proof._predecessor["hold_epoch"] += 1
        with pytest.raises(WriterAdmissionDenied, match="issuance"):
            registry.persist_pre_activation_hold_successor(proof)
    elif stage == "prepare":
        path.write_bytes(path.read_bytes() + b"\n")
        with pytest.raises(WriterAdmissionDenied, match="CAS"):
            registry.persist_pre_activation_hold_successor(proof)
    else:
        successor = registry.persist_pre_activation_hold_successor(proof)
        path.write_bytes(path.read_bytes() + b"\n")
        with pytest.raises(WriterAdmissionDenied, match="CAS"):
            registry.adopt_pre_activation_hold(
                proof, expected_successor_sha256=successor["receipt_sha256"]
            )


@pytest.mark.parametrize("mutation", ["pending", "physical", "wrong_successor", "handoff", "proof"])
def test_adoption_rechecks_pinned_evidence(tmp_path, mutation):
    _, record = dead_predecessor(tmp_path)
    registry, owners = setup(tmp_path)
    proof = prepare(registry, record)
    successor = registry.persist_pre_activation_hold_successor(proof)
    expected = successor["receipt_sha256"]
    if mutation == "pending":
        owners[0].jobs.append("late-work")
    elif mutation == "physical":
        owners[0].path.write_bytes(b"late-change")
    elif mutation == "wrong_successor":
        expected = "f" * 64
    elif mutation == "handoff":
        path = registry._cohort_receipt_path(record["ordered_roots"], COHORT)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"{}")
    elif mutation == "proof":
        proof._markers = ()
    with pytest.raises(WriterAdmissionDenied):
        registry.adopt_pre_activation_hold(proof, expected_successor_sha256=expected)
    assert all(registry._marker_path(o.identity.root).exists() for o in owners)
