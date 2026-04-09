import json
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timezone
from nexus.infrastructure.storage_interfaces import MemoryStorage, CacheStore

class LanceDBStorage(MemoryStorage):
    def __init__(self, project_root: Path):
        self.project_root = project_root

    def store(self, tenant_id: str, artifact_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        tenant_dir = self.project_root / ".nexus" / "tenants" / tenant_id
        db_dir = tenant_dir / "lancedb"
        db_dir.mkdir(parents=True, exist_ok=True)
        compressed = {
            "aaak_id": f"{artifact_type}-{int(datetime.now(timezone.utc).timestamp())}",
            "core": {k: v for k, v in data.items() if k not in ["timestamp", "metadata"]},
            "status": "COMPRESSED"
        }
        target_path = db_dir / f"{artifact_type}_stable.jsonl"
        with open(target_path, "a") as f:
            f.write(json.dumps(compressed, ensure_ascii=False) + "\n")
        return compressed

    def retrieve(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """🛡️ Fallback: Keyword search across tenant JSONL backups."""
        results = []
        limit = kwargs.get("limit", 10)
        tenant_dirs = list((self.project_root / ".nexus" / "tenants").glob("*/lancedb/*.jsonl"))
        
        for jsonl_path in tenant_dirs:
            try:
                with open(jsonl_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if query.lower() in line.lower():
                            results.append(json.loads(line.strip()))
                            if len(results) >= limit:
                                return results
            except Exception:
                continue
        return results

    def search(self, query: str, table: str = "default", limit: int = 5) -> List[Dict[str, Any]]:
        """🚀 Semantic Search: Delegates to MemoryRepository FTS."""
        from nexus.services.memory_repository import MemoryRepository
        repo = MemoryRepository(self.project_root / ".nexus" / "knowledge" / "lancedb")
        try:
            df = repo.search_fts(table_name=table, query=query, limit=limit)
            return df.to_dict("records") if not df.empty else []
        except Exception:
            return []

class LocalCacheStore(CacheStore):
    def __init__(self):
        self._data = {}

    def get(self, key: str) -> Any: return self._data.get(key)
    def set(self, key: str, value: Any, ttl: int = None): self._data[key] = value
    def delete(self, key: str): self._data.pop(key, None)
    def sadd(self, key: str, *values):
        if key not in self._data: self._data[key] = set()
        self._data[key].update(values)
    def smembers(self, key: str) -> set: return self._data.get(key, set())
