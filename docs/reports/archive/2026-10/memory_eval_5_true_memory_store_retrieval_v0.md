# MEMORY-EVAL-5 True Memory Store Retrieval Report

## 1. 任務與目標
MEMORY-EVAL-5 的核心目標是移除 MEMORY-EVAL-4B 的 eval stub 依賴，證明在沒有 stub 注入的情境下，真實的 Nexus memory store 能夠在 runtime 中為 `C_12481` 提供真實的 lesson 檢索，並使 `memory_section_included = true` 與 `trace_status = TRACE_AVAILABLE`。

---

## 2. 修復方案與 seeding 實現
我們採取了以下步驟打通真實檢索：
1. **移除 eval stub**：
   - 移除了 `MemoryRetrievalAdapter` 在 `nexus_memory_on` arm 下手動 append mock `RetrievedLesson` 的 Options B 代碼。
2. **Seeding 真實記憶卡 (MEMORY-SEED-0)**：
   - 撰寫 `scripts/learning/seed_memory_eval_5.py`，利用 `FindingsMemoryStore` API 將針對 `C_12481` 的 `FindingsCard` 寫入至 `.nexus/memory/task/episodes/C_12481_lh-12481.json`。
   - 該 card 的 title, tags, retrieval_hints 中明確包含 `"test"`, `"repair"` 等關鍵字以對位 runtime 的 query，並提供 `receipt:C_12481` 作為 `provenance`。

---

## 3. 驗收結果
我們重新運行了 comparison，在 `artifacts/runtime/memory_eval_5_true_memory_store_retrieval_v0/` 下產生了 22/22 live_runtime 檔案。

驗收數據結果：
- **`nexus_memory_on`**:
  - `prompt_memory_section_included`: `True`
  - `memory_trace_status`: `TRACE_AVAILABLE`
  - `retrieved_count`: `1`
  - `selected_ids`: `["lh-12481"]` (非 stub ID，而是真實 seeding 的 lesson ID)
  - `retrieval_sources`: `["FindingsMemoryLessonStore"]` (來自真實的 Findings Store)
  - `arm_result_arm`: `nexus_memory_on`
- **`nexus_memory_off`**:
  - `prompt_memory_section_included`: `False`
  - `memory_trace_status`: `TRACE_MISSING`
  - `retrieved_count`: `0`
  - `arm_result_arm`: `nexus_memory_off`

`validation.json` 驗證一致，顯示 `MEMORY_EVAL_5_TRUE_MEMORY_STORE_RETRIEVAL_COMPLETE`。

---

## 4. 關鍵限制與邊界 (Constraints & Boundaries)
- **真實檢索限制與宣告**：
  - 本次運行證明了真實記憶體檢索成功被觸發（`retrieval_observed = true`）。
  - 本次運行 **未證明** 解題成功率或結果有所提升（`outcome_uplift_observed = false`、`memory_helped_outcome = false`）。
- **指標禁止與宣告**：
  - `memory_uplift` 宣稱仍為 **disallowed**。
  - `production_ready` = `false`。
  - `training_export_allowed` = `false`。
  - `public_claim_allowed` = `false`。
