"""ARCHIVED 2026-10-13 legacy-engine (ARCHIVED_2026-10-13-legacy-engine.md).

``nexus.engine.cli_runner_async`` had no importer and only dispatched to the retired legacy
NexusEngine. Historical node ids are kept and now assert that tactical nodes fail closed
instead of building the engine.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest


def _forbid_legacy_engine(monkeypatch):
    def _boom(*_args, **_kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("archived legacy NexusEngine must not be constructed")

    monkeypatch.setattr("nexus.engine.config.EngineConfig", _boom)


def _run(node_id: str, intent: str, tmp_path: Path, monkeypatch):
    from nexus.engine.canonical_task_seam import LegacyEngineArchivedError
    from nexus.engine.cli_runner_async import execute_tactical_node

    _forbid_legacy_engine(monkeypatch)

    node = SimpleNamespace(node_id=node_id, intent=intent, envelope=None)
    with pytest.raises(LegacyEngineArchivedError) as excinfo:
        execute_tactical_node(node, Path(tmp_path))
    return excinfo.value


def test_execute_tactical_node_routes_bug_tasks_to_canonical_service(monkeypatch, tmp_path):
    error = _run("T1", "fix deadlock", tmp_path, monkeypatch)
    assert error.entry == "execute_single_task_via_service"
    assert error.reason == "archived_legacy_engine_2026-10-13"


def test_execute_tactical_node_routes_feature_tasks_to_canonical_service(monkeypatch, tmp_path):
    error = _run("T2", "build a dashboard", tmp_path, monkeypatch)
    assert error.entry == "execute_single_task_via_service"
    assert "ARCHIVED 2026-10-13 legacy-engine" in str(error)
