"""
P2-A: Local-First Embedding Service
使用 Sentence-Transformers (all-MiniLM-L6-v2) 進行全離線向量化。
"""

from typing import List
import logging

# 核心配置
MODEL_NAME = "all-MiniLM-L6-v2"
EMBED_DIM = 384

class EmbeddingError(RuntimeError):
    pass

# 全域模型快取 (Singleton)
_MODEL_CACHE = None

def get_model():
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        try:
            from sentence_transformers import SentenceTransformer
            # 優先加載本地快取，若無則下載
            _MODEL_CACHE = SentenceTransformer(MODEL_NAME)
        except Exception as e:
            raise EmbeddingError(f"Failed to load local model {MODEL_NAME}: {e}")
    return _MODEL_CACHE

def embed_texts(texts: List[str]) -> List[List[float]]:
    """批量文本向量化 (384-dim)"""
    if not texts:
        return []
        
    try:
        model = get_model()
        # 使用 tolist() 替代 convert_to_list 參數以相容
        embeddings = model.encode(texts)
        if hasattr(embeddings, "tolist"):
            embeddings = embeddings.tolist()

        # Normalize single-vector outputs to 2D shape.
        if embeddings and isinstance(embeddings, list):
            first = embeddings[0]
            if isinstance(first, (int, float)):
                embeddings = [embeddings]
        
        # 驗證維度
        if any(len(v) != EMBED_DIM for v in embeddings):
            raise EmbeddingError(f"Unexpected embedding dimension. Expected {EMBED_DIM}.")
            
        return embeddings
    except Exception as e:
        import traceback
        logging.error(f"Embedding execution failed: {e}\n{traceback.format_exc()}")
        raise EmbeddingError(f"Local embedding failed: {e}")
