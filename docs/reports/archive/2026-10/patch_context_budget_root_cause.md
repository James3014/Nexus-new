# Patch Context Budget Root-Cause Verification Report

**Date**: 2026-06-16
**Status**: `CONFIRMED`
**Target Model**: Qwen2.5-Coder 14B Q3 (Local Ollama)

## 1. 取證結果 (Evidences)

### A. 實際 `num_ctx` 設定
- **來源**: `nexus/engine/local_model_policy.py`
- **設定值**: 14B 模型預設為 `8192` (受限於 16GB 系統記憶體)。
- **驗證**: `ollama_calls.log` 顯示所有 14B 請求皆帶有 `"num_ctx": 8192`。

### B. 失敗樣本統計 (Task 2: astropy-14182)
- **Prompt Token Count**: `8191`
- **Reserved Generation (num_predict)**: `3072`
- **Actual `eval_count` (output tokens)**: `1`
- **Done Reason**: `"length"`
- **Raw Response**: `"###"`
- **Parser Outcome**: `NO_BLOCKS_FOUND` (因輸出只有 3 個 # 號，無有效代碼塊)。

## 2. 根因判定 (Root-Cause Determination)

**判定結果**: `CONFIRMED` (Prompt Over Budget 為主因)

**詳細描述**:
14B 模型的 Context Window (8192) 被超長 Prompt (8191) 徹底填滿。在這種情況下，模型僅剩 1 個 token 的生成空間，導致推論立即因達到長度上限而終止。Parser 因為拿不到任何實體代碼，只能報錯 `NO_BLOCKS_FOUND`。

## 3. 偏差與風險
- **硬體限制**: 由於系統記憶體僅 16GB，將 14B 的 `num_ctx` 提高到 16384 會大幅增加 Swap 使用與 OOM 風險。
- **遺漏資訊**: 現有的 `PromptBuilder` 並未對「局部代碼擷取」後的總長度進行二次檢查或優先級排序，導致多個檔案合併後容易爆炸。

## 4. 修復行動 (Proposed Fixes)

### 階段 A：Prompt Slimming (優先)
1. **實作 Token Budget Gate**: 在 `PromptBuilder` 中加入長度預估邏輯。
2. **優先級裁切**: 
   - [P0] 修復策略 (Strategy) & 任務描述 (Task)
   - [P1] 重現證據 (Reproduction Evidence)
   - [P2] 檔案局部上下文 (Source Context) - 若過長，將優先裁切此部分。
3. **保留 Headroom**: 強制確保 Prompt + 緩衝區不超過 `num_ctx * 0.7` (例如 6000 tokens)，保留至少 2000 tokens 給 Patch 生成。

### 階段 B：可觀測性強化
1. 在 `receipt.json` 記錄 `prompt_trimmed` 旗標與裁切比例。
2. 若裁切後仍超標，主動拋出 `PROMPT_OVER_BUDGET` 而非由 Parser 報錯。

## 5. 決策請求
- 建議維持 14B 作為 Patch 主力，不進行 7B Fallback，改由 **Prompt Slimming** 解決問題。

## 6. Rerun 驗證紀錄 (2026-06-16)

- **狀態**: ✅ SUCCESS (Patch Lane Restored)
- **結果**: 
    - Task 2 (astropy-14182) 成功在 14B Q3 模型上生成了 SEARCH/REPLACE blocks。
    - Prompt Token Count 從原先的 8191 tokens 裁切至約 5800 tokens。
    - 留出了約 2400 tokens 的生成空間 (高於預設的 2048)。
    - LLM 成功產出了 298 tokens 的 Patch。
    - 雖然最終因 `SEARCH_MISMATCH` 失敗，但這屬於模型推論能力的限制，而非 Context Budget 導致的生成崩潰。
- **後續修正**: 在 Rerun 過程中發現並修正了 3 處 `NoneType` 潛在崩潰點（`patch_synthesis.py` 2 處，`orchestrator.py` 1 處）。
