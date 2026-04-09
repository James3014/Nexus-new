import os
import json
import lancedb
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer

class BrainLoopClosure:
    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path(__import__("pathlib").Path(__file__).resolve().parents[2])
        self.knowledge_dir = self.repo_root / ".nexusknowledge"
        self.db_path = self.repo_root / ".nexus/vector_db/"
        
        self.beliefs_path = self.knowledge_dir / "beliefs.jsonl"
        self.artifacts_path = self.knowledge_dir / "artifacts.jsonl"
        self.edges_path = self.knowledge_dir / "dependency_edges.jsonl"
        
        # Ensure v0.2 files exist
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        for p in [self.beliefs_path, self.artifacts_path, self.edges_path]:
            if not p.exists(): p.touch()

        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.db = lancedb.connect(str(self.db_path))
        self.table_name = "nexus_knowledge"

    # --- v0.2 Belief Revision Core ---

    def load_jsonl(self, path: Path) -> List[Dict[str, Any]]:
        if not path.exists(): return []
        with open(path, 'r', encoding='utf-8') as f:
            return [json.loads(line) for line in f if line.strip()]

    def save_jsonl(self, path: Path, data: List[Dict[str, Any]]):
        with open(path, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')

    def propagate_belief_revision(self, belief_id: str, new_status: str):
        """🚀 [v0.2] 沿 Dependency Graph 傳播信念修訂影響"""
        beliefs = self.load_jsonl(self.beliefs_path)
        artifacts = self.load_jsonl(self.artifacts_path)
        edges = self.load_jsonl(self.edges_path)
        
        # 1. 更新 Belief 狀態
        found = False
        for b in beliefs:
            if b.get("id") == belief_id:
                b["status"] = new_status
                b["updated_at"] = datetime.utcnow().isoformat()
                found = True
                break
        if not found:
            print(f"⚠️ [v0.2] Belief ID {belief_id} not found.")
            return

        # 2. 尋找直接受影響的 Artifacts (depends_on / derived_from)
        affected_artifact_ids = [
            e["to_id"] for e in edges 
            if e["from_id"] == belief_id and e["type"] in ["depends_on", "derived_from"]
        ]

        # 3. 標記 Artifacts 為 Stale
        for art in artifacts:
            if art.get("id") in affected_artifact_ids:
                if new_status in ["retracted", "superseded"]:
                    art["status"] = "stale"
                    art["stale_reason"] = f"Underlying belief {belief_id} became {new_status}"
                    art["updated_at"] = datetime.utcnow().isoformat()
                    print(f"🛡️ [v0.2] Artifact {art['id']} marked STALE due to {belief_id}")

        # 4. 存檔
        self.save_jsonl(self.beliefs_path, beliefs)
        self.save_jsonl(self.artifacts_path, artifacts)
        print(f"✅ [v0.2] Propagation complete for belief {belief_id}")

    # --- Knowledge Fusion Logic ---

    def _clean_table(self):
        res = self.db.list_tables()
        tables = res if isinstance(res, list) else (res.tables if hasattr(res, "tables") else res)
        if self.table_name in tables:
            self.db.drop_table(self.table_name)

    def collect_knowledge(self):
        batch_data = []
        
        # [原有邏輯] Autoresearch Reports
        runtime_path = self.repo_root / "Autoresearch_runtime"
        if runtime_path.exists():
            for r_file in list(runtime_path.glob("*.json"))[:150]:
                try:
                    with open(r_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    summary = data.get("summary", "No summary")
                    if isinstance(summary, dict): summary = json.dumps(summary)
                    batch_data.append(self._format("Research Report", r_file.stem, summary))
                except: pass

        # [v0.2 整合] 將 Active Beliefs 注入向量庫
        beliefs = self.load_jsonl(self.beliefs_path)
        for b in beliefs:
            if b.get("status") == "active":
                batch_data.append(self._format("Belief", b.get("id"), b.get("content", "")))

        return batch_data

    def _format(self, category, title, body):
        task = f"[{category}] {title}"
        vector = self.model.encode(task).tolist()
        return {
            "task": task,
            "resolution": body[:3000],
            "vector": vector,
            "timestamp": datetime.utcnow().isoformat()
        }

    def execute_closure(self):
        self._clean_table()
        data = self.collect_knowledge()
        if data:
            self.db.create_table(self.table_name, data=data)
            print(f"✅ [BrainLoop] v0.2 Wisdom Fusion: {len(data)} units synthesized.")

if __name__ == "__main__":
    loop = BrainLoopClosure()
    # 測試 Propagation 邏輯
    loop.execute_closure()
