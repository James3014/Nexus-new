# Nexus Trinity Evolution: TDD TODO List

## Phase 1: Foundation (契約與基礎測試)
- [ ] **[RED]** 建立 `tests/test_contracts_v2.py`：驗證 `plan.json` 與 `autonomic_weights.json` 的新欄位讀寫。
- [ ] **[GREEN]** 修改 `nexus/core/state_contracts.py` 增加強化版 `NexusPlan` 與 `NexusWeights` 類別。
- [ ] **[REFACTOR]** 統一 `StateIO` 的落檔路徑，確保與 v9 藍圖一致。

## Phase 2: Intent Gate (意圖鎖定實作)
- [ ] **[RED]** 建立 `tests/test_intent_gate.py`：構造模糊任務情境（如：「幫我改一下代碼」），預期回傳 `RefusalError`。
- [ ] **[GREEN]** 實作 `nexus/engine/phases/planning.py` 中的 `IntentGuard`。
    - 實作語義檢查：檢查 `success_criteria` 數量與 `scope_boundary` 的具體性。
- [ ] **[REFACTOR]** 優化 P 階段的 `ask_user` 提示詞，使其更具備導引性。

## Phase 3: Coherence Filter (語義壓縮實作)
- [ ] **[RED]** 建立 `tests/test_context_coherence.py`：輸入含有大量冗餘日誌的 Context，驗證 TOON 視圖是否遺漏關鍵 Error。
- [ ] **[GREEN]** 修改 `nexus/core/context_hub.py`。
    - 實作 `ToonRenderer`：將 JSONL 歷史轉換為 Markdown 表格。
    - 實作 `ContextScorer`：依據當前 Phase 進行檔案相關性權重計算。
- [ ] **[REFACTOR]** 將 TOON 渲染邏輯抽離為獨立的 Utility 模組。

## Phase 4: Autonomic Learning (創傷驅動調權)
- [ ] **[RED]** 建立 `tests/test_trauma_weighting.py`：模擬重複失敗任務，驗證 `autonomic_weights.json` 的負向更新。
- [ ] **[GREEN]** 實作 `nexus/core/crystal_analyzer.py` 中的 `TraumaEngine`。
    - 計算 `learning_velocity`：公式 `(success_delta / time_window) - retry_penalty`。
    - 更新 `SkillsRouter` 決策表。
- [ ] **[REFACTOR]** 將權重更新邏輯接入 `ci_gate.py` 的後置處理。

## Phase 5: Integration & Verification (整合與驗證)
- [ ] **[SMOKE]** 執行 `scripts/ops/gate_ladder.sh` 確保基礎設施未壞。
- [ ] **[BENCHMARK]** 執行 `nexus:benchmark` 比較實作前後的 Token 消耗率（目標下降 50%）。
- [ ] **[DOCS]** 更新 `docs/SYSTEM_ARCHITECTURE_BLUEPRINT.md` 反映新的權重機制。

---
%% 
由 Muse-Core Orchestrator 依據 TDD 硬規則編寫。
%%
