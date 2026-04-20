#!/usr/bin/env python3
from pathlib import Path
from typing import Any, Dict, List
import json

try:
    import lancedb  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    lancedb = None

import pandas as pd

import logging
import urllib.request
from nexus.core.config import NexusGlobalConfig

logger = logging.getLogger("nexus.vector_rag")
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
        self.enabled = lancedb is not None

        if self.enabled:
            self.db = lancedb.connect(str(self.db_path))
            logger.info("🔮 [VectorRAG] Connecting to local LanceDB and using Ollama embeddings...")
        else:
            self._ensure_fallback_file()
            logger.warning("⚠️ [VectorRAG] Running in JSON fallback mode; LanceDB unavailable.")

    def _get_embedding(self, text: str) -> List[float]:
        try:
            req = urllib.request.Request(
                f"{NexusGlobalConfig.OLLAMA_ENDPOINT}/api/embeddings",
                data=json.dumps({"model": NexusGlobalConfig.OLLAMA_EMBED_MODEL, "prompt": text}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5.0) as response:
                result = json.loads(response.read())
                return result.get("embedding", [])
        except Exception as e:
            logger.error(f"🔮 [VectorRAG] Ollama embedding failed ({NexusGlobalConfig.OLLAMA_EMBED_MODEL}): {e}")
            return []

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

        logger.info(f"🚀 [VectorRAG] Indexing {len(knowledge_data)} items...")

        if not self.enabled or self.db is None:
            rows = self._load_fallback_rows()
            rows.extend(knowledge_data)
            self._save_fallback_rows(rows)
            logger.info(f"✅ [VectorRAG] Fallback index updated. Total items: {len(rows)}")
            return

        df = pd.DataFrame(knowledge_data)
        texts = df["task"].tolist()
        # Use Ollama
        embeddings = [self._get_embedding(t) for t in texts]
        # fallback for empty
        for i in range(len(embeddings)):
            if not embeddings[i]: embeddings[i] = [0.0]*768

        df["vector"] = embeddings.tolist()

        if self.table_name in self.db.list_tables():
            table = self.db.open_table(self.table_name)
            table.add(df)
        else:
            self.db.create_table(self.table_name, data=df)

        logger.info(f"✅ [VectorRAG] Index Updated. Total items: {len(self.db.open_table(self.table_name))}")

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
        if not self.enabled or self.db is None:
            rows = self._load_fallback_rows()
            ranked = sorted(rows, key=lambda row: self._fallback_score(row, task_query), reverse=True)
            results = [row for row in ranked if self._fallback_score(row, task_query) > 0][:k]
            if not results:
                results = ranked[:k]
            logger.info(f"🔍 [VectorRAG] Fallback query returned {len(results)} matches for: {task_query[:30]}...")
            return results

        if self.table_name not in self.db.list_tables():
            return []

        table = self.db.open_table(self.table_name)
        query_vector = self._get_embedding(task_query)
        if not query_vector: query_vector = [0.0]*768

        results = table.search(query_vector).limit(k).to_list()

        logger.info(f"🔍 [VectorRAG] Query returned {len(results)} matches for: {task_query[:30]}...")
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

