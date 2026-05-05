# Nexus 治理與事件系統架構診斷報告 (v25.5)

## 1. 核心問題診斷

### 1.1 事件系統的「淺模組」問題 (Shallow Event Bus)
*   `nexus/core/event_bus.py` 僅作為底層傳輸的相容介面 (Facade)，缺乏領域語義封裝。
*   後果：Core 邏輯必須處理原始事件的 JSON 結構，當通訊協定變更時，修改範圍會波及整個系統。

### 1.2 治理邏輯分散 (Logic Fragmentation)
*   學習決策（LearningGovernance）與學習執行（PolicyManager）分離。
*   後果：決策路徑難以追蹤，關於「是否凍結學習」與「是否吸收經驗」的判斷散落在不同類別中。

### 1.3 硬編碼的治理規則 (Hardcoded Guardrails)
*   好奇心分數 (Curiosity Score) 的權重與檢查規則被硬編碼在引擎中。
*   後果：系統缺乏彈性，難以針對不同的專案環境或學習目標調整治理強度。

## 2. 改進建議

### 建議一：建立語義化領域事件匯流排 (Domain Event Bus)
*   **目標**：隱藏底層傳輸細節，提供具備領域意義的方法。
*   **方案**：在 `event_bus.py` 中定義顯式的通知方法（如 `emit_audit_failure`），而非通用的 `publish`。

### 建議二：統一學習狀態機 (Learning Steward)
*   **目標**：整合治理決策與執行。
*   **方案**：建立 `LearningSteward` 模組，作為處理執行證據、計分並決定最終學習動作的單一入口。

### 建議三：抽象化治理配置文件 (Policy Profiles)
*   **目標**：解耦治理引擎與治理規則。
*   **方案**：透過 `GovernanceProfile` 接口傳入好奇心權重與物理證據檢查規範。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*
