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

    def propagate_belief_revision(self, belief_id: str, new_status: str, reason: str = "Unspecified"):
        """🚀 [v24.0 Hardened] 沿 Dependency Graph 雙向傳播信念修訂影響 (含向量同步)"""
        beliefs = self.load_jsonl(self.beliefs_path)
        artifacts = self.load_jsonl(self.artifacts_path)
        edges = self.load_jsonl(self.edges_path)
        
        # 1. 更新 Belief 狀態與熵值
        target_belief = next((b for b in beliefs if b.get("id") == belief_id), None)
        if not target_belief:
            print(f"⚠️ [v24.0] Belief ID {belief_id} not found.")
            return

        target_belief["status"] = new_status
        target_belief["updated_at"] = datetime.utcnow().isoformat()
        # 🧪 [Round 20] 增加修正計數 (Entropy Tracking)
        target_belief["revision_count"] = target_belief.get("revision_count", 0) + 1
        if target_belief["revision_count"] > 3:
            target_belief["trust_level"] = "UNTRUSTED"

        # 2. 同步移除向量庫索引 (防止認知污染)
        if new_status in ["retracted", "superseded", "failed"]:
            try:
                # 🧪 Atomic Vector Sync
                self.db.open_table(self.table_name).delete(f"task = '[Belief] {belief_id}'")
                print(f"🧹 [BrainLoop:Sync] Removed retracted belief {belief_id} from Vector DB.")
            except Exception: pass

        # 3. 尋找受影響的 Artifacts (Downstream)
        affected_ids = [e.get("to_id") for e in edges if e.get("from_id") == belief_id]
        for art in artifacts:
            if art.get("id") in affected_ids:
                art["status"] = "stale"
                art["stale_reason"] = f"Origin belief {belief_id} rescinded: {reason}"

        # 4. [Round 20] 反向溯源 (Upstream Propagation)
        # 如果 Artifact 失敗，撤銷所有支撐它的 Beliefs
        if new_status == "failed":
            upstream_belief_ids = [e.get("from_id") for e in edges if e.get("to_id") == belief_id and e.get("type") == "supports"]
            for ub_id in upstream_belief_ids:
                print(f"🔄 [BrainLoop:Reverse] Artifact failure triggering rescission of upstream belief {ub_id}")
                self.propagate_belief_revision(ub_id, "retracted", reason=f"Upstream support for failed artifact {belief_id}")

        self.save_jsonl(self.beliefs_path, beliefs)
        self.save_jsonl(self.artifacts_path, artifacts)
        print(f"✅ [BrainLoop:v24.0] Full-path revision complete for {belief_id}")

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
