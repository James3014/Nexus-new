# 📐 Context Scoring & TOON Compression
**[PHYSICAL_STATUS: SEMANTIC_PRUNING | ERROR_PRIORITY]**

## 1. 上下文衛生與壓縮
為了防止長任務中 LLM 產生「注意力漂移」，Nexus 實施強制的語義剪裁與對話熵減。

## ⚙️ 實體化壓縮規約
- **TOON 渲染器**: 
    - 根據 `aggression` 決定保留的步驟數量。
- **對話熵減 (De-Entropy)**: 
    - **失敗優先**: 絕對保留包含 `FAIL` 或 `ERROR` 的輪次，其餘輪次激進剪裁。
    - **效益**: 字元數減少 > 70%，顯著提升推理「信噪比」。
- **內容評分 (ContextScorer)**: 
    - 依據當前 P-X-D-R-A-C 階段自動調整檔案優先權權重。

## 2. 物理實體
- **控制器**: `nexus/core/context_compression.py` 與 `brain_de_entropy.py`。

---
**[Source: New Dimension Audit Batch D - 2026-04-20]**
