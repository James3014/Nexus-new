# MEMORY-EVAL-7 Task-Specific Memory Retrieval Precision Report

## 1. 任務與目標
MEMORY-EVAL-7 的核心目標是解決 MEMORY-EVAL-6 中暴露的「檢索真實但混撈」的問題，將記憶體檢索從「真實但無差別檢索」推進到「Task-Specific Precision (任務精準檢索)」。我們實施了通用的 `task_id-aware ranking` 機制，確保不同任務的 `nexus_memory_on` 運行時，其對應的真實記憶卡能夠最優先被選取。

---

## 2. 實作方案：通用 Task-ID 權重評分
我們在 `MemoryRetrievalAdapter` 及 `HealOrchestrator` 中引入了通用的 `task_id-aware scoring boost` 機制：
1. **傳遞 Task ID**：在 `orchestrator.py` 的記憶體追蹤綁定步驟中，將目前修復運行的 `ctx.op.instance_id` (即 `task_id`) 傳給 `MemoryRetrievalAdapter.retrieve_reranked`。
2. **優化 Rerank 評分**：
   - 擴展 `RetrievedLesson` 結構，新增並填充其 `task_id` 屬性。
   - 在 `retrieve_reranked()` 方法的排序評估中，若發現該 lesson 的 `task_id` 與目前運行的 `task_id` 在大小寫與特殊符號正規化後（`normalize_id`）一致，則額外給予大額的分數 boost (`+10.0`)。
3. **優點**：此方案完全通用，不包含任何針對特例 `C_12481` 或 `C_13453` 的硬編碼，具有完全的擴展性。

---

## 3. 驗收結果
我們對 44 個實體 `live_runtime` 標記的 JSON artifacts 進行了掃描與驗證，結果如下：

### C_12481 / nexus_memory_on
- **`memory_trace_status`**: `TRACE_AVAILABLE`
- **`retrieved_count`**: `2`
- **`selected_ids`**: `["lh-12481", "lh-13453"]`
- **`primary_selected_id`**: `"lh-12481"` (成功將本任務對應的記憶卡排在首位！)

### C_13453 / nexus_memory_on
- **`memory_trace_status`**: `TRACE_AVAILABLE`
- **`retrieved_count`**: `2`
- **`selected_ids`**: `["lh-13453", "lh-12481"]`
- **`primary_selected_id`**: `"lh-13453"` (成功將本任務對應的記憶卡排在首位！)

### 對照組 nexus_memory_off
- 兩個任務的 `nexus_memory_off` 均穩定關閉檢索：
  - `memory_trace_status`: `TRACE_MISSING` / `NOT_USED`
  - `retrieved_count`: `0`

與 `validation.json` 及 `memory_impact_comparison.json` 保持 100% 一致。

---

## 4. 關鍵限制與邊界 (Constraints & Boundaries)
- **True retrieval already proven in MEMORY-EVAL-6**：MEMORY-EVAL-6 已證實能從 FindingsMemoryLessonStore 讀取真實資料。
- **MEMORY-EVAL-7 proves task-specific retrieval precision**：本階段已成功證實任務精準對照檢索。
- **Outcome uplift remains not proven**：雖然檢索精準度提升，但並未觀察到解題成功率提升（`outcome_uplift_observed = false`、`memory_helped_outcome = false`）。
- **指標禁止與宣告**：
  - `memory_uplift` 宣稱仍為 **disallowed**。
  - `production_ready` = `false`。
  - `training_export_allowed` = `false`。
  - `public_claim_allowed` = `false`。
  - `internal_only` = `true`。
