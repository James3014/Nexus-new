import os
import json
import lancedb
from pathlib import Path
from datetime import datetime
from sentence_transformers import SentenceTransformer

class WisdomVault:
    def __init__(self, db_path="str(REPO_ROOT)/.nexus/vector_db/"):
        self.db_path = os.path.expanduser(db_path)
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.db = lancedb.connect(self.db_path)
        self.table_name = "nexus_knowledge" # 原生核心智慧表
        
    def ingest_mirror_batch(self, mirror_dir="/tmp/nexus_mirror"):
        mirror_path = Path(mirror_dir)
        if not mirror_path.exists():
            print(f"❌ [WisdomVault] Mirror dir {mirror_dir} not found.")
            return

        episodes = list(mirror_path.glob("*.json"))
        print(f"🚀 [WisdomVault] Scanning {len(episodes)} episodes...")

        batch_data = []
        for ep_file in episodes:
            try:
                with open(ep_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                title = data.get("title", "Unknown Episode")
                body = data.get("body", "")
                extra = data.get("extra", {})
                score = extra.get("audit_score", 0)
                
                # 🛡️ 原生 Schema 對位: task / resolution
                task_content = f"[Swarm Episode] {title}"
                resolution_content = f"Result: {body}\nAudit Score: {score}\nTask ID: {data.get('task_id')}"
                
                # 模型向量化
                vector = self.model.encode(task_content).tolist()
                
                batch_data.append({
                    "task": task_content,
                    "resolution": resolution_content,
                    "vector": vector
                })
            except Exception as e:
                print(f"⚠️ [WisdomVault] Failed to parse {ep_file.name}: {e}")

        if not batch_data:
            return

        # 🛡️ 核心表寫入
        if self.table_name in self.db.table_names():
            table = self.db.open_table(self.table_name)
            table.add(batch_data)
            print(f"✅ [WisdomVault] Fused {len(batch_data)} records into {self.table_name}.")
        else:
            print(f"⚠️ [WisdomVault] Table {self.table_name} missing from {self.db_path}")

    def search_wisdom(self, query: str, limit: int = 3):
        """🔍 原生語義檢索。"""
        if self.table_name not in self.db.table_names():
            return None
        table = self.db.open_table(self.table_name)
        query_vector = self.model.encode(query).tolist()
        results = table.search(query_vector).limit(limit).to_pandas()
        return results

if __name__ == "__main__":
    vault = WisdomVault()
    vault.ingest_mirror_batch()
