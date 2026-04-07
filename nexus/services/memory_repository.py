import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
try:
    from nexus.core.ui import InfrastructureError
except (ImportError, ModuleNotFoundError):
    class InfrastructureError(RuntimeError):
        """Fallback for Nexus Infrastructure errors when core modules are missing."""
        pass

try:
    import lancedb
    import numpy as np
except ModuleNotFoundError:
    lancedb = None
    np = None

logger = logging.getLogger(__name__)

class MemoryRepository:
    """
    Authoritative DAO for Nexus Brain (LanceDB).
    Implements v23.5 Hardened Semantic Dedup and Knowledge Ingest.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db = None

    def _get_db(self):
        if self._db is None and lancedb:
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self._db = lancedb.connect(self.db_path)
            except Exception as e:
                logger.error(f"Failed to connect to LanceDB: {e}")
                raise InfrastructureError(f"LanceDB connection failed: {e}")
        return self._db

    def semantic_dedup_ingest(self, table_name: str, new_record: Dict[str, Any], vector_col: str = "vector"):
        """🚀 Nexus v23.5 Hardened Ingest: <0.1 discard / 0.1-0.3 merge / >0.3 new."""
        db = self._get_db()
        if not db or table_name not in db.list_tables():
            self.add_rows(table_name, [new_record])
            return "NEW_INITIAL"

        table = db.open_table(table_name)
        if vector_col not in new_record:
            self.add_rows(table_name, [new_record])
            return "NEW_NO_VECTOR"

        query_vec = new_record[vector_col]
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
            logger.info(f"DEDUP: Discarded highly similar record (dist_sq: {dist_sq:.4f})")
            return "DISCARDED"
        
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

    def ensure_table(self, table_name: str, initial_data: List[Dict[str, Any]] = None, fts_column: Optional[str] = None):
        db = self._get_db()
        if not db: return
        
        if table_name not in db.list_tables():
            if initial_data:
                tbl = db.create_table(table_name, data=initial_data)
                if fts_column: tbl.create_fts_index(fts_column, replace=True)

    def add_rows(self, table_name: str, rows: List[Dict[str, Any]]):
        db = self._get_db()
        if not db: return
        if table_name not in db.list_tables():
            self.ensure_table(table_name, initial_data=rows)
        else:
            table = db.open_table(table_name)
            for row in rows:
                if "updated_at" not in row: row["updated_at"] = time.time()
            table.add(rows)

    def get_all_rows(self, table_name: str) -> pd.DataFrame:
        db = self._get_db()
        if not db or table_name not in db.list_tables():
            return pd.DataFrame()
        return db.open_table(table_name).to_pandas()
