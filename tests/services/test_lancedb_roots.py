from __future__ import annotations

from pathlib import Path

import pytest

from nexus.services import lancedb_roots as roots


def test_default_roots_match_legacy_hardcoded_paths(tmp_path, monkeypatch):
    monkeypatch.delenv(roots.MEMORY_DB_PATH_ENV, raising=False)
    assert roots.resolve_lancedb_root(roots.KNOWLEDGE, tmp_path) == tmp_path / ".nexus" / "knowledge" / "lancedb"
    assert roots.resolve_lancedb_root(roots.MEMORY_INDEX, tmp_path) == tmp_path / ".nexus/memory/memory_index.lancedb"
    assert roots.resolve_lancedb_root(roots.REPOSITORY, str(tmp_path)) == tmp_path / ".nexus" / "memory_repository"
    assert roots.resolve_lancedb_root(roots.VECTOR_DB, tmp_path) == tmp_path / ".nexus" / "vector_db"
    assert roots.resolve_lancedb_root(roots.TENANT_JSONL, tmp_path, tenant_id="t1") == tmp_path / ".nexus/tenants/t1/lancedb"


def test_env_override_only_for_kinds_that_honor_it(tmp_path, monkeypatch):
    monkeypatch.setenv(roots.MEMORY_DB_PATH_ENV, str(tmp_path / "override"))
    override = Path(tmp_path / "override")
    assert roots.resolve_lancedb_root(roots.KNOWLEDGE, tmp_path) == override
    assert roots.resolve_lancedb_root(roots.MEMORY_INDEX, tmp_path) == override
    assert roots.resolve_lancedb_root(roots.MEMORY_INDEX, tmp_path, honor_env=False) != override
    assert roots.resolve_lancedb_root(roots.VECTOR_DB, tmp_path) == tmp_path / ".nexus" / "vector_db"


def test_unknown_kind_and_missing_tenant_raise(tmp_path):
    with pytest.raises(ValueError):
        roots.resolve_lancedb_root("nope", tmp_path)
    with pytest.raises(ValueError):
        roots.resolve_lancedb_root(roots.TENANT_JSONL, tmp_path)
