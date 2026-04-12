import os
import json
import lancedb
import re
from pathlib import Path
from sentence_transformers import SentenceTransformer

class OmniInfusion:
    def __init__(self, db_path=str(__import__("pathlib").Path(__file__).resolve().parents[2] / ".nexus/vector_db/")):
        self.db_path = os.path.expanduser(db_path)
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.db = lancedb.connect(self.db_path)
        self.table_name = "nexus_knowledge"
        
    def _clean_table(self):
        """🧹 WIPE the old hollow core."""
        if self.table_name in self.db.list_tables():
            self.db.drop_table(self.table_name)
            print(f"🧹 [OmniInfusion] Truncated {self.table_name}")

    def collect_all(self):
        batch_data = []
        
        # 1. Codex Lessons
        codex_path = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2] / ".codex_lessons.md"))
        if codex_path.exists():
            content = codex_path.read_text()
            lessons = re.findall(r"## \[(.*?)\](.*?)(?=## \[|### 🧠|$)", content, re.DOTALL)
            for title, body in lessons:
                batch_data.append(self._format("Codex Lesson", title.strip(), body.strip()))
            print(f"📖 [OmniInfusion] Collected {len(lessons)} Codex lessons.")

        # 2. Phase Reports (P1-P8)
        phase_files = list(Path(str(__import__("pathlib").Path(__file__).resolve().parents[2])).rglob("PHASE*_RESEARCH*.md"))
        for p_file in phase_files:
            batch_data.append(self._format("Phase Report", p_file.stem, p_file.read_text()[:500]))
        print(f"🎯 [OmniInfusion] Collected {len(phase_files)} Phase reports.")

        # 3. Superpowers / Hyper-tests
        superpowers_logs = list(Path(str(__import__("pathlib").Path(__file__).resolve().parents[2] / ".nexus/workspaces/")).rglob("superpowers-test1/tracelog.jsonl"))
        for log in superpowers_logs[:10]: # Limit for perf
            ws_id = log.parts[-4]
            batch_data.append(self._format("Superpowers Test", ws_id, f"Trace log from hyper-test at {log}"))
        print(f"⚡ [OmniInfusion] Collected {len(superpowers_logs)} Superpowers traces.")

        # 4. Swarm Episodes (Today)
        mirror_path = Path("/tmp/nexus_mirror")
        if mirror_path.exists():
            episodes = list(mirror_path.glob("*.json"))
            for ep in episodes:
                with open(ep, 'r') as f:
                    data = json.load(f)
                batch_data.append(self._format("Swarm Episode", data.get("title"), data.get("body")))
            print(f"🚀 [OmniInfusion] Collected {len(episodes)} Swarm episodes.")

        return batch_data

    def _format(self, category, title, body):
        task = f"[{category}] {title}"
        vector = self.model.encode(task).tolist()
        return {
            "task": task,
            "resolution": body[:2000], # Keep it sane
            "vector": vector
        }

    def execute_fusion(self):
        self._clean_table()
        data = self.collect_all()
        if data:
            self.db.create_table(self.table_name, data=data)
            print(f"✅ [OmniInfusion] Fused {len(data)} high-signal records into core brain.")

if __name__ == "__main__":
    infusion = OmniInfusion()
    infusion.execute_fusion()
