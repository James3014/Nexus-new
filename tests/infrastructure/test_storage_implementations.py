import ast
from pathlib import Path

from nexus.infrastructure.storage_implementations import LanceBeliefStore, LanceDBStorage, LocalCacheStore


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
    assert storage.retrieve("alpha", artifact_type="lesson", limit=5, include_all_tenants=True) == []
    assert storage.audit_events[-1]["event"] == "lancedb_global_search_blocked"
    assert storage.audit_events[-1]["reason"] == "missing_audit_reason"
    assert storage.retrieve("alpha", artifact_type="lesson", limit=5, include_all_tenants=True, audit_reason="explicit_include_all_tenants")
    assert storage.audit_events[-1]["event"] == "lancedb_global_search"
    assert storage.audit_events[-1]["include_all_tenants"] is True
    assert storage.audit_events[-1]["reason"] == "explicit_include_all_tenants"


def test_lancedb_storage_global_search_audit_is_shared_with_scoped_handles(tmp_path):
    storage = LanceDBStorage(tmp_path)
    storage.store("tenant-a", "lesson", {"content": "alpha secret"})

    tenant_a = storage.scoped_access("tenant-a")
    assert tenant_a.retrieve("alpha", artifact_type="lesson", limit=5)
    assert storage.audit_events == []

    assert storage.retrieve("alpha", artifact_type="lesson", limit=5, include_all_tenants=True, audit_reason="ops_audit")
    assert tenant_a.audit_events[-1]["reason"] == "ops_audit"


def test_memory_storage_protocol_does_not_include_search():
    from nexus.infrastructure.storage_interfaces import MemoryStorage, SearchProvider

    assert "search" not in MemoryStorage.__dict__
    assert "search" in SearchProvider.__dict__


def test_belief_store_exposes_semantic_weight_without_storage_ranking(tmp_path):
    store = LanceBeliefStore(tmp_path)

    weight = store.semantic_weight_for(["semantic:task:doc", ".nexus/reports/codeintel/impact.json"])

    assert weight == 0.55


def test_lancedb_store_skips_tenant_ledger_under_state_read_only(tmp_path, monkeypatch):
    """#2721 L-B: NEXUS_STATE_READ_ONLY=1 must leave the tenant ledger byte-identical."""
    from nexus.infrastructure.storage_implementations import LanceDBStorage

    storage = LanceDBStorage(tmp_path)
    storage.store("t1", "worker_task_contract", {"a": 1})
    ledger = tmp_path / ".nexus" / "tenants" / "t1" / "lancedb" / "worker_task_contract_stable.jsonl"
    before = ledger.read_bytes()
    monkeypatch.setenv("NEXUS_STATE_READ_ONLY", "1")
    out = storage.store("t1", "worker_task_contract", {"a": 2})
    assert out["status"] == "SKIPPED_READ_ONLY"
    assert ledger.read_bytes() == before
    out2 = storage.store("t2", "worker_task_contract", {"a": 3})
    assert out2["status"] == "SKIPPED_READ_ONLY"
    assert not (tmp_path / ".nexus" / "tenants" / "t2").exists()
    monkeypatch.delenv("NEXUS_STATE_READ_ONLY")
    assert storage.store("t1", "worker_task_contract", {"a": 4})["status"] == "COMPRESSED"
    assert ledger.read_bytes() != before
