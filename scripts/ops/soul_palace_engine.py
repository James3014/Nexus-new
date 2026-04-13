import os
import json
import lancedb
from pathlib import Path
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer

class SoulPalaceEngine:
    """🛡️ Nexus v0.3 Soul-Palace (MemPalace Aligned)"""
    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path(__import__("pathlib").Path(__file__).resolve().parents[2])
        self.knowledge_dir = self.repo_root / ".nexusknowledge"
        self.db_path = self.repo_root / ".nexus/vector_db/"
        
        # Files
        self.beliefs_path = self.knowledge_dir / "beliefs.jsonl"
        self.artifacts_path = self.knowledge_dir / "artifacts.jsonl"
        self.edges_path = self.knowledge_dir / "dependency_edges.jsonl"
        
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.db = lancedb.connect(str(self.db_path))
        self.table_name = "nexus_soul_palace"

    def aaak_compress(self, text: str) -> str:
        """🚀 [AAAK] 模擬 30x AI 原生壓縮協議"""
        # 實務上會由 LLM 轉化，這裡模擬將冗長文字提取核心 token
        words = text.split()
        return "::".join([w for w in words if len(w) > 4][:10])

    def spatial_categorize(self, category: str, content: str) -> Dict[str, str]:
        """🏠 空間分類邏輯 (Method of Loci)"""
        content_low = content.lower()
        if "policy" in content_low or "audit" in content_low:
            return {"wing": "GOVERNANCE", "room": "AUDIT_LANE"}
        if "router" in content_low or "dispatch" in content_low:
            return {"wing": "ENGINE", "room": "ROUTER_CORE"}
        return {"wing": "CODE", "room": "GENERAL"}

    def store_knowledge(self, k_type: str, content: str, layer: int = 2):
        """存入宮殿：分層、分類、壓縮"""
        spatial = self.spatial_categorize(k_type, content)
        compressed = self.aaak_compress(content) if layer == 1 else content
        
        record = {
            "id": f"{k_type[0].upper()}-{datetime.now(UTC).timestamp()}",
            "wing": spatial["wing"],
            "room": spatial["room"],
            "type": k_type,
            "content": compressed,
            "layer": layer,
            "status": "active",
            "timestamp": datetime.now(UTC).isoformat()
        }
        # 寫入 JSONL (Beliefs or Artifacts)
        target = self.beliefs_path if k_type == "belief" else self.artifacts_path
        with open(target, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
            
        # 寫入 LanceDB (Layer 3 Deep Search)
        vector = self.model.encode(content).tolist()
        table_data = [{**record, "vector": vector}]
        if self.table_name in self.db.list_tables():
            table = self.db.open_table(self.table_name)
            table.add(table_data)
        else:
            self.db.create_table(self.table_name, data=table_data)
        
        print(f"🏰 [SoulPalace] Stored in {spatial['wing']} -> {spatial['room']} (Layer {layer})")

    def retrieve_context(self, query: str) -> str:
        """🚀 四層記憶棧檢索 (Stack Retrieval)"""
        # Layer 0: Identity (Always load)
        # Layer 1: Critical (Compressed)
        # Layer 2: Room-Specific
        # Layer 3: Deep Search
        print(f"🔍 [SoulPalace] Retrieving stack for: {query}")
        # 這裡僅模擬返回，實務上會從 JSONL 與 LanceDB 聚合
        return "NEXUS_IDENTITY::ACTIVE | WING::GOVERNANCE::L1::PASS"

if __name__ == "__main__":
    palace = SoulPalaceEngine()
    palace.store_knowledge("belief", "The system must prioritize local environment variables over hardcoded paths.", layer=1)
    palace.store_knowledge("artifact", "Implementation of dynamic path resolver in nexus_cli.py", layer=2)
    palace.retrieve_context("path resolution")
