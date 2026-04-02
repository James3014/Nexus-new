from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
#!/usr/bin/env python3
import lancedb
import pandas as pd
import os
from sentence_transformers import SentenceTransformer

class VectorRAG:
    """
    🔮 Nexus VectorRAG (Phase 10.2)
    職責: 執行高效能向量檢索，為 Planner 提供歷史經驗上下文。
    對齊 P10.2 實施標準 (Top-K=5)。
    """
    
    def __init__(self, db_path=".nexus/vector_db"):
        self.project_root = Path(__file__).resolve().parents[2]
        self.db_path = self.project_root / db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. 建立 LanceDB 連接
        self.db = lancedb.connect(self.db_path)
        self.table_name = "nexus_knowledge"
        
        # 2. 載入本機嵌入模型 (all-MiniLM-L6-v2)
        print("🔮 [VectorRAG] Loading Embedding Model: all-MiniLM-L6-v2...")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')

    def update_index(self, knowledge_data: List[Dict[str, Any]]):
        """
        將知識庫數據（解密後）執行向量化並存入 LanceDB。
        """
        if not knowledge_data: return
        
        print(f"🚀 [VectorRAG] Indexing {len(knowledge_data)} items...")
        
        # 預處理數據：生成向量
        df = pd.DataFrame(knowledge_data)
        # 假設 knowledge_data 包含 'content' 或 'task'
        texts = df['task'].tolist()
        embeddings = self.model.encode(texts)
        
        df['vector'] = embeddings.tolist()
        
        # 寫入或更新表
        if self.table_name in self.db.table_names():
            table = self.db.open_table(self.table_name)
            table.add(df)
        else:
            self.db.create_table(self.table_name, data=df)
            
        print(f"✅ [VectorRAG] Index Updated. Total items: {len(self.db.open_table(self.table_name))}")

    def query(self, task_query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        執行語義搜索，返回 Top-K 匹配模式。
        """
        if self.table_name not in self.db.table_names():
            return []
            
        table = self.db.open_table(self.table_name)
        query_vector = self.model.encode([task_query])[0]
        
        # 執行向量搜索 (Cosine Similarity)
        results = table.search(query_vector).limit(k).to_list()
        
        print(f"🔍 [VectorRAG] Query returned {len(results)} matches for: {task_query[:30]}...")
        return results

    def format_for_prompt(self, results: List[Dict[str, Any]]) -> str:
        """
        將檢索結果格式化為 LLM 可讀的上下文塊。
        """
        if not results: return ""
        
        prompt_block = "\n### 🧬 歷史成功模式 (REUSED PATTERNS)\n"
        for i, res in enumerate(results):
            prompt_block += f"{i+1}. [模式] {res.get('task')}\n"
            if 'resolution' in res:
                prompt_block += f"   [解法] {res.get('resolution')}\n"
        
        return prompt_block

if __name__ == "__main__":
    # 簡單冒煙測試
    rag = VectorRAG()
    sample_data = [
        {"task": "Fix Python timezone bug", "resolution": "Use pytz.timezone('UTC')"},
        {"task": "Implement React Glassmorphism", "resolution": "backdrop-filter: blur(10px)"}
    ]
    rag.update_index(sample_data)
    hits = rag.query("How to handle UTC times in Python?")
    print(rag.format_for_prompt(hits))
