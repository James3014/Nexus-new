# MEMORY-EVAL-6 Multi-Task True Memory Retrieval Report

## 1. 任務與目標
MEMORY-EVAL-6 的目標是擴展真實檢索評估樣本，一併對 `C_12481` 與 `C_13453` 兩個任務執行 `nexus_memory_on` 與 `nexus_memory_off` arms 的對照評估，藉此驗證真實 memory store（FindingsMemoryLessonStore）在多任務情境下的檢索可靠性，並徹底移除任何對 stub 的依賴。

---

## 2. 實作與 Seeding 方案
為了解決 evaluation 環境無預載資料的問題，我們建立了真實 `seeding` 流程：
1. **Seeding 真實記憶卡 (MEMORY-SEED-0)**：
   - 撰寫 `scripts/learning/seed_memory_eval_6.py`，利用 `FindingsMemoryStore` API 將真實記憶卡寫入至 `.nexus/memory/task/episodes/` 下，檔名分別為：
     - `C_12481_lh-12481.json` (lesson_id="lh-12481", provenance="receipt:C_12481")
     - `C_13453_lh-13453.json` (lesson_id="lh-13453", provenance="receipt:C_13453")
   - 這兩筆 card 均配置了符合 Rerun query 的關鍵字以實現自然對位檢索。
2. **Rerun 編排**：
   - 執行 `scratch/run_rerun.py` 產生這 4 個 task-arm pairs 的實體運行檔，共產出 44 個 live_runtime 標記的 JSON artifacts。

---

## 3. 驗收結果
我們重新驗證了產出的 44 個 JSON 檔，兩邊的對照指標如下：

### C_12481
- **`nexus_memory_on`**:
  - `prompt_memory_section_included`: `True`
  - `memory_trace_status`: `TRACE_AVAILABLE`
  - `retrieved_count`: `1`
  - `selected_ids`: `["lh-12481"]` (真實 seeding ID，無 stub)
  - `retrieval_sources`: `["FindingsMemoryLessonStore"]` (真實 store)
- **`nexus_memory_off`**:
  - `prompt_memory_section_included`: `False`
  - `memory_trace_status`: `TRACE_MISSING`
  - `retrieved_count`: `0`

### C_13453
- **`nexus_memory_on`**:
  - `prompt_memory_section_included`: `True`
  - `memory_trace_status`: `TRACE_AVAILABLE`
  - `retrieved_count`: `1`
  - `selected_ids`: `["lh-13453"]` (真實 seeding ID，無 stub)
  - `retrieval_sources`: `["FindingsMemoryLessonStore"]` (真實 store)
- **`nexus_memory_off`**:
  - `prompt_memory_section_included`: `False`
  - `memory_trace_status`: `TRACE_MISSING`
  - `retrieved_count`: `0`

`validation.json` 與實體 artifacts 完全一致。

---

## 4. 關鍵限制與邊界 (Constraints & Boundaries)
- **真實檢索限制與宣告**：
  - 本次運行證明了真實多任務記憶體檢索成功被觸發（`retrieval_observed = true`）。
  - 本次運行 **未證明** 解題成功率或結果有所提升（`outcome_uplift_observed = false`、`memory_helped_outcome = false`）。
- **指標禁止與宣告**：
  - `memory_uplift` 宣稱仍為 **disallowed**。
  - `production_ready` = `false`。
  - `training_export_allowed` = `false`。
  - `public_claim_allowed` = `false`。
