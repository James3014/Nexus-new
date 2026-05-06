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


def test_infrastructure_layer_has_no_service_layer_imports():
    violations = []
    for path in Path("nexus/infrastructure").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imports = []
            if isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            violations.extend(f"{path}:{name}" for name in imports if name.startswith("nexus.services"))

    assert violations == []


def test_lancedb_storage_scoped_access_keeps_tenants_isolated(tmp_path):
    storage = LanceDBStorage(tmp_path)
    storage.store("tenant-a", "lesson", {"content": "alpha secret"})
    storage.store("tenant-b", "lesson", {"content": "beta secret"})

    tenant_a = storage.scoped_access("tenant-a")
    tenant_b = storage.scoped_access("tenant-b")

    assert tenant_a.retrieve("alpha", artifact_type="lesson", limit=5)
    assert tenant_a.retrieve("beta", artifact_type="lesson", limit=5) == []
    assert tenant_b.retrieve("beta", artifact_type="lesson", limit=5)


def test_lancedb_storage_unscoped_retrieve_is_fail_closed(tmp_path):
    storage = LanceDBStorage(tmp_path)
    storage.store("tenant-a", "lesson", {"content": "alpha secret"})

    assert storage.retrieve("alpha", artifact_type="lesson", limit=5) == []
    assert storage.retrieve("alpha", artifact_type="lesson", limit=5, include_all_tenants=True)


def test_memory_storage_protocol_does_not_include_search():
    from nexus.infrastructure.storage_interfaces import MemoryStorage, SearchProvider

    assert "search" not in MemoryStorage.__dict__
    assert "search" in SearchProvider.__dict__
