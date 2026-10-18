import json
import logging
import time
import hashlib
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Protocol, runtime_checkable

try:
    from nexus.core.ui import InfrastructureError
except (ImportError, ModuleNotFoundError):
    class InfrastructureError(RuntimeError):
        """Fallback for Nexus Infrastructure errors when core modules are missing."""
        pass

logger = logging.getLogger(__name__)

EMBEDDING_PROVIDER_ENV = "NEXUS_MEMORY_EMBEDDING_PROVIDER"
OLLAMA_AAAK_ENV = "NEXUS_MEMORY_OLLAMA_AAAK"
OLLAMA_ENDPOINT_ENV = "NEXUS_OLLAMA_ENDPOINT"
OLLAMA_EMBED_MODEL_ENV = "NEXUS_MEMORY_EMBEDDING_MODEL"
EMBEDDING_METADATA_COLUMNS = ("embedding_status", "embedding_provider", "embedding_reason")
# Dual-mode metadata that semantic_dedup_ingest stamps on every row; old tables may predate it.
INGEST_METADATA_COLUMNS = ("tenant_id", "drawer_id", "aaak_content")
_TRUTHY = {"1", "true", "yes", "on"}


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Injectable embedding port. Return None when no vector is available.

    Implementations may raise; the repository records the failure (status/reason
    + warning log) and keeps writing the row without a vector.
    """

    name: str

    def embed(self, text: str) -> Optional[List[float]]:
        ...

    # Optional: providers may also expose ``dimension: Optional[int]`` (fixed vector width).
    # When set, new tables get a fixed-size vector column up front. It is deliberately not a
    # Protocol member so providers written before it existed still satisfy isinstance().


class NoEmbeddingProvider:
    """Default provider: never embeds and never touches the network."""

    name = "none"
    dimension: Optional[int] = None

    def embed(self, text: str) -> Optional[List[float]]:
        return None


class OllamaEmbeddingProvider:
    """Explicit opt-in provider (NEXUS_MEMORY_EMBEDDING_PROVIDER=ollama)."""

    name = "ollama"

    def __init__(self, endpoint: Optional[str] = None, model: Optional[str] = None, timeout: float = 2.0):
        self.endpoint = (endpoint or os.environ.get(OLLAMA_ENDPOINT_ENV) or "http://localhost:11434").rstrip("/")
        self.model = model or os.environ.get(OLLAMA_EMBED_MODEL_ENV) or "nomic-embed-text"
        self.timeout = timeout

    def embed(self, text: str) -> Optional[List[float]]:
        import urllib.request

        req = urllib.request.Request(
            f"{self.endpoint}/api/embeddings",
            data=json.dumps({"model": self.model, "prompt": text[:2000]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            result = json.loads(response.read())
        vec = result.get("embedding")
        return [float(x) for x in vec] if vec else None


def default_embedding_provider() -> EmbeddingProvider:
    """Resolve the provider from env; anything but an explicit opt-in is 'none'."""
    choice = os.environ.get(EMBEDDING_PROVIDER_ENV, "none").strip().lower()
    if choice == "ollama":
        return OllamaEmbeddingProvider()
    if choice not in {"", "none"}:
        logger.warning("Unknown %s=%r; using no embedding provider", EMBEDDING_PROVIDER_ENV, choice)
    return NoEmbeddingProvider()


class MemoryRepository:
    """
    Authoritative DAO for Nexus Brain (LanceDB).
    Implements v23.5 Hardened Semantic Dedup and v24.0 AAAK Eternal Compression.
    """
    def __init__(self, db_path: Path, embedding_provider: Optional[EmbeddingProvider] = None):
        self.db_path = db_path
        self._db = None
        self.embedding_provider: EmbeddingProvider = embedding_provider or default_embedding_provider()
        # Visible outcome of the most recent embedding attempt: {"status","provider","reason"}.
        self.last_embedding: Dict[str, str] = {}
        # Outcome of the most recent schema evolution attempt on an existing table.
        self.last_schema_evolution: Dict[str, Any] = {}

    def compress_to_aaak(self, text: str) -> str:
        """⚡ AAAK (Aggressive Agentic Knowledge) 30x Compression Dialect."""
        if len(text) < 100: return text
        
        digest = hashlib.md5(text.encode()).hexdigest()[:8]
        
        # Local LLM (Ollama) distillation is explicit opt-in: no network on the default write path.
        if os.environ.get(OLLAMA_AAAK_ENV, "").strip().lower() in _TRUTHY:
            try:
                import urllib.request
                req = urllib.request.Request(
                    "http://localhost:11434/api/generate",
                    data=json.dumps({
                        "model": "llama3",
                        "prompt": f"Compress to extreme AAAK shorthand dialect (max 1/30 length, keep nouns/verbs/code/paths only). Source: {text[:2000]}",
                        "stream": False
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=2.0) as response:
                    result = json.loads(response.read())
                    if "response" in result:
                        return f"aaak:{digest}: {result['response'].strip()}"
            except Exception as exc:
                logger.warning("AAAK Ollama compression failed, using heuristic fallback: %s", exc)

        # AAAK Heuristic Dialect Fallback (Regex-driven structural compression)
        import re
        
        # 1. 保留核心結構 (paths, classes, functions, ids)
        core_elements = re.findall(r'(?:/[/\w.-]+|\b(?:class|def|struct)\s+\w+|\b[A-Z][a-z]+[A-Z]\w+|\b[a-z]+_[a-z_]+\b)', text)
        
        # 2. 保留重要關鍵字語境 (error, fail, pass, auth, etc)
        keywords = re.findall(r'\b(?:error|fail|pass|auth|api|sql|db|key|sync|lock|thread)\b', text.lower())
        
        # 3. 過濾重複並組合
        unique_elements = list(dict.fromkeys(core_elements + keywords))
        
        # 4. 構建極短方言
        compressed = " ".join(unique_elements[:50]) # limit max 50 tokens
        
        return f"aaak:{digest}:{compressed} [dialect_fallback]"

    def _get_db(self):
        if self._db is None:
            try:
                import lancedb
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self._db = lancedb.connect(self.db_path)
            except Exception as e:
                logger.error(f"Failed to connect to LanceDB: {e}")
                raise InfrastructureError(f"LanceDB connection failed: {e}")
        return self._db

    def list_tables(self) -> List[str]:
        """[TD-3 Hardened] Public method to list available memory tables."""
        db = self._get_db()
        if db is None:
            return []
        raw = db.list_tables() if hasattr(db, 'list_tables') else db.table_names()
        tables = getattr(raw, "tables", raw)
        return [str(name) for name in list(tables or [])]


    def _resolve_embedding(self, record: Dict[str, Any], vector_col: str) -> Optional[List[float]]:
        """Fill embedding_status/provider/reason on the record; never raises, never swallows silently."""
        provider_name = str(getattr(self.embedding_provider, "name", type(self.embedding_provider).__name__))
        vec = record.get(vector_col)
        reason = ""
        if vec is None:
            text = str(record.get("content") or "")
            if not text:
                reason = "no_content"
            else:
                try:
                    vec = self.embedding_provider.embed(text)
                except Exception as exc:
                    reason = f"provider_error:{type(exc).__name__}"
                    logger.warning("Embedding provider %s failed: %s", provider_name, exc)
                else:
                    if not vec:
                        vec = None
                        reason = "provider_none" if provider_name == "none" else "provider_returned_no_vector"
        if vec is not None:
            record[vector_col] = [float(x) for x in vec]
            status = "ok"
        else:
            record.pop(vector_col, None)
            status = "missing"
        record["embedding_status"] = status
        record["embedding_provider"] = provider_name
        record["embedding_reason"] = reason
        self.last_embedding = {"status": status, "provider": provider_name, "reason": reason}
        return record.get(vector_col)

    def semantic_dedup_ingest(self, table_name: str, new_record: Dict[str, Any], vector_col: str = "vector", tenant_id: str = "default"):
        """Hardened ingest: <0.1 DUPLICATE / 0.1-0.3 MERGED / >0.3 NEW.

        Vectors come from the record or the injected EmbeddingProvider. Without a vector the
        row is still written with embedding_status="missing" (no dedup, no blocking call).
        """
        # 🛡️ Dual-Mode Metadata Injection
        new_record["tenant_id"] = tenant_id
        content = new_record.get("content", "")
        new_record["drawer_id"] = hashlib.md5(f"{tenant_id}:{content}".encode()).hexdigest()
        new_record["aaak_content"] = self.compress_to_aaak(content)
        query_vec = self._resolve_embedding(new_record, vector_col)

        db = self._get_db()
        if db is None or table_name not in self.list_tables():
            self.add_rows(table_name, [new_record], vector_col=vector_col)
            return "NEW_INITIAL"

        table = db.open_table(table_name)
        # LanceDB rejects columns absent from the table schema; drop (visibly) rather than fail the write.
        self._evolve_table_schema(table, table_name, vector_col)
        columns = set(table.schema.names)
        for key in INGEST_METADATA_COLUMNS:
            if key in new_record and key not in columns:
                logger.warning("Table %s has no %s column; field dropped, row stored without it", table_name, key)
                new_record.pop(key, None)
        provider_name = str(new_record.get("embedding_provider", ""))
        for key in (vector_col, "embedding_status", "embedding_provider", "embedding_reason"):
            if key in new_record and key not in columns:
                if key == vector_col:
                    logger.warning("Table %s has no %s column; vector dropped, row stored without it", table_name, vector_col)
                    new_record["embedding_status"] = "missing"
                    new_record["embedding_reason"] = "table_has_no_vector_column"
                    self.last_embedding = {"status": "missing", "provider": provider_name, "reason": "table_has_no_vector_column"}
                    query_vec = None
                new_record.pop(key, None)
        if query_vec is None:
            self.add_rows(table_name, [new_record])
            return "NEW_NO_VECTOR"

        # Search for the nearest neighbor to calculate semantic distance
        results = table.search(query_vec).limit(1).to_pandas()
        
        if results.empty:
            self.add_rows(table_name, [new_record])
            return "NEW_EMPTY_TABLE"

        # LanceDB distance is L2 (squared Euclidean), we check sqrt for standard distance
        # threshold < 0.1 (dist^2 < 0.01)
        dist_sq = results.iloc[0].get("_distance", 1.0)
        
        # 🛡️ Threshold Enforcement
        if dist_sq < 0.01: # < 0.1 distance
            logger.info(f"DEDUP: Duplicate record not written (dist_sq: {dist_sq:.4f})")
            return "DUPLICATE"
        
        elif dist_sq <= 0.09: # 0.1 - 0.3 distance
            # MERGE: Update metadata of the existing record
            target_id = results.iloc[0].get("id")
            logger.info(f"DEDUP: Merging record into {target_id} (dist_sq: {dist_sq:.4f})")
            
            # Update existing row with new evidence_ids and timestamp
            # NOTE: LanceDB update logic varies by version, using delete+add for atomicity if needed
            new_record["updated_at"] = time.time()
            if "evidence_ids" in results.columns and "evidence_ids" in new_record:
                combined_evidence = list(set(results.iloc[0]["evidence_ids"]) | set(new_record["evidence_ids"]))
                new_record["evidence_ids"] = combined_evidence
            
            table.delete(f"id = '{target_id}'")
            table.add([new_record])
            return "MERGED"
        
        else: # > 0.3 distance
            logger.info(f"DEDUP: Inserting new distinct record (dist_sq: {dist_sq:.4f})")
            new_record["updated_at"] = time.time()
            table.add([new_record])
            return "NEW"

    def _vector_dimension(self) -> Optional[int]:
        dim = getattr(self.embedding_provider, "dimension", None)
        return dim if isinstance(dim, int) and not isinstance(dim, bool) and dim > 0 else None

    def _metadata_fields(self, vector_col: str, existing: Optional[Any] = None) -> List[Any]:
        """Fields every table must carry so schema never depends on the first row written."""
        import pyarrow as pa

        have = set(existing.names) if existing is not None else set()
        fields = [pa.field(n, pa.string(), nullable=True) for n in EMBEDDING_METADATA_COLUMNS if n not in have]
        dim = self._vector_dimension()
        if dim and vector_col not in have:
            fields.append(pa.field(vector_col, pa.list_(pa.float32(), dim), nullable=True))
        return fields

    def _build_schema(self, rows: List[Dict[str, Any]], vector_col: str):
        """Infer the row schema, then force the metadata/vector columns to stable nullable types."""
        import pyarrow as pa

        inferred = pa.Table.from_pylist(
            [{k: v for k, v in row.items() if k != vector_col} for row in rows]
        ).schema
        fields = []
        for field in inferred:
            if field.name in EMBEDDING_METADATA_COLUMNS:
                field = pa.field(field.name, pa.string(), nullable=True)
            fields.append(field)
        extra = self._metadata_fields(vector_col, existing=pa.schema(fields))
        dim = self._vector_dimension()
        if not dim and any(row.get(vector_col) is not None for row in rows):
            width = len(next(row[vector_col] for row in rows if row.get(vector_col) is not None))
            extra.append(pa.field(vector_col, pa.list_(pa.float32(), width), nullable=True))
        return pa.schema(fields + extra)

    def _evolve_table_schema(self, table: Any, table_name: str, vector_col: str = "vector") -> bool:
        """Add missing embedding metadata, ingest metadata (tenant_id/drawer_id/aaak_content) and vector columns.

        The vector column is added only when the embedding dimension is known.

        Uses LanceDB add_columns (all-null backfill; existing rows are never rewritten or dropped).
        On failure, records the reason and leaves the caller's warn-and-strip path in place.
        """
        missing = self._metadata_fields(vector_col, existing=table.schema)
        have = set(table.schema.names)
        import pyarrow as pa

        missing += [pa.field(n, pa.string(), nullable=True) for n in INGEST_METADATA_COLUMNS if n not in have]
        if not missing:
            return True

        try:
            table.add_columns(pa.schema(missing))
        except Exception as exc:
            reason = f"schema_evolution_failed:{type(exc).__name__}"
            logger.warning("Table %s missing columns %s; %s: %s", table_name, [f.name for f in missing], reason, exc)
            self.last_schema_evolution = {"table": table_name, "status": "failed", "reason": reason}
            return False
        self.last_schema_evolution = {"table": table_name, "status": "added", "columns": [f.name for f in missing]}
        return True

    def ensure_table(
        self,
        table_name: str,
        initial_data: List[Dict[str, Any]] = None,
        fts_column: Optional[str] = None,
        vector_col: str = "vector",
    ):
        db = self._get_db()
        if db is None:
            return

        if table_name in self.list_tables() or not initial_data:
            return

        try:
            import pyarrow as pa

            schema = self._build_schema(initial_data, vector_col)
            data = pa.Table.from_pylist(initial_data, schema=schema)
            tbl = db.create_table(table_name, data=data, schema=schema)
        except Exception as e:
            if "already exists" in str(e).lower() or table_name in self.list_tables():
                logger.debug(f"LanceDB table already exists during ensure_table race: {table_name}")
                return
            logger.warning("Explicit-schema create of %s failed (%s); falling back to inferred schema", table_name, e)
            tbl = db.create_table(table_name, data=initial_data)

        if fts_column:
            try:
                tbl.create_fts_index(fts_column, replace=True)
            except Exception as e:
                logger.debug(f"LanceDB FTS index init skipped for {table_name}: {e}")

    def add_rows(self, table_name: str, rows: List[Dict[str, Any]], vector_col: str = "vector"):
        db = self._get_db()
        if db is None:
            return
        # Stamp before create/append so the first row's schema matches later appends.
        for row in rows:
            if "updated_at" not in row: row["updated_at"] = time.time()
        if table_name not in self.list_tables():
            self.ensure_table(table_name, initial_data=rows, vector_col=vector_col)
        else:
            table = db.open_table(table_name)
            table.add(rows)

    def update_table(self, table_name: str, data: Any) -> None:
        """Replace a table with dataframe/list records for learning-weight updates."""
        rows = data.to_dict("records") if hasattr(data, "to_dict") else list(data or [])
        if not rows:
            return
        db = self._get_db()
        if db is None:
            return
        if table_name not in self.list_tables():
            self.ensure_table(table_name, initial_data=rows)
            return
        table = db.open_table(table_name)
        try:
            table.delete("true")
        except Exception:
            try:
                table.delete("1 = 1")
            except Exception:
                logger.debug("LanceDB full-table delete skipped for %s", table_name)
        table.add(rows)

    def get_all_rows(self, table_name: str):
        import pandas as pd
        db = self._get_db()
        if db is None or table_name not in self.list_tables():
            return pd.DataFrame()
        return db.open_table(table_name).to_pandas()

    def search_fts_across_tables(self, query: str, tables: List[str], limit: int = 10):
        """🚀 跨表全文搜尋 (NexusFS grep 的後端)。"""
        import pandas as pd
        all_results = []
        for table_name in tables:
            try:
                df = self.search_fts(table_name, query, limit=limit)
                if not df.empty:
                    df["_source_table"] = table_name
                    all_results.append(df)
            except Exception as e:
                logger.debug(f"FTS search failed on {table_name}: {e}")
                continue
        
        if not all_results:
            return pd.DataFrame()
        
        combined = pd.concat(all_results, ignore_index=True)
        if "_score" in combined.columns:
            combined = combined.sort_values("_score", ascending=False).head(limit)
        return combined

    def search_fts(self, table_name: str, query: str, limit: int = 10, fallback_columns: List[str] = None):
        """執行單表全文搜尋。

        Tries the table's LanceDB full-text index first. Without one (LanceDB raises, e.g.
        "There is no vector column"), falls back to tokenised BM25 scoring over
        ``fallback_columns`` (#2640) instead of matching the whole query as one substring.
        Fallback rows carry a ``_score`` column and are sorted by it, highest first. Columns
        named in ``fallback_columns`` that the table does not have are skipped (an absent
        ``aaak_content`` used to raise ``KeyError``). Without ``fallback_columns`` there is
        no fallback and the result is empty, as before. The fallback applies the BM25
        relevance floor (``BM25Index.floored_scores``).
        """
        import pandas as pd
        db = self._get_db()
        if db is None or table_name not in self.list_tables():
            return pd.DataFrame()
            
        table = db.open_table(table_name)
        try:
            # 優先執行 FTS
            return table.search(query).limit(limit).to_pandas()
        except Exception:
            # 如果 FTS 索引不存在，退回到 BM25 關鍵字排序
            if not fallback_columns:
                return pd.DataFrame()
            df = table.to_pandas()
            ranked = bm25_frame_search(df, query, limit=limit, columns=fallback_columns)
            return pd.DataFrame() if ranked.empty else ranked


def bm25_frame_search(df: Any, query: str, *, limit: int = 10, columns: Optional[List[str]] = None):
    """Rank DataFrame rows by tokenised BM25 over ``columns`` (missing columns are skipped).

    Rows must pass the relevance floor (``BM25Index.floored_scores``). ``columns=None``
    means every string column. Returns an empty slice of ``df`` when nothing matches.
    """
    from nexus.services.bm25_retrieval import BM25Index

    if df.empty or not str(query or "").strip():
        return df.iloc[0:0]
    if columns is None:
        usable = [col for col in df.columns if df[col].dtype == object and not str(col).startswith("_")]
    else:
        usable = [col for col in columns if col in df.columns]
    if not usable:
        return df.iloc[0:0]
    texts = (
        df[usable]
        .apply(lambda row: "\n".join(str(v) for v in row if isinstance(v, str) and v), axis=1)
        .tolist()
    )
    scores = BM25Index(enumerate(texts)).floored_scores(query)
    if not scores:
        return df.iloc[0:0]
    order = sorted(scores, key=lambda index: (-scores[index], index))
    if limit is not None and limit >= 0:
        order = order[:limit]
    result = df.iloc[order].copy()
    result["_score"] = [scores[index] for index in order]
    return result
