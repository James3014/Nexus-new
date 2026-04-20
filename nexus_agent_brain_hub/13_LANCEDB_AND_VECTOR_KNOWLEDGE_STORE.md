# 🗄️ LanceDB & Vector Knowledge Store

## 1. 物理存儲層
Nexus 使用 LanceDB 作為其向量數據庫的核心，存放全專案的向量化斷言 (Claims)。

## 2. 存儲 Schema 定義
- **`id`**: 原始碼路徑或物件 UUID。
- **`vector`**: 經由 Embedding 模型生成的特徵向量。
- **`content`**: 原始文本內容。
- **`metadata`**: 包含 `version_id`, `source_hash`, `ttl` (生命週期)。

## 3. RAG 實作細節
- **Hybrid Search**: 結合 BM25 關鍵字檢索與向量語義比對。
- **Relevance Reranking**: 使用專屬評分函數對檢索結果進行二次排序，過濾噪點。
- **Citation Enforce**: 任何從 LanceDB 提取的內容，在產出報告時必須標註引用 ID。

## 4. 維護策略
- **Incremental Write**: 每當 Git Commit 時，系統自動觸發增量寫入。
- **Local Fallback**: 即使 LanceDB 服務不可用，系統也能退回至傳統的「靜態文件檢索」模式。

---
**[Source: nexus_wiki_vault/02_Modules/Module - Memory Repository.md]**
