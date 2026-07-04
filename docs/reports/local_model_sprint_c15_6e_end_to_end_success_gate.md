# C15-6E: End-to-End Success Gate — Report

**Sprint**: C15-6E  
**Date**: 2026-07-05  
**HEAD Commit**: `def3a561b docs(localheal): record C15-6D triple-model truth-chain validation`  
**Branch**: `feature/bridge-fastmatcher-20260606`  
**Status**: 🔬 C15_6E_CONTROLLED_SUCCESS_PROVEN_REAL_SOLVE_NOT_PROVEN

---

## 1. Dirty-State Preflight & Mock Pollution Check

- **Benchmark Mock Pollution Check**:
  - `git diff -- scripts/bench/m1_real_local_solve_benchmark.py` 的 output 為空，確認無 mock 污染，完全採用真實 Ollama 本地服務進行模型輸出生成。
- **C15-6D Report Commit Hash**:
  - `def3a561b docs(localheal): record C15-6D triple-model truth-chain validation`

---

## 2. Controlled Committee Success Test Design & Evidence

### 2.1 測試設計
在 `tests/unit/local_heal/test_local_model_executor.py` 中新增 `test_c15_6e_controlled_committee_success_proven` 整合測試：
- 模擬 `LocalModelExecutor.run` 當中 `localheal_pipeline` 的執行拓樸。
- 模擬主 pipeline 修復失敗，觸發 delegated retry 機制。
- 模擬多候選模型（`["ornith:9b", "qwythos:9b"]`）。
- 使用 `unittest.mock.patch` 模擬隔離區套用（`run_isolated_workspace_apply`）與驗證器（`run_isolated_verifier`），分別為不同候選提供對應的 Mock Receipts。
- 候選模型 1 (`ornith:9b`) 被設定為 isolated verifier `pass`，成為 winner 模型。
- 候選模型 2 (`qwythos:9b`) 驗證失敗。

### 2.2 測試執行與證據
執行 focused pytest：
```bash
/Users/jameschen/.local/bin/uv run pytest \
  tests/unit/local_heal/test_local_model_executor.py -k "test_c15_6e_controlled_committee_success_proven"
```
輸出結果：
```text
tests/unit/local_heal/test_local_model_executor.py .                     [100%]
====================== 1 passed, 161 deselected in 0.56s =======================
```
產出的 metadata 屬性符合要求：
- `delegated_retry_committee_path_used` = `True`
- `delegated_retry_heterogeneous_candidate_count` = `2`
- `delegated_retry_heterogeneous_winner_model` = `"ornith:9b"`
- `selected_candidate_hash_matches_applied` = `True`
- `isolated_apply_status` = `"applied"`
- `isolated_verifier_status` = `"pass"`
- `verifier_result` = `"pass"`
- `solved` = `True`
- `C15_6E_CONTROLLED_COMMITTEE_SUCCESS_PROVEN` = `True`

---

## 3. Real Dual/Triple Model Live Evidence

### 3.1 Dual Run A (qwen2.5-coder:7b-instruct + deepseek-coder:6.7b-instruct)
- **指令**:
  ```bash
  /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py \
    --task-id toy-math-verifier-evidence-gap \
    --executor-model qwen2.5-coder:7b-instruct \
    --primary-proposer-model qwen2.5-coder:7b-instruct \
    --secondary-proposer-model deepseek-coder:6.7b-instruct \
    --delegated-retry-candidate-models qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct \
    --judge-model qwen2.5-s2t-advisor:3b \
    --provider-timeout-sec 120
  ```
- **結果**: FAILED (`solved = False`, `duration = 348.91s`)

### 3.2 Dual Run B (qwen2.5-coder:7b-instruct + ornith:9b)
- **指令**:
  ```bash
  /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py \
    --task-id toy-math-verifier-evidence-gap \
    --executor-model qwen2.5-coder:7b-instruct \
    --primary-proposer-model qwen2.5-coder:7b-instruct \
    --secondary-proposer-model ornith:9b \
    --delegated-retry-candidate-models qwen2.5-coder:7b-instruct,ornith:9b \
    --judge-model qwen2.5-s2t-advisor:3b \
    --provider-timeout-sec 120
  ```
- **結果**: FAILED (`solved = False`, `duration = 135.54s`)

### 3.3 Triple Run (qwen2.5-coder:7b-instruct + deepseek-coder:6.7b-instruct + ornith:9b)
- **指令**:
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
- **結果**: FAILED (`solved = False`, `duration = 248.92s`)

---

## 4. Run & Candidate Telemetry Tables

### 4.1 Row-level Summary

| Run | Topology | Candidate Count | Provider Called | Winner Model | Solved | Solve Mechanism | Duration (s) |
|---|---|---|---|---|---|---|---|
| **Dual Run A** | `localheal_pipeline` | 2 | True | `""` | False | `delegated_retry_unresolved` | 348.91 |
| **Dual Run B** | `localheal_pipeline` | 2 | True | `""` | False | `delegated_retry_unresolved` | 135.54 |
| **Triple Run** | `localheal_pipeline` | 3 | True | `""` | False | `delegated_retry_unresolved` | 248.92 |

### 4.2 Candidate-level Table

