from __future__ import annotations

import pandas as pd

from nexus.services.memory import MemoryService
from nexus.services.semantic_searcher import SemanticSearcher


class FakeRepository:
    def __init__(self):
        self.calls = []

    def search_fts(self, **kwargs):
        self.calls.append(kwargs)
        return pd.DataFrame(
            [{"rule_id": "r1", "condition": "bug", "action": "run targeted pytest", "_score": 0.8, "confidence": 0.91}]
        )


def test_semantic_searcher_wraps_repository_search():
    repo = FakeRepository()
    searcher = SemanticSearcher(repo)

    out = searcher.search("bug", table_name="policy", limit=2)

    assert repo.calls[0]["table_name"] == "policy"
    assert repo.calls[0]["query"] == "bug"
    assert out == [
        {
            "id": "r1",
            "content": "run targeted pytest",
            "relevance": 0.8,
            "confidence": 0.91,
            "confidence_source": "row",
            "evidence_ref": "semantic:policy:r1",
            "source": "lancedb-fts",
        }
    ]


def test_memory_service_delegates_semantic_search_to_service_seam(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_MEMORY_AUTO_INIT", "0")
    repo = FakeRepository()
    service = MemoryService(str(tmp_path), repo=repo)

    out = service.semantic_search("bug")

    assert out[0]["content"] == "run targeted pytest"
    assert repo.calls[0]["fallback_columns"] == ["condition", "action"]
