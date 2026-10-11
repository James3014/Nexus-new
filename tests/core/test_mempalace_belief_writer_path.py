"""Characterize the only main-flow writer of ``nexus_soul_palace``.

CrystallizationService.persist_outcome -> SoulPalaceEngine.store_knowledge writes an
``artifact`` outcome row (not a constraint-bearing belief). These tests pin that the row
is readable by MemPalace, derives no constraints, and that an unreadable store is still
reported as ``constraints_source == "unavailable"``.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

lancedb = pytest.importorskip("lancedb")

from nexus.core.capability_constraints import CapabilityConstraints  # noqa: E402
from nexus.engine.crystallization_service import CrystallizationService  # noqa: E402
from nexus.services.mem_palace import MemPalace  # noqa: E402


class _StubModel:
    def __init__(self, *_args, **_kwargs):
        pass

    def encode(self, _text):
        return SimpleNamespace(tolist=lambda: [0.0] * 4)


@pytest.fixture
def stub_embedder(monkeypatch):
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = _StubModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)


def _signal() -> SimpleNamespace:
    return SimpleNamespace(task_desc="regular coding task")


def test_outcome_writer_row_is_readable_but_yields_no_constraints(tmp_path, stub_embedder):
    service = CrystallizationService(project_root=tmp_path, reporter=MagicMock())
    service.persist_outcome({
        "task_id": "T-1",
        "skill_id": "skill_a",
        "passed": False,
        "decision_id": "d1",
    })

    palace = MemPalace(str(tmp_path))
    rows = palace.list_beliefs(status="ACTIVE")
    assert len(rows) == 1
    assert rows[0]["type"] == "artifact"

    verdict = CapabilityConstraints(str(tmp_path), mem_palace=palace).evaluate_constraints(
        _signal()
    )
    assert verdict["constraints_source"] == "ok"
    assert verdict["forbidden_skills_rules"] == []
    assert verdict["required_skills_rules"] == []
    assert verdict["preferred_skills_rules"] == []


def test_unreadable_store_reports_unavailable_not_silent_empty(tmp_path, monkeypatch):
    (tmp_path / ".nexus" / "vector_db").mkdir(parents=True)

    def _boom(_path):
        raise RuntimeError("db corrupted")

    monkeypatch.setattr(lancedb, "connect", _boom)
    palace = MemPalace(str(tmp_path))
    verdict = CapabilityConstraints(str(tmp_path), mem_palace=palace).evaluate_constraints(
        _signal()
    )

    assert verdict["constraints_source"] == "unavailable"
    assert "db corrupted" in verdict["constraints_unavailable_reason"]
    assert verdict["forbidden_skills_rules"] == []
