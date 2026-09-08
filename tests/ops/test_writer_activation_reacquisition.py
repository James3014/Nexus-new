from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nexus.orchestrator import writer_activation_cohort as cohort
from scripts.ops import mcp_gateway_durable as manager
from scripts.ops import state_owner_transition as cli
from tests.integration.test_writer_activation_cohort import _real_cohort


def _loaded_fixture(tmp_path: Path):
    coordinator, _ = _real_cohort(tmp_path)
    assert coordinator.activate().state == "ACTIVE"
    return coordinator


def _tree_snapshot(coordinator) -> dict[str, str]:
    """Hash every selected-root byte plus the durable cohort receipt."""
    paths = [coordinator.state_path]
    for root in coordinator.hold.roots:
        base = Path(root)
        paths.extend(path for path in base.rglob("*") if path.is_file() and not path.is_symlink())
        paths.append(coordinator.registry._marker_path(root))
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in set(paths)
        if path.is_file() and not path.is_symlink()
    }


def test_cli_and_manager_use_loaded_typed_cohort_without_mutation(tmp_path, monkeypatch, capsys):
    coordinator = _loaded_fixture(tmp_path)
    before_tree = _tree_snapshot(coordinator)
    monkeypatch.setattr(cohort, "get_loaded_writer_activation_cohort", lambda: coordinator)

    assert cli.main(["--cohort-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["cohort_id"] == coordinator.cohort_id
    assert status["state"] == "ACTIVE"

    observed = manager.observe_loaded_writer_activation_cohort()
    assert observed["cohort_id"] == coordinator.cohort_id
    reconciled = manager.reconcile_writer_activation_cohort(coordinator)
    assert reconciled["state"] == "ACTIVE"
    assert _tree_snapshot(coordinator) == before_tree
    assert coordinator.registry._held_roots


def test_cli_rejects_request_selected_cohort_and_absent_binding(tmp_path, monkeypatch):
    monkeypatch.setattr(cohort, "get_loaded_writer_activation_cohort", lambda: None)
    with pytest.raises(SystemExit):
        cli.main(["--cohort-status", "--request", str(tmp_path / "request.json")])
    with pytest.raises(SystemExit):
        cli.main(["--cohort-reconcile"])
    with pytest.raises(SystemExit):
        cli.main(["--cohort-status", "--apply"])


def test_manager_rejects_forged_or_stale_cohort_binding(tmp_path):
    with pytest.raises(manager.GatewayContractError):
        manager.observe_writer_activation_cohort(object())

    coordinator = _loaded_fixture(tmp_path)
    actual_state = coordinator.state_path
    original_state = actual_state.read_bytes()
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps({"cohort_id": coordinator.cohort_id, "state": "ACTIVE"}))
    coordinator.state_path = forged  # type: ignore[misc]
    with pytest.raises(Exception):
        manager.observe_writer_activation_cohort(coordinator)
    coordinator.state_path = actual_state  # type: ignore[misc]

    original = json.loads(original_state)
    for field, value in (
        ("source_identity", "forged-source"),
        ("process_start_identity", "forged-process"),
        ("ordered_roots", list(reversed(original["ordered_roots"]))),
    ):
        raw = dict(original)
        raw[field] = value
        payload = dict(raw)
        payload.pop("receipt_sha256", None)
        raw["receipt_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        actual_state.write_text(json.dumps(raw, sort_keys=True) + "\n")
        before = hashlib.sha256(actual_state.read_bytes()).hexdigest()
        with pytest.raises(manager.GatewayContractError):
            manager.observe_writer_activation_cohort(coordinator)
        assert hashlib.sha256(actual_state.read_bytes()).hexdigest() == before
        actual_state.write_bytes(original_state)


def test_active_readback_is_typed_and_physical_tamper_denies(tmp_path, monkeypatch, capsys):
    coordinator, roots = _real_cohort(tmp_path)
    active = coordinator.activate()
    assert active.state == "ACTIVE"
    monkeypatch.setattr(cohort, "get_loaded_writer_activation_cohort", lambda: coordinator)

    assert cli.main(["--cohort-status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "ACTIVE"
    before_tree = _tree_snapshot(coordinator)
    assert cli.main(["--cohort-reconcile"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "ACTIVE"
    assert manager.observe_loaded_writer_activation_cohort()["state"] == "ACTIVE"
    assert manager.reconcile_writer_activation_cohort(coordinator)["state"] == "ACTIVE"
    assert _tree_snapshot(coordinator) == before_tree

    generation = Path(roots[0].root) / ".nexus" / "events" / "event_log.generation.v1.json"
    original = generation.read_bytes()
    state_before_tamper = hashlib.sha256(coordinator.state_path.read_bytes()).hexdigest()
    generation.write_bytes(original.replace(b'"generation":2', b'"generation":99'))
    with pytest.raises(manager.GatewayContractError):
        manager.observe_loaded_writer_activation_cohort()
    with pytest.raises(SystemExit):
        cli.main(["--cohort-status"])
    with pytest.raises(manager.GatewayContractError):
        manager.reconcile_writer_activation_cohort(coordinator)
    assert hashlib.sha256(coordinator.state_path.read_bytes()).hexdigest() == state_before_tamper
    generation.write_bytes(original)
    released = coordinator.release(active)
    assert released.state == "RELEASED"
    assert released.release_state == "RELEASED"
    before_released = _tree_snapshot(coordinator)
    assert cli.main(["--cohort-status"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "RELEASED"
    assert cli.main(["--cohort-reconcile"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "RELEASED"
    assert _tree_snapshot(coordinator) == before_released
