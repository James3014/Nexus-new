# L3-C: EvoEmbedding Real sentence-transformers

**Status**: L3_C_REAL_EVO_EMBEDDING_PASS

## Files changed
- `nexus/knowledge/evo_embedding_index.py` — 新增 `RealEvoEmbeddingIndex` class、`_cosine_similarity()`、`_encode()`；`NEXUS_EMBEDDING_MODEL` env gate
- `tests/knowledge/test_evo_embedding_index.py` — 新增 5 個 L3-C 測試

## Test counts
- 5 new (L3-C) + 5 existing = 10 total PASS

## Changes
1. `RealEvoEmbeddingIndex(EvoEmbeddingIndex)` — `NEXUS_EMBEDDING_MODEL` 有值時用 sentence-transformers 做真實 embedding
2. `_cosine_similarity` — 支援 cosine similarity（取代 Jaccard）
3. `_encode` — lazy load SentenceTransformer，normalize_embeddings=True
4. 錯誤處理: 模型載入失敗或 encode 失敗 → fallback 到父類 Jaccard

## Activation env vars
- `NEXUS_EMBEDDING_MODEL=all-MiniLM-L6-v2` — 啟用真實 embedding 模型

## Governance boundary
- `_model_available=False` 時 query/add 走父類 Jaccard path
- `_embedding_store` 與 `_store` 同步 maintained
