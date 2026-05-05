import json
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timezone
from nexus.infrastructure.storage_interfaces import MemoryStorage, CacheStore

class LanceDBStorage(MemoryStorage):
    def __init__(self, project_root: Path, tenant_id: str | None = None):
        self.project_root = project_root
        self.tenant_id = tenant_id

    def scoped_access(self, tenant_id: str) -> "LanceDBStorage":
        return LanceDBStorage(self.project_root, tenant_id=str(tenant_id))

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
        tenant_id = str(kwargs.get("tenant_id") or self.tenant_id or "")
        tenants_root = self.project_root / ".nexus" / "tenants"
        if tenant_id:
            tenant_dirs = list((tenants_root / tenant_id / "lancedb").glob("*.jsonl"))
        else:
            tenant_dirs = list(tenants_root.glob("*/lancedb/*.jsonl"))
        
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
        """Keyword search fallback kept infra-pure; semantic search belongs in services."""
        return self.retrieve(query, artifact_type=table, limit=limit)

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
