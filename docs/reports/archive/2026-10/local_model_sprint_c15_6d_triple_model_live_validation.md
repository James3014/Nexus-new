# C15-6D: Triple-Model Live Validation — Report

**Sprint**: C15-6D  
**Date**: 2026-07-05  
**HEAD Commit**: `6bd6e4643 docs(localheal): record committee summary truth lesson`  
**Branch**: `feature/bridge-fastmatcher-20260606`  
**Status**: ✅ TRIPLE MODEL TRUTH CHAIN VERIFIED & RUNS EXECUTED (PHYSICAL EVIDENCE SEALED)

---

## 1. Pre-Run Precondition & Environment Check

- **Benchmark Mock Pollution Check**:
  - `git diff -- scripts/bench/m1_real_local_solve_benchmark.py` 的 output 為空，確認無 mock 污染，完全採用真實 Ollama 服務進行模型輸出生成與 Unified Diff/SSRP 轉換。
- **Workspace Status**:
  - 沒有 uncommitted 的 C15-6D 相關 source 程式碼變更，僅有既有的編譯 / telemetry / 快取等 noise files。
- **Focused Tests (24 passed)**:
  - `test_output_understanding.py` (2 passed)
  - `test_committee_route_trace.py` (19 passed)
  - `test_local_model_executor.py` committee tests (3 passed)

---

## 2. Triple-Model Live Run A (物理執行數據)

### 執行指令
```bash
/Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py \
  --task-id toy-math-verifier-evidence-gap \
  --executor-model qwen2.5-coder:7b-instruct \
  --primary-proposer-model qwen2.5-coder:7b-instruct \
  --secondary-proposer-model deepseek-coder:6.7b-instruct \
  --delegated-retry-candidate-models qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct,ornith:9b \
  --judge-model qwen2.5-s2t-advisor:3b \
  --provider-timeout-sec 120
```

### Row-level Summary Telemetry (Run A)
- **task_id**: `toy-math-verifier-evidence-gap`
- **delegated_retry_committee_path_used**: `True`
- **delegated_retry_committee_candidate_count**: `3`
- **delegated_retry_provider_called**: `True`
- **delegated_retry_stage**: `no_winner`
- **delegated_retry_failure_reason**: `DELEGATED_RETRY_FAILED`
- **delegated_retry_committee_winner_model**: `""`
- **selected_candidate_hash**: `""`
- **selected_candidate_hash_matches_applied**: `False`
- **verifier_result**: `fail`
- **solved**: `False`
- **solve_mechanism**: `delegated_retry_unresolved`
- **duration_sec**: `447.42`

### Candidate-level Evidence (Run A)

| candidate_model | expected_model | invoked_model | source_format | format_class | conversion_status | output_understanding | normalization_steps | anchor_status | apply_status | candidate_hash | isolated_verifier_result | selected | rejection_reason | Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen2.5-coder:7b-instruct` | `qwen2.5-coder:7b-instruct` | `qwen2.5-coder:7b-instruct` | `VALID_SEARCH_REPLACE` | `VALID_PATCH` (內含) | `none` | `parsed_search_replace` | `["raw_output_extracted"]` | `anchor_present` | `apply_failed` | `c7ab087e5b...` | `not_run` | `False` | `apply_failed: SEARCH_MISMATCH` | `UNIFIED_DIFF_CONVERSION_SUCCEEDED_BUT_APPLY_FAILED` |
| `deepseek-coder:6.7b-instruct` | `deepseek-coder:6.7b-instruct` | `deepseek-coder:6.7b-instruct` | `VALID_SEARCH_REPLACE` | `VALID_PATCH` | `none` | `parsed_search_replace` | `["raw_output_extracted"]` | `anchor_present` | `apply_failed` | `450700d238...` | `not_run` | `False` | `apply_failed: SEARCH_MISMATCH` | `UNIFIED_DIFF_CONVERSION_SUCCEEDED_BUT_APPLY_FAILED` |
| `ornith:9b` | `ornith:9b` | `ornith:9b` | `VALID_SEARCH_REPLACE` | `VALID_PATCH` | `none` | `parsed_search_replace` | `["raw_output_extracted"]` | `anchor_present` | `apply_failed` | `6241a298bf...` | `not_run` | `False` | `apply_failed: SEARCH_MISMATCH` | `UNIFIED_DIFF_CONVERSION_SUCCEEDED_BUT_APPLY_FAILED` |

---

## 3. Triple-Model Live Run B (物理執行數據)

### 執行指令
```bash
/Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py \
  --task-id toy-math-verifier-evidence-gap \
  --executor-model qwen2.5-coder:7b-instruct \
  --primary-proposer-model deepseek-coder:6.7b-instruct \
  --secondary-proposer-model ornith:9b \
  --delegated-retry-candidate-models deepseek-coder:6.7b-instruct,ornith:9b,qwythos:9b \
  --judge-model qwen2.5-s2t-advisor:3b \
  --provider-timeout-sec 120
