import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
from nexus.core.errors import InfrastructureError

try:
    import lancedb
except ModuleNotFoundError:
    lancedb = None

logger = logging.getLogger(__name__)

class MemoryRepository:
    """
    Data Access Object (DAO) for LanceDB storage.
    Handles low-level table operations, FTS indexing, and search.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db = None

    def _get_db(self):
        if self._db is None:
            if lancedb is None:
                return None
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self._db = lancedb.connect(self.db_path)
            except Exception as e:
                logger.error(f"Failed to connect to LanceDB at {self.db_path}: {e}")
                raise InfrastructureError(f"LanceDB connection failed: {e}")
        return self._db

    def ensure_table(self, table_name: str, initial_data: List[Dict[str, Any]] = None, fts_column: Optional[str] = None):
        db = self._get_db()
        if not db:
            return
        
        table_names = db.list_tables()
        if table_name not in table_names:
            if initial_data:
                try:
                    tbl = db.create_table(table_name, data=initial_data)
                    if fts_column:
                        tbl.create_fts_index(fts_column, replace=True)
                    logger.info(f"Created table '{table_name}' with initial data.")
                except Exception as e:
                    logger.error(f"Failed to create table '{table_name}': {e}")
                    raise InfrastructureError(f"Table creation failed: {e}")

    def search_fts(self, table_name: str, query: str, limit: int = 3, fallback_columns: List[str] = None) -> pd.DataFrame:
        db = self._get_db()
        if not db or table_name not in db.list_tables():
            return pd.DataFrame()

        table = db.open_table(table_name)
        try:
            return table.search(query, query_type="fts").limit(limit).to_pandas()
        except Exception as e:
            logger.warning(f"FTS search failed on '{table_name}', falling back: {e}")
            if not fallback_columns:
                return pd.DataFrame()
            
            df = table.to_pandas()
            q = str(query).lower()
            mask = pd.Series([False] * len(df))
            for col in fallback_columns:
                if col in df.columns:
                    mask |= df[col].str.contains(q, case=False, na=False)
            return df[mask].head(limit)

    def update_table(self, table_name: str, data: pd.DataFrame, mode: str = "overwrite"):
        db = self._get_db()
        if not db:
            return
        try:
            db.create_table(table_name, data=data, mode=mode)
        except Exception as e:
            logger.error(f"Failed to update table '{table_name}': {e}")
            raise InfrastructureError(f"Table update failed: {e}")

    def add_rows(self, table_name: str, rows: List[Dict[str, Any]]):
        db = self._get_db()
        if not db:
            return
        try:
            if table_name not in db.list_tables():
                self.ensure_table(table_name, initial_data=rows)
            else:
                table = db.open_table(table_name)
                table.add(rows)
        except Exception as e:
            logger.error(f"Failed to add rows to '{table_name}': {e}")
            raise InfrastructureError(f"Insert failed: {e}")

    def get_all_rows(self, table_name: str) -> pd.DataFrame:
        db = self._get_db()
        if not db or table_name not in db.list_tables():
            return pd.DataFrame()
        return db.open_table(table_name).to_pandas()
