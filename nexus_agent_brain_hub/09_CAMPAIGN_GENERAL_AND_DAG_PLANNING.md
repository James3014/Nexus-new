# 🗺️ Campaign General & DAG Planning

## 1. 史詩級任務調度 (Macro-Planning)
`CampaignGeneral` 負責將「模糊的宏觀意圖」轉化為「可執行的任務圖 (Directed Acyclic Graph, DAG)」。

## 2. 規劃邏輯
- **層級化拆解**: 宏觀目標 -> 戰役 (Campaign) -> 節點 (TaskNode)。
- **依賴管理**: 自動偵測節點間的檔案衝突與時序依賴。
- **神經銜接 (Neural Interface)**: 銜接 L4 的指揮層與 L3 的執行層。

## 3. 戰略封套 (Strategic Envelope)
隨附於每個任務節點，包含：
- **ReadOnly Files**: 被禁止修改的「真值檔案」。
- **Global Constraints**: 必須遵守的核心規約 (如 MUSE_PROTO)。
- **Upstream Artifacts**: 上游節點產出的關鍵憑證。

## 4. 韌性設計
- **Bursting Handling**: 當任一節點失敗，觸發全域中斷與證據保全。
- **Cycle Detection**: 強制檢測 DAG 中的循環依賴，防止任務死鎖。

---
**[Source: nexus_wiki_vault/02_Modules/Module - Task Scheduling and Swarm Adapters.md]**