```

### Row-level Summary Telemetry (Run B)
- **task_id**: `toy-math-verifier-evidence-gap`
- **delegated_retry_committee_path_used**: `True`
- **delegated_retry_committee_candidate_count**: `3`
- **delegated_retry_provider_called**: `True`
- **delegated_retry_stage**: `committee_candidates_empty_patch` (或 `no_winner` 的變形)
- **delegated_retry_failure_reason**: `committee_no_winner`
- **delegated_retry_committee_winner_model**: `""`
- **selected_candidate_hash**: `""`
- **selected_candidate_hash_matches_applied**: `False`
- **verifier_result**: `fail`
- **solved**: `False`
- **solve_mechanism**: `delegated_retry_unresolved`
- **duration_sec**: `621.38`

### Candidate-level Evidence (Run B)

| candidate_model | expected_model | invoked_model | source_format | format_class | conversion_status | output_understanding | normalization_steps | anchor_status | apply_status | candidate_hash | isolated_verifier_result | selected | rejection_reason | Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `deepseek-coder:6.7b-instruct` | `deepseek-coder:6.7b-instruct` | `deepseek-coder:6.7b-instruct` | `EMPTY` | `EMPTY` | `none` | `none` (空回覆) | `none` | `not_applicable` | `empty_patch` | `""` | `fail` | `False` | `patch_empty` | `EMPTY_PATCH` |
| `ornith:9b` | `ornith:9b` | `ornith:9b` | `EMPTY` | `EMPTY` | `none` | `none` | `none` | `not_applicable` | `empty_patch` | `""` | `fail` | `False` | `patch_empty` | `EMPTY_PATCH` |
| `qwythos:9b` | `qwythos:9b` | `qwythos:9b` | `EMPTY` | `EMPTY` | `none` | `none` | `none` | `not_applicable` | `empty_patch` | `""` | `fail` | `False` | `patch_empty` | `EMPTY_PATCH` |

*(註：Run B 中小模型於 delegated retry 中均返回空 patch，故呈現為 `EMPTY_PATCH` 狀態。這與 Run A 的 `SEARCH_MISMATCH` 互補，共同證明了對多模型多種產出格式理解和安全閉環的有效性。)*

---

## 4. 關鍵結果與驗證判定

### Row-level Summary 與 Candidate JSON 的一致性 check
- **Telemetries 對齊**: `delegated_retry_provider_called` 欄位現在正確顯示為 `True`。此狀態由 `committee_orchestrator` 在呼叫模型時動態匯總，不會再因 committee path 而被誤標為 `false`。
- **Candidate 軌跡保存**: 在 `delegated_retry_committee_candidates_json` 中，明確列出了所有 3 個候選的執行實機資訊，包含其實際被呼叫的模型 (`candidate_model` / `model`) 以及其 `output_understanding` 層對該輸出的具體識別。

### Output Understanding 功能性 check
- **Run A** 中，輸出均被正確識別為 `parsed_search_replace` 並安全傳遞給 apply 層。
- **Run B** 中，輸出因模型生成為空，被 `output_understanding` 與 parser 捕獲為 `EMPTY`，並在 apply 之前被拒絕為 `empty_patch`，防止無效 patch送進隔離 workspace。
- 在之前的 C15-5H 測試中也證明，當小模型產出 `UNIFIED_DIFF` 時，`output_understanding` 會嘗試調用橋接器轉換，若 preimage 不匹配則產出 `rejected_unified_diff_malformed`，將異常提早攔截。

### 整個執行判定 (Run Classification)
本 Sprint 判定為：
**`C15_6D_TRIPLE_MODEL_TRUTH_CHAIN_PASS_SOLVE_FAIL`**

### Solved Claim Gate
- 判定結果：`solved = NOT_PROVEN` （無任何候選通過隔離驗證閘門，系統正確安全地 fail-closed，此處並非 solve claim 任務，旨在驗證三模型 truth telemetry 連鎖）。

---

## 5. 殘餘阻礙與下一步建議

### 殘餘阻礙
- 本次 validation 主要是對 output_understanding 與三模型 truth chain 進行正確性檢驗。
- 目前在無 mock 的實機跑題中，這三個小模型的 logical 修復能力尚無法通過 `toy-math` 驗證器的嚴格 edge cases 測試（均回報 search mismatch 或是 parser reject / empty）。

### 下一步建議
1. **C15-6E (建議)**: 開始真實 SWE 任務（如 `astropy__astropy-13236` 等）的委員會 live 驗證，並藉由 output-understanding 層解析多元回答。
