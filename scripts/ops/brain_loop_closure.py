import os
import json
import lancedb
import re
from pathlib import Path
from sentence_transformers import SentenceTransformer

class BrainLoopClosure:
    def __init__(self, db_path=str(__import__("pathlib").Path(__file__).resolve().parents[2] / ".nexus/vector_db/")):
        self.db_path = os.path.expanduser(db_path)
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.db = lancedb.connect(self.db_path)
        self.table_name = "nexus_knowledge"
        
    def _clean_table(self):
        """🧹 WIPE the old hollow core."""
        if self.table_name in self.db.table_names():
            self.db.drop_table(self.table_name)
            print(f"🧹 [BrainLoop] Truncated {self.table_name}")

    def collect_knowledge(self):
        batch_data = []
        
        # 1. Autoresearch JSON Reports (Strategic Wisdom)
        runtime_path = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2] / "Autoresearch_runtime"))
        if runtime_path.exists():
            reports = list(runtime_path.glob("*.json"))
            for r_file in reports[:150]: # Focus on most relevant
                try:
                    with open(r_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 提煉核心教訓
                    summary = data.get("summary", "No summary")
                    if isinstance(summary, dict): summary = json.dumps(summary)
                    
                    batch_data.append(self._format("Research Report", r_file.stem, summary))
                except:
                    pass
            print(f"🚀 [BrainLoop] Collected {len(batch_data)} research reports.")

        # 2. Nexus Wiki Vault (Legal & Operational Standards)
        wiki_vault = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2] / "nexus_wiki_vault"))
        if wiki_vault.exists():
            wiki_files = list(wiki_vault.rglob("*.md"))
            for w_file in wiki_files:
                batch_data.append(self._format("Wiki Standard", w_file.stem, w_file.read_text()[:1500]))
            print(f"📖 [BrainLoop] Collected {len(wiki_files)} Wiki standards.")

        # 3. Codex Lessons (Critical Fixes)
        codex_path = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2] / ".codex_lessons.md"))
        if codex_path.exists():
            content = codex_path.read_text()
            lessons = re.findall(r"## \[(.*?)\](.*?)(?=\n## \[|\n### 🧠|$)", content, re.DOTALL)
            for title, body in lessons:
                batch_data.append(self._format("Codex Lesson", title.strip(), body.strip()))
            print(f"🧬 [BrainLoop] Collected {len(lessons)} Codex lessons.")

        return batch_data

    def _format(self, category, title, body):
        task = f"[{category}] {title}"
        vector = self.model.encode(task).tolist()
        return {
            "task": task,
            "resolution": body[:3000], # Detailed but sane
            "vector": vector
        }

    def execute_closure(self):
        self._clean_table()
        data = self.collect_knowledge()
        if data:
            self.db.create_table(self.table_name, data=data)
            print(f"✅ [BrainLoop] Closed the loop: {len(data)} high-signal wisdom units fused with core.")

if __name__ == "__main__":
    loop = BrainLoopClosure()
    loop.execute_closure()
