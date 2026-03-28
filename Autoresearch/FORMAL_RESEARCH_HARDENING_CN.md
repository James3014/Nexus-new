# Formal Research Hardening（接線說明）

這份模組把你目前的研究輸出做「強約束收斂判定」，避免再次出現：

- 單輪看起來很漂亮，但全局其實沒過 Gate。
- `Converged=True` 與最終 `RESEARCH FAILED` 語義衝突。

## 1. 輸入格式

輸入檔：`round_summary.jsonl`（每輪一行 JSON）  
至少建議欄位：

- `round`：輪次
- `alignment`：該輪對齊分數
- `checks_triggered`：該輪是否有觸發檢查（bool）
- `generated_patches`：該輪 patch 生成數（int）
- `proof_passed_patches`：該輪有證據通過的 patch 數（int）
- `learning_frozen`：該輪是否凍結學習（bool）
- `proof_ratio`：該輪證據率（0~100）
- `freeze_ratio`：該輪凍結率（0~100）
- `fail_fast_reason`：失敗原因字串（可選）
- `params`：當前參數快照（可選 dict）

## 2. 執行方式

```bash
cd /Users/jameschen/Workspace/nexus
python3 Autoresearch/formal_research_hardening.py \
  --round-summary /path/to/round_summary.jsonl \
  --output-dir /path/to/output_dir
```

## 3. 輸出檔（固定三件）

- `gate_eval.json`
- `param_state.json`
- `round_summary.jsonl`（重寫後版本，含 `local_fit` 與 `fail_bucket`）

## 4. 判定邏輯（已硬化）

- `local_fit`：rolling window gate 是否通過（預設 window=20）
- `global_converged`：同時滿足
  - `gate_pass_rate >= 80%`
  - `max_consecutive_windows >= 3`

> 也就是：只有全局通過才叫收斂；單輪高分不算。

## 5. Fail-Fast 分桶

- `proof_fail`：`proof_ratio < 90`
- `freeze_fail`：`freeze_ratio > 35`
- `both_fail`：兩者同時發生

`gate_eval.json` 會輸出：

- `fail_bucket_counts`
- `top_fail_reasons`（Top-3）

## 6. 保守期規則

預設前 30 輪標記為 `mode=conservative`，30 輪後才進入探索。  
可避免一開始就高探索把證據率打崩。
