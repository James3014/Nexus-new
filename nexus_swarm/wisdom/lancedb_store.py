# 🛡️ Nexus Wisdom Memory Layer (LanceDB Integrated)
# [ARCH-EVO: v23 WISDOM EDITION STORAGE]

import lancedb
import pandas as pd
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import pyarrow as pa
import os

class WisdomMemory:
    def __init__(self, db_path: str = "./nexus-swarm/wisdom/wisdom_memory"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = lancedb.connect(db_path)
        # 🛡️ Using local-first all-MiniLM-L6-v2 (384-dim)
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.table_name = "wisdom_patterns"
        self.table = self._get_or_create_table()
    
    def _get_or_create_table(self):
        if self.table_name in self.db.list_tables():
            return self.db.open_table(self.table_name)
        
        # 🛡️ Defining Nexus Wisdom Schema
        schema = pa.schema([
            pa.field("pattern_id", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), 384)),
            pa.field("repo", pa.string()),
            pa.field("language", pa.string()),
            pa.field("issue_type", pa.string()),
            pa.field("decision_type", pa.string()),
            pa.field("confidence", pa.float32()),
            pa.field("fp_count", pa.int32()),
            pa.field("human_feedback", pa.string()),
            pa.field("last_updated", pa.string())
        ])
        
        return self.db.create_table(self.table_name, schema=schema)
    
    def store_pattern(self, pattern_data: Dict[str, Any], code_snippet: str):
        """存入新 pattern 與生成的向量表"""
        embedding = self.embedding_model.encode(code_snippet)
        data = {
            **pattern_data, 
            "embedding": embedding.tolist()
        }
        # 🛡️ Optimistic Update (Manual deduplication in first version)
        self.table.add([data])
    
    def lookup_similar(self, code_snippet: str, repo: str, language: str, top_k: int = 5) -> List[Dict]:
        """執行 Metadata Pre-filtered Vector Search"""
        embedding = self.embedding_model.encode(code_snippet)
        
        # 🛡️ P95 < 150ms Performance Goal
        results = self.table.search(
            embedding,
            query_type="vector"
        ).where(
            f"repo = '{repo}' AND language = '{language}'"
        ).limit(top_k).to_pandas().to_dict('records')
        
        return results

if __name__ == "__main__":
    # Unit Test: Wisdom Storage Capability
    wm = WisdomMemory("/tmp/wisdom_test")
    test_pattern = {
        "pattern_id": "rust-lock-poison-22",
        "repo": "nexus",
        "language": "rust",
        "issue_type": "concurrency",
        "decision_type": "escalate",
        "confidence": 0.85,
        "fp_count": 0,
        "human_feedback": "INITIAL_SEED",
        "last_updated": "2026-04-04T00:00:00Z"
    }
    wm.store_pattern(test_pattern, "let lock = mutex.lock().unwrap();")
    
    hits = wm.lookup_similar("mutex.lock().unwrap()", "nexus", "rust")
    print(f"🛡️ Wisdom Lookup Hit: {len(hits)} results found.")
    for hit in hits:
        print(f"  - Pattern: {hit['pattern_id']}, Confidence: {hit['confidence']}")
