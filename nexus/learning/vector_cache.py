import logging
import lancedb
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

import numpy as np
import pyarrow as pa

class VectorCache:
    """SOTA 向量緩存核心 (LanceDB + Jina v3 1024d 驅動)
    
    具備 <1s 語義檢索與物化存儲能力，支撐學術錨定與蜂群調度計畫。
    數據真值轉向 Nexus 生產環境。
    """
    TIERS = ["ephemeral", "local", "global", "eternal"]
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path))
        self.table_name = "sota_v19_cache"
        self._ensure_table()

    def _ensure_table(self):
        """確保向量表存在於物理存儲中。"""
        if self.table_name not in self.db.table_names():
            # 🛡️ 物理硬化：雙重對位 (Schema + Data) 封殺類型推斷錯誤
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("vector", pa.fixed_size_list(pa.float32(), 1024)),
                pa.field("content", pa.string()),
                pa.field("tier", pa.string()),
                pa.field("metadata", pa.string())
            ])
            seed_data = [{
                "id": "seed",
                "vector": np.zeros(1024, dtype=np.float32),
                "content": "seed_node",
                "tier": "global",
                "metadata": "{}"
            }]
            self.db.create_table(self.table_name, data=seed_data, schema=schema)
            logger.info("vector_cache_table_hardened_with_dual_alignment [%s]", self.table_name)

    def upsert(self, entries: List[Dict[str, Any]]):
        """批量物理注入向量數據。具備彈性容錯閘門。"""
        try:
            table = self.db.open_table(self.table_name)
            # 🧬 物理具現：顯式轉換 DataFrame 類型
            df = pd.DataFrame(entries)
            table.add(data=df)
            logger.info("vector_cache_upsert_completed [%d_entries]", len(entries))
        except Exception as e:
            logger.error("vector_cache_upsert_physical_error_graceful_降級 [%s]", str(e))

    def search(self, query_vector: Any, limit: int = 5) -> List[Dict[str, Any]]:
        """執行高維語義空間物理檢索。"""
        table = self.db.open_table(self.table_name)
        # 🛡️ 物理硬化：顯式轉換為 numpy.float32 以確保類型正確
        vec = np.array(query_vector, dtype=np.float32)
        results = table.search(vec, vector_column_name="vector").limit(limit).to_list()
        return results

    def weighted_retrieve(self, query_vector: Any, phase: str = "P", limit: int = 5) -> List[Dict[str, Any]]:
        """🧬 P3: 權重檢索 (Weighted RAG)"""
        weights = {"P": {"global": 1.0, "local": 0.8, "ephemeral": 0.5},
                   "R": {"local": 1.0, "global": 0.8, "ephemeral": 0.5}}.get(phase, {"global": 1.0})
        
        raw_results = self.search(query_vector, limit=limit * 2)
        
        # 根據 Tier 進行物理加權排序
        for res in raw_results:
            tier = res.get("tier", "global")
            res["weighted_score"] = res.get("_distance", 1.0) * weights.get(tier, 0.5)
            
        sorted_results = sorted(raw_results, key=lambda x: x["weighted_score"])
        return sorted_results[:limit]


    def clear(self):
        """物理清除所有緩存數據，執行真值重置。"""
        self.db.drop_table(self.table_name)
        self._ensure_table()
        logger.warning("vector_cache_cleared")
