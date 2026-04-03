#!/usr/bin/env python3
from pathlib import Path
from typing import Any, Dict, List
import json

try:
    import lancedb  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    lancedb = None

import pandas as pd

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    SentenceTransformer = None


class VectorRAG:
    """
    🔮 Nexus VectorRAG (Phase 10.2)
    職責: 執行高效能向量檢索，為 Planner 提供歷史經驗上下文。
    對齊 P10.2 實施標準 (Top-K=5)。
    """

    def __init__(self, db_path: str = ".nexus/vector_db"):
        self.project_root = Path(__file__).resolve().parents[2]
        self.db_path = self.project_root / db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.table_name = "nexus_knowledge"
        self.fallback_file = self.db_path.parent / f"{self.table_name}.json"
        self.db = None
        self.model = None
        self.enabled = lancedb is not None and SentenceTransformer is not None

        if self.enabled:
            self.db = lancedb.connect(str(self.db_path))
            print("🔮 [VectorRAG] Loading Embedding Model: all-MiniLM-L6-v2...")
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
        else:
            self._ensure_fallback_file()
            print("⚠️ [VectorRAG] Running in JSON fallback mode; vector dependencies unavailable.")

    def _ensure_fallback_file(self) -> None:
        self.fallback_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.fallback_file.exists():
            self.fallback_file.write_text("[]", encoding="utf-8")

    def _load_fallback_rows(self) -> List[Dict[str, Any]]:
        self._ensure_fallback_file()
        try:
            return json.loads(self.fallback_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def _save_fallback_rows(self, rows: List[Dict[str, Any]]) -> None:
        self._ensure_fallback_file()
        self.fallback_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def update_index(self, knowledge_data: List[Dict[str, Any]]):
        """
        將知識庫數據（解密後）執行向量化並存入 LanceDB。
        """
        if not knowledge_data:
            return

        print(f"🚀 [VectorRAG] Indexing {len(knowledge_data)} items...")

        if not self.enabled or self.db is None or self.model is None:
            rows = self._load_fallback_rows()
            rows.extend(knowledge_data)
            self._save_fallback_rows(rows)
            print(f"✅ [VectorRAG] Fallback index updated. Total items: {len(rows)}")
            return

        df = pd.DataFrame(knowledge_data)
        texts = df["task"].tolist()
        embeddings = self.model.encode(texts)

        df["vector"] = embeddings.tolist()

        if self.table_name in self.db.table_names():
            table = self.db.open_table(self.table_name)
            table.add(df)
        else:
            self.db.create_table(self.table_name, data=df)

        print(f"✅ [VectorRAG] Index Updated. Total items: {len(self.db.open_table(self.table_name))}")

    def _fallback_score(self, row: Dict[str, Any], query: str) -> int:
        haystack = " ".join(
            [
                str(row.get("task", "")),
                str(row.get("resolution", "")),
                str(row.get("content", "")),
            ]
        ).lower()
        tokens = [token for token in query.lower().split() if token]
        return sum(1 for token in tokens if token in haystack)

    def query(self, task_query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        執行語義搜索，返回 Top-K 匹配模式。
        """
        if not self.enabled or self.db is None or self.model is None:
            rows = self._load_fallback_rows()
            ranked = sorted(rows, key=lambda row: self._fallback_score(row, task_query), reverse=True)
            results = [row for row in ranked if self._fallback_score(row, task_query) > 0][:k]
            if not results:
                results = ranked[:k]
            print(f"🔍 [VectorRAG] Fallback query returned {len(results)} matches for: {task_query[:30]}...")
            return results

        if self.table_name not in self.db.table_names():
            return []

        table = self.db.open_table(self.table_name)
        query_vector = self.model.encode([task_query])[0]

        results = table.search(query_vector).limit(k).to_list()

        print(f"🔍 [VectorRAG] Query returned {len(results)} matches for: {task_query[:30]}...")
        return results

    def format_for_prompt(self, results: List[Dict[str, Any]]) -> str:
        """
        將檢索結果格式化為 LLM 可讀的上下文塊。
        """
        if not results:
            return ""

        prompt_block = "\n### 🧬 歷史成功模式 (REUSED PATTERNS)\n"
        for i, res in enumerate(results):
            prompt_block += f"{i+1}. [模式] {res.get('task')}\n"
            if "resolution" in res:
                prompt_block += f"   [解法] {res.get('resolution')}\n"

        return prompt_block


if __name__ == "__main__":
    rag = VectorRAG()
    sample_data = [
        {"task": "Fix Python timezone bug", "resolution": "Use pytz.timezone('UTC')"},
        {"task": "Implement React Glassmorphism", "resolution": "backdrop-filter: blur(10px)"},
    ]
    rag.update_index(sample_data)
    hits = rag.query("How to handle UTC times in Python?")
    print(rag.format_for_prompt(hits))
