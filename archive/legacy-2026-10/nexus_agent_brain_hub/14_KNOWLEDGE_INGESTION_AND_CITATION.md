# 📚 Knowledge Ingestion & Citation Lineage
**[PHYSICAL_STATUS: CLAIM_VERIFIED | CITATION_ENFORCED]**

## 1. 知識攝取與引證溯源
Nexus 嚴禁「憑空引用」。所有的知識點 (Claims) 必須具備物理來源。

## ⚙️ 實體化引證規約
- **攝取管線 (Ingestion)**: 
    - 將外部文檔分割為「原子斷言」。
    - **Metadata**: 強制攜帶 `source_url` 與 `ingest_time`。
- **精準引證 (Citation)**: 
    - Agent 必須標註 `[Source: {id}]`。
    - **核驗**: `verify_report_claims.py` 自動比對 LanceDB。
- **AAAK 提煉**: 
    - `memory_repository.py` 實作了 LLM 原生提煉與 Regex 雙通道壓縮，達成 30x 語義提煉。

## 2. 物理與認知對位
- **漂移偵測**: 透過 Hash 對位，確保原始碼修改後引用自動失效。

---
**[Source: New Dimension Audit Batch C - 2026-04-20]**
