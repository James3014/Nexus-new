import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timezone
from nexus.infrastructure.storage_interfaces import MemoryStorage, CacheStore, JsonlStore, BeliefStore, ConfigStore

logger = logging.getLogger(__name__)


def _lancedb_table_names(db: Any) -> List[str]:
    """Table names across lancedb versions (list, or a response with ``.tables``)."""
    tables: Any = db.list_tables()
    if not isinstance(tables, list):
        tables = getattr(tables, "tables", tables)
    return [str(name) for name in tables]


def _is_missing(value: Any) -> bool:
    """True for None and float NaN (pandas' marker for a null cell)."""
    return value is None or (isinstance(value, float) and value != value)

class LanceDBStorage(MemoryStorage):
    def __init__(self, project_root: Path, tenant_id: str | None = None, audit_events: list[dict[str, Any]] | None = None):
        self.project_root = project_root
        self.tenant_id = tenant_id
        self.audit_events = audit_events if audit_events is not None else []

    def scoped_access(self, tenant_id: str) -> "LanceDBStorage":
        return LanceDBStorage(self.project_root, tenant_id=str(tenant_id), audit_events=self.audit_events)

    def store(self, tenant_id: str, artifact_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        compressed = {
            "aaak_id": f"{artifact_type}-{int(datetime.now(timezone.utc).timestamp())}",
            "core": {k: v for k, v in data.items() if k not in ["timestamp", "metadata"]},
            "status": "COMPRESSED"
        }
        from nexus.core.state_root import state_read_only

        if state_read_only():  # #2721 L-B: frozen state, the tenant ledger is not appended
            return {**compressed, "status": "SKIPPED_READ_ONLY"}
        tenant_dir = self.project_root / ".nexus" / "tenants" / tenant_id
        db_dir = tenant_dir / "lancedb"
        db_dir.mkdir(parents=True, exist_ok=True)
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
            audit_reason = str(kwargs.get("audit_reason") or "").strip()
            if not audit_reason:
                self.audit_events.append(
                    {
                        "event": "lancedb_global_search_blocked",
                        "query": str(query),
                        "include_all_tenants": True,
                        "reason": "missing_audit_reason",
                    }
                )
                return []
            tenant_dirs = list(tenants_root.glob("*/lancedb/*.jsonl"))
            self.audit_events.append(
                {
                    "event": "lancedb_global_search",
                    "query": str(query),
                    "include_all_tenants": True,
                    "tenant_count": len({path.parts[-3] for path in tenant_dirs if len(path.parts) >= 3}),
                    "reason": audit_reason,
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
        # "ok" | "unavailable"; set by every list_beliefs call so callers can tell
        # an empty belief set from a failed read.
        self.last_read_status: str = "ok"
        self.last_read_error: str = ""
        # "" (no write yet) | "ok" | "unavailable"; set by upsert_belief / set_belief_status.
        self.last_write_status: str = ""
        self.last_write_error: str = ""

    _TABLE = "nexus_soul_palace"

    def _open_table(self, create_rows: List[Dict[str, Any]] | None = None):
        """Open the belief table; create it (nullable vector) from ``create_rows`` if missing."""
        import lancedb
        import pyarrow as pa

        db_path = self.project_root / ".nexus" / "vector_db"
        db_path.mkdir(parents=True, exist_ok=True)
        db = lancedb.connect(str(db_path))
        if self._TABLE in _lancedb_table_names(db):
            return db.open_table(self._TABLE)
        if create_rows is None:
            return None
        text_cols = ("id", "type", "status", "content", "skill_id", "domain", "trust_level", "created_at", "updated_at")
        fields = [pa.field(k, pa.string()) for k in text_cols]
        # An all-null vector column cannot be created by lancedb; only add it when a vector exists.
        if any(r.get("vector") for r in create_rows):
            fields.append(pa.field("vector", pa.list_(pa.float32())))
        schema = pa.schema(fields)
        return db.create_table(self._TABLE, data=pa.Table.from_pylist(create_rows, schema=schema), schema=schema)

    def upsert_belief(self, row: Dict[str, Any]) -> bool:
        """Idempotently upsert a belief row by ``id``. Never raises; see ``last_write_status``."""
        self.last_write_status = "ok"
        self.last_write_error = ""
        try:
            import pyarrow as pa

            table = self._open_table(create_rows=[row])
            if table is None:
                raise RuntimeError("belief table unavailable")
            names = set(table.schema.names)
            if "id" not in names:
                raise ValueError("belief table has no id column")
            missing = {k: "cast(NULL as string)" for k in ("type", "updated_at", "trust_level") if k not in names}
            if missing:
                table.add_columns(missing)
            safe_id = str(row["id"]).replace("'", "")
            table.delete(f"id = '{safe_id}'")
            fields = table.schema.names
            table.add(pa.Table.from_pylist([{k: row.get(k) for k in fields}], schema=table.schema))
            return True
        except Exception as exc:
            self.last_write_status = "unavailable"
            self.last_write_error = f"{type(exc).__name__}: {exc}"
            logger.warning("LanceBeliefStore: belief write failed (nexus_soul_palace): %s", self.last_write_error)
            return False

    def set_belief_status(self, belief_id: str, status: str, updated_at: str) -> bool:
        """Set ``status`` of an existing belief row. Never raises; False if the table is absent."""
        self.last_write_status = "ok"
        self.last_write_error = ""
        try:
            table = self._open_table()
            if table is None:
                return False
            values = {"status": status}
            if "updated_at" in table.schema.names:
                values["updated_at"] = updated_at
            table.update(where=f"id = '{str(belief_id).replace(chr(39), '')}'", values=values)
            return True
        except Exception as exc:
            self.last_write_status = "unavailable"
            self.last_write_error = f"{type(exc).__name__}: {exc}"
            logger.warning("LanceBeliefStore: belief status write failed (nexus_soul_palace): %s", self.last_write_error)
            return False

    def list_beliefs(self, status: str = "ACTIVE") -> List[Dict[str, Any]]:
        self.last_read_status = "ok"
        self.last_read_error = ""
        try:
            import lancedb
            db_path = self.project_root / ".nexus" / "vector_db"
            if not db_path.exists():
                return []
            db = lancedb.connect(str(db_path))
            if "nexus_soul_palace" not in _lancedb_table_names(db):
                return []
            records = db.open_table("nexus_soul_palace").to_pandas().to_dict("records")
            beliefs: List[Dict[str, Any]] = []
            for raw in records:
                row = {str(k): (None if _is_missing(v) else v) for k, v in raw.items()}
                # Only belief rows are beliefs; outcome artifacts and untyped legacy rows are not.
                if str(row.get("type") or "").lower() != "belief":
                    continue
                if status != "ALL" and "status" in row and str(row.get("status")).upper() != status.upper():
                    continue
                beliefs.append(row)
            return beliefs
        except Exception as exc:
            self.last_read_status = "unavailable"
            self.last_read_error = f"{type(exc).__name__}: {exc}"
            logger.warning("LanceBeliefStore: belief read failed (nexus_soul_palace): %s", self.last_read_error)
            return []

    def semantic_weight_for(self, evidence_refs: List[str]) -> float:
        refs = [str(item).lower() for item in evidence_refs if str(item).strip()]
        if not refs:
            return 0.0
        semantic_refs = sum(1 for ref in refs if ref.startswith("semantic:") or "semantic_searcher" in ref)
        code_refs = sum(1 for ref in refs if "codeintel" in ref or ref.endswith(".py"))
        return min(1.0, round((semantic_refs * 0.35) + (code_refs * 0.2), 4))


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
