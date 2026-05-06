# Nexus 與 OpenSeeker-v2 技術融合重構規格 (v25.5)

## 1. 背景與目標
參考論文 [arXiv:2605.04036 (OpenSeeker-v2)](https://arxiv.org/abs/2605.04036)，將「高資訊密度軌跡」與「長鏈路推理穩定性」策略植入 Nexus，提升戰甲在複雜研究與深層診斷任務中的表現。

## 2. 核心重構策略

### 2.1 高難度軌跡過濾 (Low-step Filtering)
*   **模組**：`nexus/core/learning_steward.py`
*   **變更**：在 `decide()` 流程中加入軌跡長度檢查。
*   **規則**：新增 `MIN_EVOLUTION_STEPS = 10`。步數少於此閾值的任務，雖然執行成功但不允許「結晶」為長期記憶，避免低價值數據稀釋模型的深度搜尋能力。

### 2.2 多跳證據拼接 (Multi-hop Evidence Stitching)
*   **模組**：`nexus/engine/autoreason_service.py`
*   **變更**：升級 `CandidateFactory`。
*   **規則**：支援跨多個異構來源（如：GitHub Issue + Wiki + Local Code + OTel Log）的自動證據拼接，強制 Agent 在推理時建立多步關聯，而非僅依賴單一檢索結果。

### 2.3 信心感知的思考鏈 (Belief-Aware CoT)
*   **模組**：`nexus/services/prompt_builder.py` 與各 Skill 模板。
*   **變更**：在系統提示詞中強制要求「語義化狀態追蹤」。
*   **規則**：Agent 在生成 `Thought` 時，必須包含當前的 `Belief Confidence` (來自 BeliefEngine)。
    *   範例格式：`Thought: [Belief: 0.4] 偵測到 A/B 數據不一致，下一步將調用儀器工具進行探測。`

### 2.4 工具戰術關聯圖譜 (Tactical Tool Map)
*   **模組**：`nexus/engine/capability_router.py`
*   **變更**：從「工具清單」進化為「工具因果矩陣」。
*   **規則**：定義工具間的推薦序列（例如：`Diagnose` 失敗後優先推薦 `Research`），減少 AI 在長路徑搜尋中的隨機遊走現象。

## 3. 預期效益
*   **穩定性提升**：大幅降低長週期任務（超過 20 步）中的推理漂移風險。
*   **記憶品質**：確保結晶出的教訓（Lessons）皆具備高度的技術複雜度與參考價值。
*   **透明度**：實現「貝式治理」與「AI 思考過程」的深度對位。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*
