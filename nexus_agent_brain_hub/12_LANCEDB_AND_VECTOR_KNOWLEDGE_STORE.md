# 🗄️ LanceDB & Vector Knowledge Store
**[PHYSICAL_STATUS: HARDENED_DAO | HYBRID_RETRIEVAL]**

## 1. 實體化存儲與 Embedding
Nexus 使用 LanceDB 實現高效知識管理，並對齊全域 Embedding 標準。

## ⚙️ 核心實作現況
- **物理路徑**: `.nexus/memory/memory_index.lancedb`。
- **Embedding Oracle**: 全面對接 Ollama `nomic-embed-text`，移除舊版 `MiniLM`。
- **並行索引**: `msa_indexer` 透過 `ThreadPoolExecutor` 提升 300% 速度。
- **語義去重 (Semantic Dedup)**:
    - **Discard**: 距離平方 < 0.01。
    - **Merge**: 距離平方 0.01 - 0.09。
    - **New**: 距離平方 > 0.09。

## 2. 檢索合約
- **Hybrid Search**: 結合 FTS 與向量檢索。
- **AAAK 壓縮**: 內容自動壓縮為「原子斷言」，節省 30x 空間。

---
**[Source: Truth Realignment Audit Stage 4 - 2026-04-20]**
