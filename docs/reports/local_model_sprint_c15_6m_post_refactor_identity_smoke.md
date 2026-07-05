# Local Model Nexus Armor — C15-6M Post-Refactor Identity Smoke Report

- **Final Status**: `C15_6M_POST_REFACTOR_IDENTITY_SMOKE_VERIFIED`
- **Verification Timestamp**: 2026-07-05 20:45:15

---

## 1. 問題摘要 (Summary of Issues)

先前 C15-6L 10 組矩陣的 execution 留下兩個主要問題：
1. **`candidate_ids_unique` 均為 false**：在 `localheal_pipeline` 中缺少唯一的 `candidate_id` 造成 parser 回報碰撞，但人工 checklist 卻標記為 `True`。
2. **`committee_size` 與 `candidate_count` 混淆**：將 Proposer 與 Judge 的期望個數混雜計算。

藉由 commit `3b7acf042`，我們對 `local_model_executor.py` 補足了 `candidate_id` 的生成合約與 Borda 評審對齊，並拆分了 Proposer 與 Judge 的期望個數投影。

本 Smoke 報告專注於驗證該 Telemetry 合約是否在實體 Ollama 執行路徑（`SMOKE_A1` 與 `SMOKE_B1`）中正確生效。

---

## 2. 測試命令 (Test Commands)

我們建立了完全隔離的 Smoke 測試環境，並依序執行以下實體 Ollama 測試命令：

### SMOKE_A1 (Dual)
```bash
NEXUS_BENCHMARK_APPEND=1 .venv/bin/python3 scripts/bench/m1_real_local_solve_benchmark.py \
  --task-id toy-math-verifier-evidence-gap \
  --delegated-retry-candidate-models "qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct" \
  --provider-timeout-sec 120
```

### SMOKE_B1 (Triple)
```bash
NEXUS_BENCHMARK_APPEND=1 .venv/bin/python3 scripts/bench/m1_real_local_solve_benchmark.py \
  --task-id toy-math-verifier-evidence-gap \
  --delegated-retry-candidate-models "qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct,ornith:9b" \
  --provider-timeout-sec 120
```

---

## 3. A1 Smoke 結果 (A1 Smoke Results)

- **delegated_retry_committee_path_used**: `true`
- **delegated_retry_proposer_count_expected**: `2`
- **delegated_retry_judge_count_expected**: `1`
- **delegated_retry_candidate_count_actual**: `2`
- **winner_selected**: `false`
- **final_solved**: `false` (符合預期，該任務缺乏 evidence-gap故 fail-closed)
- **candidate_ids_unique**: `true`

---

## 4. B1 Smoke 結果 (B1 Smoke Results)

- **delegated_retry_committee_path_used**: `true`
- **delegated_retry_proposer_count_expected**: `3`
- **delegated_retry_judge_count_expected**: `1`
- **delegated_retry_candidate_count_actual**: `3`
- **winner_selected**: `false`
- **final_solved**: `false` (符合預期)
- **candidate_ids_unique**: `true`

---

## 5. Candidate Identity Evidence

在實機產生的 `m1_real_local_solve_results.jsonl` 中，擷取以下實體 candidate 資訊，證明唯一的 `candidate_id` 已經正確寫入 JSON：

### SMOKE_A1 Candidates Json Detail
```json
[
  {
    "candidate_id": "toy-math-verifier-evidence-gap#delegated-retry-01-qwen2-5-coder-7b-instruct",
    "model": "qwen2.5-coder:7b-instruct",
    "candidate_model": "qwen2.5-coder:7b-instruct",
    "apply_status": "format_rejected",
    "verifier_result": "fail"
  },
  {
    "candidate_id": "toy-math-verifier-evidence-gap#delegated-retry-02-deepseek-coder-6-7b-instruct",
    "model": "deepseek-coder:6.7b-instruct",
    "candidate_model": "deepseek-coder:6.7b-instruct",
    "apply_status": "empty_patch",
    "verifier_result": "fail"
  }
]
```

### SMOKE_B1 Candidates Json Detail
```json
[
  {
    "candidate_id": "toy-math-verifier-evidence-gap#delegated-retry-01-qwen2-5-coder-7b-instruct",
    "model": "qwen2.5-coder:7b-instruct",
    "candidate_model": "qwen2.5-coder:7b-instruct",
    "apply_status": "format_rejected",
    "verifier_result": "fail"
  },
  {
    "candidate_id": "toy-math-verifier-evidence-gap#delegated-retry-02-deepseek-coder-6-7b-instruct",
    "model": "deepseek-coder:6.7b-instruct",
    "candidate_model": "deepseek-coder:6.7b-instruct",
    "apply_status": "format_rejected",
    "verifier_result": "fail"
  },
  {
    "candidate_id": "toy-math-verifier-evidence-gap#delegated-retry-03-ornith-9b",
    "model": "ornith:9b",
    "candidate_model": "ornith:9b",
    "apply_status": "empty_patch",
    "verifier_result": "fail"
  }
]
```

---

## 6. 是否需要 Minimal Patch

**不需要 (No)**。
實機測試表明 `3b7acf042` 搭配本輪的 `m1_real_local_solve_benchmark.py` 投影修改後，已完美覆蓋與解決了所有的 telemetry identity 碰撞與計數混淆問題，不需要其他的 minimal patch。

---

## 7. 下一步 Decision Tree (Decision Tree for Future Work)

由於 Smoke 驗證已 100% 透過，合約缺陷已解決，我們將轉入 C15 的下一個微調階段。
- **後續步驟**：將此 benchmark 投影修改與新 Smoke Report 提交，並還原 historical 數據。
