# 🧬 Task Lineage & DAG Provenance
**[PHYSICAL_STATUS: DAG_INTERNALIZED | TRACEABILITY_HIGH]**

## 1. 任務譜系與因果溯源
Nexus 的溯源能力深度整合在 `CampaignGeneral` 的任務圖 (DAG) 邏輯中，非獨立組件。

## ⚙️ 實體化溯源規約
- **TaskNode 結構**: 
    - **Dependencies**: 紀錄任務間的物理依賴路徑。
    - **Impact Files**: 鎖定該節點允許修改的「物理邊界」。
    - **Belief Confidence**: 隨執行結果動態衰減或增加。
- **譜系追蹤 (Lineage)**: 
    - 透過 `traceid` (UUID) 貫穿全過程。
    - 所有的變更均可溯源至最初的「宏觀意圖 (Macro Intent)」。

## 2. 物理證據
- **`evolve_trace.log`**: 紀錄 DAG 執行的物理軌跡。
- **`tracelog_governance_hardening.jsonl`**: 紀錄治理硬化階段的邏輯判斷。

---
**[Source: New Dimension Audit Batch B - 2026-04-20]**
