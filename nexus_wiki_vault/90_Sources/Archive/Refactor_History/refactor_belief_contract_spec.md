---
status: realized
merged_to: nexus_wiki_vault/01_System/BeliefEngine
---
[DONE - ARCHIVED]
# 深化建議：BeliefEngine 與 Orchestrator 的通訊協定重構 (v25.5)

## 1. 現有摩擦點 (Architectural Friction)
目前的 `Orchestrator` 與 `BeliefEngine` 之間的互動屬於「淺模組」通訊，存在以下問題：
*   **邏輯洩露**：信心值更新邏輯（如失敗時降至 0.1）硬編碼在 `Orchestrator` 中，而非由 `BeliefEngine` 根據策略決定。
*   **參數脆弱**：`update_belief` 依賴多個原始類型的參數，缺乏結構化契約。
*   **初始化混亂**：`Orchestrator` 內部存在對 `MagicMock` 的顯式檢查與路徑初始化，違反了相依注入原則。

## 2. 重構方案：顯式信念契約 (The Belief Contract)

### 2.1 引入強類型事件 [DONE]
建議定義 `AuditOutcome` 資料類別，將審核結果封裝為不可變對象。

### 2.2 介面深化 (Module Deepening) [DONE]
*   **移除**：`BeliefEngine.update_belief(task_id, assumption, confidence, ...)`
*   **新增**：`BeliefEngine.process_audit_outcome(outcome: AuditOutcome)`
    *   **邏輯封裝**：內部的貝式信心更新、證據記錄與持久化邏輯應對外隱藏。
    *   **自主決策**：引擎應根據 `outcome` 自動計算信心增減幅度。

### 2.3 介面隔離 (Interface Segregation) [DONE]
建議定義 `BeliefGate` Protocol（或抽象類別），使 `Orchestrator` 僅依賴於抽象介面，從而徹底移除代碼中的 `MagicMock` 檢查邏輯。

## 3. 預期效益
*   **Locality**：信心計算邏輯集中於 `BeliefEngine`。
*   **Leverage**：`Orchestrator` 的介面更簡單，但背後獲得的治理能力更強。
*   **Testability**：可透過 Mock `BeliefGate` 輕鬆進行邊界測試，無需依賴實體檔案系統。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*
