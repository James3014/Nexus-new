# 🗺️ Campaign General & DAG Planning
**[PHYSICAL_STATUS: LLM_ENABLED | DYNAMIC_DECOMPOSITION]**

## 1. 史詩級任務拆解 (Macro-Planning)
`CampaignGeneral` 負責將「模糊意圖」轉化為「可執行的任務圖 (DAG)」。

## 2. 實體化拆解規約
- **LLM 賦能**: 已正式接線 Ollama (`/api/generate`)，透過語言理解生成 3-5 步的高精準度任務節點。
- **Heuristic Fallback**: 只有在 LLM 無法連線時，才退化至關鍵字匹配模式。
- **戰略封套 (Strategic Envelope)**: 傳遞 `ReadOnly Files`、`Global Constraints` 與上游憑證至執行層。

## 3. 任務節點 (TaskNode) 結構
- **Dependencies**: 紀錄任務間的物理依賴。
- **Impact Files**: 鎖定該節點允許修改的物理邊界。
- **Belief Confidence**: 隨執行結果動態衰減或增加的信任分。

## 4. 韌性設計
- **Bursting**: 當任務複雜度溢出時，自動分裂子任務。
- **Cycle Detection**: 強制檢測 DAG 循環，防止邏輯死鎖。

---
**[Source: nexus_wiki_vault/02_Modules/Module - Task Scheduling and Swarm Adapters.md]**
