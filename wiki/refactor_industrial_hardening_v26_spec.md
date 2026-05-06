# Nexus 工業化硬化 2.0 重構規格 (v26.0 預備)

## 1. 背景與目標
在 v25.5 完成「插件組合模式」轉型後，後續審計發現雖然結構已解耦，但「數據通訊」仍存在淺層依賴與狀態污染風險。本規格旨在透過「強介面封裝」與「不可變黑板」實現 Nexus 架構的極限嚴謹度。

## 2. 核心重構組件

### 2.1 不可變黑板模式 (Immutable Blackboard)
*   **目標**：徹底杜絕《治理執行協定》中禁止的「歷史修改」行為。
*   **重構內容**：
    *   廢除 `run(state, context: Dict)` 中的原生字典傳遞。
    *   實作 `nexus.core.blackboard.Blackboard` 類別。
    *   **API 規範**：
        *   `append(phase: str, key: str, value: Any)`: 僅允許追加。
        *   `view(phase_filter: Optional[str] = None) -> ReadOnlyDict`: 僅提供唯讀視圖。
*   **效益**：實現 100% 的真相追溯 (Provenance)，任何數據變動皆有跡可循。

### 2.2 階段工廠模式 (Phase Factory)
*   **目標**：解決 `PhaseHandler` 建構子臃腫（Wide Interface）問題。
*   **重構內容**：
    *   建立 `PhaseFactory` 類別，封裝所有 Default Providers 的實例化邏輯。
    *   **Orchestrator 調用簡化**：
        *   舊：`PlannerPhaseHandler(root, run_dir, predictor=Predictor(), intent=DefaultIntent()...)`
        *   新：`factory.create_phase("P")`
*   **效益**：提升模組深度 (Depth)，使駕駛員（Orchestrator）不再需要瞭解底層供應商的配置細節。

### 2.3 語義握手協定 (Semantic Handshake)
*   **目標**：消除跨階段的「隱性依賴」，實現 Fail-Fast。
*   **重構內容**：
    *   在 `BasePhaseHandler` 加入 `required_artifacts()` 宣告方法。
    *   **邏輯**：在 Pipeline 啟動前，框架自動掃描 Blackboard，驗證 `RepairPhase` 所需的 `impact_map` 是否已被 `PlannerPhase` 正式簽名產出。
*   **效益**：將「邏輯漂移」錯誤攔截在執行之前，增強系統韌性。

## 3. 預期演化成果
*   **架構純淨度**：徹底消滅「隱形狀態流」。
*   **開發摩擦力降低**：雖然介面變嚴謹，但透過 Factory 簡化了組裝難度。
*   **工業化指標**：實現「零副作用、強契約、高槓桿」的終極戰甲形態。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*
