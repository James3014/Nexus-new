"""MEMORY_INDEX consumers keep their old behaviour: no FTS index + no columns -> no hit (#2640 F1)."""

from __future__ import annotations

import pytest

from nexus.core.capability_signal_set import CapabilitySignalSet
from nexus.services.lancedb_roots import MEMORY_INDEX, resolve_lancedb_root
from nexus.services.memory_repository import MemoryRepository, NoEmbeddingProvider

pytest.importorskip("lancedb")


def _seed(root):
    repo = MemoryRepository(
        resolve_lancedb_root(MEMORY_INDEX, root, honor_env=False),
        embedding_provider=NoEmbeddingProvider(),
    )
    repo.add_rows(
        "findings_cards",
        [
            {
                "id": f"c{i}",
                "title": "LocalHeal lesson",
                "content": "verifier failed with error in the module",
            }
            for i in range(5)
        ],
    )


def test_capability_signal_set_belief_not_lowered_by_generic_task(tmp_path):
    _seed(tmp_path)
    signal = CapabilitySignalSet.from_context(
        {"task_desc": "the test fails with an error in the module"}, project_root=str(tmp_path)
    )
    assert signal.belief_confidence == pytest.approx(0.7)


def test_router_palace_search_reports_no_hit_without_fts_index(tmp_path):
    from nexus.core.router import SkillsRouter

    _seed(tmp_path)
    result = SkillsRouter(str(tmp_path))._palace_search("the test fails with an error", "default")
    assert result["hit_rate"] == 0.0
    assert result["results"] == []
