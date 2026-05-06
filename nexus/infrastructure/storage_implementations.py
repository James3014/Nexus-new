import json
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timezone
from nexus.infrastructure.storage_interfaces import MemoryStorage, CacheStore, JsonlStore, BeliefStore, ConfigStore

class LanceDBStorage(MemoryStorage):
    def __init__(self, project_root: Path, tenant_id: str | None = None, audit_events: list[dict[str, Any]] | None = None):
        self.project_root = project_root
        self.tenant_id = tenant_id
        self.audit_events = audit_events if audit_events is not None else []

    def scoped_access(self, tenant_id: str) -> "LanceDBStorage":
        return LanceDBStorage(self.project_root, tenant_id=str(tenant_id), audit_events=self.audit_events)

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
        """Keyword search scoped to one tenant unless global search is explicit."""
        results = []
        limit = kwargs.get("limit", 10)
        tenant_id = str(kwargs.get("tenant_id") or self.tenant_id or "")
        include_all_tenants = bool(kwargs.get("include_all_tenants", False))
        tenants_root = self.project_root / ".nexus" / "tenants"
        if tenant_id:
            tenant_dirs = list((tenants_root / tenant_id / "lancedb").glob("*.jsonl"))
        elif include_all_tenants:
            tenant_dirs = list(tenants_root.glob("*/lancedb/*.jsonl"))
            self.audit_events.append(
                {
                    "event": "lancedb_global_search",
                    "query": str(query),
                    "include_all_tenants": True,
                    "tenant_count": len({path.parts[-3] for path in tenant_dirs if len(path.parts) >= 3}),
                    "reason": str(kwargs.get("audit_reason") or "explicit_include_all_tenants"),
                }
            )
        else:
            return []
        
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


class FileJsonlStore(JsonlStore):
    def read_rows(self, path: str) -> List[Dict[str, Any]]:
        target = Path(path)
        if not target.exists():
            return []
        rows: List[Dict[str, Any]] = []
        with open(target, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
        return rows

    def append_row(self, path: str, row: Dict[str, Any]) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def write_rows(self, path: str, rows: List[Dict[str, Any]]) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class LanceBeliefStore(BeliefStore):
    def __init__(self, project_root: Path):
        self.project_root = project_root

    def list_beliefs(self, status: str = "ACTIVE") -> List[Dict[str, Any]]:
        try:
            import lancedb
            db_path = self.project_root / ".nexus" / "vector_db"
            if not db_path.exists():
                return []
            db = lancedb.connect(str(db_path))
            tables = db.list_tables()
            table_names = tables if isinstance(tables, list) else (tables.tables if hasattr(tables, "tables") else tables)
            if "nexus_soul_palace" not in table_names:
                return []
            df = db.open_table("nexus_soul_palace").to_pandas()
            if status != "ALL" and "status" in df.columns:
                df = df[df["status"].str.upper() == status.upper()]
            return df.to_dict("records")
        except Exception:
            return []


class FileConfigStore(ConfigStore):
    def __init__(self, project_root: Path):
        self.project_root = project_root

    def get_router_bias(self) -> List[float] | None:
        dna_path = self.project_root / "configs" / "federated_dna.yaml"
        if not dna_path.exists():
            return None
        try:
            import yaml
            with open(dna_path, "r", encoding="utf-8") as handle:
                dna = yaml.safe_load(handle)
            value = dna.get("global_router_bias") if isinstance(dna, dict) else None
            return list(value) if isinstance(value, list) else None
        except Exception:
            return None
