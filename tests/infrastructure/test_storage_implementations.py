import ast
from pathlib import Path

from nexus.infrastructure.storage_implementations import LanceDBStorage, LocalCacheStore


def test_local_cache_store_roundtrip_sets():
    cache = LocalCacheStore()

    cache.set("k", "v")
    cache.sadd("set", "a", "b")

    assert cache.get("k") == "v"
    assert cache.smembers("set") == {"a", "b"}
    cache.delete("k")
    assert cache.get("k") is None


def test_lancedb_storage_search_has_no_service_layer_import():
    source = Path("nexus/infrastructure/storage_implementations.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)

    assert not any(name.startswith("nexus.services") for name in imports)


def test_lancedb_storage_scoped_access_keeps_tenants_isolated(tmp_path):
    storage = LanceDBStorage(tmp_path)
    storage.store("tenant-a", "lesson", {"content": "alpha secret"})
    storage.store("tenant-b", "lesson", {"content": "beta secret"})

    tenant_a = storage.scoped_access("tenant-a")
    tenant_b = storage.scoped_access("tenant-b")

    assert tenant_a.search("alpha", table="lesson", limit=5)
    assert tenant_a.search("beta", table="lesson", limit=5) == []
    assert tenant_b.search("beta", table="lesson", limit=5)
