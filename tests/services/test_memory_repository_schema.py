from __future__ import annotations

import pytest

pytest.importorskip("lancedb")
pa = pytest.importorskip("pyarrow")

from nexus.services.memory_repository import MemoryRepository, NoEmbeddingProvider  # noqa: E402

LONG = "findings card about semantic dedup of vectors " * 5


def _legacy_row():
    """Row shaped like a table created before embedding metadata existed."""
    return {
        "id": "old",
        "content": "legacy row",
        "tenant_id": "default",
        "drawer_id": "d0",
        "aaak_content": "legacy row",
        "updated_at": 1.0,
    }


class DimProvider:
    name = "fake"
    dimension = 4

    def embed(self, text):
        return [1.0, 0.0, 0.0, 0.0]


class FlakyProvider(DimProvider):
    """Returns no vector for the first call, then a stable vector."""

    def __init__(self):
        self.calls = 0

    def embed(self, text):
        self.calls += 1
        return None if self.calls == 1 else [1.0, 0.0, 0.0, 0.0]


def test_first_row_without_vector_does_not_lose_later_vectors(tmp_path):
    repo = MemoryRepository(tmp_path / "db", embedding_provider=FlakyProvider())

    assert repo.semantic_dedup_ingest("t", {"id": "a", "content": LONG}) == "NEW_INITIAL"
    schema = repo._get_db().open_table("t").schema
    assert pa.types.is_fixed_size_list(schema.field("vector").type)
    assert {"embedding_status", "embedding_provider", "embedding_reason"} <= set(schema.names)

    assert repo.semantic_dedup_ingest("t", {"id": "b", "content": LONG + " v2"}).startswith("NEW")
    df = repo.get_all_rows("t")
    assert df.loc[df["id"] == "a", "embedding_status"].iloc[0] == "missing"
    assert df.loc[df["id"] == "b", "embedding_status"].iloc[0] == "ok"
    assert list(df.loc[df["id"] == "b", "vector"].iloc[0]) == [1.0, 0.0, 0.0, 0.0]

    assert repo.semantic_dedup_ingest("t", {"id": "c", "content": LONG + " v3"}) == "DUPLICATE"
    assert len(repo.get_all_rows("t")) == 2


def test_no_provider_table_has_metadata_columns_and_null_vector_rows(tmp_path):
    repo = MemoryRepository(tmp_path / "db", embedding_provider=NoEmbeddingProvider())
    assert repo.semantic_dedup_ingest("t", {"id": "a", "content": LONG}) == "NEW_INITIAL"
    assert repo.semantic_dedup_ingest("t", {"id": "b", "content": LONG + "x"}) == "NEW_NO_VECTOR"
    df = repo.get_all_rows("t")
    assert len(df) == 2
    assert set(df["embedding_status"]) == {"missing"}
    assert set(df["embedding_reason"]) == {"provider_none"}


def test_existing_old_style_table_gets_metadata_columns_without_row_loss(tmp_path):
    import lancedb

    lancedb.connect(tmp_path / "db").create_table("t", data=[_legacy_row()])

    repo = MemoryRepository(tmp_path / "db", embedding_provider=DimProvider())
    assert repo.semantic_dedup_ingest("t", {"id": "new", "content": LONG}).startswith("NEW")
    assert repo.last_schema_evolution["status"] == "added"

    df = repo.get_all_rows("t")
    assert set(df["id"]) == {"old", "new"}
    assert df.loc[df["id"] == "old", "content"].iloc[0] == "legacy row"
    new = df.loc[df["id"] == "new"].iloc[0]
    assert new["embedding_status"] == "ok"
    assert new["embedding_provider"] == "fake"
    assert list(new["vector"]) == [1.0, 0.0, 0.0, 0.0]


def test_schema_evolution_failure_falls_back_to_strip_with_reason(tmp_path, monkeypatch):
    import lancedb

    lancedb.connect(tmp_path / "db").create_table("t", data=[_legacy_row()])
    repo = MemoryRepository(tmp_path / "db", embedding_provider=DimProvider())

    def _boom(self, *args, **kwargs):
        raise NotImplementedError("no add_columns")

    monkeypatch.setattr(type(repo._get_db().open_table("t")), "add_columns", _boom)
    repo.semantic_dedup_ingest("t", {"id": "new", "content": LONG})
    assert repo.last_schema_evolution["status"] == "failed"
    assert repo.last_schema_evolution["reason"].startswith("schema_evolution_failed")
    assert repo.last_embedding["reason"] == "table_has_no_vector_column"
    assert set(repo.get_all_rows("t")["id"]) == {"old", "new"}


def _pre_governance_row():
    """Row shaped like a table created before tenant_id/drawer_id/aaak_content existed."""
    return {"id": "old", "content": "pre-governance row", "updated_at": 1.0}


def test_old_table_missing_tenant_drawer_aaak_accepts_new_row_after_evolution(tmp_path):
    import lancedb

    lancedb.connect(tmp_path / "db").create_table("t", data=[_pre_governance_row()])

    repo = MemoryRepository(tmp_path / "db", embedding_provider=NoEmbeddingProvider())
    assert repo.semantic_dedup_ingest(
        "t", {"id": "new", "content": LONG}, tenant_id="acme"
    ).startswith("NEW")
    assert repo.last_schema_evolution["status"] == "added"
    assert {"tenant_id", "drawer_id", "aaak_content"} <= set(repo.last_schema_evolution["columns"])

    df = repo.get_all_rows("t")
    assert set(df["id"]) == {"old", "new"}
    old = df.loc[df["id"] == "old"].iloc[0]
    assert old["content"] == "pre-governance row"
    assert old["tenant_id"] is None or old["tenant_id"] != old["tenant_id"]
    new = df.loc[df["id"] == "new"].iloc[0]
    assert new["tenant_id"] == "acme"
    assert new["drawer_id"]
    assert new["aaak_content"]


def test_governance_column_evolution_failure_records_reason_and_still_writes(tmp_path, monkeypatch):
    import lancedb

    lancedb.connect(tmp_path / "db").create_table("t", data=[_pre_governance_row()])
    repo = MemoryRepository(tmp_path / "db", embedding_provider=NoEmbeddingProvider())

    def _boom(self, *args, **kwargs):
        raise NotImplementedError("no add_columns")

    monkeypatch.setattr(type(repo._get_db().open_table("t")), "add_columns", _boom)
    repo.semantic_dedup_ingest("t", {"id": "new", "content": LONG})
    assert repo.last_schema_evolution["status"] == "failed"
    assert repo.last_schema_evolution["reason"].startswith("schema_evolution_failed")
    df = repo.get_all_rows("t")
    assert set(df["id"]) == {"old", "new"}
    assert "tenant_id" not in df.columns
