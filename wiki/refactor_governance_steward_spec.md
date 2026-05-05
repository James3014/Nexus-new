# 深化建議：LearningSteward 治理模式重構規格 (v25.5)

## 1. 目標
將分散的治理邏輯整合為一個具備深度的「治理管理模組」，確保決策的一致性與局部性。

## 2. 重構要點

### 2.1 角色定義：LearningSteward
*   **輸入**：`NexusState` 與執行產出的證據 (Evidence)。
*   **職責**：
    1. 調用評分器計算 `Curiosity Score`。
    2. 檢查物理證據 (Physical Proof)。
    3. 發布最終的「學習決策」：`INGEST`（吸收）、`FREEZE`（凍結）或 `DISCARD`（捨棄）。
*   **輸出**：`LearningDecision` 物件。

### 2.2 移除執行邏輯洩露
*   `PolicyManager` 不應直接讀取 `sir_veto_learning`。
*   這些外部訊號應由 `LearningSteward` 統一評估後，僅回傳一個最終的執行指令。

### 2.3 權重動態化
*   `LearningSteward` 在計算分數時，應從 `GovernanceProfile` 讀取 `ALPHA/BETA/GAMMA` 參數，而非使用類別常數。

## 3. 預期效益
*   **決策一致性**：所有的「學習守衛」邏輯都集中在一處，易於審核。
*   **維護性**：調整治理強度只需更換 Profile，無需修改引擎核心代碼。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*
