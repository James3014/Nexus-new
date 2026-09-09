"""Owner-installed pre-hold inventory loader tests."""

import hashlib
import json
from pathlib import Path

import pytest

from nexus.orchestrator.writer_activation_inventory import (
    LoadedPreholdInventory,
    PreholdInventoryError,
    _load_installed_prehold_inventory,
)


def _write_inventory(tmp_path, **changes):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source_root = Path(__file__).resolve().parents[2]
    card = source_root / "README.md"
    receipt = tmp_path / "accepted-source.json"
    receipt.write_bytes(b"accepted source receipt\n")
    receipt.chmod(0o600)
    roots = []
    for root_id, roles in (
        ("task", ("task_state",)),
        ("event", ("event_log",)),
        ("runtime", ("runtime_receipt", "effect_journal")),
    ):
        root = tmp_path / root_id
        root.mkdir()
        roots.append({
            "root_id": root_id,
            "root": str(root.resolve()),
            "owner_id": "owner-" + root_id,
            "next_writer_id": "writer-" + root_id,
            "authority_publication": {
                "tracked_relative": "tasks/transition.json",
                "durable_path": str((tmp_path / (root_id + "-authority.json")).resolve()),
            },
            "selections": [
                {
                    "entry_id": role,
                    "role": role,
                    "relative_path": {
                        "event_log": ".nexus/events/event_log.jsonl",
                        "effect_journal": ".nexus/events/effect_journal.v1.json",
                    }.get(role, role + ".json"),
                }
                for role in roles
            ],
        })
    data = {
        "schema": "nexus.writer_activation_prehold_inventory.v1",
        "backing_source_root": str(source_root),
        "source": {
            "repository": "James3014/Nexus-new",
            "source_head": __import__("subprocess")
            .check_output(["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True)
            .strip(),
            "source_tree": __import__("subprocess")
            .check_output(["git", "-C", str(source_root), "rev-parse", "HEAD^{tree}"], text=True)
            .strip(),
            "card_path": "README.md",
            "card_sha256": hashlib.sha256(card.read_bytes()).hexdigest(),
        },
        "cohort_id": "installed-cohort",
        "task_id": "prehold-task",
        "accepted_source_receipt": str(receipt),
        "accepted_source_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
        "roots": roots,
    }
    data.update(changes)
    unsigned = dict(data)
    data["installed_receipt_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    path = tmp_path / "inventory.json"
    path.write_bytes(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )
    path.chmod(0o600)
    return path


def test_load_installed_inventory_validates_real_source_and_roots(tmp_path):
    loaded = _load_installed_prehold_inventory(_write_inventory(tmp_path))
    assert isinstance(loaded, LoadedPreholdInventory)
    assert len(loaded.roots) == 3
    assert loaded.raw_bytes
    assert loaded.source.repository == "James3014/Nexus-new"


@pytest.mark.parametrize(
    "change",
    [
        {"cohort_id": ""},
        {"roots": []},
        {"source": {"repository": "foreign"}},
    ],
)
def test_inventory_rejects_changed_inputs(tmp_path, change):
    path = _write_inventory(tmp_path, **change)
    with pytest.raises(PreholdInventoryError):
        _load_installed_prehold_inventory(path)


def test_inventory_rejects_overlapping_or_unknown_roles(tmp_path):
    path = _write_inventory(tmp_path)
    data = json.loads(path.read_text())
    data["roots"][1]["root"] = data["roots"][0]["root"]
    path.write_text(json.dumps(data))
    with pytest.raises(PreholdInventoryError):
        _load_installed_prehold_inventory(path)


def test_inventory_rejects_symlink_root_and_foreign_loaded_provenance(tmp_path):
    path = _write_inventory(tmp_path)
    data = json.loads(path.read_text())
    target = Path(data["roots"][0]["root"])
    link = tmp_path / "task-link"
    link.symlink_to(target, target_is_directory=True)
    data["roots"][0]["root"] = str(link)
    path.write_text(json.dumps(data))
    with pytest.raises(PreholdInventoryError):
        _load_installed_prehold_inventory(path)
    valid = _write_inventory(tmp_path / "foreign")
    with pytest.raises(PreholdInventoryError, match="HOST_PROVENANCE_MISSING"):
        _load_installed_prehold_inventory(valid, loaded_module_root=tmp_path / "foreign-host")


def test_inventory_requires_owner_only_inventory_and_source_receipt(tmp_path):
    path = _write_inventory(tmp_path)
    path.chmod(0o644)
    with pytest.raises(PreholdInventoryError, match="NOT_OWNER_ONLY"):
        _load_installed_prehold_inventory(path)
