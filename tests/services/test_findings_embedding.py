from __future__ import annotations

import logging
import socket
import urllib.request

import pytest

pytest.importorskip("lancedb")

from nexus.research import findings_vector_sync as fvs
from nexus.services.memory_repository import (
    EmbeddingProvider,
    MemoryRepository,
    NoEmbeddingProvider,
    OllamaEmbeddingProvider,
    default_embedding_provider,
)

LONG = "findings card about semantic dedup of vectors " * 5


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def embed(self, text):
        self.calls += 1
        return [1.0, 0.0, 0.0, 0.0]


class BoomProvider:
    name = "boom"

    def embed(self, text):
        raise TimeoutError("embed down")


@pytest.fixture
def no_network(monkeypatch):
    calls = []

    def _boom(*args, **kwargs):
        calls.append(args)
        raise AssertionError("network call attempted")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket.socket, "connect", _boom)
    try:
        import requests

        monkeypatch.setattr(requests.sessions.Session, "request", _boom)
    except ImportError:
        pass
    return calls


def _rec(rid, content=LONG):
    return {"id": rid, "content": content}


def test_fake_provider_populates_vector_and_dedups(tmp_path):
    provider = FakeProvider()
    repo = MemoryRepository(tmp_path / "db", embedding_provider=provider)
    assert isinstance(provider, EmbeddingProvider)

    assert repo.semantic_dedup_ingest("t", _rec("a")) == "NEW_INITIAL"
    df = repo.get_all_rows("t")
    assert list(df["vector"].iloc[0]) == [1.0, 0.0, 0.0, 0.0]
    assert df["embedding_status"].iloc[0] == "ok"
    assert df["embedding_provider"].iloc[0] == "fake"

    assert repo.semantic_dedup_ingest("t", _rec("b")) == "DUPLICATE"
    assert len(repo.get_all_rows("t")) == 1
    assert repo.last_embedding["status"] == "ok"


def test_no_provider_marks_missing_without_network(tmp_path, no_network, monkeypatch):
    monkeypatch.delenv("NEXUS_MEMORY_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("NEXUS_MEMORY_OLLAMA_AAAK", raising=False)
    repo = MemoryRepository(tmp_path / "db")
    assert isinstance(repo.embedding_provider, NoEmbeddingProvider)

    assert repo.semantic_dedup_ingest("t", _rec("a")) == "NEW_INITIAL"
    assert repo.semantic_dedup_ingest("t", _rec("b", LONG + " different")) == "NEW_NO_VECTOR"
    df = repo.get_all_rows("t")
    assert len(df) == 2
    assert set(df["embedding_status"]) == {"missing"}
    assert set(df["embedding_reason"]) == {"provider_none"}
    assert no_network == []


def test_provider_failure_is_visible_and_row_still_written(tmp_path, caplog):
    repo = MemoryRepository(tmp_path / "db", embedding_provider=BoomProvider())
    with caplog.at_level(logging.WARNING):
        repo.semantic_dedup_ingest("t", _rec("a"))
    assert "Embedding provider boom failed" in caplog.text
    assert repo.last_embedding == {
        "status": "missing",
        "provider": "boom",
        "reason": "provider_error:TimeoutError",
    }
    df = repo.get_all_rows("t")
    assert df["embedding_status"].iloc[0] == "missing"
    assert df["embedding_reason"].iloc[0] == "provider_error:TimeoutError"


def test_vector_into_table_without_vector_column_is_not_lost_silently(tmp_path, caplog):
    repo = MemoryRepository(tmp_path / "db")
    repo.semantic_dedup_ingest("t", _rec("a"))
    repo.embedding_provider = FakeProvider()
    with caplog.at_level(logging.WARNING):
        assert repo.semantic_dedup_ingest("t", _rec("b", LONG + " other")) == "NEW_NO_VECTOR"
    assert "no vector column" in caplog.text
    assert repo.last_embedding["reason"] == "table_has_no_vector_column"
    assert len(repo.get_all_rows("t")) == 2


def test_ollama_provider_is_opt_in(monkeypatch):
    monkeypatch.delenv("NEXUS_MEMORY_EMBEDDING_PROVIDER", raising=False)
    assert isinstance(default_embedding_provider(), NoEmbeddingProvider)
    monkeypatch.setenv("NEXUS_MEMORY_EMBEDDING_PROVIDER", "ollama")
    assert isinstance(default_embedding_provider(), OllamaEmbeddingProvider)


def test_findings_sync_reuses_shared_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_FINDINGS_LANCEDB_SYNC", "1")
    monkeypatch.setenv("NEXUS_MEMORY_DB_PATH", str(tmp_path / "db"))
    monkeypatch.delenv("NEXUS_MEMORY_EMBEDDING_PROVIDER", raising=False)
    fvs.reset_shared_registry()
    sync = fvs.MemoryRepositoryFindingsVectorSync(tmp_path)
    assert sync.sync({"id": "f1", "body": LONG})
    assert fvs._SHARED_REGISTRY.cache_size() == 1
    repo = next(iter(fvs._SHARED_REGISTRY._cache.values()))
    assert sync.sync({"id": "f2", "body": LONG + " more"})
    assert fvs._SHARED_REGISTRY.cache_size() == 1
    assert next(iter(fvs._SHARED_REGISTRY._cache.values())) is repo
    assert set(repo.get_all_rows("findings_cards")["embedding_status"]) == {"missing"}
    fvs.reset_shared_registry()