| Run | candidate_model | expected_model | invoked_model | format_class | apply_status | verifier_result | selected | rejection_reason |
|---|---|---|---|---|---|---|---|---|
| **A** | `qwen2.5-coder:7b-instruct` | `qwen2.5-coder:7b-instruct` | `qwen2.5-coder:7b-instruct` | `UNIFIED_DIFF` | `format_rejected` | `fail` | False | `unified_diff_malformed` |
| **A** | `deepseek-coder:6.7b-instruct` | `deepseek-coder:6.7b-instruct` | `deepseek-coder:6.7b-instruct` | `MALFORMED_SEARCH_REPLACE` | `empty_patch` | `fail` | False | `patch_empty` |
| **B** | `qwen2.5-coder:7b-instruct` | `qwen2.5-coder:7b-instruct` | `qwen2.5-coder:7b-instruct` | `UNIFIED_DIFF` | `format_rejected` | `fail` | False | `unified_diff_malformed` |
| **B** | `ornith:9b` | `ornith:9b` | `ornith:9b` | `EMPTY` | `empty_patch` | `fail` | False | `patch_empty` |
| **Triple** | `qwen2.5-coder:7b-instruct` | `qwen2.5-coder:7b-instruct` | `qwen2.5-coder:7b-instruct` | `UNIFIED_DIFF` | `format_rejected` | `fail` | False | `unified_diff_malformed` |
| **Triple** | `deepseek-coder:6.7b-instruct` | `deepseek-coder:6.7b-instruct` | `deepseek-coder:6.7b-instruct` | `MALFORMED_SEARCH_REPLACE` | `empty_patch` | `fail` | False | `patch_empty` |
| **Triple** | `ornith:9b` | `ornith:9b` | `ornith:9b` | `EMPTY` | `empty_patch` | `fail` | False | `patch_empty` |

---

## 5. Solved Claim Gate & Failure Taxonomy

### 5.1 Solved Claim Gate

| Run | winner_model != "" | hash_matches = true | isolated_verifier = pass | verifier_result = pass | solved |
|---|---|---|---|---|---|
| **Controlled** | True | True | True | True | **True** (C15_6E_CONTROLLED_COMMITTEE_SUCCESS_PROVEN) |
| **Dual Run A** | False | False | False | False | False (`REAL_DUAL_MODEL_SOLVE_NOT_PROVEN`) |
| **Dual Run B** | False | False | False | False | False (`REAL_DUAL_MODEL_SOLVE_NOT_PROVEN`) |
| **Triple Run** | False | False | False | False | False (`REAL_TRIPLE_MODEL_SOLVE_NOT_PROVEN`) |

### 5.2 Failure Taxonomy for Non-Winning Candidates
針對所有實機小模型候選，依以下定義進行故障歸類：
- **A. model output empty**: 模型生成為空或無法提取。
- **C. output_understanding gap**: 模型生成了 unified diff 但轉換失敗。

| Candidate Model | Run | Rejection Reason | Failure Class |
|---|---|---|---|
| `qwen2.5-coder:7b-instruct` | Run A | `unified_diff_malformed` | **C. output_understanding gap** |
| `deepseek-coder:6.7b-instruct` | Run A | `patch_empty` | **A. model output empty** |
| `qwen2.5-coder:7b-instruct` | Run B | `unified_diff_malformed` | **C. output_understanding gap** |
| `ornith:9b` | Run B | `patch_empty` | **A. model output empty** |
| `qwen2.5-coder:7b-instruct` | Triple | `unified_diff_malformed` | **C. output_understanding gap** |
| `deepseek-coder:6.7b-instruct` | Triple | `patch_empty` | **A. model output empty** |
| `ornith:9b` | Triple | `patch_empty` | **A. model output empty** |

---

## 6. 結論與下一步建議

1. **Nexus 完整裝甲路徑是否連通**: 
   - **是**。透過 `test_c15_6e_controlled_committee_success_proven` 整合測試的執行，證明了：當至少有一個候選模型通過隔離區 apply 且驗證器為 `pass` 時，Nexus Armor 可以自動提取正確的 winner 資訊、對齊 patch 哈希、並在主執行器層面將 `solved` 正確標記為 `True`。
2. **剩餘阻礙**:
   - **本地小模型程式碼修復能力依舊是主要瓶頸**（即 `REAL_SOLVE_NOT_PROVEN`）。
   - 小模型輸出的 patch（如 `qwen2.5-coder:7b-instruct`）經常以 unified diff 呈現，但因為 preimage 殘缺或 markdown 包裹語法污染，導致 output_understanding 轉換時拋出 malformed 拒絕，或是在實機任務中無法通過嚴格的 `toy-math` 驗證。
   - `deepseek-coder` 與 `ornith` 模型在 retry 過程中高機率回報空值（EMPTY）。
3. **下一步建議**:
   - **C15-6F (建議)**: 在 Controlled Success 已通、實機能力不足的當下，下一個 sprint 應對 output_understanding 層之 `UNIFIED_DIFF` 轉換與 Preimage 修補機制進行深化與優化（例如容忍 unified diff 行號偏移、不完全 preimage 的 fuzzy matching），提高小模型成果的格式轉化成功率，藉此解決 output_understanding gap。
