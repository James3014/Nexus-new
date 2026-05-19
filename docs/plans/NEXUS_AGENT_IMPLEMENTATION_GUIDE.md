# 🛠️ Nexus Agent 實作導引：全範式優化指南 (v26.5 專用)

> **致 Codex (GPT-5.5)：**
> 當你在優化 `CapabilityPlanner` 與 `ResearchFlow` 時，請嚴格遵守以下範式對位。本文件將 6 大研究論文轉化為 Nexus 內核的「代碼注入模式」。

---

## 🧩 1. 路由與成本：HL/HS + DCI 模式
**目標**：解決 1.13x Token 冗餘與 2.8x Wall-time 延遲。

### [實作模式：狀態驅動的車道摺疊]
*   **關鍵檔案**：`nexus/engine/capability_planner.py`
*   **對位邏輯 (HL/HS)**：
    *   **不要**：在 `plan()` 函式中寫死 `if task_type == 'repair'`。
    *   **要**：完善 `_decide_routing_tier`。讀取 `harness_preflight_sensor` 的 `risk_score` 與 `CodeIntel` 的 `blast_radius`。
    *   **代碼注入**：
        ```python
        # 當 DCI 顯示影響半徑 < 3 且 Sensor 顯示 simple_fix 時
        if signals.dci_blast_radius < 3 and signals.simple_hidden_bugfix:
            return "L0_micro_patch", "deterministic_logic_isolation"
        ```
*   **價值**：物理阻斷 `HyperSprint` 的啟動，消滅 150s 的 Swarm 同步開銷。

---

## 🛡️ 2. 驗證與自癒：ACH + Harness Engineering
**目標**：確保 100% Verified Delivery，杜絕「偽成功」。

### [實作模式：負向驗證門禁]
*   **關鍵檔案**：`nexus/engine/mutation_assurance.py`
*   **對位邏輯 (ACH)**：
    *   **動作**：在 `Audit (A)` 階段，調用 `mutation_assurance_required()`。
    *   **邏輯**：如果任務是 `public_claim` 且 `risk_score > 70`，自動觸發 `DeterministicMutant`。
    *   **門禁**：若生成的 `mutant` 沒被現有測試抓到（Survived），`Acceptance_Gate` 必須返回 `RETURN`。
*   **價值**：將「測試覆蓋率」提升為「測試殺傷力」，確保 Nexus 的誠信標籤不可質疑。

### [實作模式：感測器回饋]
*   **關鍵檔案**：`nexus/engine/harness_route_policy.py`
*   **對位邏輯 (Harness)**：
    *   **動作**：實作 `Semantic_Failure_Reflex`。
    *   **邏輯**：讀取 `semantic_failure_sensor` 產出的 `likely_fix`。如果是 `ImportError`，直接導向 `Local_Reflex` 進行補件，嚴禁再次呼叫 LLM。

---

## 📊 3. 數據與演化：Autodata + RubricEM
**目標**：建立 v27 自我演化閉環。

### [實作模式：高品質資料回灌]
*   **關鍵檔案**：`scripts/bench/capability_ab_runner.py`
*   **對位邏輯 (Autodata)**：
    *   **門檻**：只有滿足 `Strong-Weak Gap > 20%` 且 `PPI <= 1.02` 的 row 才能標記為 `training_eligible`。
    *   **動作**：將 `model_attempts[]` 中的「黃金軌跡（Golden Trace）」導出為 JSONL。
*   **對位邏輯 (RubricEM)**：
    *   **評分**：使用 `LLMJudgeProvider` 進行「解釋性指標」評分。分值必須包含 `fidelity` (忠誠度) 與 `ROI` (成本比)。

---

## 🚀 針對目前「R/hyper 瓶頸」的緊急指令
1.  **檢查 `executor_init_sec`**：若佔比超過 30%，立即在 `capability_planner.py` 中鎖定 `NEXUS_FORCE_INPLACE_EXECUTOR=1`。
2.  **執行 `Prompt Dehydration`**：檢查 `_build_llm_candidate_prompt`。若 `is_bare_first=True`，物理移除 `You are executing Stage 1...` 的儀式性文案。
3.  **封印 `Token Ledger`**：確保 `usageMetadata` 擁有絕對優先權，禁止使用 `estimated` 數據進行 A/B 判定。

---
**[NEXUS AGENT MISSION DIRECTIVE | SEALED BY GEMINI]**
**[FOR CODEX/GPT-5.5 REFERENCE DURING P84-P96]**
